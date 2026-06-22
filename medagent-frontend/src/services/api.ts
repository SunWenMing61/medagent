// 引入 axios 库及其类型定义：AxiosInstance（axios 实例类型）、InternalAxiosRequestConfig（请求配置类型）、AxiosResponse（响应类型）
import axios, { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios';

// API 基础 URL：优先使用环境变量 REACT_APP_API_BASE_URL，未设置则默认回退到本地开发服务器 http://localhost:8000/api
const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api';

// 创建 axios 单例实例，统一配置 baseURL、超时时间和默认请求头
const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,       // 所有请求的基准路径
  timeout: 60000,              // 请求超时时间：60 秒
  headers: {
    'Content-Type': 'application/json',  // 默认请求体格式为 JSON
  },
});

// ===== 请求拦截器：在每个请求发出前，自动附加 JWT 令牌到 Authorization 请求头 =====
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 从 localStorage 获取 JWT 访问令牌
    const token = localStorage.getItem('access_token');
    // 如果令牌存在且请求头对象可用，则添加 Bearer 认证头
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;  // 返回修改后的配置继续发送请求
  },
  (error) => {
    // 请求配置出错时直接拒绝 Promise，交由调用方处理
    return Promise.reject(error);
  }
);

// ===== 响应拦截器：统一处理后端返回的 401 未授权错误 =====
api.interceptors.response.use(
  (response: AxiosResponse) => response,  // 正常响应直接返回
  (error) => {
    // 检查 HTTP 状态码是否为 401（未授权/令牌过期）
    if (error.response?.status === 401) {
      // 清除本地存储中的所有认证信息
      localStorage.removeItem('access_token');
      localStorage.removeItem('user_role');
      localStorage.removeItem('user_id');
      localStorage.removeItem('username');
      // 强制跳转到登录页，重新登录
      window.location.href = '/login';
    }
    return Promise.reject(error);  // 继续向上抛出错误，供调用方 catch 处理
  }
);

// ==================== 认证相关 API ====================

// 注册请求参数接口：包含用户名、密码、邮箱
export interface RegisterParams {
  username: string;
  password: string;
  email: string;
}

// 登录请求参数接口：包含用户名和密码
export interface LoginParams {
  username: string;
  password: string;
}

// 登录成功后的响应接口：包含访问令牌、令牌类型、用户 ID、用户名、角色
export interface LoginResponse {
  access_token: string;   // JWT 访问令牌
  token_type: string;     // 令牌类型（通常是 "bearer"）
  user_id: number;        // 用户 ID
  username: string;       // 用户名
  role: string;           // 用户角色（user / admin）
}

// 用户信息接口：包含 ID、用户名、邮箱、角色、状态
export interface UserInfo {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
}

// 发送注册请求，POST /auth/register，返回包含消息的响应体
export const register = async (params: RegisterParams): Promise<{ message: string }> => {
  const response = await api.post('/auth/register', params);
  return response.data;
};

// 发送登录请求，POST /auth/login，返回包含令牌和用户信息的响应体
export const login = async (params: LoginParams): Promise<LoginResponse> => {
  const response = await api.post('/auth/login', params);
  return response.data;
};

// 获取当前登录用户的信息，GET /auth/me，需要 JWT 令牌认证
export const getCurrentUser = async (): Promise<UserInfo> => {
  const response = await api.get('/auth/me');
  return response.data;
};

// ==================== 用户资料相关 API ====================

// 更新当前用户的个人资料，PUT /users/me，传入部分 UserInfo 字段
export const updateMyProfile = async (data: Partial<UserInfo>): Promise<UserInfo> => {
  const response = await api.put('/users/me', data);
  return response.data;
};

// 获取当前用户的个人资料，GET /users/me
export const getMyProfile = async (): Promise<UserInfo> => {
  const response = await api.get('/users/me');
  return response.data;
};

// ==================== 知识库相关 API ====================

// 知识库信息接口：包含 ID、名称、描述、类型、可见性、文档数、时间戳、所有者 ID
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

