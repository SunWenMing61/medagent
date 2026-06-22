// 引入 React 及其 Hooks：useState（状态管理）、useEffect（副作用处理）、useRef（DOM 引用）、useCallback（回调函数记忆化）
import React, { useState, useEffect, useRef, useCallback } from 'react';
// 引入 Ant Design 组件：Input（输入框）、Button（按钮）、Select（下拉选择）、Card（卡片）、Typography（排版）、Space（间距）、Spin（加载）、Empty（空状态）、Alert（警告/提示）、Tag（标签）、Divider（分割线）、Modal（弹窗）、List（列表）、message（全局提示）、Tooltip（工具提示）、theme（设计令牌）、Switch（开关）
import {
  Input, Button, Select, Card, Typography, Space, Spin, Empty, Alert,
  Tag, Divider, Modal, List, message as antMessage, Tooltip, theme,
  Switch,
} from 'antd';
// 引入 Ant Design 图标：Send（发送）、Robot（机器人）、User（用户）、Delete（删除）、History（历史）、Warning（警告）、Book（书籍）、Plus（添加）、Like/Dislike（点赞/点踩）、Link（链接）、PaperClip（附件）、CloseCircle（关闭）、File（文件）、Upload（上传）、Global（全球网络）、MenuFold/MenuUnfold（折叠/展开）、Message（消息）
import {
  SendOutlined, RobotOutlined, UserOutlined, DeleteOutlined,
  HistoryOutlined, WarningOutlined, BookOutlined, PlusOutlined,
  LikeOutlined, DislikeOutlined, LinkOutlined,
  PaperClipOutlined, CloseCircleOutlined, FileOutlined, UploadOutlined,
  GlobalOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined,
} from '@ant-design/icons';
// 引入 ReactMarkdown 将 AI 返回的 Markdown 文本渲染为 HTML
import ReactMarkdown from 'react-markdown';
// 引入 remark-gfm 插件，支持 GFM（GitHub Flavored Markdown）扩展语法（表格、任务列表等）
import remarkGfm from 'remark-gfm';
// 引入 rehype-raw 插件，允许在 Markdown 中使用原始 HTML 标签
import rehypeRaw from 'rehype-raw';
// 引入自定义主题上下文 Hook，用于获取当前主题模式和背景设置
import { useThemeContext } from '../contexts/ThemeContext';
// 引入 API 服务中的函数和类型：获取知识库列表、获取会话列表/详情、删除会话、提交反馈、多部分问答
import {
  getKnowledgeBases, getSessions, getSessionDetail, deleteSession, submitFeedback,
  askQuestionMultipart,
  type KnowledgeBase, type Session, type SessionDetail, type Message, type ChatResponse,
} from '../services/api';

// 从 Input 中解构出 TextArea（多行文本输入框）
const { TextArea } = Input;
// 从 Typography 中解构出 Text（文本）、Title（标题）、Paragraph（段落）
const { Text, Title, Paragraph } = Typography;

/**
 * ChatInterface 组件的 Props 接口定义
 * @property title - 对话界面标题（如"通用问答"或"健康咨询"）
 * @property subtitle - 可选的副标题，显示在标题下方
 * @property apiFunction - 问答 API 调用函数（非流式），根据不同类型的问答使用不同的后端端点
 * @property kbTypeFilter - 可选的知识库类型过滤条件（如只显示 medical 类型的知识库）
 * @property showSafetyWarning - 是否显示健康安全警告（仅健康咨询页面启用）
 * @property autoBindKB - 是否自动绑定所有知识库（无需用户手动选择）
 * @property hideKBSelector - 是否隐藏知识库选择器
 * @property streamEndpoint - 可选的流式端点路径，启用 SSE 流式输出
 * @property extraActions - 可选的额外操作按钮，渲染在顶部操作栏
 * @property initialSessionId - 可选的初始加载的会话 ID（从外部传入时加载指定历史会话）
 * @property initialShowHistory - 是否初始显示历史会话弹窗
 * @property autoLoadLastSession - 是否自动加载最近的会话
 * @property sessionType - 会话类型，用于区分通用问答和健康咨询的会话
 */
export interface ChatInterfaceProps {
  title: string;
  subtitle?: string;
  apiFunction: (params: { question: string; kb_ids: number[]; session_id?: string; web_search_enabled?: boolean; deep_thinking_enabled?: boolean }) => Promise<ChatResponse>;
  kbTypeFilter?: string;
  showSafetyWarning?: boolean;
  autoBindKB?: boolean;
  hideKBSelector?: boolean;
  streamEndpoint?: string;
  extraActions?: React.ReactNode;
  initialSessionId?: string;
  initialShowHistory?: boolean;
  autoLoadLastSession?: boolean;
  sessionType?: string;
}

/**
 * 聊天消息的本地数据结构（将后端 API 返回的 Message 转换为前端使用的格式）
 * @property id - 消息唯一标识（前端生成，格式如 "user-时间戳" 或 "assistant-时间戳"）
 * @property role - 消息角色：'user' 用户消息 / 'assistant' AI 回复
 * @property content - 消息文本内容（用户输入或 AI 的 Markdown 回答）
 * @property thinking - AI 的深度思考过程文本（可选，用于展示推理步骤）
 * @property references - 参考文献列表（可选，AI 回答中引用的知识库文档）
 * @property safety_flag - 安全标记（健康咨询中标记需添加医疗免责声明）
 * @property disclaimer - 自定义免责声明文本
 * @property messageId - 后端返回的消息 ID（用于提交反馈）
 * @property feedbackType - 用户反馈类型（'like' / 'dislike' / null）
 * @property timestamp - 消息发送时间戳
 */
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  references?: any[];
  safety_flag?: boolean;
  disclaimer?: string;
  messageId?: number;
  feedbackType?: string | null;
  timestamp: Date;
}

