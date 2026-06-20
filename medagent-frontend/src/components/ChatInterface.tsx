import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Input, Button, Select, Card, Typography, Space, Spin, Empty, Alert,
  Tag, Divider, Modal, List, message as antMessage, Tooltip, theme,
  Switch,
} from 'antd';
import {
  SendOutlined, RobotOutlined, UserOutlined, DeleteOutlined,
  HistoryOutlined, WarningOutlined, BookOutlined, PlusOutlined,
  LikeOutlined, DislikeOutlined, LinkOutlined,
  PaperClipOutlined, CloseCircleOutlined, FileOutlined, UploadOutlined,
  GlobalOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { useThemeContext } from '../contexts/ThemeContext';
import {
  getKnowledgeBases, getSessions, getSessionDetail, deleteSession, submitFeedback,
  askQuestionMultipart,
  type KnowledgeBase, type Session, type SessionDetail, type Message, type ChatResponse,
} from '../services/api';

const { TextArea } = Input;
const { Text, Title, Paragraph } = Typography;

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

const ChatInterface: React.FC<ChatInterfaceProps> = ({
  title, subtitle, apiFunction, kbTypeFilter,
  showSafetyWarning = false, autoBindKB = false, hideKBSelector = false,
  streamEndpoint, extraActions,
  initialSessionId, initialShowHistory, autoLoadLastSession = false,
  sessionType,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKBIds, setSelectedKBIds] = useState<number[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | undefined>(undefined);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [kbLoading, setKbLoading] = useState(false);
  const [historyVisible, setHistoryVisible] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingThinking, setStreamingThinking] = useState('');
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);
  const [deepThinkingEnabled, setDeepThinkingEnabled] = useState(false);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [sidebarLoading, setSidebarLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { token } = theme.useToken();
  const { resolvedMode, activeBgDataUrl } = useThemeContext();
  const isBgActive = !!activeBgDataUrl;
  // Fully transparent backgrounds so custom bg image shows through completely
  const bgContainer = isBgActive
    ? 'transparent'
    : token.colorBgContainer;
  const bgLayout = isBgActive
    ? 'transparent'
    : token.colorBgLayout;
  const bgBubbleUser = isBgActive
    ? 'rgba(22,119,255,0.12)'
    : token.colorPrimaryBg;
  const bgElevated = isBgActive
    ? 'rgba(0,0,0,0.08)'
    : token.colorBgElevated;

  // File attachment state
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const ALLOWED_FILE_TYPES = '.jpg,.jpeg,.png,.gif,.webp,.pdf,.docx,.doc,.txt,.md';
  const ALLOWED_MIME_TYPES = [
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'text/plain', 'text/markdown',
  ];

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);

  // File attachment helpers
  const isImageFile = (file: File) => file.type.startsWith('image/');
  const getFilePreviewUrl = (file: File): string => {
    if (isImageFile(file)) return URL.createObjectURL(file);
    return '';
  };
  const [previewUrls, setPreviewUrls] = useState<Map<File, string>>(new Map());

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const filesArray = Array.from(newFiles);
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
    setAttachedFiles((prev) => {
      const existing = new Set(prev.map((f) => f.name + f.size));
      const deduped = valid.filter((f) => !existing.has(f.name + f.size));
      return [...prev, ...deduped];
    });
  }, []);

  const removeFile = useCallback((fileToRemove: File) => {
    setAttachedFiles((prev) => prev.filter((f) => f !== fileToRemove));
    // Revoke preview URL if created
    setPreviewUrls((prev) => {
      const next = new Map(prev);
      next.delete(fileToRemove);
      return next;
    });
  }, []);

  const handleFilePicker = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files);
      e.target.value = '';
    }
  }, [addFiles]);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, streamingContent, scrollToBottom]);
  useEffect(() => { fetchKnowledgeBases(); }, []);
  useEffect(() => {
    if (initialSessionId) {
      loadSession(initialSessionId);
    }
  }, [initialSessionId]);
  useEffect(() => {
    if (initialShowHistory) {
      fetchSessions();
      setHistoryVisible(true);
    }
  }, [initialShowHistory]);
  useEffect(() => {
    if (autoLoadLastSession && !initialSessionId) {
      getSessions(sessionType).then(sessions => {
        if (sessions.length > 0) {
          loadSession(sessions[0].id);
        }
      }).catch(() => {});
    }
  }, [autoLoadLastSession, sessionType]);

  const filteredKBs = useCallback(() => {
    if (kbTypeFilter) return knowledgeBases.filter((kb) => kb.type.toLowerCase() === kbTypeFilter.toLowerCase());
    return knowledgeBases;
  }, [knowledgeBases, kbTypeFilter]);

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

  const fetchSessions = async () => {
    setSessionsLoading(true);
    try { setSessions(await getSessions(sessionType)); } catch { antMessage.error('获取会话列表失败'); } finally { setSessionsLoading(false); }
  };

  const fetchAllSessions = useCallback(async () => {
    setSidebarLoading(true);
    try {
      const sessions = await getSessions(sessionType);
      setAllSessions(sessions);
    } catch {}
    setSidebarLoading(false);
  }, [sessionType]);

  useEffect(() => { fetchAllSessions(); }, [fetchAllSessions]);

  const groupedSessions = React.useMemo(() => {
    const now = Date.now();
    const threeDaysAgo = now - 3 * 24 * 60 * 60 * 1000;
    const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;

    const groups: { title: string; key: string; sessions: Session[] }[] = [
      { title: '近三天', key: '3d', sessions: [] },
      { title: '近一周', key: '7d', sessions: [] },
      { title: '近30天', key: '30d', sessions: [] },
    ];

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

    return groups.filter(g => g.sessions.length > 0);
  }, [allSessions]);

  const loadSession = async (sessionId: string) => {
    setSessionLoading(true);
    setHistoryVisible(false);
    try {
      const detail: SessionDetail = await getSessionDetail(sessionId);
      setCurrentSessionId(sessionId);
      setMessages(detail.messages.map((msg: Message) => ({
        id: `msg-${msg.id}`, role: msg.role as 'user' | 'assistant',
        content: msg.content, thinking: (msg as any).thinking, references: msg.references,
        safety_flag: msg.safety_flag,
        disclaimer: msg.disclaimer, messageId: msg.id, feedbackType: msg.feedback_type,
        timestamp: new Date(msg.created_at || Date.now()),
      })));
      // Restore KB IDs saved with this session
      if (detail.session.kb_ids && detail.session.kb_ids.length > 0) {
        setSelectedKBIds(detail.session.kb_ids);
      }
    } catch { antMessage.error('加载会话失败'); } finally { setSessionLoading(false); }
  };

  const handleNewSession = () => { setCurrentSessionId(undefined); setMessages([]); setStreamingContent(''); setStreamingThinking(''); };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await deleteSession(sessionId);
      antMessage.success('会话已删除');
      fetchSessions();
      fetchAllSessions();
      if (currentSessionId === sessionId) handleNewSession();
    } catch { antMessage.error('删除会话失败'); }
  };

  const buildStreamUrl = (endpoint: string, hasFiles: boolean) =>
    hasFiles ? endpoint.replace('/ask', '/ask-multipart') : endpoint;

  const handleSend = async () => {
    const question = inputValue.trim();
    if (!question && attachedFiles.length === 0) return;
    if (selectedKBIds.length === 0 && !autoBindKB && !hideKBSelector) {
      antMessage.warning('请先选择知识库');
      return;
    }
    const displayText = question || `[${attachedFiles.length} 个附件]`;
    setMessages((prev) => [...prev, { id: `user-${Date.now()}`, role: 'user', content: displayText, timestamp: new Date() }]);
    setInputValue('');
    setAttachedFiles([]);
    setLoading(true);
    setStreamingContent('');
    setStreamingThinking('');
    const hasFiles = attachedFiles.length > 0;

    if (streamEndpoint) {
      const baseUrl = process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000/api';
      const token = localStorage.getItem('access_token');
      const endpoint = buildStreamUrl(streamEndpoint, hasFiles);
      try {
        let body: BodyInit;
        const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
        if (hasFiles) {
          const formData = new FormData();
          formData.append('question', question);
          formData.append('web_search_enabled', String(webSearchEnabled));
          formData.append('deep_thinking_enabled', String(deepThinkingEnabled));
          formData.append('kb_ids', JSON.stringify(selectedKBIds));
          if (currentSessionId) formData.append('session_id', String(currentSessionId));
          attachedFiles.forEach((f) => formData.append('files', f));
          body = formData;
        } else {
          headers['Content-Type'] = 'application/json';
          body = JSON.stringify({ question, kb_ids: selectedKBIds, session_id: currentSessionId, web_search_enabled: webSearchEnabled, deep_thinking_enabled: deepThinkingEnabled });
        }
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
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const d = JSON.parse(line.slice(6));
              if (d.type === 'think' && d.token) {
                thinkingText += d.token;
                setStreamingThinking(thinkingText);
              } else if (d.token) {
                fullText += d.token;
                setStreamingContent(fullText);
              }
              if (d.done) {
                newSid = d.session_id || '';
                if (d.thinking) thinkingText = d.thinking;
                if (d.message_id) newMessageId = d.message_id;
              }
              if (d.error) antMessage.error(d.error);
            } catch { /* skip */ }
          }
        }
        if (!currentSessionId && newSid) {
          setCurrentSessionId(newSid);
          fetchAllSessions();
        }
        setMessages((prev) => [...prev, { id: `assistant-${Date.now()}`, role: 'assistant', content: fullText, thinking: thinkingText, messageId: newMessageId, timestamp: new Date() }]);
        setStreamingContent('');
        setStreamingThinking('');
      } catch (error: any) { antMessage.error('请求失败: ' + error.message); setStreamingContent(''); setStreamingThinking(''); } finally { setLoading(false); }
    } else {
      // Non-streaming
      if (hasFiles) {
        // Use multipart endpoint
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

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleFeedback = async (messageId: number, feedbackType: string) => {
    if (!messageId) return;
    try {
      await submitFeedback({ message_id: messageId, feedback_type: feedbackType });
      antMessage.success('感谢您的反馈！');
      setMessages((prev) => prev.map((msg) => msg.messageId === messageId ? { ...msg, feedbackType } : msg));
    } catch { antMessage.error('提交反馈失败'); }
  };

  const openHistory = () => { fetchSessions(); setHistoryVisible(true); };

  const renderReferences = (references: any[]) => {
    if (!references || references.length === 0) return null;
    return (
      <div style={{ marginTop: 12, padding: '8px 12px', background: bgElevated, borderRadius: 6, border: `1px solid ${token.colorBorder}` }}>
        <Space style={{ marginBottom: 4 }}><BookOutlined style={{ color: token.colorPrimary }} /><Text strong style={{ fontSize: 13 }}>参考文献</Text></Space>
        <List size="small" dataSource={references} renderItem={(ref: any, index: number) => (
          <List.Item style={{ padding: '4px 0', border: 'none' }}>
            <Space align="start">
              <Tag color="blue" style={{ minWidth: 20, textAlign: 'center' }}>{index + 1}</Tag>
              <div>
                <Text style={{ fontSize: 13 }}>{ref.title || ref.filename || `文献 ${index + 1}`}</Text>
                {ref.content && <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>{ref.content.substring(0, 200)}{ref.content.length > 200 ? '...' : ''}</Text>}
                {ref.url && <a href={ref.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12 }}><LinkOutlined /> 查看原文</a>}
              </div>
            </Space>
          </List.Item>
        )} />
      </div>
    );
  };

  const renderMessage = (msg: ChatMessage) => {
    const isUser = msg.role === 'user';
    return (
      <div key={msg.id} style={{ display: 'flex', flexDirection: isUser ? 'row-reverse' : 'row', marginBottom: 20, gap: 12 }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: isUser ? token.colorPrimary : token.colorSuccess, color: '#fff', flexShrink: 0, fontSize: 16 }}>
          {isUser ? <UserOutlined /> : <RobotOutlined />}
        </div>
        <div style={{ maxWidth: '80%', padding: '12px 16px', borderRadius: 12, background: isUser ? bgBubbleUser : bgContainer, borderTopRightRadius: isUser ? 4 : 12, borderTopLeftRadius: isUser ? 12 : 4 }}>
          {isUser ? <Text style={{ whiteSpace: 'pre-wrap', fontSize: 14 }}>{msg.content}</Text>
            : <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{msg.content}</ReactMarkdown></div>}
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
            {!isUser && msg.references && msg.references.length > 0 && renderReferences(msg.references)}
          {!isUser && showSafetyWarning && msg.safety_flag && (
            <Alert message="健康提醒" description="以上内容仅供参考，不能替代专业医疗建议。如有身体不适，请及时就医。" type="warning" showIcon icon={<WarningOutlined />} style={{ marginTop: 12, fontSize: 13 }} />
          )}
          {!isUser && msg.disclaimer && <Alert message="免责声明" description={msg.disclaimer} type="info" showIcon style={{ marginTop: 12, fontSize: 13 }} />}
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

  const kbOptions = (kbTypeFilter ? filteredKBs() : knowledgeBases).map((kb) => ({ label: kb.name, value: kb.id }));

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 140px)', gap: 16 }}>
      {/* Sidebar */}
      {!sidebarCollapsed ? (
        <div style={{ width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, overflow: 'hidden' }}>
          <div style={{ padding: '12px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text strong style={{ fontSize: 14 }}>📋 历史对话</Text>
            <Button type="text" size="small" icon={<MenuFoldOutlined />} onClick={() => setSidebarCollapsed(true)} />
          </div>
          <div style={{ padding: '8px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
            <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={handleNewSession} block>新对话</Button>
          </div>
          <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
            {sidebarLoading ? (
              <div style={{ textAlign: 'center', padding: 20 }}><Spin size="small" /></div>
            ) : groupedSessions.length === 0 ? (
              <Empty description="暂无历史对话" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ padding: '20px 0' }} />
            ) : (
              groupedSessions.map(group => (
                <div key={group.key}>
                  <div style={{ padding: '4px 16px 4px 16px', fontSize: 12, color: token.colorTextSecondary, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <MessageOutlined style={{ fontSize: 10 }} /> {group.title}
                  </div>
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
                        background: currentSessionId === session.id ? token.colorPrimaryBg : 'transparent',
                        borderLeft: currentSessionId === session.id ? `3px solid ${token.colorPrimary}` : '3px solid transparent',
                      }}
                    >
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <Text ellipsis style={{ fontSize: 13, fontWeight: currentSessionId === session.id ? 500 : 400 }}>
                          {session.title || `会话 ${session.id.substring(0, 8)}`}
                        </Text>
                        <div style={{ fontSize: 11, color: token.colorTextQuaternary, marginTop: 2 }}>
                          {session.created_at
                            ? new Date(session.created_at).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                            : ''}
                        </div>
                      </div>
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
        <div
          style={{ width: 40, flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, padding: '12px 0', cursor: 'pointer' }}
          onClick={() => setSidebarCollapsed(false)}
          title="展开历史对话"
        >
          <MenuUnfoldOutlined style={{ fontSize: 18, color: token.colorTextSecondary }} />
          <Text style={{ fontSize: 10, color: token.colorTextTertiary, marginTop: 4, writingMode: 'vertical-rl', letterSpacing: 2 }}>历史</Text>
        </div>
      )}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: bgContainer, borderRadius: 8, border: `1px solid ${token.colorBorderSecondary}`, overflow: 'hidden' }}>
        <div style={{ padding: '12px 20px', borderBottom: `1px solid ${token.colorBorderSecondary}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <div><Title level={5} style={{ margin: 0 }}>{title}</Title>{subtitle && <Text type="secondary" style={{ fontSize: 12 }}>{subtitle}</Text>}</div>
          <Space>
            {hideKBSelector ? <Tag color="blue" style={{ marginRight: 0 }}>已绑定所有知识库</Tag>
              : <>{autoBindKB && <Tag color="blue" style={{ marginRight: 0 }}>对话历史已绑定</Tag>}
                <Select mode="multiple" placeholder={autoBindKB ? "可选其他知识库" : "选择知识库"} value={selectedKBIds} onChange={setSelectedKBIds} options={kbOptions} loading={kbLoading} style={{ minWidth: 200, maxWidth: 400 }} allowClear notFoundContent={kbLoading ? <Spin size="small" /> : <Empty description="暂无知识库" />} />
              </>}
            <Tooltip title={webSearchEnabled ? '联网搜索已开启，将同时搜索网络和知识库' : '联网搜索已关闭，仅使用知识库'}>
              <Space size={4}>
                <GlobalOutlined style={{ color: webSearchEnabled ? token.colorPrimary : token.colorTextQuaternary }} />
                <Switch size="small" checked={webSearchEnabled} onChange={setWebSearchEnabled} />
              </Space>
            </Tooltip>
            <Tooltip title={deepThinkingEnabled ? '深度思考已开启，将展示推理过程' : '深度思考已关闭，仅展示最终答案'}>
              <Space size={4}>
                <span style={{ fontSize: 16 }}>🧠</span>
                <Switch size="small" checked={deepThinkingEnabled} onChange={setDeepThinkingEnabled} />
              </Space>
            </Tooltip>
            <Button icon={<HistoryOutlined />} onClick={() => { fetchSessions(); openHistory(); }}>历史记录</Button>
            <Button icon={<PlusOutlined />} onClick={handleNewSession}>新对话</Button>
            {extraActions}
          </Space>
        </div>

        <div
          style={{
            flex: 1, overflow: 'auto', padding: '20px', background: bgLayout,
            outline: isDragOver ? `2px dashed ${token.colorPrimary}` : 'none',
            outlineOffset: -2,
          }}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
          onDrop={(e) => { e.preventDefault(); setIsDragOver(false); if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files); }}
        >
          {isDragOver && (
            <div style={{ textAlign: 'center', padding: 40, color: token.colorPrimary }}>
              <UploadOutlined style={{ fontSize: 36 }} />
              <Title level={5} style={{ color: token.colorPrimary, marginTop: 8 }}>释放文件以附加到对话</Title>
            </div>
          )}
          {sessionLoading ? <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载会话中..." /></div>
            : messages.length === 0 ? (
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
              <>
                {messages.map(renderMessage)}
                {loading && (
                  <div style={{ display: 'flex', flexDirection: 'row', marginBottom: 20, gap: 12 }}>
                    <div style={{ width: 36, height: 36, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: token.colorSuccess, color: '#fff', flexShrink: 0 }}><RobotOutlined /></div>
                    <div style={{ maxWidth: '80%', padding: '12px 16px', borderRadius: 12, background: bgContainer, borderTopLeftRadius: 4 }}>
                      {streamingThinking && (
                        <div style={{ marginBottom: streamingContent ? 12 : 0, padding: 8, background: token.colorFillQuaternary, borderRadius: 6, border: `1px solid ${token.colorBorderSecondary}`, maxHeight: 'none', overflow: 'visible' }}>
                          <Text strong style={{ fontSize: 12, color: token.colorPrimary }}>🧠 深度思考过程</Text>
                          <div className="markdown-content" style={{ marginTop: 4, fontSize: 13, color: token.colorTextSecondary }}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingThinking}</ReactMarkdown>
                          </div>
                        </div>
                      )}
                      {streamingContent ? (
                        <div className="markdown-content"><ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>{streamingContent}</ReactMarkdown></div>
                      ) : (
                        <Space><Spin size="small" /><Text type="secondary">思考中...</Text></Space>
                      )}
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </>
            )}
        </div>

        <div style={{ padding: '12px 20px', borderTop: `1px solid ${token.colorBorderSecondary}`, background: bgContainer }}>
          {/* File attachment preview */}
          {attachedFiles.length > 0 && (
            <div
              style={{
                display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8,
                padding: 8, background: token.colorFillQuaternary, borderRadius: 8,
              }}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
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
                  {isImageFile(file) ? (
                    <img
                      src={URL.createObjectURL(file)}
                      alt={file.name}
                      style={{ width: 28, height: 28, borderRadius: 4, objectFit: 'cover' }}
                    />
                  ) : (
                    <FileOutlined style={{ fontSize: 16, color: token.colorPrimary }} />
                  )}
                  <Text ellipsis style={{ fontSize: 12, maxWidth: 100 }}>{file.name}</Text>
                  <CloseCircleOutlined
                    style={{ color: token.colorError, cursor: 'pointer', fontSize: 12 }}
                    onClick={() => removeFile(file)}
                  />
                </div>
              ))}
            </div>
          )}
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <TextArea ref={inputRef} value={inputValue} onChange={(e) => setInputValue(e.target.value)} onKeyDown={handleKeyDown}
              placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行..." autoSize={{ minRows: 2, maxRows: 6 }} disabled={loading} style={{ flex: 1 }} />
            <Tooltip title="上传图片或文件">
              <Button
                icon={<PaperClipOutlined />}
                onClick={handleFilePicker}
                disabled={loading}
                style={{ height: 42, width: 42 }}
              />
            </Tooltip>
            <Button type="primary" icon={<SendOutlined />} onClick={handleSend} loading={loading}
              disabled={(!inputValue.trim() && attachedFiles.length === 0) || (selectedKBIds.length === 0 && !autoBindKB && !hideKBSelector)} style={{ height: 42 }}>
              发送
            </Button>
          </div>
          {/* Hidden file input */}
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

      <Modal title={<Space><HistoryOutlined />历史会话</Space>} open={historyVisible} onCancel={() => setHistoryVisible(false)} footer={null} width={480}>
        {sessionsLoading ? <div style={{ textAlign: 'center', padding: 40 }}><Spin /></div>
          : sessions.length === 0 ? <Empty description="暂无历史会话" />
          : <List dataSource={sessions} renderItem={(session) => (
              <List.Item actions={[
                <Button type="link" onClick={() => loadSession(session.id)} disabled={sessionLoading}>加载</Button>,
                <Button type="link" danger onClick={() => handleDeleteSession(session.id)}><DeleteOutlined /></Button>,
              ]}>
                <List.Item.Meta title={session.title || `会话 ${session.id.substring(0, 8)}`}
                  description={<Space><Text type="secondary" style={{ fontSize: 12 }}>{session.created_at ? new Date(session.created_at).toLocaleString('zh-CN') : ''}</Text></Space>} />
              </List.Item>
            )} />
        }
      </Modal>

      <style>{`
        .sidebar-session-item:hover { background:${token.colorFillTertiary} !important; }
        .sidebar-session-item:hover .sidebar-delete-btn { opacity:1 !important; }
        .sidebar-delete-btn { opacity:0; transition: opacity 0.15s; }
        .markdown-content h1,.markdown-content h2,.markdown-content h3,.markdown-content h4 { margin-top:12px; margin-bottom:8px; font-weight:600; }
        .markdown-content p { margin-bottom:8px; line-height:1.6; }
        .markdown-content ul,.markdown-content ol { padding-left:20px; margin-bottom:8px; }
        .markdown-content li { margin-bottom:4px; }
        .markdown-content code { background:${token.colorFillSecondary}; padding:2px 6px; border-radius:3px; font-size:0.9em; }
        .markdown-content pre { background:${resolvedMode === 'dark' ? token.colorBgElevated : '#1e1e1e'}; padding:12px; border-radius:6px; overflow-x:auto; margin-bottom:12px; }
        .markdown-content pre code { background:transparent; color:${resolvedMode === 'dark' ? token.colorText : '#d4d4d4'}; padding:0; }
        .markdown-content table { border-collapse:collapse; width:100%; margin-bottom:12px; }
        .markdown-content th,.markdown-content td { border:1px solid ${token.colorBorder}; padding:8px 12px; text-align:left; }
        .markdown-content th { background:${token.colorBgLayout}; font-weight:600; }
        .markdown-content blockquote { border-left:3px solid ${token.colorPrimary}; padding-left:12px; margin:8px 0; color:${token.colorTextSecondary}; }
        .markdown-content a { color:${token.colorPrimary}; }
        .markdown-content hr { margin:16px 0; border:none; border-top:1px solid ${token.colorBorder}; }
        .markdown-content img { max-width:100%; border-radius:4px; }
      `}</style>
    </div>
  );
};

export default ChatInterface;
