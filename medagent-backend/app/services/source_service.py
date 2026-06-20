"""Source service for synchronizing online knowledge sources."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.adapters import get_adapter
from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_source import KnowledgeSource
from app.services.vector_service import vector_service
from app.utils.text_splitter import split_text
from app.core.config import settings

logger = logging.getLogger(__name__)


def split_and_store_content(
    pg_db: Session,
    document_id: int,
    kb_id: int,
    full_text: str,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> int:
    """Split text, generate embeddings, and store as DocumentChunks.

    Shared function used by both file uploads and online source sync.
    Returns the number of chunks created.
    """
    cs = chunk_size or settings.CHUNK_SIZE
    co = chunk_overlap or settings.CHUNK_OVERLAP

    chunks = split_text(full_text, chunk_size=cs, chunk_overlap=co)
    if not chunks:
        return 0

    # Delete existing chunks for this document (idempotent)
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()

    successful = 0
    for i, chunk_text in enumerate(chunks):
        if not chunk_text.strip():
            continue

        try:
            embedding = vector_service.embed_text(chunk_text)
        except Exception:
            embedding = None

        chunk = DocumentChunk(
            document_id=document_id,
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
    return successful


class SourceService:
    """Service for managing and synchronizing online knowledge sources."""

    def sync_source(self, source_id: int) -> dict:
        """Execute a full sync for a knowledge source.

        Called by RQ worker. This is a blocking function that:
        1. Loads the KnowledgeSource config
        2. Instantiates the appropriate adapter
        3. Fetches content and stores as Documents + Chunks
        """
        mysql_db: Session = MySQLSessionLocal()
        pg_db: Session = PgSessionLocal()

        try:
            source = mysql_db.query(KnowledgeSource).filter(
                KnowledgeSource.id == source_id
            ).first()
            if not source:
                raise ValueError(f"KnowledgeSource {source_id} not found")

            # Update status to syncing
            source.sync_status = "syncing"
            source.error_message = None
            mysql_db.commit()

            config = json.loads(source.config) if isinstance(source.config, str) else source.config
            adapter = get_adapter(source.source_type)

            total_docs = 0
            total_chunks = 0

            async def consume():
                nonlocal total_docs, total_chunks
                async for source_doc in adapter.fetch_content(config):
                    if not source_doc.content.strip():
                        continue

                    # Create Document record
                    doc = Document(
                        kb_id=source.kb_id,
                        source_id=source.id,
                        source_url=source_doc.source_url,
                        filename=source_doc.title[:255],
                        file_type="source_text",
                        file_size=len(source_doc.content.encode("utf-8")),
                        parse_status="success",
                        vector_status="processing",
                        uploader_id=0,
                    )
                    mysql_db.add(doc)
                    mysql_db.commit()
                    mysql_db.refresh(doc)

                    # Split, embed, and store chunks
                    try:
                        n_chunks = split_and_store_content(
                            pg_db, doc.id, source.kb_id, source_doc.content,
                        )
                        doc.vector_status = "success" if n_chunks > 0 else "failed"
                        mysql_db.commit()
                        total_chunks += n_chunks
                        total_docs += 1
                    except Exception as e:
                        doc.vector_status = "failed"
                        doc.error_message = str(e)[:500]
                        mysql_db.commit()
                        logger.warning(f"Failed to process doc '{source_doc.title}': {e}")

            asyncio.run(consume())

            # Update source status
            source.sync_status = "success"
            source.last_sync_at = datetime.now(timezone.utc)
            source.error_message = None
            mysql_db.commit()

            return {
                "status": "success",
                "source_id": source_id,
                "documents_created": total_docs,
                "chunks_created": total_chunks,
            }

        except Exception as e:
            logger.exception(f"Sync failed for source {source_id}")
            try:
                source = mysql_db.query(KnowledgeSource).filter(
                    KnowledgeSource.id == source_id
                ).first()
                if source:
                    source.sync_status = "failed"
                    source.error_message = str(e)[:500]
                    mysql_db.commit()
            except Exception:
                mysql_db.rollback()
            return {"status": "failed", "source_id": source_id, "error": str(e)}

        finally:
            mysql_db.close()
            pg_db.close()

    def delete_source(self, source_id: int) -> int:
        """Delete a knowledge source and all associated documents + chunks.
        Returns the number of documents deleted.
        """
        mysql_db: Session = MySQLSessionLocal()
        pg_db: Session = PgSessionLocal()

        try:
            source = mysql_db.query(KnowledgeSource).filter(
                KnowledgeSource.id == source_id
            ).first()
            if not source:
                return 0

            # Find all documents for this source
            doc_ids = [
                d[0] for d in mysql_db.query(Document.id).filter(
                    Document.source_id == source_id
                ).all()
            ]

            # Delete chunks from PostgreSQL
            for doc_id in doc_ids:
                pg_db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc_id
                ).delete()
            pg_db.commit()

            # Delete documents from MySQL
            deleted = mysql_db.query(Document).filter(
                Document.source_id == source_id
            ).delete()
            mysql_db.commit()

            # Delete the source config
            mysql_db.delete(source)
            mysql_db.commit()

            return deleted

        finally:
            mysql_db.close()
            pg_db.close()

    def get_source_document_count(self, source_id: int) -> int:
        """Get the number of documents synced from a source."""
        mysql_db: Session = MySQLSessionLocal()
        try:
            count = mysql_db.query(Document).filter(
                Document.source_id == source_id
            ).count()
            return count
        finally:
            mysql_db.close()

    def cleanup_orphaned_sources(self) -> int:
        """Delete KnowledgeSources whose linked KnowledgeBase no longer exists.

        This prevents stale sources from appearing after their KB is deleted.
        Returns the number of sources deleted.
        """
        mysql_db: Session = MySQLSessionLocal()
        try:
            # Get all existing KB IDs
            existing_kb_ids = {
                row[0] for row in mysql_db.query(
                    KnowledgeBase.id
                ).filter(KnowledgeBase.status == 1).all()
            }

            # Find sources whose kb_id is not in the existing set
            orphaned = mysql_db.query(KnowledgeSource).all()
            to_delete = [s for s in orphaned if s.kb_id not in existing_kb_ids]

            if not to_delete:
                return 0

            deleted_count = 0
            for source in to_delete:
                try:
                    self.delete_source(source.id)
                    deleted_count += 1
                except Exception:
                    mysql_db.delete(source)
                    mysql_db.commit()
                    deleted_count += 1

            return deleted_count
        finally:
            mysql_db.close()

    def update_source_from_sync(self, mysql_db: Session, source_id: int, status: str, error: str = None):
        """Update source sync status (used during sync lifecycle)."""
        source = mysql_db.query(KnowledgeSource).filter(
            KnowledgeSource.id == source_id
        ).first()
        if source:
            source.sync_status = status
            if error:
                source.error_message = str(error)[:500]
            if status == "syncing":
                source.error_message = None
            mysql_db.commit()


source_service = SourceService()
