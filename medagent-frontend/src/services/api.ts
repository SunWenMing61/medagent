import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api';

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach JWT token
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: handle 401
api.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_role');
      localStorage.removeItem('user_id');
      localStorage.removeItem('username');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ==================== Auth API ====================

export interface RegisterParams {
  username: string;
  password: string;
  email: string;
}

export interface LoginParams {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  username: string;
  role: string;
}

export interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
}

export const register = async (params: RegisterParams): Promise<{ message: string }> => {
  const response = await api.post('/auth/register', params);
  return response.data;
};

export const login = async (params: LoginParams): Promise<LoginResponse> => {
  const response = await api.post('/auth/login', params);
  return response.data;
};

export const getCurrentUser = async (): Promise<UserInfo> => {
  const response = await api.get('/auth/me');
  return response.data;
};

// ==================== User API ====================

export const updateMyProfile = async (data: Partial<UserInfo>): Promise<UserInfo> => {
  const response = await api.put('/users/me', data);
  return response.data;
};

export const getMyProfile = async (): Promise<UserInfo> => {
  const response = await api.get('/users/me');
  return response.data;
};

// ==================== Knowledge Base API ====================

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string;
  type: string;
  visibility: string;
  document_count?: number;
  created_at?: string;
  updated_at?: string;
  owner_id?: number;
}

export interface CreateKBParams {
  name: string;
  description: string;
  type: string;
  visibility: string;
}

export const createKnowledgeBase = async (params: CreateKBParams): Promise<KnowledgeBase> => {
  const response = await api.post('/kb', params);
  return response.data;
};

export const getKnowledgeBases = async (): Promise<KnowledgeBase[]> => {
  const response = await api.get('/kb');
  return response.data;
};

export const deleteKnowledgeBase = async (id: number): Promise<void> => {
  await api.delete(`/kb/${id}`);
};

// ==================== Document API ====================

export interface Document {
  id: number;
  filename: string;
  kb_id: number;
  status: string;
  file_type?: string;
  file_size?: number;
  content_type?: string;
  source_id?: number | null;
  source_url?: string | null;
  parse_status?: string;
  vector_status?: string;
  uploader_id?: number;
  created_at?: string;
  updated_at?: string;
  error_message?: string;
}

export const uploadDocument = async (kbId: number, file: File): Promise<Document> => {
  const formData = new FormData();
  formData.append('kb_id', String(kbId));
  formData.append('file', file);

  const response = await api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return response.data;
};

export const getDocuments = async (kbId?: number): Promise<Document[]> => {
  const params = kbId ? { kb_id: kbId } : {};
  const response = await api.get('/documents', { params });
  return response.data;
};

export const deleteDocument = async (id: number): Promise<void> => {
  await api.delete(`/documents/${id}`);
};

// ==================== Chat API ====================

export interface ChatRequest {
  question: string;
  kb_ids: number[];
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  references?: any[];
  safety_flag?: boolean;
  disclaimer?: string;
  thinking?: string;
}

export interface Session {
  id: string;
  title?: string;
  session_type?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  kb_ids?: number[];
}

export interface SessionDetail {
  session: Session;
  messages: Message[];
}

export interface Message {
  id: number;
  session_id: string;
  role: string;
  content: string;
  references?: any[];
  safety_flag?: boolean;
  disclaimer?: string;
  feedback_type?: string | null;
  created_at?: string;
  thinking?: string;
}

export const askQuestion = async (params: ChatRequest): Promise<ChatResponse> => {
  const response = await api.post('/chat/ask', params);
  return response.data;
};

export const healthConsult = async (params: ChatRequest): Promise<ChatResponse> => {
  const response = await api.post('/chat/health', params);
  return response.data;
};

