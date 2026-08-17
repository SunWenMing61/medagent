"""Authorized structured medical-table reader."""

from app.db.session import MySQLSessionLocal
from app.models.document import Document
from app.models.document_processing import DocumentTable
from app.models.user import User
from app.services.access_control_service import resolve_authorized_kb_ids
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import MedicalTableInput, ToolExecutionResult


class MedicalTableTool:
    name = "get_medical_table"
    version = "1.0.0"

    def execute(self, payload: MedicalTableInput) -> ToolExecutionResult:
        db = MySQLSessionLocal()
        try:
            document = db.query(Document).filter(Document.id == payload.document_id).first()
            user = db.query(User).filter(
                User.id == payload.context.user_id,
                User.tenant_id == payload.context.tenant_id,
                User.status == 1,
            ).first()
            if not document or not user:
                return ToolExecutionResult(status="forbidden", error_code="TABLE_SCOPE_DENIED", message="Document scope is unavailable")
            authorized = resolve_authorized_kb_ids(user, [document.kb_id], db)
            if document.kb_id not in authorized or document.kb_id not in payload.context.authorized_kb_ids:
                return ToolExecutionResult(status="forbidden", error_code="TABLE_SCOPE_DENIED", message="Document is outside the injected KB scope")
            query = db.query(DocumentTable).filter(DocumentTable.document_id == document.id)
            if payload.table_id:
                query = query.filter(DocumentTable.table_id == payload.table_id)
            rows = query.order_by(DocumentTable.page_start).limit(20).all()
            if payload.query:
                term = payload.query.lower()
                rows = [item for item in rows if term in (item.title or "").lower() or term in item.markdown.lower()]
            if not rows:
                return ToolExecutionResult(status="no_result")
            return ToolExecutionResult(status="success", data=[{
                "table_id": item.table_id, "title": item.title, "page_start": item.page_start,
                "page_end": item.page_end, "section_path": item.section_path_json or [],
                "headers": item.headers_json or [], "rows": item.rows_json or [],
                "units": item.units_json or [], "footnotes": item.footnotes_json or [],
                "markdown": item.markdown, "confidence": item.confidence,
            } for item in rows])
        except PermissionError as exc:
            return ToolExecutionResult(status="forbidden", error_code="TABLE_SCOPE_DENIED", message=str(exc))
        except Exception as exc:
            return ToolExecutionResult(status="error", error_code="TABLE_LOOKUP_ERROR", message=str(exc))
        finally:
            db.close()


medical_table_tool = MedicalTableTool()
tool_registry.register(ToolDefinition(
    medical_table_tool.name, medical_table_tool.version, MedicalTableInput,
    description="Return an authorized parsed medical table with headers, rows, units, footnotes, pages, Markdown and JSON. Use for table-grounded questions; do not flatten or infer missing cells. Read-only and may return no_result.",
    category="document", allowed_agents=frozenset({"retrieval", "evidence_verification", "answer_generation", "supervisor"}),
    required_scopes=frozenset({"kb:read"}), timeout_seconds=3, max_retries=1,
    max_calls_per_run=3, cache_ttl_seconds=300,
), medical_table_tool)
