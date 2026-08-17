// 引入 React 及其 Hooks：useState（状态管理）、useEffect（副作用处理）、useRef（DOM 引用）、useCallback（回调函数记忆化）
import React, { useState, useEffect, useRef, useCallback } from 'react';
// 引入 Ant Design 组件：Input（输入框）、Button（按钮）、Select（下拉选择）、Card（卡片）、Typography（排版）、Space（间距）、Spin（加载）、Empty（空状态）、Alert（警告/提示）、Tag（标签）、Divider（分割线）、Modal（弹窗）、List（列表）、message（全局提示）、Tooltip（工具提示）、theme（设计令牌）、Switch（开关）
import {
  Input, Button, Select, Card, Typography, Space, Spin, Empty,
  Tag, Divider, Modal, List, message as antMessage, Tooltip, theme,
} from 'antd';
// 引入 Ant Design 图标：Send（发送）、Robot（机器人）、User（用户）、Delete（删除）、History（历史）、Warning（警告）、Book（书籍）、Plus（添加）、Like/Dislike（点赞/点踩）、Link（链接）、PaperClip（附件）、CloseCircle（关闭）、File（文件）、Upload（上传）、Global（全球网络）、MenuFold/MenuUnfold（折叠/展开）、Message（消息）
import {
  SendOutlined, RobotOutlined, UserOutlined, DeleteOutlined,
  HistoryOutlined, BookOutlined, PlusOutlined,
  LikeOutlined, DislikeOutlined, LinkOutlined,
  MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined,
  SafetyCertificateOutlined, InfoCircleOutlined, CheckCircleFilled, GlobalOutlined,
} from '@ant-design/icons';
// 引入 ReactMarkdown 将 AI 返回的 Markdown 文本渲染为 HTML
import ReactMarkdown from 'react-markdown';
// 引入 remark-gfm 插件，支持 GFM（GitHub Flavored Markdown）扩展语法（表格、任务列表等）
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
// 引入 EnhancedMarkdown 增强版渲染器（支持 LaTeX、消息编辑、引用高亮）
import EnhancedMarkdown from './EnhancedMarkdown';
import './ChatInterface.css';
// 引入自定义主题上下文 Hook，用于获取当前主题模式和背景设置
import { useThemeContext } from '../contexts/ThemeContext';
// 引入 API 服务中的函数和类型：获取知识库列表、获取会话列表/详情、删除会话、提交反馈、多部分问答
import {
  getKnowledgeBases, getSessions, getSessionDetail, deleteSession, submitFeedback,
  getAssistantProfiles, submitAnswerPreference, getAnswerPreferenceProfile,
  type KnowledgeBase, type Session, type SessionDetail, type Message, type ChatResponse,
  type AssistantProfile, type AnswerVariant, type AnswerPreferenceProfile,
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
  apiFunction: (params: { question: string; kb_ids: number[]; session_id?: string; assistant_profile?: 'general_qa' | 'memory_qa' }) => Promise<ChatResponse>;
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
  defaultAssistantProfile?: 'general_qa' | 'memory_qa';
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
  cache_hit?: boolean;
  cache_age_seconds?: number;
  answerVariants?: AnswerVariant[];
  recommendedVariantId?: string;
  selectedVariantId?: string;
  messageId?: number;
  feedbackType?: string | null;
  edited?: boolean;
  timestamp: Date;
}

interface AgentStageStatus {
  key: string;
  label: string;
  detail?: string;
  severity?: 'info' | 'warning' | 'error';
}

type AnswerSectionKey = 'main' | 'uncertainty' | 'limitations' | 'nextSteps' | 'disclaimer';

interface ParsedAnswerContent {
  main: string;
  uncertainty: string;
  limitations: string;
  nextSteps: string;
  disclaimer: string;
}

