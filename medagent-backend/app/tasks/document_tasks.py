"""Document processing tasks using RQ (Redis Queue)."""
import os
import sys

# Add project root to path for RQ worker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from rq import Queue
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.utils.file_utils import extract_text
from app.utils.text_splitter import split_text
from app.services.vector_service import vector_service

redis_conn = Redis.from_url(settings.REDIS_URL)
doc_queue = Queue("default", connection=redis_conn)


def _ensure_pgvector_extension():
    """Ensure pgvector extension is available on PostgreSQL."""
    pg_db = PgSessionLocal()
    try:
        from sqlalchemy import text
        pg_db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        pg_db.commit()
    except Exception:
        pg_db.rollback()
    finally:
        pg_db.close()


def process_document(document_id: int):
    """
    Process a document: parse text, split into chunks, generate embeddings, store vectors.
    Uses MySQL for document metadata and PostgreSQL (pgvector) for chunk vectors.
    This function is designed to work as an RQ task.
    """
    _ensure_pgvector_extension()

    mysql_db: Session = MySQLSessionLocal()
    pg_db: Session = PgSessionLocal()
    try:
        doc = mysql_db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            return {"error": "Document not found"}

        # Update parse status
        doc.parse_status = "processing"
        mysql_db.commit()

        # Extract text
        try:
            pages = extract_text(doc.file_path, doc.file_type)
        except Exception as e:
            doc.parse_status = "failed"
            doc.error_message = f"Parse failed: {str(e)}"
            mysql_db.commit()
            return {"error": str(e)}

        if not pages:
            doc.parse_status = "failed"
            doc.error_message = "No text content extracted"
            mysql_db.commit()
            return {"error": "No text content extracted"}

        # Combine all text
        full_text = "\n".join([text for _, text in pages])

        # Split into chunks
        chunks = split_text(full_text, chunk_size=settings.CHUNK_SIZE, chunk_overlap=settings.CHUNK_OVERLAP)
        if not chunks:
            doc.parse_status = "failed"
            doc.error_message = "Text splitting produced no chunks"
            mysql_db.commit()
            return {"error": "No chunks produced"}

        doc.parse_status = "success"
        mysql_db.commit()

        # Update vector status
        doc.vector_status = "processing"
        mysql_db.commit()

        # Delete existing chunks from PostgreSQL
        pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        pg_db.commit()

        # Generate embeddings and store chunks in PostgreSQL
        successful_chunks = 0
        for i, chunk_text in enumerate(chunks):
            if not chunk_text.strip():
                continue

            try:
                embedding = vector_service.embed_text(chunk_text)
            except Exception:
                embedding = None

            chunk = DocumentChunk(
                document_id=document_id,
                kb_id=doc.kb_id,
                chunk_index=i,
                content=chunk_text,
                page_num=None,
                embedding=embedding,
            )
            pg_db.add(chunk)
            successful_chunks += 1

            # Commit every 10 chunks
            if successful_chunks % 10 == 0:
                pg_db.commit()

        pg_db.commit()
        doc.vector_status = "success"
        mysql_db.commit()

        return {
            "status": "success",
            "document_id": document_id,
            "chunks": successful_chunks,
        }

    except Exception as e:
        mysql_db.rollback()
        pg_db.rollback()
        # Attempt to mark document as failed in MySQL
        doc = mysql_db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.parse_status = "failed" if doc.parse_status == "processing" else doc.parse_status
            doc.vector_status = "failed" if doc.vector_status == "processing" else doc.vector_status
            doc.error_message = str(e)
            mysql_db.commit()
        return {"error": str(e)}
    finally:
        mysql_db.close()
        pg_db.close()