// 创建知识库请求参数接口
export interface CreateKBParams {
  name: string;
  description: string;
  type: string;
  visibility: string;
}

// 创建知识库，POST /kb，传入名称、描述、类型、可见性
export const createKnowledgeBase = async (params: CreateKBParams): Promise<KnowledgeBase> => {
  const response = await api.post('/kb', params);
  return response.data;
};

// 获取所有知识库列表，GET /kb，返回数组
export const getKnowledgeBases = async (): Promise<KnowledgeBase[]> => {
  const response = await api.get('/kb');
  return response.data;
};

// 根据 ID 删除知识库，DELETE /kb/{id}，无返回值
export const deleteKnowledgeBase = async (id: number): Promise<void> => {
  await api.delete(`/kb/${id}`);
};

// ==================== 文档相关 API ====================

// 文档信息接口：包含 ID、文件名、所属知识库 ID、状态、文件类型、大小、内容类型、来源信息、解析状态、向量化状态、上传者 ID、时间戳、错误信息
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

// 上传文档到指定知识库，POST /documents/upload，使用 multipart/form-data 格式
export const uploadDocument = async (kbId: number, file: File): Promise<Document> => {
  const formData = new FormData();
  formData.append('kb_id', String(kbId));  // 知识库 ID 转为字符串追加到表单
  formData.append('file', file);            // 上传的文件

  // 发送 POST 请求，指定 Content-Type 为 multipart/form-data，超时时间延长为 120 秒（大文件上传）
  const response = await api.post('/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  });
  return response.data;
};

// 获取文档列表，可选按知识库 ID 过滤，GET /documents?kb_id={kbId}
export const getDocuments = async (kbId?: number): Promise<Document[]> => {
  const params = kbId ? { kb_id: kbId } : {};  // 如果提供了 kbId 则作为查询参数
  const response = await api.get('/documents', { params });
  return response.data;
};

// 根据 ID 删除文档，DELETE /documents/{id}
export const deleteDocument = async (id: number): Promise<void> => {
  await api.delete(`/documents/${id}`);
};

// ==================== 聊天相关 API ====================

// 聊天请求参数接口：包含问题文本、关联的知识库 ID 列表、可选的会话 ID
export interface ChatRequest {
  question: string;
  kb_ids: number[];
  session_id?: string;
}

// 聊天响应接口：包含回答文本、参考文献列表、安全标记、免责声明、思考过程
export interface ChatResponse {
  answer: string;
  references?: any[];
  safety_flag?: boolean;
  disclaimer?: string;
  thinking?: string;
}

// 会话概要信息接口：包含 ID、标题、会话类型、时间戳、消息数、关联知识库 ID 列表
export interface Session {
  id: string;
  title?: string;
  session_type?: string;
  created_at?: string;
  updated_at?: string;
  message_count?: number;
  kb_ids?: number[];
}

// 会话详情接口：包含会话信息和消息列表
export interface SessionDetail {
  session: Session;
  messages: Message[];
}

// 单条消息接口：包含 ID、会话 ID、角色（user/assistant）、内容、参考文献、安全标记、免责声明、反馈类型、时间戳、思考过程
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

// 发送问答请求（非流式），POST /chat/ask
export const askQuestion = async (params: ChatRequest): Promise<ChatResponse> => {
  const response = await api.post('/chat/ask', params);
  return response.data;
};

// 发送健康咨询请求（非流式），POST /chat/health
export const healthConsult = async (params: ChatRequest): Promise<ChatResponse> => {
  const response = await api.post('/chat/health', params);
  return response.data;
};

// 发送带文件附件的多部分问答请求（支持图片/PDF/DOCX 等），POST /chat/ask-multipart
// 参数：问题文本、知识库 ID 列表、文件数组、可选会话 ID、联网搜索开关、深度思考开关
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
  formData.append('kb_ids', JSON.stringify(kb_ids));  // 知识库 ID 列表序列化为 JSON 字符串
  if (session_id !== undefined) formData.append('session_id', String(session_id));
  files.forEach((f) => formData.append('files', f));  // 每个文件作为一个表单字段
  const response = await api.post('/chat/ask-multipart', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,  // 文件上传超时时间 120 秒
  });
  return response.data;
};

