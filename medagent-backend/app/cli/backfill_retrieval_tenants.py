"""Backfill denormalized PostgreSQL tenant/document metadata after migration 0006."""

from __future__ import annotations

import argparse

from sqlalchemy import text

from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase


def backfill(*, apply: bool) -> dict[str, int]:
    mysql = MySQLSessionLocal()
    pg = PgSessionLocal()
    counts = {"documents": 0, "chunks": 0}
    try:
        rows = (
            mysql.query(Document, KnowledgeBase)
            .join(KnowledgeBase, KnowledgeBase.id == Document.kb_id)
            .all()
        )
        for document, kb in rows:
            counts["documents"] += 1
            if apply:
                result = pg.execute(text("""
                    UPDATE document_chunk SET tenant_id=:tenant_id,
                      document_version=COALESCE(document_version, :document_version),
                      title=COALESCE(title, :title)
                    WHERE document_id=:document_id AND kb_id=:kb_id
                """), {
                    "tenant_id": kb.tenant_id, "document_id": document.id, "kb_id": document.kb_id,
                    "document_version": document.document_version or document.content_sha256 or "legacy",
                    "title": document.filename,
                })
                counts["chunks"] += int(result.rowcount or 0)
        if apply:
            pg.commit()
        else:
            pg.rollback()
        return counts
    except Exception:
        pg.rollback()
        raise
    finally:
        mysql.close()
        pg.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(backfill(apply=args.apply))
