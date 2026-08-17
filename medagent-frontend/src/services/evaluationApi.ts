import { api } from './api';
import type { DashboardData, DatasetHealth, DatasetVersion, EvaluationCandidate, EvaluationCaseResult, EvaluationComparison, EvaluationDataset, EvaluationMetricMap, EvaluationRun, EvaluationTrace, PageResult } from '../types/evaluation';

export interface CreateEvaluationRun { name?: string; dataset_id?: string; mode: 'FAST' | 'FULL' | 'CUSTOM'; architecture?:'HYBRID'|'SIMPLE_RAG'|'ALL_MULTI_AGENT'; agent_version: string; model?: string; categories?: string[]; tags?: string[]; max_cases?: number; concurrency: number; timeout?: number; seed?: number }
export interface CaseQuery { page?: number; page_size?: number; search?: string; category?: string; result?: string; difficulty?: string; critical?: boolean; sort?: string }

export const evaluationApi = {
  getDashboard: (): Promise<DashboardData> => api.get('/evaluation/dashboard').then(r => r.data),
  getDatasets: (): Promise<EvaluationDataset[]> => api.get('/evaluation/datasets').then(r => r.data),
  getDataset: (id:string): Promise<EvaluationDataset & {cases:Array<Record<string,unknown>>}> => api.get(`/evaluation/datasets/${id}`).then(r=>r.data),
  getDatasetVersions: (id:string): Promise<DatasetVersion[]> => api.get(`/evaluation/datasets/${id}/versions`).then(r=>r.data),
  getDatasetHealth: (id:string): Promise<DatasetHealth> => api.get(`/evaluation/datasets/${id}/health`).then(r=>r.data),
  getCandidates: (page=1,status?:string):Promise<PageResult<EvaluationCandidate>> => api.get('/evaluation/candidates',{params:{page,page_size:25,status}}).then(r=>r.data),
  approveCandidate: (id:string,comment?:string):Promise<EvaluationCandidate> => api.post(`/evaluation/candidates/${id}/approve`,{comment}).then(r=>r.data),
  rejectCandidate: (id:string,comment?:string):Promise<EvaluationCandidate> => api.post(`/evaluation/candidates/${id}/reject`,{comment}).then(r=>r.data),
  addCandidateToDataset: (id:string,data:{dataset_id:string;name:string;expected:Record<string,unknown>;verification_status:'reviewed'|'expert_verified';category:string;difficulty:'easy'|'medium'|'hard';tags:string[];is_critical:boolean}) => api.post(`/evaluation/candidates/${id}/add-to-dataset`,data).then(r=>r.data),
  createRun: (data: CreateEvaluationRun): Promise<EvaluationRun> => api.post('/evaluation/runs', data).then(r => r.data),
  getRuns: (page = 1, pageSize = 20): Promise<PageResult<EvaluationRun>> => api.get('/evaluation/runs', { params: { page, page_size: pageSize } }).then(r => r.data),
  getRun: (id: string): Promise<EvaluationRun> => api.get(`/evaluation/runs/${id}`).then(r => r.data),
  getRunMetrics: (id: string): Promise<EvaluationMetricMap> => api.get(`/evaluation/runs/${id}/metrics`).then(r => r.data),
  getCases: (runId: string, params: CaseQuery): Promise<PageResult<EvaluationCaseResult>> => api.get(`/evaluation/runs/${runId}/cases`, { params }).then(r => r.data),
  getCaseDetail: (id: number): Promise<EvaluationCaseResult> => api.get(`/evaluation/cases/${id}`).then(r => r.data),
  getTrace: (runId: string, traceId: string): Promise<EvaluationTrace> => api.get(`/evaluation/runs/${runId}/trace/${traceId}`).then(r => r.data),
  compareRuns: (baselineRunId: string, candidateRunId: string): Promise<EvaluationComparison> => api.get('/evaluation/compare', { params: { baseline_run_id: baselineRunId, candidate_run_id: candidateRunId } }).then(r => r.data),
  getTrends: (metric = 'overall_score'): Promise<Array<{ run_id: string; name: string; date: string; value: number }>> => api.get('/evaluation/trends', { params: { metric } }).then(r => r.data),
};
