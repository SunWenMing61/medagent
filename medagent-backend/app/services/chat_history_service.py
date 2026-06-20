"""Service for managing the global chat history knowledge base.

A single system-owned chat_history KB that automatically stores ALL users'
Q&A conversation pairs as vectorized chunks for semantic retrieval.
Old chunks are cleaned up after CHAT_HISTORY_RETENTION_DAYS.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.vector_service import vector_service
from app.utils.text_splitter import split_text
from app.core.config import settings

logger = logging.getLogger(__name__)

CHAT_HISTORY_RETENTION_DAYS = 60
CHAT_HISTORY_KB_NAME = "我的对话历史"
CHAT_HISTORY_SYSTEM_USER_ID = 0


def get_or_create_chat_history_kb() -> int:
    """Get or create the single global chat_history KB.

    Returns the KB id.
    """
    mysql_db: Session = MySQLSessionLocal()
    try:
        kb = mysql_db.query(KnowledgeBase).filter(
            KnowledgeBase.type == "chat_history",
        ).first()

        if kb:
            return kb.id

        kb = KnowledgeBase(
            name=CHAT_HISTORY_KB_NAME,
            description="自动保存的所有用户对话历史记录（仅保留最近两个月）",
            type="chat_history",
            owner_id=CHAT_HISTORY_SYSTEM_USER_ID,
            visibility="public",
            status=1,
        )
        mysql_db.add(kb)
        mysql_db.commit()
        mysql_db.refresh(kb)
        logger.info("Created global chat_history KB %s", kb.id)
        return kb.id
    finally:
        mysql_db.close()


def store_conversation(
    user_id: int,
    kb_id: int,
    question: str,
    answer: str,
    session_id: int | None = None,
) -> int:
    """Store a Q&A conversation pair as a chunk in the chat_history KB.

    Returns the number of chunks created.
    """
    # Build the conversation text — use a clear delimited format
    # so the embedding captures both the question and answer together.
    conversation_text = (
        f"[用户问题]\n{question.strip()}\n\n"
        f"[助手回答]\n{answer.strip()}"
    )
    if not conversation_text.strip():
        return 0

    # Create a Document record to track this conversation entry
    mysql_db: Session = MySQLSessionLocal()
    pg_db: Session = PgSessionLocal()
    try:
        # Truncate filename if too long
        title = question.strip()[:80]

        doc = Document(
            kb_id=kb_id,
            source_id=0,  # marker: chat-history source
            source_url=str(session_id) if session_id else "",
            filename=title,
            file_type="chat_text",
            file_size=len(conversation_text.encode("utf-8")),
            parse_status="success",
            vector_status="processing",
            uploader_id=user_id,
        )
        mysql_db.add(doc)
        mysql_db.commit()
        mysql_db.refresh(doc)

        # Split, embed, and store chunks
        chunks = split_text(
            conversation_text,
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
        )
        if not chunks:
            doc.vector_status = "failed"
            doc.error_message = "No chunks produced"
            mysql_db.commit()
            return 0

        successful = 0
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue
            try:
                embedding = vector_service.embed_text(chunk_text)
            except Exception as exc:
                logger.warning("Embedding failed for chat chunk %s: %s", i, exc)
                embedding = None

            chunk = DocumentChunk(
                document_id=doc.id,
                kb_id=kb_id,
                chunk_index=i,
                content=chunk_text,
                page_num=None,
                embedding=embedding,
            )
            pg_db.add(chunk)
            successful += 1

            if successful % 10 == 0:
                pg_db.commit()

        pg_db.commit()
        doc.vector_status = "success" if successful > 0 else "failed"
        mysql_db.commit()

        return successful

    except Exception as exc:
        logger.exception("Failed to store conversation")
        mysql_db.rollback()
        pg_db.rollback()
        return 0
    finally:
        mysql_db.close()
        pg_db.close()


def cleanup_old_chunks(kb_id: int) -> int:
    """Delete DocumentChunks older than CHAT_HISTORY_RETENTION_DAYS for the given KB.

    Returns the number of chunks deleted.
    """
    cutoff = datetime.now() - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)

    mysql_db: Session = MySQLSessionLocal()
    pg_db: Session = PgSessionLocal()
    try:
        # Find old documents for this KB
        old_docs = mysql_db.query(Document).filter(
            Document.kb_id == kb_id,
            Document.created_at < cutoff,
        ).all()

        if not old_docs:
            return 0

        doc_ids = [d.id for d in old_docs]

        # Delete chunks from PostgreSQL
        deleted = pg_db.query(DocumentChunk).filter(
            DocumentChunk.document_id.in_(doc_ids),
        ).delete(synchronize_session=False)
        pg_db.commit()

        # Delete documents from MySQL
        mysql_db.query(Document).filter(
            Document.id.in_(doc_ids),
        ).delete(synchronize_session=False)
        mysql_db.commit()

        logger.info(
            "Cleaned up %s chunks and %s documents from chat_history KB %s",
            deleted, len(doc_ids), kb_id,
        )
        return deleted

    except Exception as exc:
        logger.exception("Cleanup failed for chat_history KB %s", kb_id)
        mysql_db.rollback()
        pg_db.rollback()
        return 0
    finally:
        mysql_db.close()
        pg_db.close()