const ANSWER_SECTION_RULES: Array<{ key: Exclude<AnswerSectionKey, 'main'>; pattern: RegExp }> = [
  { key: 'disclaimer', pattern: /^(?:#{1,6}\s*)?(?:医疗免责声明(?:\s*\/\s*Medical Disclaimer)?|Medical Disclaimer|免责声明)\s*[:：]?\s*/i },
  { key: 'uncertainty', pattern: /^(?:#{1,6}\s*)?(?:不确定性|证据不确定性|不确定因素)\s*[:：]?\s*/i },
  { key: 'limitations', pattern: /^(?:#{1,6}\s*)?(?:限制|局限性|证据局限)\s*[:：]?\s*/i },
  { key: 'nextSteps', pattern: /^(?:#{1,6}\s*)?(?:下一步|建议|后续建议|建议行动)\s*[:：]\s*/i },
];

const MAIN_ANSWER_PREFIX = /^(?:#{1,6}\s*)?(?:精炼结论|核心结论|详细说明|回答摘要|结论)\s*[:：]\s*/i;

/** 将模型文本里的辅助说明从核心答案中拆出，避免所有信息挤在同一排版层级。 */
export const parseAnswerContent = (content: string): ParsedAnswerContent => {
  const normalized = (content || '')
    .replace(/([。；;])\s*((?:不确定性|限制|局限性|下一步|后续建议|医疗免责声明(?:\s*\/\s*Medical Disclaimer)?|免责声明)\s*[:：])/g, '$1\n\n$2')
    .trim();
  const sections: Record<AnswerSectionKey, string[]> = {
    main: [], uncertainty: [], limitations: [], nextSteps: [], disclaimer: [],
  };
  let active: AnswerSectionKey = 'main';
  normalized.split(/\r?\n/).forEach((originalLine, lineIndex) => {
    const markerCandidate = originalLine.replace(/^\s*(?:[-*+]\s+)?/, '');
    const matchedRule = ANSWER_SECTION_RULES.find((rule) => rule.pattern.test(markerCandidate));
    if (matchedRule) {
      active = matchedRule.key;
      const remainder = markerCandidate.replace(matchedRule.pattern, '').trim();
      if (remainder) sections[active].push(remainder);
      return;
    }
    const line = lineIndex === 0 ? originalLine.replace(MAIN_ANSWER_PREFIX, '') : originalLine;
    sections[active].push(line);
  });
  return {
    main: sections.main.join('\n').trim() || normalized,
    uncertainty: sections.uncertainty.join('\n').trim(),
    limitations: sections.limitations.join('\n').trim(),
    nextSteps: sections.nextSteps.join('\n').trim(),
    disclaimer: sections.disclaimer.join('\n').trim(),
  };
};

const AGENT_STAGE_LABELS: Record<string, string> = {
  input_safety: '\u8f93\u5165\u5b89\u5168\u68c0\u67e5',
  triage: '\u533b\u7597\u5206\u8bca',
  clarification_required: '\u7b49\u5f85\u8865\u5145\u4fe1\u606f',
  retrieval_planned: '\u5236\u5b9a\u68c0\u7d22\u8ba1\u5212',
  retrieval_started: '\u6b63\u5728\u68c0\u7d22\u8bc1\u636e',
  retrieval_completed: '\u68c0\u7d22\u5b8c\u6210',
  evidence_verification: '\u6b63\u5728\u6838\u9a8c\u8bc1\u636e',
  answer_generated: '\u5df2\u751f\u6210\u5f15\u7528\u7ed1\u5b9a\u8349\u7a3f',
  safety_review: '\u6b63\u5728\u8f93\u51fa\u5b89\u5168\u5ba1\u67e5',
  human_review_required: '\u7b49\u5f85\u4eba\u5de5\u5ba1\u6838',
  done: '\u5904\u7406\u5b8c\u6210',
  error: '\u5904\u7406\u5931\u8d25',
  cache_hit: '\u9ad8\u9891\u6807\u51c6\u7b54\u6848\u7f13\u5b58\u547d\u4e2d',
  answer_candidates_generated: '\u4e24\u4e2a Answer Agent \u5df2\u751f\u6210\u5019\u9009\u7248\u672c',
};

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
  sessionType, defaultAssistantProfile,
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
  const [agentStage, setAgentStage] = useState<AgentStageStatus | null>(null);
  const [allSessions, setAllSessions] = useState<Session[]>([]);                    // 所有会话（侧边栏用）
  const [sidebarLoading, setSidebarLoading] = useState(false);                      // 侧边栏会话列表加载中
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);                  // 侧边栏折叠状态
  const [assistantProfiles, setAssistantProfiles] = useState<AssistantProfile[]>([]);
  const [assistantProfile, setAssistantProfile] = useState<'general_qa' | 'memory_qa'>(defaultAssistantProfile ?? 'memory_qa');
  const [answerPreference, setAnswerPreference] = useState<AnswerPreferenceProfile>();
  const { token } = theme.useToken();                                               // 获取 Ant Design 设计令牌（颜色、间距等）
  const { resolvedMode, activeBgDataUrl } = useThemeContext();                      // 获取主题模式和背景
  const isBgActive = !!activeBgDataUrl;                                             // 是否有自定义背景图片
  // 以下背景色变量用于自定义背景图片时覆盖默认颜色，使内容区透明以显示背景图
  const bgContainer = isBgActive ? 'transparent' : token.colorBgContainer;          // 容器背景色
  const bgLayout = isBgActive ? 'transparent' : token.colorBgLayout;                // 布局背景色
  const bgBubbleUser = isBgActive ? 'rgba(22,119,255,0.12)' : token.colorPrimaryBg; // 用户消息气泡背景

  const messagesEndRef = useRef<HTMLDivElement>(null);   // 消息列表底部 DOM 引用（用于滚动）
  const inputRef = useRef<any>(null);                    // 输入框 DOM 引用

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

  useEffect(() => {
    getAssistantProfiles()
      .then((result) => {
        setAssistantProfiles(result.items);
        if (!defaultAssistantProfile && (result.default === 'general_qa' || result.default === 'memory_qa')) {
          setAssistantProfile(result.default);
        }
      })
      .catch(() => {
        setAssistantProfiles([
          { profile_id: 'general_qa', name: '普通问答助手', description: '非医学问题直接由大模型回答，医学问题自动融合知识库与互联网证据', session_memory_enabled: false, long_term_memory_enabled: false, auto_web_search: true, intended_use: '通用知识问答' },
          { profile_id: 'memory_qa', name: '记忆问答助手', description: '保持多轮会话上下文', session_memory_enabled: true, long_term_memory_enabled: true, auto_web_search: false, intended_use: '多轮问诊' },
        ]);
      });
  }, [defaultAssistantProfile]);

  useEffect(() => {
    getAnswerPreferenceProfile().then(setAnswerPreference).catch(() => undefined);
  }, []);

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
        answerVariants: msg.answer_variants_json,
        recommendedVariantId: msg.recommended_variant_id,
        selectedVariantId: msg.selected_variant_id,
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
   * 核心功能：发送消息并获取 AI 回复
   * 支持两种模式：
   * 1. 流式模式（streamEndpoint 有值）：通过 fetch SSE 实时显示 AI 输出
   * 2. 非流式模式：通过 API 函数获取完整回复
  */
  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question) return;
    const noKB = selectedKBIds.length === 0 && !autoBindKB && !hideKBSelector;
    const effectiveKBIds = noKB ? [] : selectedKBIds;
    // 将用户消息追加到消息列表
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', content: question, timestamp: new Date() }]);
    setInputValue('');       // 清空输入框
    setLoading(true);        // 进入加载状态
    setStreamingContent(''); // 重置流式内容
    setStreamingThinking('');
    setAgentStage({ key: 'input_safety', label: AGENT_STAGE_LABELS.input_safety });

    // ===== 流式处理分支（使用 SSE 流式输出） =====
    if (streamEndpoint) {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api';
      const token = localStorage.getItem('access_token');
      try {
        const headers: Record<string, string> = {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        };
        const body = JSON.stringify({ question, kb_ids: effectiveKBIds, session_id: currentSessionId, assistant_profile: assistantProfile });
        // 发起 SSE 流式 fetch 请求
        const resp = await fetch(`${baseUrl}${streamEndpoint}`, {
          method: 'POST',
          headers,
          body,
        });
        if (!resp.ok) { antMessage.error(`请求失败: HTTP ${resp.status}`); setLoading(false); return; }
        const reader = resp.body?.getReader();
        if (!reader) { antMessage.error('无响应数据'); setLoading(false); return; }
        const decoder = new TextDecoder();
        let buf = '', fullText = '', thinkingText = '', newSid = '', newMessageId: number | undefined = undefined;
        let cacheHit = false, cacheAgeSeconds: number | undefined = undefined;
        let answerVariants: AnswerVariant[] = [], recommendedVariantId: string | undefined = undefined;
        const streamedReferences: any[] = [];
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
              if (d.type && AGENT_STAGE_LABELS[d.type]) {
                const isError = d.type === 'error';
                const needsAttention = d.type === 'clarification_required' || d.type === 'human_review_required';
                setAgentStage({
                  key: d.type,
                  label: AGENT_STAGE_LABELS[d.type],
                  detail: d.error_code || d.reason,
                  severity: isError ? 'error' : needsAttention ? 'warning' : 'info',
                });
              }
              if (d.evidence_id) streamedReferences.push(d);
              if (d.type === 'cache_hit' || d.cache_hit) {
                cacheHit = true;
                cacheAgeSeconds = d.age_seconds ?? d.cache_age_seconds;
              }
              if (d.type === 'answer_variants' && Array.isArray(d.items)) {
                answerVariants = d.items;
                recommendedVariantId = d.recommended_variant_id;
              }
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
                if (d.recommended_variant_id) recommendedVariantId = d.recommended_variant_id;
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
        setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: fullText, thinking: thinkingText, references: streamedReferences, messageId: newMessageId, cache_hit: cacheHit, cache_age_seconds: cacheAgeSeconds, answerVariants, recommendedVariantId, timestamp: new Date() }]);
        setStreamingContent('');
        setStreamingThinking('');
      } catch (error: any) { antMessage.error('请求失败: ' + error.message); setStreamingContent(''); setStreamingThinking(''); setAgentStage({ key: 'error', label: AGENT_STAGE_LABELS.error, detail: error.message, severity: 'error' }); } finally { setLoading(false); }
    } else {
      // ===== 非流式处理分支 =====
      try {
        const response = await apiFunction({ question, kb_ids: effectiveKBIds, session_id: currentSessionId, assistant_profile: assistantProfile });
        if (!currentSessionId && (response as any).session_id) {
          setCurrentSessionId((response as any).session_id);
          fetchAllSessions();
        }
        setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: response.answer, thinking: (response as any).thinking, references: response.references, safety_flag: response.safety_flag, disclaimer: response.disclaimer, messageId: (response as any).message_id, cache_hit: response.cache_hit, cache_age_seconds: response.cache_age_seconds, answerVariants: response.answer_variants, recommendedVariantId: response.recommended_variant_id, timestamp: new Date() }]);
        setStreamingContent('');
      } catch (error: any) { antMessage.error('请求失败: ' + (error.response?.data?.detail || error.message)); setStreamingContent(''); setStreamingThinking(''); } finally { setLoading(false); }
    }
  };

  /**
   * 键盘事件处理：按 Enter 发送（Shift+Enter 换行）
   */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  /**
   * 消息编辑处理：允许用户编辑自己的消息内容
   * 编辑后消息标记为已编辑状态，并更新本地消息列表
   * @param messageId - 消息 ID
   * @param newContent - 编辑后的内容
   */
  const handleEditMessage = async (messageId: string, newContent: string) => {
    setMessages((prev) => prev.map((msg) =>
      msg.id === messageId ? { ...msg, content: newContent, edited: true } : msg
    ));
    // 可以在这里触发重新发送编辑后的消息
    antMessage.success('消息已更新');
  };

  /**
   * 引用点击处理：滚动到对应的引用区域
   */
  const handleCitationClick = useCallback((detail: { index: number; reference: any }) => {
    // 通过自定义事件，高亮对应的引用区块
    const refEl = document.getElementById(`reference-${detail.index}`);
    if (refEl) {
      refEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
      refEl.style.transition = 'background 0.5s';
      refEl.style.background = '#fff7e6';
      setTimeout(() => { refEl.style.background = ''; }, 2000);
    }
  }, []);

  // 注册引用点击事件监听
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      handleCitationClick(detail);
    };
    window.addEventListener('citation-click', handler);
    return () => window.removeEventListener('citation-click', handler);
  }, [handleCitationClick]);

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

  const handleChooseAnswerVariant = async (msg: ChatMessage, variant: AnswerVariant) => {
    if (!msg.messageId) {
      antMessage.error('回答尚未完成保存，请稍后再选择');
      return;
    }
    try {
      const result = await submitAnswerPreference(msg.messageId, variant.variant_id);
      setAnswerPreference(result.profile);
      setMessages((prev) => prev.map((item) => item.id === msg.id ? {
        ...item,
        selectedVariantId: variant.variant_id,
        content: variant.answer,
        references: variant.citations,
      } : item));
      const label = result.profile.preferred_style === 'detailed_guidance' ? '详细指导版' : '精炼证据版';
      antMessage.success(`已记录选择，当前偏好：${label}`);
    } catch (error: any) {
      antMessage.error(error.response?.data?.detail || '偏好保存失败');
    }
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
  const renderReferences = (references: any[], sharedByVariants = false) => {
    if (!references || references.length === 0) return null;
    return (
      <details className="answer-references" data-testid="answer-references">
        <summary>
          <BookOutlined style={{ color: token.colorPrimary }} />
          <Text strong style={{ fontSize: 13 }}>依据与参考文献</Text>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>{references.length} 条</Tag>
          {sharedByVariants && <Tag style={{ marginInlineEnd: 0 }}>两个版本共用</Tag>}
          <span className="answer-reference-hint">点击展开查看来源</span>
        </summary>
        <div className="answer-reference-list">
          <List size="small" dataSource={references} renderItem={(ref: any, index: number) => (
            <List.Item
              id={`reference-${index}`}
              style={{ padding: '8px 0', borderBlockEnd: index === references.length - 1 ? 'none' : undefined, borderRadius: 4, transition: 'background 0.3s' }}
            >
              <Space align="start">
                <Tag color="blue" style={{ minWidth: 24, textAlign: 'center', cursor: 'pointer', borderRadius: 12 }}
                  onClick={() => window.dispatchEvent(new CustomEvent('citation-click', { detail: { index, reference: ref } }))}
                >{index + 1}</Tag>
                <div>
                  <Text strong style={{ fontSize: 13 }}>{ref.title || ref.filename || ref.source_name || `文献 ${index + 1}`}</Text>
                  {ref.content && <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 2, lineHeight: 1.6 }}>{ref.content.substring(0, 220)}{ref.content.length > 220 ? '...' : ''}</Text>}
                  {ref.url && <a href={ref.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}><LinkOutlined /> 查看原文</a>}
                </div>
              </Space>
            </List.Item>
          )} />
        </div>
      </details>
    );
  };

  const renderStructuredAnswer = (content: string, references?: any[]) => {
    const parsed = parseAnswerContent(content);
    const secondarySections = [
      { key: 'uncertainty', title: '不确定性', content: parsed.uncertainty },
      { key: 'limitations', title: '适用范围与限制', content: parsed.limitations },
      { key: 'nextSteps', title: '下一步建议', content: parsed.nextSteps },
    ].filter((section) => section.content);
    return (
      <div className="answer-content-layout">
        <section className="answer-primary-panel" data-testid="answer-primary">
          <div className="answer-section-heading"><CheckCircleFilled /> 核心回答</div>
          <EnhancedMarkdown content={parsed.main} references={references} />
        </section>
        {secondarySections.length > 0 && (
          <div className="answer-secondary-grid" data-testid="answer-secondary-info">
            {secondarySections.map((section) => (
              <section key={section.key} className={`answer-secondary-card${secondarySections.length === 1 ? ' is-wide' : ''}`}>
                <div className="answer-secondary-title"><InfoCircleOutlined /> {section.title}</div>
                <EnhancedMarkdown content={section.content} references={references} />
              </section>
            ))}
          </div>
        )}
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
    const hasVariants = !isUser && !!msg.answerVariants && msg.answerVariants.length >= 2;
    const activeVariant = hasVariants
      ? msg.answerVariants!.find((item) => item.variant_id === msg.selectedVariantId)
        || msg.answerVariants!.find((item) => item.variant_id === msg.recommendedVariantId)
        || msg.answerVariants![0]
      : undefined;
    const sharedReferences = activeVariant?.citations?.length ? activeVariant.citations : (msg.references || []);
    const parsedMessage = !isUser ? parseAnswerContent(msg.content) : undefined;
    const embeddedDisclaimers = hasVariants
      ? msg.answerVariants!.map((variant) => parseAnswerContent(variant.answer).disclaimer)
      : [parsedMessage?.disclaimer || ''];
    const safetyNotes = Array.from(new Set([
      showSafetyWarning && msg.safety_flag ? '以上内容仅供健康参考，不能替代专业医疗建议；如有明显不适或紧急症状，请及时就医。' : '',
      ...embeddedDisclaimers,
      msg.disclaimer || '',
    ].map((item) => item.trim()).filter(Boolean)));
    const assistantSurface = isBgActive
      ? (resolvedMode === 'dark' ? 'rgba(24, 24, 28, 0.88)' : 'rgba(255, 255, 255, 0.9)')
      : token.colorBgContainer;
    const messageStyle = {
      maxWidth: isUser ? '76%' : 'calc(100% - 48px)',
      width: isUser ? 'auto' : '100%',
      minWidth: 0,
      padding: isUser ? '12px 16px' : '4px 0 10px',
      borderRadius: 12,
      background: isUser ? bgBubbleUser : 'transparent',
      borderTopRightRadius: isUser ? 4 : 12,
      borderTopLeftRadius: isUser ? 12 : 4,
      '--answer-surface': assistantSurface,
      '--answer-subtle': token.colorFillAlter,
      '--answer-border': token.colorBorderSecondary,
      '--answer-primary': token.colorPrimary,
      '--answer-primary-soft': token.colorPrimaryBg,
      '--answer-text-secondary': token.colorTextSecondary,
    } as React.CSSProperties;
    return (
      <div key={msg.id} style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', marginBottom: 20, gap: 12 }}>
        {/* 消息头像：用户为蓝色圆形+用户图标，AI 为绿色圆形+机器人图标 */}
        <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: isUser ? token.colorPrimary : token.colorSuccess, color: '#fff', flexShrink: 0, fontSize: 16 }}>
          {isUser ? <UserOutlined /> : <RobotOutlined />}
        </div>
        {/* 消息气泡 */}
        <div className={isUser ? undefined : 'assistant-message-bubble'} style={messageStyle}>
          {!isUser && msg.cache_hit && (
            <Tag color="green" style={{ marginBottom: 8 }}>
              Redis 高频答案命中{msg.cache_age_seconds !== undefined ? ` · 缓存 ${Math.round(msg.cache_age_seconds)} 秒` : ''}
            </Tag>
          )}
          {/* 用户消息：使用 EnhancedMarkdown（支持编辑）；AI 消息：增强 Markdown 渲染（支持 LaTeX、引用） */}
          {isUser ? (
            <div>
              <EnhancedMarkdown content={msg.content} isUser onEdit={(newContent) => handleEditMessage(msg.id, newContent)} />
              {msg.edited && <Text type="secondary" style={{ fontSize: 11, fontStyle: 'italic' }}>（已编辑）</Text>}
            </div>
          ) : hasVariants ? (
            <div data-testid="answer-variant-comparison">
              <div className="answer-comparison-header">
                <div>
                  <div className="answer-comparison-title"><RobotOutlined style={{ color: token.colorSuccess }} /> 两个回答版本</div>
                  <div className="answer-comparison-subtitle">使用完全相同的证据依据，仅在信息密度与表达方式上有所不同。</div>
                </div>
                <Space wrap size={[4, 4]}>
                  <Tag color="blue">共同依据 {sharedReferences.length} 条</Tag>
                  <Tag color="gold">选择偏好后持续学习</Tag>
                </Space>
              </div>
              <div className="answer-variant-grid">
                {msg.answerVariants!.map((variant) => {
                  const selected = msg.selectedVariantId === variant.variant_id;
                  const recommended = msg.recommendedVariantId === variant.variant_id;
                  return (
                    <Card
                      key={variant.variant_id}
                      size="small"
                      className={`answer-variant-card${recommended ? ' is-recommended' : ''}${selected ? ' is-selected' : ''}`}
                      title={<Space wrap><Text strong>{variant.label}</Text>{recommended && <Tag color="purple">为你优先</Tag>}{selected && <Tag color="green">已选择</Tag>}</Space>}
                      actions={[
                        <Button
                          key="choose"
                          type={selected ? 'primary' : 'default'}
                          disabled={selected || !msg.messageId}
                          onClick={() => handleChooseAnswerVariant(msg, variant)}
                          icon={selected ? <CheckCircleFilled /> : undefined}
                        >{selected ? '已选择' : '选择此版本'}</Button>,
                      ]}
                    >
                      {renderStructuredAnswer(variant.answer, variant.citations)}
                    </Card>
                  );
                })}
              </div>
              {sharedReferences.length > 0 && renderReferences(sharedReferences, true)}
            </div>
          ) : (
            renderStructuredAnswer(msg.content, msg.references)
          )}
          {!isUser && !hasVariants && sharedReferences.length > 0 && renderReferences(sharedReferences)}
          {!isUser && safetyNotes.length > 0 && (
            <section className="answer-safety-panel" data-testid="answer-safety">
              <div className="answer-safety-title"><SafetyCertificateOutlined /> 安全与使用边界</div>
              {safetyNotes.map((note, index) => <p className="answer-safety-note" key={`${note}-${index}`}>{note}</p>)}
            </section>
          )}
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
            <Tooltip title={assistantProfile === 'general_qa' ? '非医学问题直接由大模型回答；医学问题自动检索授权知识库与互联网' : '检索授权知识库，并按医疗意图调用受控在线医学来源'}>
              <Tag color={assistantProfile === 'general_qa' ? 'green' : 'cyan'} style={{ marginRight: 0 }}>
                {assistantProfile === 'general_qa' ? <><GlobalOutlined /> 智能路由问答</> : '知识库混合检索'}
              </Tag>
            </Tooltip>
            <Tooltip title={assistantProfiles.find((item) => item.profile_id === assistantProfile)?.description}>
              <Select
                value={assistantProfile}
                onChange={setAssistantProfile}
                style={{ width: 150 }}
                options={assistantProfiles.map((item) => ({ value: item.profile_id, label: item.name }))}
              />
            </Tooltip>
            <Tag color={assistantProfile === 'memory_qa' ? 'purple' : 'default'} style={{ marginRight: 0 }}>
              {assistantProfile === 'memory_qa' ? '持久记忆已开启' : '不写入持久记忆'}
            </Tag>
            <Tooltip title="每次选择都会更新下一轮的回答排序偏好">
              <Tag color="gold" style={{ marginRight: 0 }}>
                偏好学习：{answerPreference?.preferred_style === 'detailed_guidance' ? '详细版' : '精炼版'} · {answerPreference?.total_choices || 0} 次选择
              </Tag>
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
        <div style={{ flex: 1, overflow: 'auto', padding: '20px', background: bgLayout }}>
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
                    {/* 如果正在输出回答内容，显示流式 Markdown；否则显示"思考中..." */}
                    {streamingContent ? (
                      <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{streamingContent}</ReactMarkdown></div>
                    ) : (
                      <Space direction="vertical" size={4}>
                        <Space><Spin size="small" /><Text type="secondary">{agentStage?.label || '正在处理...'}</Text></Space>
                        {agentStage?.detail && <Text type={agentStage.severity === 'error' ? 'danger' : 'secondary'}>{agentStage.detail}</Text>}
                      </Space>
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
          {/* 输入框和发送按钮行 */}
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            {/* 多行文本输入框：支持自动扩展高度，Enter 发送 */}
            <TextArea ref={inputRef} value={inputValue} onChange={(e) => setInputValue(e.target.value)} onKeyDown={handleKeyDown}
              placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行..." autoSize={{ minRows: 2, maxRows: 6 }} disabled={loading} style={{ flex: 1 }} />
            {/* 发送按钮 */}
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}
              disabled={!inputValue.trim()} style={{ height: 42 }}>
              发送
            </Button>
          </div>
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
