"""ACL-scoped local retrieval tool. Authorization is checked before SQL search."""

from __future__ import annotations

from app.agents.schemas import RetrievedEvidence
from app.db.session import MySQLSessionLocal
from app.models.user import User
from app.services.access_control_service import resolve_authorized_kb_ids
from app.services.citation_service import issue_evidence_ids
from app.services.retrieval_service import RetrievalStatus, hybrid_retriever
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import LocalRetrievalInput, ToolExecutionResult


class LocalRetrievalTool:
    name = "local_knowledge_base"
    version = "2.0.0"

    def __init__(self, retriever=None, authorization_validator=None) -> None:
        self.retriever = retriever or hybrid_retriever
        self.authorization_validator = authorization_validator or self._validate_scope

    @staticmethod
    def _validate_scope(payload: LocalRetrievalInput) -> None:
        db = MySQLSessionLocal()
        try:
            user = db.query(User).filter(
                User.id == payload.context.user_id,
                User.tenant_id == payload.context.tenant_id,
                User.status == 1,
            ).first()
            if not user:
                raise PermissionError("Tool caller is not an active user in the requested tenant")
            resolved = resolve_authorized_kb_ids(user, payload.context.authorized_kb_ids, db)
            if resolved != sorted(set(payload.context.authorized_kb_ids)):
                raise PermissionError("Authorized KB scope changed during tool execution")
        finally:
            db.close()

    def execute(self, payload: LocalRetrievalInput) -> ToolExecutionResult:
        self.authorization_validator(payload)
        result = self.retriever.retrieve(
            payload.query,
            payload.context.authorized_kb_ids,
            top_k=payload.top_k,
            exact_terms=payload.exact_terms,
            numeric_constraints=payload.numeric_constraints,
            population_constraints=payload.population_constraints,
            time_constraints=payload.time_constraints,
            negations=payload.negations,
            tenant_id=payload.context.tenant_id,
            request_id=payload.context.request_id,
            user_id=payload.context.user_id,
        )
        issued = issue_evidence_ids(result.evidence)
        evidence = []
        for item in issued:
            content = str(item.get("context_content") or item.get("content") or "")
            exact = max(
                (1.0 if term and term.lower() in content.lower() else 0.0 for term in payload.exact_terms),
                default=0.0,
            )
            evidence.append(RetrievedEvidence(
                evidence_id=item["evidence_id"],
                content=content,
                source_type="local_knowledge_base",
                source_name=f"knowledge_base:{item['kb_id']}",
                document_id=item.get("document_id"),
                chunk_id=item.get("id"),
                page_num=item.get("page_num") or item.get("page_start"),
                page_start=item.get("page_start"),
                page_end=item.get("page_end"),
                parent_chunk_id=item.get("parent_chunk_id"),
                section_path=item.get("section_path") or [],
                section_title=" / ".join(item.get("section_path") or []) or None,
                retrieval_score=item.get("similarity") or item.get("rrf_score"),
                rerank_score=item.get("rerank_score"),
                dense_score=item.get("dense_score"),
                sparse_score=item.get("sparse_score") or item.get("lexical_score"),
                exact_match_score=max(exact, float(item.get("exact_score") or 0)),
                exact_score=item.get("exact_score"),
                rrf_score=item.get("rrf_score"),
                authority_level=int(item.get("authority_level") or 7),
                is_authorized=True,
                is_conversation_memory=False,
                can_support_medical_claim=bool(item.get("can_support_medical_claim", True)),
                quality_status=item.get("quality_status"),
                metadata={
                    "kb_id": item["kb_id"], "chunk_index": item.get("chunk_index"),
                    "constraint_match": item.get("constraint_match"),
                    "document_version": item.get("document_version"),
                },
            ))
        status = {
            RetrievalStatus.OK: "success",
            RetrievalStatus.NO_EVIDENCE: "no_result",
            RetrievalStatus.DEGRADED: "partial",
            RetrievalStatus.ERROR: "error",
            RetrievalStatus.FORBIDDEN: "forbidden",
            RetrievalStatus.TIMEOUT: "timeout",
        }[result.status]
        return ToolExecutionResult(
            status=status,
            evidence=evidence,
            error_code="LOCAL_RETRIEVAL_ERROR" if status in {"error", "timeout"} else None,
            message="; ".join(issue.message for issue in result.issues),
        )


local_retrieval_tool = LocalRetrievalTool()
tool_registry.register(
    ToolDefinition(
        local_retrieval_tool.name, local_retrieval_tool.version, LocalRetrievalInput,
        description="Search only the caller's server-authorized local medical knowledge bases using hybrid retrieval, fusion and reranking. Use for document-grounded medical questions; do not use without a KB scope. Read-only, may return no_result.",
        category="retrieval", allowed_agents=frozenset({"query_understanding", "retrieval", "supervisor"}),
        required_scopes=frozenset({"kb:read"}), timeout_seconds=5, max_retries=1,
        max_calls_per_run=2, cache_ttl_seconds=60,
    ),
    local_retrieval_tool,
)
