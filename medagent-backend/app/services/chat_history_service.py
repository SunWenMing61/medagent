"""全局对话历史知识库管理服务。

一个系统拥有的单一 chat_history 知识库,自动将所有用户的问答对话对
以向量化块的形式存储,用于语义检索。
旧块在超过 CHAT_HISTORY_RETENTION_DAYS 天后会被清理。
"""

import logging  # 日志记录
from datetime import datetime, timedelta  # 日期时间处理,用于计算保留期限

from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.db.session import MySQLSessionLocal, PgSessionLocal  # MySQL 和 PostgreSQL 会话工厂
from app.models.knowledge_base import KnowledgeBase  # 知识库模型
from app.models.document import Document  # 文档模型
from app.models.document_chunk import DocumentChunk  # 文档块模型(向量)
from app.services.vector_service import vector_service  # 向量服务
from app.utils.text_splitter import split_text  # 文本分块工具
from app.core.config import settings  # 应用配置

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

# 对话历史保留天数:60 天前的旧记录将被自动清理
CHAT_HISTORY_RETENTION_DAYS = 60
# 全局对话历史知识库的名称(中文显示)
CHAT_HISTORY_KB_NAME = "我的对话历史"
# 系统用户的 ID,用于标记由系统创建的知识库
CHAT_HISTORY_SYSTEM_USER_ID = 0


def get_or_create_chat_history_kb() -> int:
    """获取或创建唯一的全局对话历史知识库。

    如果已存在 type 为 'chat_history' 的知识库则直接返回其 ID,
    否则创建一个新的并返回。

    Returns:
        对话历史知识库的 ID
    """
    mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
    try:
        # 查询 type 为 'chat_history' 的知识库
        kb = mysql_db.query(KnowledgeBase).filter(
            KnowledgeBase.type == "chat_history",
        ).first()

        if kb:
            return kb.id  # 已存在则直接返回 ID

        # 不存在则创建全局对话历史知识库
        kb = KnowledgeBase(
            name=CHAT_HISTORY_KB_NAME,                              # 名称:我的对话历史
            description="自动保存的所有用户对话历史记录（仅保留最近两个月）",  # 描述
            type="chat_history",                                     # 标记为对话历史类型
            owner_id=CHAT_HISTORY_SYSTEM_USER_ID,                   # 系统所有
            visibility="public",                                     # 公开可见
            status=1,                                                # 启用状态
        )
        mysql_db.add(kb)       # 添加新知识库
        mysql_db.commit()      # 提交事务
        mysql_db.refresh(kb)   # 刷新以获取自增 ID
        logger.info("Created global chat_history KB %s", kb.id)  # 记录创建日志
        return kb.id
    finally:
        mysql_db.close()  # 确保关闭连接