// 获取会话列表，可选按类型过滤，GET /chat/sessions?type={type}
export const getSessions = async (type?: string): Promise<Session[]> => {
  const response = await api.get('/chat/sessions', { params: { type } });
  return response.data;
};

// 获取指定会话的详细信息（含消息列表），GET /chat/sessions/{id}
export const getSessionDetail = async (id: string): Promise<SessionDetail> => {
  const response = await api.get(`/chat/sessions/${id}`);
  return response.data;
};

// 删除指定会话，DELETE /chat/sessions/{id}
export const deleteSession = async (id: string): Promise<void> => {
  await api.delete(`/chat/sessions/${id}`);
};

// ==================== 反馈相关 API ====================

// 反馈提交参数接口：消息 ID、反馈类型（like/dislike）、可选的评论文字
export interface FeedbackParams {
  message_id: number;
  feedback_type: string;
  comment?: string;
}

// 提交用户反馈（点赞/点踩），POST /feedback
export const submitFeedback = async (params: FeedbackParams): Promise<any> => {
  const response = await api.post('/feedback', params);
  return response.data;
};

// ==================== 管理员相关 API ====================

// 管理员统计数据接口：包含用户数、知识库数、文档数、会话数、消息数、今日活跃用户数等
export interface AdminStats {
  total_users?: number;
  total_kbs?: number;
  total_documents?: number;
  total_sessions?: number;
  total_messages?: number;
  active_users_today?: number;
  [key: string]: any;  // 允许扩展其他统计字段
}

// 管理员视角下的用户信息接口
export interface AdminUser {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
  created_at?: string;
  last_login?: string;
}

// 管理员视角下的反馈信息接口
export interface AdminFeedback {
  id: number;
  message_id: number;
  feedback_type: string;
  comment?: string;
  user_id?: number;
  username?: string;
  created_at?: string;
}

// 系统日志条目接口
export interface LogEntry {
  id: number;
  level: string;
  message: string;
  user_id?: number;
  username?: string;
  created_at?: string;
  [key: string]: any;
}

// 模型配置接口：包含模型名称、API 密钥、API 基础地址、温度参数、最大 Token 数等
export interface ModelConfig {
  model_name?: string;
  api_key?: string;
  api_base?: string;
  temperature?: number;
  max_tokens?: number;
  [key: string]: any;
}

// 获取所有用户列表（管理员），GET /admin/users
export const getAdminUsers = async (): Promise<AdminUser[]> => {
  const response = await api.get('/admin/users');
  return response.data;
};

// 更新指定用户的状态（启用/禁用），PUT /admin/users/{userId}/status
export const updateUserStatus = async (userId: number, status: string): Promise<any> => {
  const response = await api.put(`/admin/users/${userId}/status`, { status });
  return response.data;
};

// 获取所有用户反馈列表（管理员），GET /admin/feedback
export const getAdminFeedback = async (): Promise<AdminFeedback[]> => {
  const response = await api.get('/admin/feedback');
  return response.data;
};

// 获取系统日志列表（管理员），GET /admin/logs
export const getAdminLogs = async (): Promise<LogEntry[]> => {
  const response = await api.get('/admin/logs');
  return response.data;
};

// 获取系统统计数据（管理员），GET /admin/stats
export const getAdminStats = async (): Promise<AdminStats> => {
  const response = await api.get('/admin/stats');
  return response.data;
};

// 获取当前模型配置（管理员），GET /admin/config/model
export const getModelConfig = async (): Promise<ModelConfig> => {
  const response = await api.get('/admin/config/model');
  return response.data;
};

// 更新模型配置（管理员），PUT /admin/config/model
export const updateModelConfig = async (config: ModelConfig): Promise<ModelConfig> => {
  const response = await api.put('/admin/config/model', config);
  return response.data;
};

