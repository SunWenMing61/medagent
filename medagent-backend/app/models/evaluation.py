"""Persistent evaluation datasets, executions, metrics and privacy-safe traces."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func

from app.db.base import MySQLBase

EVAL_PK = BigInteger().with_variant(Integer, "sqlite")


class EvalDataset(MySQLBase):
    __tablename__ = "eval_dataset"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    version = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String(32), nullable=False, default="database")
    case_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class EvalCase(MySQLBase):
    __tablename__ = "eval_case"
    __table_args__ = (UniqueConstraint("dataset_id", "case_key", name="uq_eval_case_dataset_key"),)

    id = Column(EVAL_PK, primary_key=True, autoincrement=True)
    dataset_id = Column(String(64), ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False, index=True)
    case_key = Column(String(128), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(64), nullable=False, index=True)
    difficulty = Column(String(16), nullable=False, default="medium")
    tags = Column(JSON, nullable=False)
    is_critical = Column(Boolean, nullable=False, default=False, index=True)
    input_text = Column(Text, nullable=False)
    expected_json = Column(JSON, nullable=False)
    thresholds_json = Column(JSON, nullable=False)
    source_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class EvalRun(MySQLBase):
    __tablename__ = "eval_run"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    dataset_id = Column(String(64), ForeignKey("eval_dataset.id"), nullable=False, index=True)
    status = Column(String(24), nullable=False, default="queued", index=True)
    mode = Column(String(16), nullable=False)
    agent_version = Column(String(64), nullable=False)
    model_name = Column(String(128), nullable=False)
    model_version = Column(String(64), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_version = Column(String(64), nullable=True)
    git_commit = Column(String(64), nullable=True)
    retrieval_config = Column(JSON, nullable=False)
    judge_model = Column(String(128), nullable=True)
    judge_prompt_version = Column(String(64), nullable=True)
    random_seed = Column(Integer, nullable=False, default=0)
    config_json = Column(JSON, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    total_cases = Column(Integer, nullable=False, default=0)
    completed_cases = Column(Integer, nullable=False, default=0)
    passed_cases = Column(Integer, nullable=False, default=0)
    failed_cases = Column(Integer, nullable=False, default=0)
    critical_failures = Column(Integer, nullable=False, default=0)
    overall_score = Column(Float, nullable=True)
    release_gate_status = Column(String(16), nullable=False, default="pending")
    release_gate_json = Column(JSON, nullable=False)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class EvalCaseResult(MySQLBase):
    __tablename__ = "eval_case_result"
    __table_args__ = (UniqueConstraint("run_id", "case_id", name="uq_eval_case_result_run_case"),)

    id = Column(EVAL_PK, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False, index=True)
    case_id = Column(BigInteger, ForeignKey("eval_case.id"), nullable=False, index=True)
    case_key = Column(String(128), nullable=False, index=True)
    trace_id = Column(String(64), nullable=True, index=True)
    status = Column(String(24), nullable=False, index=True)
    passed = Column(Boolean, nullable=False)
    critical = Column(Boolean, nullable=False, default=False, index=True)
    overall_score = Column(Float, nullable=False)
    scores_json = Column(JSON, nullable=False)
    actual_output = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    judge_reason = Column(Text, nullable=True)
    details_json = Column(JSON, nullable=False)
    latency_ms = Column(Float, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class EvalMetricResult(MySQLBase):
    __tablename__ = "eval_metric_result"
    __table_args__ = (UniqueConstraint("run_id", "metric_name", name="uq_eval_metric_run_name"),)

    id = Column(EVAL_PK, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False, index=True)
    evaluator_name = Column(String(128), nullable=False)
    metric_name = Column(String(128), nullable=False, index=True)
    score = Column(Float, nullable=False)
    passed = Column(Boolean, nullable=False)
    details_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class EvaluationTrace(MySQLBase):
    __tablename__ = "agent_trace"

    id = Column(String(64), primary_key=True)
    run_id = Column(String(64), ForeignKey("eval_run.id", ondelete="CASCADE"), nullable=False, index=True)
    case_result_id = Column(BigInteger, ForeignKey("eval_case_result.id", ondelete="CASCADE"), nullable=True, index=True)
    request_id = Column(String(64), nullable=False, index=True)
    session_id = Column(String(64), nullable=True)
    user_id_hash = Column(String(64), nullable=True)
    agent_version = Column(String(64), nullable=True)
    model_name = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    input_text = Column(Text, nullable=False)
    final_output = Column(Text, nullable=True)
    agent_steps = Column(JSON, nullable=False)
    routing_history = Column(JSON, nullable=False)
    retrievals = Column(JSON, nullable=False)
    tool_calls = Column(JSON, nullable=False)
    llm_calls = Column(JSON, nullable=False)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    estimated_cost = Column(Float, nullable=False, default=0)
    latency_ms = Column(Float, nullable=False, default=0)
    status = Column(String(24), nullable=False)
    error = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=False)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class EvalDatasetVersion(MySQLBase):
    __tablename__ = "eval_dataset_version"
    __table_args__ = (UniqueConstraint("dataset_id", "version", name="uq_eval_dataset_version"),)

    id = Column(String(64), primary_key=True)
    dataset_id = Column(String(64), ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    case_count = Column(Integer, nullable=False, default=0)
    change_summary = Column(Text, nullable=True)
    snapshot_json = Column(JSON, nullable=False)
    created_by = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class EvaluationCandidate(MySQLBase):
    __tablename__ = "evaluation_candidate"

    id = Column(String(64), primary_key=True)
    normalized_hash = Column(String(64), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    source_request_id = Column(String(64), nullable=True, index=True)
    cluster_key = Column(String(64), nullable=True, index=True)
    category = Column(String(64), nullable=False, default="production_failure", index=True)
    difficulty = Column(String(16), nullable=False, default="medium")
    status = Column(String(24), nullable=False, default="pending", index=True)
    score = Column(Float, nullable=False, default=0, index=True)
    score_breakdown = Column(JSON, nullable=False)
    runtime_metadata = Column(JSON, nullable=False)
    review_comment = Column(Text, nullable=True)
    reviewed_by = Column(BigInteger, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    target_dataset_id = Column(String(64), ForeignKey("eval_dataset.id"), nullable=True)
    target_case_id = Column(BigInteger, ForeignKey("eval_case.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class DatasetChangeLog(MySQLBase):
    __tablename__ = "dataset_change_log"

    id = Column(EVAL_PK, primary_key=True, autoincrement=True)
    dataset_id = Column(String(64), ForeignKey("eval_dataset.id", ondelete="CASCADE"), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    action = Column(String(32), nullable=False)
    case_key = Column(String(128), nullable=True)
    candidate_id = Column(String(64), nullable=True)
    actor_id = Column(BigInteger, nullable=True)
    details_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
