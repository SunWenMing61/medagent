"""Authorized chunk-to-page/block context resolver."""

from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_processing import DocumentCleanBlock
from app.models.user import User
from app.services.access_control_service import resolve_authorized_kb_ids
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import DocumentContextInput, ToolExecutionResult


class DocumentContextTool:
    name = "get_document_evidence_context"
    version = "1.0.0"

    def execute(self, payload: DocumentContextInput) -> ToolExecutionResult:
        pg = PgSessionLocal()
        mysql = MySQLSessionLocal()
        try:
            chunk = pg.query(DocumentChunk).filter(DocumentChunk.id == payload.chunk_id).first()
            if not chunk:
                return ToolExecutionResult(status="no_result")
            document = mysql.query(Document).filter(Document.id == chunk.document_id).first()
            user = mysql.query(User).filter(
                User.id == payload.context.user_id,
                User.tenant_id == payload.context.tenant_id,
                User.status == 1,
            ).first()
            if not document or not user:
                return ToolExecutionResult(status="forbidden", error_code="DOCUMENT_SCOPE_DENIED", message="Document scope is unavailable")
            authorized = resolve_authorized_kb_ids(user, [document.kb_id], mysql)
            if document.kb_id not in authorized or document.kb_id not in payload.context.authorized_kb_ids:
                return ToolExecutionResult(status="forbidden", error_code="DOCUMENT_SCOPE_DENIED", message="Document is outside the injected KB scope")
            low = max(0, int(chunk.chunk_index or 0) - payload.neighboring_chunks)
            high = int(chunk.chunk_index or 0) + payload.neighboring_chunks
            neighbors = pg.query(DocumentChunk).filter(
                DocumentChunk.document_id == chunk.document_id,
                DocumentChunk.chunk_type == "child",
                DocumentChunk.chunk_index.between(low, high),
            ).order_by(DocumentChunk.chunk_index).all()
            source_ids = list(chunk.source_block_ids or [])
            blocks = mysql.query(DocumentCleanBlock).filter(
                DocumentCleanBlock.document_id == chunk.document_id,
                DocumentCleanBlock.block_id.in_(source_ids),
            ).all() if source_ids else []
            return ToolExecutionResult(status="success", data={
                "document_id": document.id,
                "document_name": document.filename,
                "chunk_id": chunk.id,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_path": chunk.section_path or [],
                "content_type": chunk.content_type,
                "quality_status": chunk.quality_status,
                "source_block_ids": source_ids,
                "source_blocks": [{"block_id": item.block_id, "page_num": item.page_num, "bbox": item.bbox_json, "text": item.text} for item in blocks],
                "neighbor_chunks": [{"chunk_id": item.id, "content": item.content, "page_start": item.page_start, "page_end": item.page_end} for item in neighbors],
            })
        except PermissionError as exc:
            return ToolExecutionResult(status="forbidden", error_code="DOCUMENT_SCOPE_DENIED", message=str(exc))
        except Exception as exc:
            return ToolExecutionResult(status="error", error_code="DOCUMENT_CONTEXT_ERROR", message=str(exc))
        finally:
            pg.close()
            mysql.close()


document_context_tool = DocumentContextTool()
tool_registry.register(ToolDefinition(
    document_context_tool.name, document_context_tool.version, DocumentContextInput,
    description="Resolve an authorized evidence chunk to neighboring chunks, section, pages and clean-block coordinates. Use after retrieval for citation context; do not use for arbitrary document access. Read-only and may return no_result.",
    category="document", allowed_agents=frozenset({"retrieval", "evidence_verification", "supervisor"}),
    required_scopes=frozenset({"kb:read"}), timeout_seconds=3, max_retries=1,
    max_calls_per_run=4, cache_ttl_seconds=120,
), document_context_tool)
