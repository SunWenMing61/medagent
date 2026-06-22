"""在线知识源同步服务,负责从外部在线来源获取内容并存储到系统中。"""

import asyncio  # 异步 I/O 支持,用于运行异步适配器
import json     # JSON 解析,用于反序列化知识源配置
import logging  # 日志记录
from datetime import datetime, timezone  # 时间处理,用于记录同步时间
from typing import Optional  # 可选类型提示

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.adapters import get_adapter  # 适配器工厂函数,根据来源类型获取对应适配器
from app.db.session import MySQLSessionLocal, PgSessionLocal  # MySQL 和 PostgreSQL 会话工厂
from app.models.document import Document  # 文档模型
from app.models.document_chunk import DocumentChunk  # 文档块模型(向量)
from app.models.knowledge_base import KnowledgeBase  # 知识库模型
from app.models.knowledge_source import KnowledgeSource  # 知识源模型(配置)
from app.services.vector_service import vector_service  # 向量服务,用于生成嵌入
from app.utils.text_splitter import split_text  # 文本分块工具
from app.core.config import settings  # 应用配置

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器


def split_and_store_content(
    pg_db: Session,
    document_id: int,
    kb_id: int,
    full_text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> int:
    """将文本分块、生成向量嵌入并存储为 DocumentChunk。

    文件上传和在线知识源同步共用的函数。
    返回创建的块数量。

    Args:
        pg_db: PostgreSQL 数据库会话
        document_id: 文档 ID
        kb_id: 知识库 ID
        full_text: 要分块的完整文本
        chunk_size: 每块的最大字符数,默认使用配置值
        chunk_overlap: 块之间的重叠字符数,默认使用配置值

    Returns:
        成功创建的块数量
    """
    cs = chunk_size or settings.CHUNK_SIZE  # 若未指定则使用默认块大小
    co = chunk_overlap or settings.CHUNK_OVERLAP  # 若未指定则使用默认块重叠

    chunks = split_text(full_text, chunk_size=cs, chunk_overlap=co)  # 对文本进行分块
    if not chunks:
        return 0  # 分块结果为空则直接返回

    # 删除该文档已存在的旧块,保证幂等性(重复调用不会产生重复数据)
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()  # 提交删除事务

    successful = 0  # 成功处理的块计数器
    for i, chunk_text in enumerate(chunks):
        if not chunk_text.strip():
            continue  # 跳过空白块

        try:
            embedding = vector_service.embed_text(chunk_text)  # 调用向量服务生成嵌入
        except Exception:
            embedding = None  # 嵌入生成失败时设为 None,不影响后续块的处理

        # 创建 DocumentChunk 记录
        chunk = DocumentChunk(
            document_id=document_id,  # 所属文档 ID
            kb_id=kb_id,              # 所属知识库 ID
            chunk_index=i,            # 块在文档中的顺序索引
            content=chunk_text,       # 块文本内容
            page_num=None,            # 源码页码(在线来源无页码概念)
            embedding=embedding,      # 向量嵌入(可能为 None)
        )
        pg_db.add(chunk)   # 将块添加到会话
        successful += 1    # 成功计数加一

        if successful % 10 == 0:
            pg_db.commit()  # 每 10 块提交一次,避免事务过大

    pg_db.commit()  # 提交剩余的块
    return successful


class SourceService:
    """在线知识源管理与同步服务。"""

    def sync_source(self, source_id: int) -> dict:
        """对指定知识源执行完整的同步流程。

        由 RQ 工作进程调用。这是一个阻塞函数,执行步骤:
        1. 加载 KnowledgeSource 配置
        2. 实例化对应的适配器
        3. 获取内容并存储为 Document + Chunk

        Args:
            source_id: 知识源的 ID

        Returns:
            包含同步状态、源 ID、创建文档数和块数的字典
        """
        mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话(存储元数据)
        pg_db: Session = PgSessionLocal()        # 创建 PostgreSQL 会话(存储向量)

        try:
            # 从 MySQL 中查询知识源配置
            source = mysql_db.query(KnowledgeSource).filter(
                KnowledgeSource.id == source_id
            ).first()
            if not source:
                raise ValueError(f"KnowledgeSource {source_id} not found")  # 源不存在则报错

            # 将同步状态更新为"同步中"
            source.sync_status = "syncing"
            source.error_message = None  # 清除之前的错误信息
            mysql_db.commit()  # 提交状态变更

            config = json.loads(source.config) if isinstance(source.config, str) else source.config  # 解析 JSON 配置
            adapter = get_adapter(source.source_type)  # 根据源类型获取对应的适配器实例

            total_docs = 0     # 已处理的文档总数
            total_chunks = 0   # 已处理的块总数

            # 定义内部异步函数,用于消费适配器产生的数据
            async def consume():
                nonlocal total_docs, total_chunks  # 声明引用外层变量
                # 异步迭代适配器产生的 SourceDocument
                async for source_doc in adapter.fetch_content(config):
                    if not source_doc.content.strip():
                        continue  # 跳过空内容

                    # 创建 Document 记录(存储在 MySQL)
                    doc = Document(
                        kb_id=source.kb_id,               # 关联的知识库 ID
                        source_id=source.id,               # 关联的知识源 ID
                        source_url=source_doc.source_url,  # 原始来源 URL
                        filename=source_doc.title[:255],   # 文件名(截断到 255 字符)
                        file_type="source_text",            # 文件类型标记为来源文本
                        file_size=len(source_doc.content.encode("utf-8")),  # 文件大小(字节)
                        parse_status="success",             # 解析状态
                        vector_status="processing",         # 向量化状态
                        uploader_id=0,                      # 系统用户 ID
                    )
                    mysql_db.add(doc)    # 添加文档记录
                    mysql_db.commit()    # 提交获取文档 ID
                    mysql_db.refresh(doc)  # 刷新以获取自增 ID

                    # 对文档内容进行分块、嵌入并存储到 PostgreSQL
                    try:
                        n_chunks = split_and_store_content(
                            pg_db, doc.id, source.kb_id, source_doc.content,
                        )
                        doc.vector_status = "success" if n_chunks > 0 else "failed"  # 根据是否有块更新向量状态
                        mysql_db.commit()
                        total_chunks += n_chunks  # 累加块数
                        total_docs += 1           # 文档计数加一
                    except Exception as e:
                        doc.vector_status = "failed"        # 标记为失败
                        doc.error_message = str(e)[:500]    # 截断错误信息到 500 字符
                        mysql_db.commit()
                        logger.warning(f"Failed to process doc '{source_doc.title}': {e}")  # 记录警告日志

            asyncio.run(consume())  # 运行异步消费协程

            # 同步完成,更新来源状态为成功
            source.sync_status = "success"
            source.last_sync_at = datetime.now(timezone.utc)  # 记录最后同步时间(UTC)
            source.error_message = None
            mysql_db.commit()

            # 返回同步结果摘要
            return {
                "status": "success",
                "source_id": source_id,
                "documents_created": total_docs,
                "chunks_created": total_chunks,
            }

        except Exception as e:
            logger.exception(f"Sync failed for source {source_id}")  # 记录异常栈
            try:
                # 尝试将来源状态更新为失败
                source = mysql_db.query(KnowledgeSource).filter(
                    KnowledgeSource.id == source_id
                ).first()
                if source:
                    source.sync_status = "failed"
                    source.error_message = str(e)[:500]  # 截断错误信息
                    mysql_db.commit()
            except Exception:
                mysql_db.rollback()  # 回滚以防连接处于不一致状态
            return {"status": "failed", "source_id": source_id, "error": str(e)}

        finally:
            mysql_db.close()  # 关闭 MySQL 连接
            pg_db.close()     # 关闭 PostgreSQL 连接

    def delete_source(self, source_id: int) -> int:
        """删除知识源及其所有关联的文档和块。

        Args:
            source_id: 要删除的知识源 ID

        Returns:
            被删除的文档数量
        """
        mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
        pg_db: Session = PgSessionLocal()        # 创建 PostgreSQL 会话

        try:
            source = mysql_db.query(KnowledgeSource).filter(
                KnowledgeSource.id == source_id
            ).first()
            if not source:
                return 0  # 源不存在则直接返回

            # 查询该知识源下的所有文档 ID
            doc_ids = [
                d[0] for d in mysql_db.query(Document.id).filter(
                    Document.source_id == source_id
                ).all()
            ]

            # 从 PostgreSQL 中删除所有关联的文档块(向量数据)
            for doc_id in doc_ids:
                pg_db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc_id
                ).delete()
            pg_db.commit()

            # 从 MySQL 中删除所有关联的文档记录
            deleted = mysql_db.query(Document).filter(
                Document.source_id == source_id
            ).delete()
            mysql_db.commit()

            # 删除知识源配置本身
            mysql_db.delete(source)
            mysql_db.commit()

            return deleted  # 返回删除的文档数量

        finally:
            mysql_db.close()  # 确保关闭 MySQL 连接
            pg_db.close()     # 确保关闭 PostgreSQL 连接

    def get_source_document_count(self, source_id: int) -> int:
        """获取从指定知识源同步的文档数量。

        Args:
            source_id: 知识源 ID

        Returns:
            文档数量
        """
        mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
        try:
            count = mysql_db.query(Document).filter(
                Document.source_id == source_id
            ).count()
            return count
        finally:
            mysql_db.close()  # 确保关闭连接

    def cleanup_orphaned_sources(self) -> int:
        """删除其关联知识库已不存在的孤立知识源。

        防止在知识库被删除后仍然显示过期的知识源。
        返回被删除的知识源数量。

        Returns:
            被删除的孤立知识源数量
        """
        mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
        try:
            # 获取所有状态正常的现有知识库 ID
            existing_kb_ids = {
                row[0] for row in mysql_db.query(
                    KnowledgeBase.id
                ).filter(KnowledgeBase.status == 1).all()
            }

            # 找出所有 kb_id 不在现有知识库集合中的知识源
            orphaned = mysql_db.query(KnowledgeSource).all()
            to_delete = [s for s in orphaned if s.kb_id not in existing_kb_ids]

            if not to_delete:
                return 0  # 无孤立源,直接返回

            deleted_count = 0
            for source in to_delete:
                try:
                    self.delete_source(source.id)  # 优先使用完整的删除方法
                    deleted_count += 1
                except Exception:
                    mysql_db.delete(source)  # 失败时直接从数据库删除
                    mysql_db.commit()
                    deleted_count += 1

            return deleted_count
        finally:
            mysql_db.close()  # 确保关闭连接

    def update_source_from_sync(self, mysql_db: Session, source_id: int, status: str, error: str = None):
        """在同步生命周期中更新知识源的同步状态。

        Args:
            mysql_db: MySQL 数据库会话
            source_id: 知识源 ID
            status: 新的同步状态
            error: 可选的错误信息
        """
        source = mysql_db.query(KnowledgeSource).filter(
            KnowledgeSource.id == source_id
        ).first()
        if source:
            source.sync_status = status    # 更新状态
            if error:
                source.error_message = str(error)[:500]  # 设置截断后的错误信息
            if status == "syncing":
                source.error_message = None  # 开始同步时清除历史错误
            mysql_db.commit()  # 提交变更


# 全局单例实例,供其他模块直接使用
source_service = SourceService()