// ==================== 知识来源（在线爬取）相关 API ====================

// 知识来源信息接口：包含 ID、所属知识库 ID、来源类型（如网页爬虫）、名称、配置、同步状态、文档数等
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

// 创建知识来源的请求参数接口
export interface CreateSourceParams {
  kb_id: number;
  source_type: string;
  name: string;
  config: Record<string, any>;
}

// 更新知识来源的请求参数接口（部分更新）
export interface UpdateSourceParams {
  name?: string;
  config?: Record<string, any>;
  kb_id?: number;
}

// 知识来源类型的模式信息接口：描述每种来源类型的字段配置结构
export interface SourceSchemaInfo {
  source_type: string;
  display_name: string;
  config_schema: Record<string, any>;
  defaults: Record<string, any>;
}

// 知识来源的状态信息接口
export interface SourceStatus {
  id: number;
  sync_status: string;
  last_sync_at?: string;
  error_message?: string;
}

// 获取所有可用的知识来源类型及其配置模式，GET /sources/schemas
export const getSourceSchemas = async (): Promise<Record<string, SourceSchemaInfo>> => {
  const response = await api.get('/sources/schemas');
  return response.data;
};

// 创建新的知识来源，POST /sources
export const createSource = async (params: CreateSourceParams): Promise<KnowledgeSource> => {
  const response = await api.post('/sources', params);
  return response.data;
};

// 获取知识来源列表，可选按知识库 ID 过滤，GET /sources?kb_id={kbId}
export const getSources = async (kbId?: number): Promise<KnowledgeSource[]> => {
  const params = kbId ? { kb_id: kbId } : {};
  const response = await api.get('/sources', { params });
  return response.data;
};

// 获取单个知识来源的详细信息，GET /sources/{id}
export const getSource = async (id: number): Promise<KnowledgeSource> => {
  const response = await api.get(`/sources/${id}`);
  return response.data;
};

// 更新指定知识来源的配置，PUT /sources/{id}
export const updateSource = async (id: number, params: UpdateSourceParams): Promise<KnowledgeSource> => {
  const response = await api.put(`/sources/${id}`, params);
  return response.data;
};

// 删除指定知识来源，DELETE /sources/{id}，返回删除结果信息及关联文档数
export const deleteSource = async (id: number): Promise<{ message: string; deleted_documents: number }> => {
  const response = await api.delete(`/sources/${id}`);
  return response.data;
};

// 触发指定知识来源的同步操作，POST /sources/{id}/sync，返回来源 ID 和同步状态
export const triggerSourceSync = async (id: number): Promise<{ source_id: number; sync_status: string }> => {
  const response = await api.post(`/sources/${id}/sync`);
  return response.data;
};

// 获取指定知识来源的同步状态，GET /sources/{id}/status
export const getSourceStatus = async (id: number): Promise<SourceStatus> => {
  const response = await api.get(`/sources/${id}/status`);
  return response.data;
};

// ==================== 文档预览相关 API ====================

// 文档预览数据接口：包含文件名、文件类型、文本内容、总长度
export interface DocumentPreviewData {
  filename: string;
  file_type: string;
  content: string;
  total_length: number;
}

// 获取文档的原始文件（以 blob 形式下载），然后通过 URL.createObjectURL 生成可预览的 URL
export const getDocumentFileBlobUrl = async (id: number): Promise<string> => {
  const response = await api.get(`/documents/${id}/file`, {
    responseType: 'blob',  // 指定响应类型为 blob（二进制大对象）
  });
  return URL.createObjectURL(response.data);  // 创建 blob URL 供浏览器预览
};

// 获取文档的文本预览内容（仅文本提取，而非原始文件），GET /documents/{id}/preview
export const getDocumentPreview = async (id: number): Promise<DocumentPreviewData> => {
  const response = await api.get(`/documents/${id}/preview`);
  return response.data;
};

// 导出 api 实例（命名导出），供其他模块使用
export { api };
// 默认导出 api 实例（默认导出），方便直接引用
export default api;
