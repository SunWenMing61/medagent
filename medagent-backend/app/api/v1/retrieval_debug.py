"""Scoped retrieval trace and aggregate metrics APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.memory import RetrievalTrace
from app.models.user import User
from app.evaluation.hybrid_retrieval_comparison import run_hybrid_retrieval_comparison


router = APIRouter()


@router.get("/evaluation/hybrid-comparison")
def hybrid_retrieval_comparison(
    current_user: User = Depends(get_current_user),
):
    """在固定无患者数据语料上比较 Dense 基线与当前强制混合检索。"""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return run_hybrid_retrieval_comparison()


def _tenant(user: User) -> int:
    return int(getattr(user, "tenant_id", 1) or 1)


def _serialize(row: RetrievalTrace) -> dict:
    return {
        "request_id": row.request_id,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "original_query_hash": row.original_query_hash,
        "standalone_query": row.standalone_query,
        "routes": row.routes_json,
        "entities": row.entities_json,
        "constraints": row.constraints_json,
        "rankings": row.rankings_json,
        "filtered": row.filtered_json,
        "final_evidence": row.final_evidence_json,
        "timings_ms": row.timings_json,
        "status": row.status,
        "error": row.error_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/debug/{request_id}")
def get_retrieval_trace(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    query = db.query(RetrievalTrace).filter(
        RetrievalTrace.request_id == request_id,
        RetrievalTrace.tenant_id == _tenant(current_user),
    )
    if current_user.role != "admin":
        query = query.filter(RetrievalTrace.user_id == current_user.id)
    row = query.first()
    if not row:
        raise HTTPException(status_code=404, detail="Retrieval trace not found")
    return _serialize(row)


@router.get("/metrics")
def retrieval_metrics(
    limit: int = Query(default=1000, ge=1, le=10000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    query = db.query(RetrievalTrace).filter(RetrievalTrace.tenant_id == _tenant(current_user))
    if current_user.role != "admin":
        query = query.filter(RetrievalTrace.user_id == current_user.id)
    rows = query.order_by(RetrievalTrace.created_at.desc()).limit(limit).all()
    status_counts: dict[str, int] = {}
    latencies: list[float] = []
    evidence_counts: list[int] = []
    for row in rows:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        total = (row.timings_json or {}).get("total_ms")
        if total is not None:
            latencies.append(float(total))
        evidence_counts.append(len(row.final_evidence_json or []))
    latencies.sort()
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0
    return {
        "sample_size": len(rows),
        "status_counts": status_counts,
        "p95_latency_ms": p95,
        "average_evidence_count": sum(evidence_counts) / len(evidence_counts) if evidence_counts else 0.0,
    }