def store_conversation(
    user_id: int,
    kb_id: int,
    question: str,
    answer: str,
    session_id: int | None = None,
) -> int:
    """将一对问答对话存储为对话历史知识库中的一个块。

    Args:
        user_id: 用户 ID
        kb_id: 对话历史知识库的 ID
        question: 用户的问题文本
        answer: 助手的回答文本
        session_id: 可选的会话 ID,用于关联对话

    Returns:
        创建的块数量
    """
    # 构建对话文本——使用清晰的分隔格式
    # 使嵌入向量能够同时捕捉问题和答案的语义
    conversation_text = (
        f"[用户问题]\n{question.strip()}\n\n"
        f"[助手回答]\n{answer.strip()}"
    )
    if not conversation_text.strip():
        return 0  # 空白内容则不存储

    # 创建 Document 记录来跟踪这轮对话条目
    mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话(存储文档元数据)
    pg_db: Session = PgSessionLocal()        # 创建 PostgreSQL 会话(存储向量块)
    try:
        title = question.strip()[:80]  # 截取问题前 80 字符作为"文件名"

        # 创建文档记录
        doc = Document(
            kb_id=kb_id,                           # 关联的知识库 ID
            source_id=0,                            # 标记为对话历史来源(source_id=0)
            source_url=str(session_id) if session_id else "",  # 关联的会话 ID
            filename=title,                          # 文档标题(截取的问题)
            file_type="chat_text",                   # 文件类型标记为对话文本
            file_size=len(conversation_text.encode("utf-8")),  # 内容大小(字节)
            parse_status="success",                  # 解析状态
            vector_status="processing",              # 向量化状态
            uploader_id=user_id,                     # 上传者(用户 ID)
        )
        mysql_db.add(doc)       # 添加文档记录
        mysql_db.commit()       # 提交获取文档 ID
        mysql_db.refresh(doc)   # 刷新以获取自增 ID

        # 对对话文本进行分块、嵌入并存储到 PostgreSQL
        chunks = split_text(
            conversation_text,
            chunk_size=settings.CHUNK_SIZE,       # 块大小
            chunk_overlap=settings.CHUNK_OVERLAP,  # 块重叠
        )
        if not chunks:
            doc.vector_status = "failed"
            doc.error_message = "No chunks produced"  # 分块失败
            mysql_db.commit()
            return 0

        successful = 0  # 成功处理的块计数
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue  # 跳过空白块
            try:
                embedding = vector_service.embed_text(chunk_text)  # 生成向量嵌入
            except Exception as exc:
                logger.warning("Embedding failed for chat chunk %s: %s", i, exc)  # 嵌入失败则记日志
                embedding = None  # 嵌入失败不影响后续处理

            # 创建 DocumentChunk 记录
            chunk = DocumentChunk(
                document_id=doc.id,  # 所属文档 ID
                kb_id=kb_id,         # 所属知识库 ID
                chunk_index=i,       # 块索引
                content=chunk_text,  # 块文本内容
                page_num=None,       # 对话无页码概念
                embedding=embedding,  # 嵌入向量(可能为 None)
            )
            pg_db.add(chunk)   # 添加块到会话
            successful += 1    # 计数加一

            if successful % 10 == 0:
                pg_db.commit()  # 每 10 块提交一次

        pg_db.commit()  # 提交剩余块
        doc.vector_status = "success" if successful > 0 else "failed"  # 根据结果更新向量状态
        mysql_db.commit()

        return successful  # 返回成功创建的块数

    except Exception as exc:
        logger.exception("Failed to store conversation")  # 记录异常栈
        mysql_db.rollback()  # 回滚 MySQL 事务
        pg_db.rollback()     # 回滚 PostgreSQL 事务
        return 0
    finally:
        mysql_db.close()  # 确保关闭 MySQL 连接
        pg_db.close()     # 确保关闭 PostgreSQL 连接


def cleanup_old_chunks(kb_id: int) -> int:
    """删除指定知识库中早于 CHAT_HISTORY_RETENTION_DAYS 的文档块。

    Args:
        kb_id: 知识库 ID

    Returns:
        被删除的块数量
    """
    cutoff = datetime.now() - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)  # 计算截止日期

    mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
    pg_db: Session = PgSessionLocal()        # 创建 PostgreSQL 会话
    try:
        # 查询该知识库中创建时间早于截止日期的旧文档
        old_docs = mysql_db.query(Document).filter(
            Document.kb_id == kb_id,
            Document.created_at < cutoff,
        ).all()

        if not old_docs:
            return 0  # 无过期文档,直接返回

        doc_ids = [d.id for d in old_docs]  # 提取文档 ID 列表

        # 从 PostgreSQL 中删除关联的向量块
        deleted = pg_db.query(DocumentChunk).filter(
            DocumentChunk.document_id.in_(doc_ids),
        ).delete(synchronize_session=False)  # 关闭会话同步以提高批量删除性能
        pg_db.commit()

        # 从 MySQL 中删除文档记录
        mysql_db.query(Document).filter(
            Document.id.in_(doc_ids),
        ).delete(synchronize_session=False)
        mysql_db.commit()

        logger.info(
            "Cleaned up %s chunks and %s documents from chat_history KB %s",
            deleted, len(doc_ids), kb_id,  # 记录清理统计信息
        )
        return deleted  # 返回删除的块数

    except Exception as exc:
        logger.exception("Cleanup failed for chat_history KB %s", kb_id)  # 记录异常栈
        mysql_db.rollback()  # 回滚 MySQL 事务
        pg_db.rollback()     # 回滚 PostgreSQL 事务
        return 0
    finally:
        mysql_db.close()  # 确保关闭 MySQL 连接
        pg_db.close()     # 确保关闭 PostgreSQL 连接
