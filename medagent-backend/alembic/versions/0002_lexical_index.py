"""Maintain PostgreSQL lexical search vectors.

Revision ID: 0002_lexical_index
Revises: 0001_rag_metadata
"""

from alembic import op

revision = "0002_lexical_index"
down_revision = "0001_rag_metadata"
branch_labels = None
depends_on = None


def upgrade(database: str = "postgres") -> None:
    if database != "postgres":
        return
    op.execute("UPDATE document_chunk SET search_vector = to_tsvector('simple', coalesce(content, ''))")
    op.execute("""
        CREATE OR REPLACE FUNCTION document_chunk_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
          NEW.search_vector := to_tsvector('simple', coalesce(NEW.content, ''));
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER document_chunk_search_vector_trigger
        BEFORE INSERT OR UPDATE OF content ON document_chunk
        FOR EACH ROW EXECUTE FUNCTION document_chunk_search_vector_update()
    """)


def downgrade(database: str = "postgres") -> None:
    if database != "postgres":
        return
    op.execute("DROP TRIGGER IF EXISTS document_chunk_search_vector_trigger ON document_chunk")
    op.execute("DROP FUNCTION IF EXISTS document_chunk_search_vector_update()")
