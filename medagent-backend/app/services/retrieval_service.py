"""ACL-first Dense/Sparse/Exact retrieval with RRF, rerank and bounded context expansion."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Sequence

from sqlalchemy import text

from app.chunking.token_counter import count_tokens
from app.core.config import settings
from app.db.session import PgSessionLocal
from app.services.embedding_service import embedding_service

logger = logging.getLogger(__name__)


class RetrievalStatus(str, Enum):
    OK = "success"
    NO_EVIDENCE = "no_result"
    DEGRADED = "partial"
    ERROR = "error"
    FORBIDDEN = "forbidden"
    TIMEOUT = "timeout"


class RetrievalScopeError(ValueError):
    """Retrieval was attempted without an explicit authorized KB scope."""


@dataclass(slots=True)
class RetrievalIssue:
    component: str
    message: str
    retryable: bool = False
    code: str = "RETRIEVAL_COMPONENT_ERROR"


@dataclass(slots=True)
class RetrievalResult:
    status: RetrievalStatus
    evidence: list[dict]
    issues: list[RetrievalIssue] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    rankings: dict[str, list[dict]] = field(default_factory=dict)
    filtered: list[dict] = field(default_factory=list)


def reciprocal_rank_fusion(rankings: Sequence[Sequence[dict]], rrf_k: int = 60) -> list[dict]:
    """Fuse ranked lists by stable chunk ID while retaining route-specific scores."""
    fused: dict[int, dict] = {}
    for source_index, ranking in enumerate(rankings):
        for rank, candidate in enumerate(ranking, start=1):
            chunk_id = int(candidate["id"])
            item = fused.setdefault(chunk_id, dict(candidate))
            for score_name in ("dense_score", "sparse_score", "lexical_score", "exact_score", "similarity"):
                if candidate.get(score_name) is not None:
                    item[score_name] = max(float(item.get(score_name) or 0), float(candidate[score_name]))
            item["rrf_score"] = float(item.get("rrf_score", 0.0)) + 1.0 / (rrf_k + rank)
            item.setdefault("retrieval_sources", []).append(source_index)
        
    return sorted(fused.values(), key=lambda item: (-item["rrf_score"], int(item["id"])))


class HybridRetriever:
    def __init__(
        self,
        dense_fetcher: Callable[[str, list[int], int], list[dict]] | None = None,
        lexical_fetcher: Callable[[str, list[int], int], list[dict]] | None = None,
        parent_fetcher: Callable[[list[int]], dict[int, Any]] | None = None,
        reranker=None,
        exact_fetcher: Callable[[list[str], list[int], int], list[dict]] | None = None,
        neighbor_fetcher: Callable[[list[dict], list[int], int | None], dict[int, list[dict]]] | None = None,
    ) -> None:
        injected_routes = dense_fetcher is not None or lexical_fetcher is not None
        self._dense_is_default = dense_fetcher is None
        self._lexical_is_default = lexical_fetcher is None
        self._exact_is_default = exact_fetcher is None and not injected_routes
        self._dense_fetcher = dense_fetcher or self._dense_search
        self._lexical_fetcher = lexical_fetcher or self._lexical_search
        self._exact_fetcher = exact_fetcher if exact_fetcher is not None else (None if injected_routes else self._exact_search)
        self._parent_fetcher = parent_fetcher or self._fetch_parents
        # Injected route fetchers are used by offline tests and alternate backends;
        # never let them accidentally fall through to the production PostgreSQL store.
        self._neighbor_fetcher = neighbor_fetcher or ((lambda *_: {}) if injected_routes else self._fetch_neighbors)
        self._reranker = reranker

    def retrieve(
        self,
        query: str,
        kb_ids: Sequence[int],
        *,
        top_k: int | None = None,
        evidence_token_budget: int | None = None,
        exact_terms: Sequence[str] | None = None,
        numeric_constraints: Sequence[dict] | None = None,
        population_constraints: Sequence[str] | None = None,
        time_constraints: Sequence[str] | None = None,
        negations: Sequence[str] | None = None,
        tenant_id: int | None = None,
        request_id: str | None = None,
        user_id: int | None = None,
    ) -> RetrievalResult:
        scope = sorted({int(kb_id) for kb_id in kb_ids})
        if not scope:
            raise RetrievalScopeError("An explicit non-empty authorized kb_ids scope is required")
        if not query.strip():
            return RetrievalResult(RetrievalStatus.NO_EVIDENCE, [])

        total_started = time.perf_counter()
        final_k = top_k or self._dynamic_top_k(query)
        candidate_k = max(settings.RETRIEVAL_CANDIDATE_K, final_k)
        timings: dict[str, float] = {}
        issues: list[RetrievalIssue] = []
        rankings_by_name: dict[str, list[dict]] = {}
        terms = list(dict.fromkeys(str(item).strip() for item in (exact_terms or []) if str(item).strip()))[:20]
        # Dense and sparse recall are mandatory: there is no vector-only or
        # lexical-only runtime mode. Exact matching is an additional route.
        jobs: dict[str, Callable[[], list[dict]]] = {
            "dense": lambda: (
                self._dense_search(query, scope, candidate_k, tenant_id)
                if self._dense_is_default else self._dense_fetcher(query, scope, candidate_k)
            ),
            "sparse": lambda: (
                self._lexical_search(query, scope, candidate_k, tenant_id)
                if self._lexical_is_default else self._lexical_fetcher(query, scope, candidate_k)
            ),
        }
        if self._exact_fetcher and terms:
            jobs["exact"] = lambda: (
                self._exact_search(terms, scope, min(candidate_k, 20), tenant_id)
                if self._exact_is_default else self._exact_fetcher(terms, scope, min(candidate_k, 20))
            )

        started_by_route: dict[str, float] = {}
        pool = ThreadPoolExecutor(max_workers=max(1, len(jobs)), thread_name_prefix="hybrid-retrieval")
        try:
            futures = {}
            for name, job in jobs.items():
                started_by_route[name] = time.perf_counter()
                futures[pool.submit(job)] = name
            try:
                for future in as_completed(futures, timeout=settings.RETRIEVAL_TIMEOUT_SECONDS):
                    name = futures[future]
                    try:
                        rankings_by_name[name] = future.result()
                    except TimeoutError as exc:
                        issues.append(RetrievalIssue(name, str(exc) or "route timed out", True, "RETRIEVAL_TIMEOUT"))
                    except Exception as exc:
                        logger.exception("%s retrieval failed inside authorized scope", name)
                        issues.append(RetrievalIssue(name, str(exc), name == "dense", "RETRIEVAL_COMPONENT_ERROR"))
                    timings[f"{name}_ms"] = round((time.perf_counter() - started_by_route[name]) * 1000, 3)
            except FuturesTimeout:
                for future, name in futures.items():
                    if not future.done():
                        future.cancel()
                        issues.append(RetrievalIssue(name, f"{name} exceeded retrieval timeout", True, "RETRIEVAL_TIMEOUT"))
                        timings[f"{name}_ms"] = round((time.perf_counter() - started_by_route[name]) * 1000, 3)
        finally:
            # Do not wait for an unresponsive provider after the public timeout.
            pool.shutdown(wait=False, cancel_futures=True)

        if not rankings_by_name:
            timings["total_ms"] = round((time.perf_counter() - total_started) * 1000, 3)
            status = RetrievalStatus.TIMEOUT if issues and all(item.code == "RETRIEVAL_TIMEOUT" for item in issues) else RetrievalStatus.ERROR
            result = RetrievalResult(status, [], issues, timings, rankings_by_name)
            self._record_trace(result, query, request_id, tenant_id, user_id, terms)
            return result

        rankings = list(rankings_by_name.values())
        fused = reciprocal_rank_fusion(rankings, settings.RRF_K)
        fused = self._deduplicate(fused)
        filtered: list[dict] = []
        if fused:
            adaptive_floor = float(fused[0].get("rrf_score") or fused[0].get("similarity") or 0) * 0.20
            retained = []
            for item in fused:
                score = float(item.get("rrf_score") or item.get("similarity") or 0)
                if adaptive_floor and score < adaptive_floor:
                    filtered.append({"id": item["id"], "reason": "adaptive_fusion_floor"})
                else:
                    retained.append(item)
            fused = retained

        reranker = self._reranker
        if reranker is None and fused:
            try:
                from app.services.rerank_service import rerank_service
                reranker = rerank_service
            except ImportError:
                reranker = None
        if reranker is not None and fused:
            started = time.perf_counter()
            try:
                fused = reranker.rerank(query, fused, top_k=candidate_k, threshold=0.0)
            except Exception as exc:
                issues.append(RetrievalIssue("rerank", str(exc), False, "RERANK_ERROR"))
            timings["rerank_ms"] = round((time.perf_counter() - started) * 1000, 3)

        for item in fused:
            match = self._constraint_match(
                item.get("content", ""), numeric_constraints or [], population_constraints or [],
                time_constraints or [], negations or [],
            )
            item["constraint_match"] = match
            authority = float(item.get("authority_level") or self._authority(item)) / 10.0
            quality = 0.4 if item.get("quality_status") == "manual_review_required" else (0.7 if item.get("quality_status") == "medium" else 1.0)
            base = float(item.get("rerank_score") or item.get("rrf_score") or item.get("similarity") or 0)
            item["final_score"] = 0.60 * base + 0.20 * match["score"] + 0.15 * authority + 0.05 * quality
            item["authority_level"] = int(item.get("authority_level") or self._authority(item))
            item["is_authorized"] = True
            item["can_support_medical_claim"] = True
        fused.sort(key=lambda item: (-float(item.get("exact_score") or 0), -float(item.get("final_score") or 0), int(item["id"])))

        if settings.RETRIEVAL_PARENT_CHILD_ENABLED:
            parent_ids = sorted({int(item["parent_chunk_id"]) for item in fused if item.get("parent_chunk_id")})
            parents: dict[int, Any] = {}
            if parent_ids:
                try:
                    parents = self._parent_fetcher(parent_ids)
                except Exception as exc:
                    issues.append(RetrievalIssue("parent_expansion", str(exc), False, "CONTEXT_EXPANSION_ERROR"))
            for item in fused:
                parent = parents.get(int(item["parent_chunk_id"])) if item.get("parent_chunk_id") else None
                item["context_content"] = parent.get("content", item["content"]) if isinstance(parent, dict) else (parent or item["content"])
                if isinstance(parent, dict):
                    item.setdefault("metadata", {})["parent_metadata"] = {key: value for key, value in parent.items() if key != "content"}
        else:
            for item in fused:
                item["context_content"] = item["content"]

        if settings.RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED:
            expandable = [item for item in fused[:final_k] if self._needs_neighbors(item)]
            if expandable:
                try:
                    neighbors = self._neighbor_fetcher(expandable, scope, tenant_id)
                    for item in expandable:
                        values = neighbors.get(int(item["id"]), [])
                        if values:
                            item["context_content"] = "\n".join([entry["content"] for entry in values] + [item["context_content"]])
                            item.setdefault("metadata", {})["neighbor_chunk_ids"] = [entry["id"] for entry in values]
                except Exception as exc:
                    issues.append(RetrievalIssue("neighbor_expansion", str(exc), False, "CONTEXT_EXPANSION_ERROR"))

        evidence = self._apply_budget(
            fused, max_chunks=final_k,
            max_tokens=evidence_token_budget or settings.EVIDENCE_MAX_TOKENS,
        )
        if evidence:
            status = RetrievalStatus.DEGRADED if issues else RetrievalStatus.OK
        else:
            status = RetrievalStatus.DEGRADED if issues else RetrievalStatus.NO_EVIDENCE
        result = RetrievalResult(status, evidence, issues, timings, rankings_by_name, filtered)
        timings["total_ms"] = round((time.perf_counter() - total_started) * 1000, 3)
        self._record_trace(result, query, request_id, tenant_id, user_id, terms)
        return result

    @staticmethod
    def _deduplicate(items: list[dict]) -> list[dict]:
        seen: set[tuple[int, str]] = set()
        result = []
        for item in items:
            digest = item.get("content_sha256") or hashlib.sha256(item["content"].encode("utf-8")).hexdigest()
            key = (int(item["document_id"]), str(digest))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _apply_budget(items: list[dict], max_chunks: int, max_tokens: int) -> list[dict]:
        selected: list[dict] = []
        used = 0
        for item in items:
            tokens = count_tokens(item.get("context_content") or item["content"])
            if selected and used + tokens > max_tokens:
                continue
            if not selected and tokens > max_tokens:
                item = dict(item)
                item["context_content"] = item["content"]
                tokens = count_tokens(item["content"])
            selected.append(item)
            used += tokens
            if len(selected) >= max_chunks:
                break
        return selected

    @staticmethod
    def _dynamic_top_k(query: str) -> int:
        if re.search(r"比较|对比|综述|多文档|compare|review", query, re.I):
            return min(12, settings.EVIDENCE_MAX_CHUNKS)
        if re.search(r"禁忌|相互作用|说明书|剂量|drug", query, re.I):
            return min(8, settings.EVIDENCE_MAX_CHUNKS)
        return min(5, settings.EVIDENCE_MAX_CHUNKS)

    @staticmethod
    def _needs_neighbors(item: dict) -> bool:
        content = str(item.get("content", "")).strip()
        return bool(
            content.endswith((":", "："))
            or re.search(r"上述|如下|见下|continued|表注", content, re.I)
            or item.get("content_type") in {"list", "table", "footnote"}
            or not item.get("section_path")
        )

    @staticmethod
    def _constraint_match(content: str, numeric: Sequence[dict], populations: Sequence[str], times: Sequence[str], negations: Sequence[str]) -> dict:
        lower = content.lower()
        matched_numeric = [str(item.get("original_text")) for item in numeric if HybridRetriever._numeric_constraint_present(lower, item)]
        missing_numeric = [str(item.get("original_text")) for item in numeric if not HybridRetriever._numeric_constraint_present(lower, item)]
        matched_population = [item for item in populations if item.lower() in lower]
        missing_population = [item for item in populations if item.lower() not in lower]
        matched_time = [item for item in times if item.lower() in lower]
        missing_time = [item for item in times if item.lower() not in lower]
        evidence_negative = bool(re.search(r"无|没有|不推荐|禁止|禁忌|not|without|contraindicat", content, re.I))
        negation_consistent = not negations or evidence_negative
        checks = len(numeric) + len(populations) + len(times) + (1 if negations else 0)
        matches = len(matched_numeric) + len(matched_population) + len(matched_time) + (1 if negations and negation_consistent else 0)
        return {
            "matched_numeric_constraints": matched_numeric,
            "missing_numeric_constraints": missing_numeric,
            "matched_population_constraints": matched_population,
            "missing_population_constraints": missing_population,
            "matched_time_constraints": matched_time,
            "missing_time_constraints": missing_time,
            "negation_consistent": negation_consistent,
            "score": matches / checks if checks else 1.0,
        }

    @staticmethod
    def _numeric_constraint_present(content: str, constraint: dict) -> bool:
        def compact(value: str) -> str:
            return re.sub(r"\s+", "", value.casefold()).replace("％", "%")

        original = compact(str(constraint.get("original_text") or ""))
        compact_content = compact(content)
        if original and original in compact_content:
            return True
        name = compact(str(constraint.get("name") or ""))
        unit = compact(str(constraint.get("unit") or ""))
        if name and name != "numeric_condition" and name not in compact_content:
            return False
        if unit and unit not in compact_content:
            return False
        values = constraint.get("value")
        values = values if isinstance(values, list) else [values]
        numbers = [float(value) for value in values if value is not None]
        found = [float(value) for value in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])", content)]
        return bool(numbers) and all(any(abs(actual - expected) <= max(0.001, abs(expected) * 0.001) for actual in found) for expected in numbers)

    @staticmethod
    def _authority(item: dict) -> int:
        source = str(item.get("source_type") or item.get("metadata", {}).get("source_type") or "local_knowledge_base")
        return {"clinical_guideline": 10, "drug_label": 9, "fda": 9, "hospital_internal": 8, "pubmed": 8, "msd_manual": 7, "local_knowledge_base": 7}.get(source, 5)

    @staticmethod
    def _scope_clause(kb_ids: list[int]) -> tuple[str, dict]:
        params = {f"kb_{index}": value for index, value in enumerate(kb_ids)}
        return ", ".join(f":kb_{index}" for index in range(len(kb_ids))), params

    def _dense_search(self, query: str, kb_ids: list[int], limit: int, tenant_id: int | None = None) -> list[dict]:
        vector = embedding_service.embed_one(query)
        vector_text = "[" + ",".join(str(value) for value in vector) + "]"
        placeholders, scope_params = self._scope_clause(kb_ids)
        statement = text(f"""
            SELECT id, document_id, kb_id, chunk_index, content, page_num,
                   parent_chunk_id, page_start, page_end, section_path,
                   content_sha256, 1 - (embedding <=> CAST(:query_vector AS vector)) AS route_score,
                   content_type, quality_status, metadata_json, tenant_id, document_version,
                   source_type, authority_level, publication_date, section_title, title
            FROM document_chunk
            WHERE kb_id IN ({placeholders}) AND chunk_type = 'child'
              AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
              AND embedding IS NOT NULL AND embedding_model = :embedding_model
              AND embedding_dimensions = :embedding_dimensions
            ORDER BY embedding::vector({len(vector)}) <=> CAST(:query_vector AS vector({len(vector)})) LIMIT :limit
        """)
        params = {**scope_params, "tenant_id": tenant_id, "query_vector": vector_text, "embedding_model": settings.EMBEDDING_MODEL, "embedding_dimensions": len(vector), "limit": limit}
        return self._rows(statement, params, "dense_score")

    def _lexical_search(self, query: str, kb_ids: list[int], limit: int, tenant_id: int | None = None) -> list[dict]:
        placeholders, scope_params = self._scope_clause(kb_ids)
        statement = text(f"""
            SELECT id, document_id, kb_id, chunk_index, content, page_num,
                   parent_chunk_id, page_start, page_end, section_path, content_sha256,
                   ts_rank_cd(COALESCE(search_vector, to_tsvector('simple', content)),
                              websearch_to_tsquery('simple', :query))
                   + CASE WHEN content ILIKE :contains THEN 0.5 ELSE 0 END AS route_score,
                   content_type, quality_status, metadata_json, tenant_id, document_version,
                   source_type, authority_level, publication_date, section_title, title
            FROM document_chunk
            WHERE kb_id IN ({placeholders}) AND chunk_type = 'child'
              AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
              AND (COALESCE(search_vector, to_tsvector('simple', content)) @@ websearch_to_tsquery('simple', :query)
                   OR content ILIKE :contains)
            ORDER BY route_score DESC, id ASC LIMIT :limit
        """)
        return self._rows(statement, {**scope_params, "tenant_id": tenant_id, "query": query, "contains": f"%{query}%", "limit": limit}, "sparse_score")

    def _exact_search(self, terms: list[str], kb_ids: list[int], limit: int, tenant_id: int | None = None) -> list[dict]:
        placeholders, scope_params = self._scope_clause(kb_ids)
        term_params = {f"term_{index}": f"%{term}%" for index, term in enumerate(terms)}
        term_params.update({f"raw_term_{index}": term for index, term in enumerate(terms)})
        clauses = []
        for index in range(len(terms)):
            placeholder = f":term_{index}"
            raw = f":raw_term_{index}"
            clauses.append(
                f"(content ILIKE {placeholder} "
                f"OR COALESCE(medical_entities, '[]'::jsonb) @> jsonb_build_array({raw}) "
                f"OR COALESCE(keywords, '[]'::jsonb) @> jsonb_build_array({raw}) "
                f"OR COALESCE(medical_codes, '[]'::jsonb) @> jsonb_build_array({raw}) "
                f"OR COALESCE(medical_entities, '[]'::jsonb)::text ILIKE {placeholder} "
                f"OR COALESCE(keywords, '[]'::jsonb)::text ILIKE {placeholder} "
                f"OR COALESCE(medical_codes, '[]'::jsonb)::text ILIKE {placeholder})"
            )
        score = " + ".join(f"CASE WHEN content ILIKE :term_{index} THEN 1 ELSE 0 END" for index in range(len(terms)))
        statement = text(f"""
            SELECT id, document_id, kb_id, chunk_index, content, page_num,
                   parent_chunk_id, page_start, page_end, section_path, content_sha256,
                   (({score})::float / :term_count) AS route_score,
                   content_type, quality_status, metadata_json, tenant_id, document_version,
                   source_type, authority_level, publication_date, section_title, title
            FROM document_chunk
            WHERE kb_id IN ({placeholders}) AND chunk_type='child'
              AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
              AND ({' OR '.join(clauses)})
            ORDER BY route_score DESC, id ASC LIMIT :limit
        """)
        return self._rows(statement, {**scope_params, **term_params, "tenant_id": tenant_id, "term_count": len(terms), "limit": limit}, "exact_score")

    @staticmethod
    def _rows(statement, params: dict, score_name: str) -> list[dict]:
        db = PgSessionLocal()
        try:
            rows = db.execute(statement, params).fetchall()
            return [{
                "id": row[0], "document_id": row[1], "kb_id": row[2], "chunk_index": row[3],
                "content": row[4], "page_num": row[5], "parent_chunk_id": row[6],
                "page_start": row[7], "page_end": row[8], "section_path": row[9] or [],
                "content_sha256": row[10], score_name: float(row[11]), "similarity": float(row[11]),
                "content_type": row[12], "quality_status": row[13], "metadata": row[14] or {},
                "tenant_id": row[15], "document_version": row[16],
                "source_type": row[17], "authority_level": row[18],
                "publication_date": row[19].isoformat() if row[19] else None,
                "section_title": row[20], "title": row[21],
            } for row in rows]
        finally:
            db.close()

    @staticmethod
    def _fetch_parents(parent_ids: list[int]) -> dict[int, dict]:
        placeholders = ", ".join(f":id_{index}" for index in range(len(parent_ids)))
        params = {f"id_{index}": value for index, value in enumerate(parent_ids)}
        db = PgSessionLocal()
        try:
            rows = db.execute(text(f"SELECT id, content, page_start, page_end, section_path, content_type FROM document_chunk WHERE chunk_type='parent' AND id IN ({placeholders})"), params).fetchall()
            return {int(row[0]): {"content": str(row[1]), "page_start": row[2], "page_end": row[3], "section_path": row[4] or [], "content_type": row[5]} for row in rows}
        finally:
            db.close()

    @staticmethod
    def _fetch_neighbors(items: list[dict], kb_ids: list[int], tenant_id: int | None) -> dict[int, list[dict]]:
        db = PgSessionLocal()
        try:
            result: dict[int, list[dict]] = {}
            for item in items:
                rows = db.execute(text("""
                    SELECT id, content, chunk_index FROM document_chunk
                    WHERE document_id=:document_id AND kb_id=:kb_id AND chunk_type='child'
                      AND (:tenant_id IS NULL OR tenant_id=:tenant_id)
                      AND chunk_index BETWEEN :low AND :high AND id<>:id
                    ORDER BY chunk_index
                """), {"document_id": item["document_id"], "kb_id": item["kb_id"], "tenant_id": tenant_id, "low": int(item["chunk_index"]) - 1, "high": int(item["chunk_index"]) + 1, "id": item["id"]}).fetchall()
                result[int(item["id"])] = [{"id": int(row[0]), "content": str(row[1]), "chunk_index": int(row[2])} for row in rows]
            return result
        finally:
            db.close()

    @staticmethod
    def _record_trace(result: RetrievalResult, query: str, request_id: str | None, tenant_id: int | None, user_id: int | None, terms: list[str]) -> None:
        if not settings.RETRIEVAL_TRACE_ENABLED or not request_id or tenant_id is None or user_id is None:
            return
        try:
            from app.services.retrieval_observability_service import retrieval_observability_service
            retrieval_observability_service.record(
                request_id=request_id, tenant_id=tenant_id, user_id=user_id,
                original_query=query, standalone_query=query, routes=list(result.rankings),
                entities=terms, constraints=[], rankings=result.rankings,
                filtered=result.filtered, final_evidence=result.evidence,
                timings=result.timings_ms, status=result.status.value,
                error=asdict(result.issues[0]) if result.issues else None,
            )
        except Exception:
            logger.exception("Failed to persist retrieval trace")


hybrid_retriever = HybridRetriever()