/**
 * ChatInterface 组件：智能问答对话界面的核心组件
 * 支持功能：
 * - 多轮对话（基于会话 ID 维持上下文）
 * - 流式输出（Server-Sent Events）
 * - 文件附件上传（图片/PDF/DOCX/TXT/MD）
 * - 联网搜索开关
 * - 深度思考开关（展示 AI 推理过程）
 * - 历史会话管理（侧边栏 + 弹窗）
 * - 消息反馈（点赞/点踩）
 * - 参考文献展示
 * - 拖拽上传文件
 * - 背景图片自适应
 */
const ChatInterface: React.FC<ChatInterfaceProps> = ({
  title, subtitle, apiFunction, kbTypeFilter,
  showSafetyWarning = false, autoBindKB = false, hideKBSelector = false,
  streamEndpoint, extraActions,
  initialSessionId, initialShowHistory, autoLoadLastSession = false,
  sessionType,
}) => {
  // ===== 核心对话状态 =====
  const [messages, setMessages] = useState<ChatMessage[]>([]);                      // 当前会话的消息列表
  const [inputValue, setInputValue] = useState('');                                 // 输入框当前文本
  const [loading, setLoading] = useState(false);                                    // 是否正在等待 AI 回复
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);         // 所有可选的知识库列表
  const [selectedKBIds, setSelectedKBIds] = useState<number[]>([]);                 // 用户选择的知识库 ID 列表
  const [sessions, setSessions] = useState<Session[]>([]);                          // 历史会话列表（弹窗用）
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>(undefined);  // 当前会话 ID
  const [sessionLoading, setSessionLoading] = useState(false);                      // 正在加载单个会话详情
  const [sessionsLoading, setSessionsLoading] = useState(false);                    // 正在加载会话列表
  const [kbLoading, setKbLoading] = useState(false);                                // 正在加载知识库列表
  const [historyVisible, setHistoryVisible] = useState(false);                      // 历史会话弹窗可见性
  const [streamingContent, setStreamingContent] = useState('');                     // 流式输出中的 AI 回答文本
  const [streamingThinking, setStreamingThinking] = useState('');                   // 流式输出中的思考过程文本
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);                  // 联网搜索开关
  const [deepThinkingEnabled, setDeepThinkingEnabled] = useState(false);            // 深度思考开关
  const [allSessions, setAllSessions] = useState<Session[]>([]);                    // 所有会话（侧边栏用）
  const [sidebarLoading, setSidebarLoading] = useState(false);                      // 侧边栏会话列表加载中
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);                  // 侧边栏折叠状态
  const { token } = theme.useToken();                                               // 获取 Ant Design 设计令牌（颜色、间距等）
  const { resolvedMode, activeBgDataUrl } = useThemeContext();                      // 获取主题模式和背景
  const isBgActive = !!activeBgDataUrl;                                             // 是否有自定义背景图片
  // 以下背景色变量用于自定义背景图片时覆盖默认颜色，使内容区透明以显示背景图
  const bgContainer = isBgActive ? 'transparent' : token.colorBgContainer;          // 容器背景色
  const bgLayout = isBgActive ? 'transparent' : token.colorBgLayout;                // 布局背景色
  const bgBubbleUser = isBgActive ? 'rgba(22,119,255,0.12)' : token.colorPrimaryBg; // 用户消息气泡背景
  const bgElevated = isBgActive ? 'rgba(0,0,0,0.08)' : token.colorBgElevated;       // 浮层面板背景

  // ===== 文件附件状态 =====
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);                   // 当前附加的文件列表
  const fileInputRef = useRef<HTMLInputElement>(null);                              // 隐藏的文件选择器 DOM 引用
  const [isDragOver, setIsDragOver] = useState(false);                              // 拖拽文件悬停状态
  const ALLOWED_FILE_TYPES = '.jpg,.jpeg,.png,.gif,.webp,.pdf,.docx,.doc,.txt,.md'; // 允许的文件扩展名
  const ALLOWED_MIME_TYPES = [                                                       // 允许的 MIME 类型
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'text/plain', 'text/markdown',
  ];

  const messagesEndRef = useRef<HTMLDivElement>(null);   // 消息列表底部 DOM 引用（用于滚动）
  const inputRef = useRef<any>(null);                    // 输入框 DOM 引用

  // ===== 文件附件辅助函数 =====
  // 判断文件是否为图片类型
  const isImageFile = (file: File) => file.type.startsWith('image/');
  // 获取文件的预览 URL（仅图片文件返回 blob URL，其他类型返回空字符串）
  const getFilePreviewUrl = (file: File): string => {
    if (isImageFile(file)) return URL.createObjectURL(file);
    return '';
  };
  const [previewUrls, setPreviewUrls] = useState<Map<File, string>>(new Map());  // 文件预览 URL 映射表

  /**
   * 添加文件到附件列表：验证文件类型和大小，去重后追加
   * @param newFiles - 用户选择的文件列表（来自文件选择器或拖拽）
   */
  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const filesArray = Array.from(newFiles);
    // 过滤：验证文件扩展名、MIME 类型和大小限制（20MB）
    const valid = filesArray.filter((f) => {
      const ext = '.' + f.name.split('.').pop()?.toLowerCase();
      if (f.size > 20 * 1024 * 1024) {
        antMessage.warning(`"${f.name}" 超过 20MB 限制，已跳过`);
        return false;
      }
      return ALLOWED_FILE_TYPES.includes(ext) || ALLOWED_MIME_TYPES.includes(f.type);
    });
    if (valid.length === 0) {
      antMessage.warning('不支持的文件格式，支持: JPG/PNG/GIF/WEBP/PDF/DOCX/TXT/MD');
      return;
    }
    // 去重：基于文件名+文件大小组合去重
    setAttachedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      const deduped = valid.filter((f) => !existing.has(f.name + f.size));
      return [...prev, ...deduped];
    });
  }, []);

  /**
   * 从附件列表中移除指定文件
   * @param fileToRemove - 要移除的文件对象
   */
  const removeFile = useCallback((fileToRemove: File) => {
    setAttachedFiles((prev) => prev.filter((f) => f !== fileToRemove));
    // 同时移除对应的预览 URL
    setPreviewUrls((prev) => {
      const next = new Map(prev);
      next.delete(fileToRemove);
      return next;
    });
  }, []);

  // 触发隐藏的文件选择器点击
  const handleFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // 文件选择器 change 事件处理：获取选择的文件列表并调用 addFiles
  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
      e.target.value = '';  // 重置 input 值，允许重复选择同一文件
    }
  }, [addFiles]);

  /**
   * 滚动到消息列表底部
   * 使用 setTimeout 延迟 100ms 以确保 DOM 更新完成后再滚动
   */
  const scrollToBottom = useCallback(() => {
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
  }, []);

  // ===== 副作用：消息或流式内容变化时自动滚动到底部 =====
  useEffect(() => { scrollToBottom(); }, [messages, streamingContent, scrollToBottom]);

  // ===== 副作用：组件挂载时加载知识库列表 =====
  useEffect(() => { fetchKnowledgeBases(); }, []);

  // ===== 副作用：如果提供了 initialSessionId，加载该历史会话 =====
  useEffect(() => {
    if (initialSessionId) {
      loadSession(initialSessionId);
    }
  }, [initialSessionId]);

  // ===== 副作用：如果设置了 initialShowHistory，加载会话列表并显示历史弹窗 =====
  useEffect(() => {
    if (initialShowHistory) {
      fetchSessions();
      setHistoryVisible(true);
    }
  }, [initialShowHistory]);

  // ===== 副作用：如果启用了 autoLoadLastSession，自动加载最新会话 =====
  useEffect(() => {
    if (autoLoadLastSession && !initialSessionId) {
      getSessions(sessionType).then(sessions => {
        if (sessions.length > 0) {
          loadSession(sessions[0].id);  // 加载最新（第一个）会话
        }
      }).catch(() => {});
    }
  }, [autoLoadLastSession, sessionType]);

  /**
   * 根据 kbTypeFilter 过滤知识库列表
   * 如果未设置过滤条件则返回完整列表
   */
  const filteredKBs = useCallback(() => {
    if (kbTypeFilter) return knowledgeBases.filter((kb) => kb.type.toLowerCase() === kbTypeFilter.toLowerCase());
    return knowledgeBases;
  }, [knowledgeBases, kbTypeFilter]);

  /**
   * 从后端获取所有知识库列表
   * 如果设置了 kbTypeFilter，自动选中对应类型的所有知识库
   */
  const fetchKnowledgeBases = async () => {
    setKbLoading(true);
    try {
      const kbs = await getKnowledgeBases();
      setKnowledgeBases(kbs);
      if (kbTypeFilter) {
        const filtered = kbs.filter((kb) => kb.type.toLowerCase() === kbTypeFilter.toLowerCase());
        if (filtered.length > 0) setSelectedKBIds(filtered.map((kb) => kb.id));
      }
    } catch { antMessage.error('获取知识库列表失败'); } finally { setKbLoading(false); }
  };

  /**
   * 从后端获取历史会话列表（用于弹窗显示）
   */
  const fetchSessions = async () => {
    setSessionsLoading(true);
    try { setSessions(await getSessions(sessionType)); } catch { antMessage.error('获取会话列表失败'); } finally { setSessionsLoading(false); }
  };

  /**
   * 从后端获取所有会话列表（用于侧边栏显示）
   * 使用 useCallback 记忆化，依赖 sessionType
   */
  const fetchAllSessions = useCallback(async () => {
    setSidebarLoading(true);
    try {
      const sessions = await getSessions(sessionType);
      setAllSessions(sessions);
    } catch {}
    setSidebarLoading(false);
  }, [sessionType]);

  // ===== 副作用：组件挂载时加载侧边栏会话列表 =====
  useEffect(() => { fetchAllSessions(); }, [fetchAllSessions]);

  /**
   * 将会话列表按时间分组：近三天、近一周、近30天
   * 使用 useMemo 优化，只在 allSessions 变化时重新计算
   */
  const groupedSessions = React.useMemo(() => {
    const now = Date.now();
    const threeDaysAgo = now - 3 * 24 * 60 * 60 * 1000;   // 3 天前的时间戳
    const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;   // 7 天前的时间戳

    // 定义三个分组容器
    const groups: { title: string; key: string; sessions: Session[] }[] = [
      { title: '近三天', key: '3d', sessions: [] },
      { title: '近一周', key: '7d', sessions: [] },
      { title: '近30天', key: '30d', sessions: [] },
    ];

    // 遍历所有会话，根据创建时间放入对应分组
    for (const session of allSessions) {
      const date = new Date(session.created_at || Date.now()).getTime();
      if (date >= threeDaysAgo) {
        groups[0].sessions.push(session);
      } else if (date >= sevenDaysAgo) {
        groups[1].sessions.push(session);
      } else {
        groups[2].sessions.push(session);
      }
    }

    return groups.filter(g => g.sessions.length > 0);  // 过滤掉空分组
  }, [allSessions]);

  /**
   * 加载指定会话的全部消息
   * @param sessionId - 会话 ID
   */
  const loadSession = async (sessionId: string) => {
    setSessionLoading(true);
    setHistoryVisible(false);  // 加载后关闭历史弹窗
    try {
      const detail: SessionDetail = await getSessionDetail(sessionId);
      setCurrentSessionId(sessionId);
      // 将后端返回的 Message 数组转换为前端的 ChatMessage 格式
      setMessages(detail.messages.map((msg: Message) => ({
        id: `msg-${msg.id}`, role: msg.role as 'user' | 'assistant',
        content: msg.content, thinking: (msg as any).thinking, references: msg.references,
        safety_flag: msg.safety_flag,
        disclaimer: msg.disclaimer, messageId: msg.id, feedbackType: msg.feedback_type,
        timestamp: new Date(msg.created_at || Date.now()),
      })));
      // 恢复该会话绑定的知识库 ID 列表
      if (detail.session.kb_ids && detail.session.kb_ids.length > 0) {
        setSelectedKBIds(detail.session.kb_ids);
      }
    } catch { antMessage.error('加载会话失败'); } finally { setSessionLoading(false); }
  };

  /**
   * 创建新对话：重置会话 ID、清空消息列表和流式内容
   */
  const handleNewSession = () => { setCurrentSessionId(undefined); setMessages([]); setStreamingContent(''); setStreamingThinking(''); };

  /**
   * 删除指定会话
   * @param sessionId - 要删除的会话 ID
   */
  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      antMessage.success('会话已删除');
      fetchSessions();       // 刷新弹窗中的会话列表
      fetchAllSessions();    // 刷新侧边栏中的会话列表
      if (currentSessionId === sessionId) handleNewSession();  // 如果删除了当前会话，创建新会话
    } catch { antMessage.error('删除会话失败'); }
  };

  /**
   * 构建流式请求的 URL：如果附加了文件，将端点从 /ask 替换为 /ask-multipart
   * @param endpoint - 原始端点路径
   * @param hasFiles - 是否包含文件
   * @returns 调整后的端点路径
   */
  const buildStreamUrl = (endpoint: string, hasFiles: boolean) =>
    hasFiles ? endpoint.replace('/ask', '/ask-multipart') : endpoint;

  /**
   * 核心功能：发送消息并获取 AI 回复
   * 支持两种模式：
   * 1. 流式模式（streamEndpoint 有值）：通过 fetch SSE 实时显示 AI 输出
   * 2. 非流式模式：通过 API 函数获取完整回复
   */
  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question && attachedFiles.length === 0) return;  // 无内容且无附件则不发送
    // 检查是否已选择知识库
    if (selectedKBIds.length === 0 && !autoBindKB && !hideKBSelector) {
      antMessage.warning('请先选择知识库');
      return;
    }
    // 如果没有文字但有附件，显示附件数量作为消息内容
    const displayText = question || `[${attachedFiles.length} 个附件]`;
    // 将用户消息追加到消息列表
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', content: displayText, timestamp: new Date() }]);
    setInputValue('');       // 清空输入框
    setAttachedFiles([]);    // 清空附件
    setLoading(true);        // 进入加载状态
    setStreamingContent(''); // 重置流式内容
    setStreamingThinking('');
    const hasFiles = attachedFiles.length > 0;

    // ===== 流式处理分支（使用 SSE 流式输出） =====
    if (streamEndpoint) {
      const baseUrl = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api';
      const token = localStorage.getItem('access_token');
      const endpoint = buildStreamUrl(streamEndpoint, hasFiles);
      try {
        let body: BodyInit;
        const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
        if (hasFiles) {
          // 有附件时使用 FormData 方式提交
          const formData = new FormData();
          formData.append('question', question);
          formData.append('web_search_enabled', String(webSearchEnabled));
          formData.append('deep_thinking_enabled', String(deepThinkingEnabled));
          formData.append('kb_ids', JSON.stringify(selectedKBIds));
          if (currentSessionId) formData.append('session_id', String(currentSessionId));
          attachedFiles.forEach((f) => formData.append('files', f));
          body = formData;
        } else {
          // 纯文本请求使用 JSON 格式
          headers['Content-Type'] = 'application/json';
          body = JSON.stringify({ question, kb_ids: selectedKBIds, session_id: currentSessionId, web_search_enabled: webSearchEnabled, deep_thinking_enabled: deepThinkingEnabled });
        }
        // 发起 SSE 流式 fetch 请求
        const resp = await fetch(`${baseUrl}${endpoint}`, {
          method: 'POST',
          headers,
          body,
        });
        if (!resp.ok) { antMessage.error(`请求失败: HTTP ${resp.status}`); setLoading(false); return; }
        const reader = resp.body?.getReader();
        if (!reader) { antMessage.error('无响应数据'); setLoading(false); return; }
        const decoder = new TextDecoder();
        let buf = '', fullText = '', thinkingText = '', newSid = '', newMessageId: number | undefined = undefined;
        // 持续读取流式响应数据
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() || '';  // 保留不完整的行等待下一次数据
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;  // SSE 数据以 "data: " 开头
            try {
              const d = JSON.parse(line.slice(6));  // 去掉 "data: " 前缀后解析 JSON
              if (d.type === 'think' && d.token) {
                // 思考过程 token（type 为 "think"）
                thinkingText += d.token;
                setStreamingThinking(thinkingText);
              } else if (d.token) {
                // 普通回答 token
                fullText += d.token;
                setStreamingContent(fullText);
              }
              if (d.done) {
                // 流式结束标记：获取会话 ID、完整思考过程和消息 ID
                newSid = d.session_id || '';
                if (d.thinking) thinkingText = d.thinking;
                if (d.message_id) newMessageId = d.message_id;
              }
              if (d.error) antMessage.error(d.error);
            } catch { /* 跳过解析失败的行 */ }
          }
        }
        // 如果是新会话（当前无 sessionId），记录返回的会话 ID 并刷新侧边栏
        if (!currentSessionId && newSid) {
          setCurrentSessionId(newSid);
          fetchAllSessions();
        }
        // 将完整的 AI 回复追加到消息列表
        setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: fullText, thinking: thinkingText, messageId: newMessageId, timestamp: new Date() }]);
        setStreamingContent('');
        setStreamingThinking('');
      } catch (error: any) { antMessage.error('请求失败: ' + error.message); setStreamingContent(''); setStreamingThinking(''); } finally { setLoading(false); }
    } else {
      // ===== 非流式处理分支 =====
      if (hasFiles) {
        // 有附件：使用 multipart 上传接口
        try {
          const response = await askQuestionMultipart(
            question, selectedKBIds, attachedFiles,
            currentSessionId ? Number(currentSessionId) : undefined,
            webSearchEnabled, deepThinkingEnabled,
          );
          if (!currentSessionId && (response as any).session_id) {
            setCurrentSessionId(String((response as any).session_id));
            fetchAllSessions();
          }
          setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: response.answer, thinking: (response as any).thinking, references: response.references, safety_flag: response.safety_flag, disclaimer: response.disclaimer, messageId: (response as any).message_id, timestamp: new Date() }]);
          setStreamingContent('');
        } catch (error: any) { antMessage.error('请求失败: ' + (error.response?.data?.detail || error.message)); setStreamingContent(''); setStreamingThinking(''); } finally { setLoading(false); }
      } else {
        // 纯文本：使用传入的 apiFunction
        try {
          const response = await apiFunction({ question, kb_ids: selectedKBIds, session_id: currentSessionId, web_search_enabled: webSearchEnabled, deep_thinking_enabled: deepThinkingEnabled });
          if (!currentSessionId && (response as any).session_id) {
            setCurrentSessionId((response as any).session_id);
            fetchAllSessions();
          }
          setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: response.answer, thinking: (response as any).thinking, references: response.references, safety_flag: response.safety_flag, disclaimer: response.disclaimer, messageId: (response as any).message_id, timestamp: new Date() }]);
          setStreamingContent('');
        } catch (error: any) { antMessage.error('请求失败: ' + (error.response?.data?.detail || error.message)); setStreamingContent(''); setStreamingThinking(''); } finally { setLoading(false); }
      }
    }
  };

  /**
   * 键盘事件处理：按 Enter 发送（Shift+Enter 换行）
   */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  /**
   * 用户反馈处理：点赞或点踩某条 AI 回复
   * @param messageId - 后端消息 ID
   * @param feedbackType - 反馈类型：'like' 或 'dislike'
   */
  const handleFeedback = async (messageId: number, feedbackType: string) => {
    if (!messageId) return;
    try {
      await submitFeedback({ message_id: messageId, feedback_type: feedbackType });
      antMessage.success('感谢您的反馈！');
      // 更新本地消息的反馈状态
      setMessages((prev) => prev.map((msg) => msg.messageId === messageId ? { ...msg, feedbackType } : msg));
    } catch { antMessage.error('提交反馈失败'); }
  };

  /**
   * 打开历史会话弹窗：先刷新会话列表再显示
   */
  const openHistory = () => { fetchSessions(); setHistoryVisible(true); };

  /**
   * 渲染参考文献区域：展示 AI 回答引用的知识库文档列表
   * @param references - 参考文献数组
   * @returns JSX 元素或 null
   */
  const renderReferences = (references: any[]) => {
    if (!references || references.length === 0) return null;
    return (
      <div style={{ marginTop: 12, padding: '8px 12px', background: bgElevated, borderRadius: 6, border: `1px solid ${token.colorBorder}` }}>
        {/* 参考文献标题行 */}
        <Space style={{ marginBottom: 4 }}><BookOutlined style={{ color: token.colorPrimary }} /><Text strong style={{ fontSize: 13 }}>参考文献</Text></Space>
        {/* 文献列表 */}
        <List size="small" dataSource={references} renderItem={(ref: any, index: number) => (
          <List.Item style={{ padding: '4px 0', border: 'none' }}>
            <Space align="start">
              {/* 序号 */}
              <Tag color="blue" style={{ minWidth: 20, textAlign: 'center' }}>{index + 1}</Tag>
              <div>
                {/* 文献标题/文件名 */}
                <Text style={{ fontSize: 13 }}>{ref.title || ref.filename || `文献 ${index + 1}`}</Text>
                {/* 文献内容摘要（截断前 200 字符） */}
                {ref.content && <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>{ref.content.substring(0, 200)}{ref.content.length > 200 ? '...' : ''}</Text>}
                {/* 原始链接（如果有） */}
                {ref.url && <a href={ref.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}><LinkOutlined /> 查看原文</a>}
              </div>
            </Space>
          </List.Item>
        )} />
      </div>
    );
  };

  /**
   * 渲染单条聊天消息
   * @param msg - 聊天消息对象
   * @returns JSX 元素
   */
  const renderMessage = (msg: ChatMessage) => {
    const isUser = msg.role === 'user';
    return (
      <div key={msg.id} style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', marginBottom: 20, gap: 12 }}>
        {/* 消息头像：用户为蓝色圆形+用户图标，AI 为绿色圆形+机器人图标 */}
        <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: isUser ? token.colorPrimary : token.colorSuccess, color: '#fff', flexShrink: 0, fontSize: 16 }}>
          {isUser ? <UserOutlined /> : <RobotOutlined />}
        </div>
        {/* 消息气泡 */}
        <div style={{ maxWidth: '80%', padding: '12px 16px', borderRadius: 12, background: isUser ? bgBubbleUser : bgContainer, borderTopRightRadius: isUser ? 4 : 12, borderTopLeftRadius: isUser ? 12 : 4 }}>
          {/* 用户消息：纯文本显示；AI 消息：Markdown 渲染 */}
          {isUser ? <Text style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{msg.content}</Text>
            : <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{msg.content}</ReactMarkdown></div>}
          {/* AI 深度思考过程：可折叠/展开的 details 标签 */}
          {!isUser && msg.thinking && (
              <details style={{ marginTop: 12, marginBottom: 12 }} open>
                <summary style={{ cursor: 'pointer', userSelect: 'none', fontSize: 13, color: token.colorPrimary, fontWeight: 500 }}>
                  🧠 深度思考过程
                </summary>
                <div style={{ marginTop: 8, padding: 10, background: token.colorFillQuaternary, borderRadius: 6, border: `1px solid ${token.colorBorderSecondary}`, fontSize: 13, color: token.colorTextSecondary, lineHeight: 1.6 }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.thinking}</ReactMarkdown>
                </div>
              </details>
            )}
          {/* 参考文献展示 */}
          {!isUser && msg.references && msg.references.length > 0 && renderReferences(msg.references)}
          {/* 健康安全警告（仅健康咨询页面启用） */}
          {!isUser && showSafetyWarning && msg.safety_flag && (
            <Alert message="健康提醒" description="以上内容仅供参考，不能替代专业医疗建议。如有身体不适，请及时就医。" type="warning" showIcon icon={<WarningOutlined />} style={{ marginTop: 12, fontSize: 13 }} />
          )}
          {/* 自定义免责声明 */}
          {!isUser && msg.disclaimer && <Alert message="免责声明" description={msg.disclaimer} type="info" showIcon style={{ marginTop: 12, fontSize: 13 }} />}
          {/* 点赞/点踩反馈按钮 */}
          {!isUser && msg.messageId && (
            <div style={{ marginTop: 8, display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
              <Tooltip title="有帮助"><Button type="text" size="small" icon={<LikeOutlined />} style={{ color: msg.feedbackType === 'like' ? token.colorPrimary : undefined }} onClick={() => handleFeedback(msg.messageId!, msg.feedbackType === 'like' ? 'none' : 'like')} /></Tooltip>
              <Tooltip title="需要改进"><Button type="text" size="small" icon={<DislikeOutlined />} style={{ color: msg.feedbackType === 'dislike' ? token.colorError : undefined }} onClick={() => handleFeedback(msg.messageId!, msg.feedbackType === 'dislike' ? 'none' : 'dislike')} /></Tooltip>
            </div>
          )}
        </div>
      </div>
    );
  };

  // 知识库选择器的选项列表（根据 kbTypeFilter 过滤后生成）
  const kbOptions = (kbTypeFilter ? filteredKBs() : knowledgeBases).map((kb) => ({ label: kb.name, value: kb.id }));

  // ===== 主渲染区域 =====
  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 140px)', gap: 16 }}>
      {/* ===== 左侧历史会话侧边栏 ===== */}
      {!sidebarCollapsed ? (
        // -------------------- 展开状态 --------------------
        <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, overflow: 'hidden' }}>
          {/* 侧边栏标题栏 */}
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text strong style={{ fontSize: 14 }}>📋 历史对话</Text>
            <Button type="text" size="small" icon={<MenuFoldOutlined />} onClick={() => setSidebarCollapsed(true)} />
          </div>
          {/* 新对话按钮 */}
          <div style={{ padding: '8px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={handleNewSession} block>新对话</Button>
          </div>
          {/* 按时间分组的历史会话列表 */}
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
            {sidebarLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}><Spin size="small" /></div>
            ) : groupedSessions.length === 0 ? (
              <Empty description="暂无历史对话" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '20px 0' }} />
            ) : (
              // 遍历分组（近三天/近一周/近30天）
              groupedSessions.map(group => (
                <div key={group.key}>
                  {/* 分组标题 */}
                  <div style={{ padding: '4px 16px 4px 16px', fontSize: 12, color: token.colorTextSecondary, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <MessageOutlined style={{ fontSize: 10 }} /> {group.title}
                  </div>
                  {/* 该分组下的会话列表 */}
                  {group.sessions.map(session => (
                    <div
                      key={session.id}
                      className="sidebar-session-item"
                      onClick={() => loadSession(session.id)}
                      style={{
                        padding: '8px 16px 8px 20px',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        background: currentSessionId === session.id ? token.colorPrimaryBg : 'transparent',  // 当前选中高亮
                        borderLeft: currentSessionId === session.id ? `3px solid ${token.colorPrimary}` : '3px solid transparent',
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        {/* 会话标题（自动省略） */}
                        <Text ellipsis style={{ fontSize: 13, fontWeight: currentSessionId === session.id ? 500 : 400 }}>
                          {session.title || `会话 ${session.id.substring(0, 8)}`}
                        </Text>
                        {/* 会话时间 */}
                        <div style={{ fontSize: 11, color: token.colorTextQuaternary, marginTop: 2 }}>
                          {session.created_at
                            ? new Date(session.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                            : ''}
                        </div>
                      </div>
                      {/* 删除按钮（hover 时显示） */}
                      <DeleteOutlined
                        className="sidebar-delete-btn"
                        style={{ color: token.colorTextTertiary, fontSize: 12, cursor: 'pointer' }}
                        onClick={(e) => { e.stopPropagation(); handleDeleteSession(session.id); }}
                      />
                    </div>
                  ))}
                </div>
              ))
            )}
          </div>
        </div>
      ) : (
        // -------------------- 折叠状态：仅显示图标 --------------------
        <div
          style={{ width: 40, flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, padding: '12px 0', cursor: 'pointer' }}
          onClick={() => setSidebarCollapsed(false)}
          title="展开历史对话"
        >
          <MenuUnfoldOutlined style={{ fontSize: 18, color: token.colorTextSecondary }} />
          <Text style={{ fontSize: 10, color: token.colorTextTertiary, marginTop: 4, writingMode: 'vertical-rl', letterSpacing: 2 }}>历史</Text>
        </div>
      )}

      {/* ===== 右侧主对话区域 ===== */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, overflow: 'hidden' }}>
        {/* ----- 顶部工具栏 ----- */}
        <div style={{ padding: '12px 20px', borderBottom: `1px solid ${token.colorBorderSecondary}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          {/* 左侧标题 */}
          <div><Title level={5} style={{ margin: 0 }}>{title}</Title>{subtitle && <Text type="secondary" style={{ fontSize: 12 }}>{subtitle}</Text>}</div>
          {/* 右侧操作按钮组 */}
          <Space>
            {/* 知识库选择器 */}
            {hideKBSelector ? <Tag color="blue" style={{ marginRight: 0 }}>已绑定所有知识库</Tag>
              : <>{autoBindKB && <Tag color="blue" style={{ marginRight: 0 }}>对话历史已绑定</Tag>}
                  {/* 多选下拉：选择要绑定的知识库 */}
                  <Select mode="multiple" placeholder={autoBindKB ? "可选其他知识库" : "选择知识库"} value={selectedKBIds} onChange={setSelectedKBIds} options={kbOptions} loading={kbLoading} style={{ minWidth: 200, maxWidth: 400 }} allowClear notFoundContent={kbLoading ? <Spin size="small" /> : <Empty description="暂无知识库" />} />
                </>}
            {/* 联网搜索开关 */}
            <Tooltip title={webSearchEnabled ? '联网搜索已开启，将同时搜索网络和知识库' : '联网搜索已关闭，仅使用知识库'}>
              <Space size={4}>
                <GlobalOutlined style={{ color: webSearchEnabled ? token.colorPrimary : token.colorTextQuaternary }} />
                <Switch size="small" checked={webSearchEnabled} onChange={setWebSearchEnabled} />
              </Space>
            </Tooltip>
            {/* 深度思考开关 */}
            <Tooltip title={deepThinkingEnabled ? '深度思考已开启，将展示推理过程' : '深度思考已关闭，仅展示最终答案'}>
              <Space size={4}>
                <span style={{ fontSize: 16 }}>🧠</span>
                <Switch size="small" checked={deepThinkingEnabled} onChange={setDeepThinkingEnabled} />
              </Space>
            </Tooltip>
            {/* 历史记录按钮 */}
            <Button icon={<HistoryOutlined />} onClick={() => { fetchSessions(); openHistory(); }}>历史记录</Button>
            {/* 新对话按钮 */}
            <Button icon={<PlusOutlined />} onClick={handleNewSession}>新对话</Button>
            {/* 额外操作（由父组件传入） */}
            {extraActions}
          </Space>
        </div>

        {/* ----- 消息展示区域 ----- */}
        <div
          style={{
            flex: 1, overflow: 'auto', padding: '20px', background: bgLayout,
            outline: isDragOver ? `2px dashed ${token.colorPrimary}` : 'none',  // 拖拽悬停时显示虚线边框
            outlineOffset: -2,
          }}
          // 拖拽事件处理
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
          onDrop={(e) => { e.preventDefault(); setIsDragOver(false); if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files); }}
        >
          {/* 拖拽悬停时显示的提示文字 */}
          {isDragOver && (
            <div style={{ textAlign: 'center', padding: 40, color: token.colorPrimary }}>
              <UploadOutlined style={{ fontSize: 36 }} />
              <Title level={5} style={{ color: token.colorPrimary, marginTop: 8 }}>释放文件以附加到对话</Title>
            </div>
          )}
          {sessionLoading ? (
            // 正在加载会话详情
            <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载会话中..." /></div>
          ) : messages.length === 0 ? (
            // 空状态：没有消息时的引导提示
            <div style={{ textAlign: 'center', padding: 60 }}>
              <RobotOutlined style={{ fontSize: 48, color: token.colorTextQuaternary, marginBottom: 16 }} />
              <Title level={4} type="secondary" style={{ fontWeight: 400 }}>您好！我是 MedAgent 智能助手</Title>
              <Paragraph type="secondary">
                {hideKBSelector ? '已自动绑定所有知识库，输入您的问题开始对话'
                  : autoBindKB ? '对话历史已自动绑定，输入您的问题开始对话'
                  : '请在上方选择知识库，然后输入您的问题开始对话'}
              </Paragraph>
            </div>
          ) : (
            // 有消息时渲染消息列表
            <>
              {messages.map(renderMessage)}
              {/* AI 正在回复时的加载状态：显示流式内容或思考动画 */}
              {loading && (
                <div style={{ display: 'flex', flexDirection: 'row', marginBottom: 20, gap: 12 }}>
                  <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: token.colorSuccess, color: '#fff', flexShrink: 0 }}><RobotOutlined /></div>
                  <div style={{ maxWidth: '80%', padding: '12px 16px', borderRadius: 12, background: bgContainer, borderTopLeftRadius: 4 }}>
                    {/* 如果正在输出思考过程，显示思考框 */}
                    {streamingThinking && (
                      <div style={{ marginBottom: streamingContent ? 12 : 0, padding: 8, background: token.colorFillQuaternary, borderRadius: 6, border: `1px solid ${token.colorBorderSecondary}`, maxHeight: 'none', overflow: 'visible' }}>
                        <Text strong style={{ fontSize: 12, color: token.colorPrimary }}>🧠 深度思考过程</Text>
                        <div className="markdown-content" style={{ marginTop: 4, fontSize: 13, color: token.colorTextSecondary }}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingThinking}</ReactMarkdown>
                        </div>
                      </div>
                    )}
                    {/* 如果正在输出回答内容，显示流式 Markdown；否则显示"思考中..." */}
                    {streamingContent ? (
                      <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{streamingContent}</ReactMarkdown></div>
                    ) : (
                      <Space><Spin size="small" /><Text type="secondary">思考中...</Text></Space>
                    )}
                  </div>
                </div>
              )}
              {/* 用于自动滚动的底部锚点 */}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* ===== 底部输入区域 ===== */}
        <div style={{ padding: '12px 20px', borderTop: `1px solid ${token.colorBorderSecondary}`, background: bgContainer }}>
          {/* 已附加文件的预览缩略图列表 */}
          {attachedFiles.length > 0 && (
            <div
              style={{
                display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8,
                padding: 8, background: token.colorFillQuaternary, borderRadius: 8,
              }}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}  // 防止拖拽区域嵌套干扰
            >
              {attachedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  style={{
                    position: 'relative', display: 'flex', alignItems: 'center',
                    gap: 4, padding: '2px 8px 2px 4px',
                    background: token.colorBgContainer, borderRadius: 6,
                    border: `1px solid ${token.colorBorderSecondary}`,
                    maxWidth: 200,
                  }}
                >
                  {/* 图片文件显示缩略图，其他文件显示文件图标 */}
                  {isImageFile(file) ? (
                    <img
                      src={URL.createObjectURL(file)}
                      alt={file.name}
                      style={{ width: 28, height: 28, borderRadius: 4, objectFit: 'cover' }}
                    />
                  ) : (
                    <FileOutlined style={{ fontSize: 16, color: token.colorPrimary }} />
                  )}
                  {/* 文件名（自动省略） */}
                  <Text ellipsis style={{ fontSize: 12, maxWidth: 100 }}>{file.name}</Text>
                  {/* 移除按钮 */}
                  <CloseCircleOutlined
                    style={{ color: token.colorError, cursor: 'pointer', fontSize: 12 }}
                    onClick={() => removeFile(file)}
                  />
                </div>
              ))}
            </div>
          )}
          {/* 输入框和发送按钮行 */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            {/* 多行文本输入框：支持自动扩展高度，Enter 发送 */}
            <TextArea ref={inputRef} value={inputValue} onChange={(e) => setInputValue(e.target.value)} onKeyDown={handleKeyDown}
              placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行..." autoSize={{ minRows: 2, maxRows: 6 }} disabled={loading} style={{ flex: 1 }} />
            {/* 附件上传按钮 */}
            <Tooltip title="上传图片或文件">
              <Button
                icon={<PaperClipOutlined />}
                onClick={handleFilePicker}
                disabled={loading}
                style={{ height: 42, width: 42 }}
              />
            </Tooltip>
            {/* 发送按钮 */}
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}
              disabled={(!inputValue.trim() && attachedFiles.length === 0) || (selectedKBIds.length === 0 && !autoBindKB && !hideKBSelector)} style={{ height: 42 }}>
              发送
            </Button>
          </div>
          {/* 隐藏的文件选择器 input */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ALLOWED_FILE_TYPES}
            onChange={handleFileInputChange}
            style={{ display: 'none' }}
          />
        </div>
      </div>

      {/* ===== 历史会话弹窗 Modal ===== */}
      <Modal title={<Space><HistoryOutlined />历史会话</Space>} open={historyVisible} onCancel={() => setHistoryVisible(false)} footer={null} width={480}>
        {sessionsLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
        ) : sessions.length === 0 ? (
          <Empty description="暂无历史会话" />
        ) : (
          <List dataSource={sessions} renderItem={(session) => (
            <List.Item actions={[
              <Button type="link" onClick={() => loadSession(session.id)} disabled={sessionLoading}>加载</Button>,
              <Button type="link" danger onClick={() => handleDeleteSession(session.id)}><DeleteOutlined /></Button>,
            ]}>
              <List.Item.Meta title={session.title || `会话 ${session.id.substring(0, 8)}`}
                description={<Space><Text type="secondary" style={{ fontSize: 12 }}>{session.created_at ? new Date(session.created_at).toLocaleString('zh-CN') : ''}</Text></Space>} />
            </List.Item>
          )} />
        )}
      </Modal>

      {/* ===== 全局样式：Markdown 内容渲染、侧边栏交互效果 ===== */}
      <style>{`
        /* 侧边栏会话项 hover 效果 */
        .sidebar-session-item:hover { background:${token.colorFillTertiary} !important; }
        .sidebar-session-item:hover .sidebar-delete-btn { opacity:1 !important; }
        .sidebar-delete-btn { opacity:0; transition: opacity 0.15s; }
        /* Markdown 标题样式 */
        .markdown-content h1,.markdown-content h2,.markdown-content h3,.markdown-content h4 { margin-top:12px; margin-bottom:8px; font-weight:600; }
        /* Markdown 段落样式 */
        .markdown-content p { margin-bottom:8px; line-height:1.6; }
        /* Markdown 列表样式 */
        .markdown-content ul,.markdown-content ol { padding-left:20px; margin-bottom:8px; }
        .markdown-content li { margin-bottom:4px; }
        /* Markdown 内联代码样式 */
        .markdown-content code { background:${token.colorFillSecondary}; padding:2px 6px; border-radius:3px; font-size:0.9em; }
        /* Markdown 代码块样式 */
        .markdown-content pre { background:${resolvedMode === 'dark' ? token.colorBgElevated : '#1e1e1e'}; padding:12px; border-radius:6px; overflow-x:auto; margin-bottom:12px; }
        .markdown-content pre code { background:transparent; color:${resolvedMode === 'dark' ? token.colorText : '#d4d4d4'}; padding:0; }
        /* Markdown 表格样式 */
        .markdown-content table { border-collapse:collapse; width:100%; margin-bottom:12px; }
        .markdown-content th,.markdown-content td { border:1px solid ${token.colorBorder}; padding:8px 12px; text-align:left; }
        .markdown-content th { background:${token.colorBgLayout}; font-weight:600; }
        /* Markdown 引用块样式 */
        .markdown-content blockquote { border-left:3px solid ${token.colorPrimary}; padding-left:12px; margin:8px 0; color:${token.colorTextSecondary}; }
        /* Markdown 链接样式 */
        .markdown-content a { color:${token.colorPrimary}; }
        /* Markdown 水平线样式 */
        .markdown-content hr { margin:16px 0; border:none; border-top:1px solid ${token.colorBorder}; }
        /* Markdown 图片样式 */
        .markdown-content img { max-width:100%; border-radius:4px; }
      `}</style>
    </div>
  );
};

// 默认导出 ChatInterface 组件
export default ChatInterface;