export const askQuestionMultipart = async (
  question: string,
  kb_ids: number[],
  files: File[],
  session_id?: number,
  web_search_enabled?: boolean,
  deep_thinking_enabled?: boolean,
): Promise<ChatResponse> => {
  const formData = new FormData();
  formData.append('question', question);
  formData.append('web_search_enabled', web_search_enabled ? 'true' : 'false');
  formData.append('deep_thinking_enabled', deep_thinking_enabled ? 'true' : 'false');
  formData.append('kb_ids', JSON.stringify(kb_ids));
  if (session_id !== undefined) formData.append('session_id', String(session_id));
  files.forEach((f) => formData.append('files', f));
  const response = await api.post('/chat/ask-multipart', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return response.data;
};

export const getSessions = async (type?: string): Promise<Session[]> => {
  const response = await api.get('/chat/sessions', { params: { type } });
  return response.data;
};

export const getSessionDetail = async (id: string): Promise<SessionDetail> => {
  const response = await api.get(`/chat/sessions/${id}`);
  return response.data;
};

export const deleteSession = async (id: string): Promise<void> => {
  await api.delete(`/chat/sessions/${id}`);
};

// ==================== Feedback API ====================

export interface FeedbackParams {
  message_id: number;
  feedback_type: string;
  comment?: string;
}

export const submitFeedback = async (params: FeedbackParams): Promise<any> => {
  const response = await api.post('/feedback', params);
  return response.data;
};

// ==================== Admin API ====================

export interface AdminStats {
  total_users?: number;
  total_kbs?: number;
  total_documents?: number;
  total_sessions?: number;
  total_messages?: number;
  active_users_today?: number;
  [key: string]: any;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
  created_at?: string;
  last_login?: string;
}

export interface AdminFeedback {
  id: number;
  message_id: number;
  feedback_type: string;
  comment?: string;
  user_id?: number;
  username?: string;
  created_at?: string;
}

export interface LogEntry {
  id: number;
  level: string;
  message: string;
  user_id?: number;
  username?: string;
  created_at?: string;
  [key: string]: any;
}

export interface ModelConfig {
  model_name?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  [key: string]: any;
}

export const getAdminUsers = async (): Promise<AdminUser[]> => {
  const response = await api.get('/admin/users');
  return response.data;
};

export const updateUserStatus = async (userId: number, status: string): Promise<any> => {
  const response = await api.put(`/admin/users/${userId}/status`, { status });
  return response.data;
};

export const getAdminFeedback = async (): Promise<AdminFeedback[]> => {
  const response = await api.get('/admin/feedback');
  return response.data;
};

export const getAdminLogs = async (): Promise<LogEntry[]> => {
  const response = await api.get('/admin/logs');
  return response.data;
};

export const getAdminStats = async (): Promise<AdminStats> => {
  const response = await api.get('/admin/stats');
  return response.data;
};

export const getModelConfig = async (): Promise<ModelConfig> => {
  const response = await api.get('/admin/config/model');
  return response.data;
};

export const updateModelConfig = async (config: ModelConfig): Promise<ModelConfig> => {
  const response = await api.put('/admin/config/model', config);
  return response.data;
};

// ==================== Knowledge Source API ====================

export interface KnowledgeSource {
  id: number;
  kb_id: number;
  source_type: string;
  name: string;
  config: Record<string, any>;
  sync_status: string;
  document_count?: number;
  last_sync_at?: string;
  error_message?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CreateSourceParams {
  kb_id: number;
  source_type: string;
  name: string;
  config: Record<string, any>;
}

export interface UpdateSourceParams {
  name?: string;
  config?: Record<string, any>;
  kb_id?: number;
}

export interface SourceSchemaInfo {
  source_type: string;
  display_name: string;
  config_schema: Record<string, any>;
  defaults: Record<string, any>;
}

export interface SourceStatus {
  id: number;
  sync_status: string;
  last_sync_at?: string;
  error_message?: string;
}

export const getSourceSchemas = async (): Promise<Record<string, SourceSchemaInfo>> => {
  const response = await api.get('/sources/schemas');
  return response.data;
};

export const createSource = async (params: CreateSourceParams): Promise<KnowledgeSource> => {
  const response = await api.post('/sources', params);
  return response.data;
};

export const getSources = async (kbId?: number): Promise<KnowledgeSource[]> => {
  const params = kbId ? { kb_id: kbId } : {};
  const response = await api.get('/sources', { params });
  return response.data;
};

export const getSource = async (id: number): Promise<KnowledgeSource> => {
  const response = await api.get(`/sources/${id}`);
  return response.data;
};

export const updateSource = async (id: number, params: UpdateSourceParams): Promise<KnowledgeSource> => {
  const response = await api.put(`/sources/${id}`, params);
  return response.data;
};

export const deleteSource = async (id: number): Promise<{ message: string; deleted_documents: number }> => {
  const response = await api.delete(`/sources/${id}`);
  return response.data;
};

export const triggerSourceSync = async (id: number): Promise<{ source_id: number; sync_status: string }> => {
  const response = await api.post(`/sources/${id}/sync`);
  return response.data;
};

export const getSourceStatus = async (id: number): Promise<SourceStatus> => {
  const response = await api.get(`/sources/${id}/status`);
  return response.data;
};

// ==================== Document Preview API ====================

export interface DocumentPreviewData {
  filename: string;
  file_type: string;
  content: string;
  total_length: number;
}

export const getDocumentFileBlobUrl = async (id: number): Promise<string> => {
  const response = await api.get(`/documents/${id}/file`, {
    responseType: 'blob',
  });
  return URL.createObjectURL(response.data);
};

export const getDocumentPreview = async (id: number): Promise<DocumentPreviewData> => {
  const response = await api.get(`/documents/${id}/preview`);
  return response.data;
};

export { api };
export default api;
