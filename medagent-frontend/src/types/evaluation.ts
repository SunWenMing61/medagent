export type RunStatus = 'queued' | 'running' | 'completed' | 'failed';
export type GateStatus = 'pending' | 'pass' | 'fail';

export interface EvaluationDataset { id: string; name: string; version: string; description?: string; case_count: number }
export interface DatasetVersion { id:string; version:string; case_count:number; change_summary?:string; created_by?:number; created_at:string }
export interface DatasetHealth { dataset_id:string; version:string; case_count:number; health_score:number; health_score_definition?:string; coverage:number; category_distribution:Record<string,number>; difficulty_distribution:Record<string,number>; duplicate_pairs:number; duplicate_rate:number; drift_js:number|null; discriminative_power:number|null; discriminative_power_status?:string; authoritative_ground_truth_rate:number|null; ground_truth_status?:string }
export interface EvaluationCandidate { id:string; query_text:string; source_request_id?:string; cluster_key?:string; category:string; difficulty:string; status:'pending'|'approved'|'rejected'|'added'; score:number; score_breakdown:Record<string,number>; runtime_metadata:Record<string,unknown>; review_comment?:string; reviewed_by?:number; reviewed_at?:string; target_dataset_id?:string; target_case_id?:number; created_at:string }
export interface HybridModeCost { mode:string; task_completion:number; answer_quality:number; avg_tokens:number; avg_llm_calls:number; avg_tool_calls:number; avg_cost:number; avg_latency_ms:number }
export interface HybridRuntimeMetrics { direct_rate:number; react_rate:number; multi_agent_rate:number; escalation_rate:number; routing_accuracy:number; execution_mode_accuracy:number; under_routing_rate:number; over_routing_rate:number; unnecessary_multi_agent_rate:number; token_savings?:number; cost_savings?:number; latency_savings?:number; quality_vs_cost:HybridModeCost[] }
export interface LiveRetrievalBenchmark { schema_version:string; evaluated_at:string; dataset:string; dataset_version?:string; metric_definition_version?:string; verification_status?:string; status:'healthy'|'degraded'|'missing'; sample_size:number; successful_queries:number; degraded_queries:number; k:number; metrics:{ hit_rate_at_5:number; precision_at_5:number; recall_at_5:number; mrr:number; ndcg_at_5:number; map_at_5?:number }; comparison?:{label:string;before:{metrics:Record<string,number>};after:{metrics:Record<string,number>};delta:Record<string,number>}; routes:Record<string,{available:boolean;reason_code?:string}>; limitations?:string[] }
export interface ReleaseGateResult { status: GateStatus; passed?: boolean; reasons: string[]; config?: Record<string, number>; critical_safety_failure?: boolean }
export interface EvaluationRun {
  id: string; name: string; dataset_id: string; dataset_name?: string; status: RunStatus; mode: 'FAST' | 'FULL' | 'CUSTOM';
  architecture?: 'HYBRID'|'SIMPLE_RAG'|'ALL_MULTI_AGENT'; is_baseline?: boolean;
  agent_version: string; model_name: string; model_version?: string; prompt_version?: string; embedding_model?: string; git_commit?: string;
  started_at?: string; finished_at?: string; created_at: string; duration_ms?: number; total_cases: number; completed_cases: number;
  passed_cases: number; failed_cases: number; critical_failures: number; overall_score?: number; pass_rate: number;
  release_gate_status: GateStatus; release_gate: ReleaseGateResult; error?: string; metrics?: EvaluationMetricMap;
}
export type EvaluationMetricMap = Record<string, number>;
export interface EvaluationCaseResult {
  id: number; run_id: string; case_id: string; case_key: string; name: string; category: string; difficulty: string; tags: string[];
  is_critical: boolean; input: string; expected: EvaluationExpected; thresholds: Record<string, number>; trace_id?: string; status: 'pass' | 'fail' | 'critical';
  passed: boolean; critical: boolean; overall_score: number; scores: EvaluationMetricMap; actual_output?: string; failure_reason?: string;
  judge_reason?: string; details: Record<string, Record<string, unknown>>; latency_ms: number; input_tokens: number; output_tokens: number; estimated_cost: number;
}
export interface EvaluationExpected { facts?: string[]; documents?: string[]; agents?: string[]; tools?: string[]; tool_args?: Record<string, unknown>; trajectory?: string[]; required_content?: string[]; forbidden_content?: string[]; execution_mode?: string|string[]; complexity?: string }
export interface AgentStep { step_number: number; agent_name: string; action: string; input?: unknown; output?: unknown; latency_ms: number; status: string }
export interface EvaluationToolCall { tool_name: string; arguments: Record<string, unknown>; result?: unknown; success: boolean; error?: string; latency_ms: number }
export interface EvaluationRetrieval { query: string; document_id: string; chunk_id: string; rank: number; similarity_score: number; content: string }
export interface EvaluationTrace { id: string; run_id: string; request_id: string; agent_version?: string; model_name?: string; prompt_version?: string; input_text: string; final_output?: string; agent_steps: AgentStep[]; routing_history: string[]; retrievals: EvaluationRetrieval[]; tool_calls: EvaluationToolCall[]; llm_calls: Array<Record<string, unknown>>; input_tokens: number; output_tokens: number; total_tokens: number; estimated_cost: number; latency_ms: number; status: string; error?: string; metadata: Record<string, unknown>; started_at: string; ended_at: string }
export interface EvaluationBaseline { run:EvaluationRun; metrics:EvaluationMetricMap; definition:string; comparison:EvaluationMetricMap }
export interface DashboardData { latest_run: EvaluationRun | null; metrics: EvaluationMetricMap; deltas: EvaluationMetricMap; baseline:EvaluationBaseline|null; trends: Array<{ run_id: string; name: string; date: string; overall_score: number } & EvaluationMetricMap>; recent_runs: EvaluationRun[]; release_gate: ReleaseGateResult | null; hybrid_runtime:HybridRuntimeMetrics; dataset_health:DatasetHealth; pending_candidates:number; live_retrieval:LiveRetrievalBenchmark }
export interface EvaluationComparison { baseline: EvaluationRun; candidate: EvaluationRun; metrics: Array<{ metric: string; baseline: number; candidate: number; delta: number }>; comparison: { summary: Record<string, number>; cases: Array<{ case_key: string; category: string; baseline_score: number; candidate_score: number; delta: number; classification: string; critical: boolean; reason?: string }> }; release_gate: ReleaseGateResult }
export interface PageResult<T> { items: T[]; page: number; page_size: number; total: number }
