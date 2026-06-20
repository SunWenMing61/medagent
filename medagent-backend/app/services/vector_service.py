from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.db.session import PgSessionLocal


class VectorService:
    """Service for vector search using pgvector."""

    def _get_embedding(self, text: str) -> List[float]:
        """Get embedding vector using configured embedding API."""
        import httpx

        api_key = settings.EMBEDDING_API_KEY
        if not api_key:
            raise ValueError("EMBEDDING_API_KEY not configured")

        response = httpx.post(
            f"{settings.EMBEDDING_API_BASE}/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": settings.EMBEDDING_MODEL, "input": text, "dimensions": 1024},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

    def embed_text(self, text: str) -> List[float]:
        return self._get_embedding(text)

    def search(
        self,
        query: str,
        kb_ids: Optional[List[int]] = None,
        top_k: int = None,
        threshold: float = None,
    ) -> List[dict]:
        """Search for similar chunks using pgvector cosine similarity."""
        if top_k is None:
            top_k = settings.TOP_K
        if threshold is None:
            threshold = settings.SIMILARITY_THRESHOLD

        query_vector = self._get_embedding(query)
        vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

        db: Session = PgSessionLocal()
        try:
            if kb_ids:
                kb_placeholders = ",".join(str(k) for k in kb_ids)
                sql = text(f"""
                    SELECT id, document_id, kb_id, chunk_index, content, page_num,
                           1 - (embedding <=> '{vector_str}'::vector) AS similarity
                    FROM document_chunk
                    WHERE kb_id IN ({kb_placeholders})
                      AND embedding IS NOT NULL
                      AND 1 - (embedding <=> '{vector_str}'::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """)
            else:
                sql = text(f"""
                    SELECT id, document_id, kb_id, chunk_index, content, page_num,
                           1 - (embedding <=> '{vector_str}'::vector) AS similarity
                    FROM document_chunk
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> '{vector_str}'::vector) >= :threshold
                    ORDER BY similarity DESC
                    LIMIT :top_k
                """)

            rows = db.execute(sql, {"top_k": top_k, "threshold": threshold}).fetchall()
            results = []
            for row in rows:
                results.append({
                    "id": row[0],
                    "document_id": row[1],
                    "kb_id": row[2],
                    "chunk_index": row[3],
                    "content": row[4],
                    "page_num": row[5],
                    "similarity": float(row[6]),
                })
            return results
        finally:
            db.close()


vector_service = VectorService()
