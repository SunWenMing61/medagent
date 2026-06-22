"""使用 RQ(Redis 任务队列)处理的文档任务。"""
import os   # 操作系统接口,用于路径处理
import sys  # 系统接口,用于修改 Python 模块搜索路径

# 将项目根目录添加到模块搜索路径,以便 RQ 工作进程能够正确导入应用模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from rq import Queue  # RQ 任务队列
from redis import Redis  # Redis 客户端
from sqlalchemy.orm import Session  # SQLAlchemy 会话类型

from app.core.config import settings  # 应用配置
from app.db.session import MySQLSessionLocal, PgSessionLocal  # MySQL 和 PostgreSQL 会话工厂
from app.models.document import Document  # 文档模型
from app.models.document_chunk import DocumentChunk  # 文档块模型(向量)
from app.utils.file_utils import extract_text  # 文件文本提取工具
from app.utils.text_splitter import split_text  # 文本分块工具
from app.services.vector_service import vector_service  # 向量服务

# 从配置的 Redis URL 创建 Redis 连接
redis_conn = Redis.from_url(settings.REDIS_URL)
# 创建名为 "default" 的 RQ 任务队列
doc_queue = Queue("default", connection=redis_conn)


def _ensure_pgvector_extension():
    """确保 PostgreSQL 上已启用 pgvector 扩展。"""
    pg_db = PgSessionLocal()  # 创建 PostgreSQL 会话
    try:
        from sqlalchemy import text  # 导入 text 函数用于执行原生 SQL
        pg_db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))  # 创建 vector 扩展(如果不存在)
        pg_db.commit()  # 提交事务
    except Exception:
        pg_db.rollback()  # 出错则回滚
    finally:
        pg_db.close()  # 关闭连接


def process_document(document_id: int):
    """处理文档:解析文本、分块、生成向量嵌入、存储向量。

    使用 MySQL 存储文档元数据,PostgreSQL (pgvector) 存储分块向量。
    此函数设计为 RQ 任务执行。

    Args:
        document_id: 要处理的文档 ID

    Returns:
        处理结果字典,包含 status、document_id、chunks 数量或 error 信息
    """
    _ensure_pgvector_extension()  # 确保 pgvector 扩展已安装

    mysql_db: Session = MySQLSessionLocal()  # 创建 MySQL 会话
    pg_db: Session = PgSessionLocal()        # 创建 PostgreSQL 会话
    try:
        doc = mysql_db.query(Document).filter(Document.id == document_id).first()  # 查询文档
        if not doc:
            return {"error": "Document not found"}  # 文档不存在

        # 将解析状态更新为"处理中"
        doc.parse_status = "processing"
        mysql_db.commit()

        # 尝试从文件中提取文本
        try:
            pages = extract_text(doc.file_path, doc.file_type)  # 根据文件类型提取文本
        except Exception as e:
            doc.parse_status = "failed"                       # 解析失败
            doc.error_message = f"Parse failed: {str(e)}"     # 记录错误信息
            mysql_db.commit()
            return {"error": str(e)}

        if not pages:
            doc.parse_status = "failed"
            doc.error_message = "No text content extracted"  # 无文本内容
            mysql_db.commit()
            return {"error": "No text content extracted"}

        # 将所有页的文本合并为一个完整的文本
        full_text = "\n".join([text for _, text in pages])

        # 将完整文本分割成块
        chunks = split_text(full_text, chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
        if not chunks:
            doc.parse_status = "failed"
            doc.error_message = "Text splitting produced no chunks"  # 分块未产生结果
            mysql_db.commit()
            return {"error": "No chunks produced"}

        doc.parse_status = "success"  # 文本解析成功
        mysql_db.commit()

        # 更新向量化状态为"处理中"
        doc.vector_status = "processing"
        mysql_db.commit()

        # 删除该文档在 PostgreSQL 中已存在的旧块(保证幂等性)
        pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        pg_db.commit()

        # 为每个文本块生成向量嵌入并存储到 PostgreSQL
        successful_chunks = 0  # 成功处理的块计数
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue  # 跳过空白块

            try:
                embedding = vector_service.embed_text(chunk_text)  # 生成向量嵌入
            except Exception:
                embedding = None  # 嵌入失败设为 None,不影响后续块

            # 创建 DocumentChunk 记录
            chunk = DocumentChunk(
                document_id=document_id,   # 所属文档 ID
                kb_id=doc.kb_id,           # 所属知识库 ID
                chunk_index=i,             # 块索引
                content=chunk_text,        # 块文本内容
                page_num=None,             # 页码(文件处理时已合并所有页)
                embedding=embedding,       # 向量嵌入
            )
            pg_db.add(chunk)       # 添加块到会话
            successful_chunks += 1

            if successful_chunks % 10 == 0:
                pg_db.commit()     # 每 10 块提交一次

        pg_db.commit()                    # 提交剩余块
        doc.vector_status = "success"      # 向量化成功
        mysql_db.commit()

        # 返回处理成功结果
        return {
            "status": "success",
            "document_id": document_id,
            "chunks": successful_chunks,
        }

    except Exception as e:
        mysql_db.rollback()  # 回滚 MySQL 事务
        pg_db.rollback()     # 回滚 PostgreSQL 事务
        # 尝试在 MySQL 中将文档标记为失败状态
        doc = mysql_db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.parse_status = "failed" if doc.parse_status == "processing" else doc.parse_status
            doc.vector_status = "failed" if doc.vector_status == "processing" else doc.vector_status
            doc.error_message = str(e)
            mysql_db.commit()
        return {"error": str(e)}
    finally:
        mysql_db.close()  # 确保关闭 MySQL 连接
        pg_db.close()     # 确保关闭 PostgreSQL 连接
