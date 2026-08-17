// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）、useCallback（回调缓存）钩子
import React, { useState, useEffect, useCallback } from 'react';
// 从 Ant Design 导入大量 UI 组件：Table（表格）、Button（按钮）、Upload（上传）、Space（间距）、message（消息提示）、Typography（排版）、Tag（标签）、Popconfirm（确认弹窗）、Select（选择器）、Card（卡片）、Empty（空状态）、Spin（加载）、Row（行）、Col（列）、Statistic（统计）、Tooltip（提示）、Modal（模态框）、theme（主题）
import {
  Table,
  Button,
  Upload,
  Space,
  message as antMessage,
  Typography,
  Tag,
  Popconfirm,
  Select,
  Card,
  Empty,
  Spin,
  Row,
  Col,
  Statistic,
  Tooltip,
  Modal,
  Progress,
  theme,
} from 'antd';
// 从 Ant Design 图标库导入：上传、删除、刷新、文件、收件箱、PDF、文本文档、勾选、关闭、同步、预览等图标
import {
  UploadOutlined,
  DeleteOutlined,
  ReloadOutlined,
  FileOutlined,
  InboxOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  SyncOutlined,
  EyeOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
// 从 Ant Design 导入 Upload 组件相关的类型定义
import type { UploadFile, UploadProps } from 'antd';
// 从 react-router-dom 导入 useParams（获取路由参数）和 useNavigate（编程式导航）
import { useParams, useNavigate } from 'react-router-dom';
// 从 API 服务层导入大量函数和类型：获取文档、获取知识库、上传、删除、获取预览等
import {
  getDocuments,
  getKnowledgeBases,
  uploadDocument,
  deleteDocument,
  retryDocumentProcessing,
  rebuildKnowledgeBaseVectors,
  getDocumentFileBlobUrl,
  getDocumentPreview,
  type Document,
  type KnowledgeBase,
  type DocumentPreviewData,
} from '../services/api';
import {
  getDocumentPipelineStatus,
  getDocumentProgress,
  getDocumentProgressMessage,
} from '../utils/documentProcessing';
// 导入 ReactMarkdown Markdown 渲染组件
import ReactMarkdown from 'react-markdown';
// 导入 remark-gfm 插件（支持 GFM：表格、任务列表等）
import remarkGfm from 'remark-gfm';
// 导入 rehype-raw 插件（支持直接渲染 HTML 标签）
import rehypeRaw from 'rehype-raw';

// 解构 Typography 中的 Title（标题）和 Text（文本）组件
const { Title, Text } = Typography;
// 解构 Upload 中的 Dragger（拖拽上传组件）
const { Dragger } = Upload;

// 定义 DocumentManagement 文档管理组件，类型为 React.FC
const DocumentManagement: React.FC = () => {
  // 使用 Ant Design 的 theme token 获取主题设计变量
  const { token } = theme.useToken();
  // 当前选中知识库下的文档列表
  const [docs, setDocs] = useState<Document[]>([]);
  // 所有知识库列表
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  // 当前文档列表的加载状态
  const [loading, setLoading] = useState(false);
  // 当前选中的知识库 ID
  const [selectedKbId, setSelectedKbId] = useState<number | undefined>(undefined);
  // 上传操作中的加载状态
  const [uploading, setUploading] = useState(false);
  // 知识库列表加载状态
  const [kbLoading, setKbLoading] = useState(false);
  // 全量文档列表（用于统计跨知识库的数据）
  const [allDocs, setAllDocs] = useState<Document[]>([]);
  // 批量上传的文件列表
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [retryingDocumentIds, setRetryingDocumentIds] = useState<number[]>([]);
  const [rebuildingVectorStore, setRebuildingVectorStore] = useState(false);

  // 文档预览相关状态
  const [previewVisible, setPreviewVisible] = useState(false);  // 预览弹窗是否可见
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);  // 当前预览的文档
  const [previewContent, setPreviewContent] = useState('');  // 预览文本内容
  const [previewLoading, setPreviewLoading] = useState(false);  // 预览加载状态
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);  // PDF 的 Blob URL

  // 从路由参数中获取 kbId（例如 /documents/3 中的 3）
  const { kbId } = useParams<{ kbId: string }>();
  // 编程式导航
  const navigate = useNavigate();

  // 获取知识库列表的回调函数
  const fetchKBs = useCallback(async () => {
    setKbLoading(true); // 开启知识库加载状态
    try {
      const data = await getKnowledgeBases(); // 调用 API 获取所有知识库
      setKbs(data);

      // 如果 URL 中有 kbId 参数，自动选中对应知识库
      if (kbId) {
        const id = Number(kbId); // 转为数字
        if (data.some((kb) => kb.id === id)) { // 确认知识库存在
          setSelectedKbId(id); // 设置选中
        }
      }
    } catch {
      antMessage.error('获取知识库列表失败');
    } finally {
      setKbLoading(false); // 关闭知识库加载状态
    }
  }, [kbId]);

  // 获取指定知识库下文档列表的回调函数
  const fetchDocs = useCallback(async (kbId?: number, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const data = await getDocuments(kbId); // 调用 API 获取文档，传 kbId 过滤
      setDocs(data); // 更新文档列表
    } catch {
      antMessage.error('获取文档列表失败');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  // 获取全量文档列表（不传参，用于统计）
  const fetchAllDocs = useCallback(async () => {
    try {
      const data = await getDocuments(); // 不传知识库 ID，获取所有文档
      setAllDocs(data);
    } catch {
      // 统计静默失败，使用已有数据
    }
  }, []);

  // 组件挂载时获取知识库列表和全量文档
  useEffect(() => {
    fetchKBs();
    fetchAllDocs();
  }, [fetchKBs, fetchAllDocs]);

  // 选中的知识库变化时，重新获取该知识库的文档列表
  useEffect(() => {
    fetchDocs(selectedKbId);
  }, [selectedKbId, fetchDocs]);

  // 只在存在待处理/处理中任务时轮询，避免空闲页面持续发请求。
  const hasActiveDocuments = docs.some((doc) => {
    const activeStatus = ['pending', 'processing'].includes(getDocumentPipelineStatus(doc));
    // Redis 暂时不可用时尚无 task_id，但 pending 文档仍需轮询等待 Outbox 恢复。
    // 旧数据中没有 task_id 且长期停在 vector=processing 的记录不应永久轮询。
    return activeStatus && (Boolean(doc.processing_task_id) || doc.parse_status === 'pending');
  });

  useEffect(() => {
    if (!hasActiveDocuments) return;
    const interval = window.setInterval(() => {
      fetchDocs(selectedKbId, true);
      fetchAllDocs();
    }, 3000);
    return () => window.clearInterval(interval);
  }, [hasActiveDocuments, selectedKbId, fetchDocs, fetchAllDocs]);

  // 处理单个文件上传：验证格式和大小后调用 API
  const handleUpload = async (file: File) => {
    // 没有选中知识库时不允许上传
    if (!selectedKbId) {
      antMessage.warning('请先选择知识库');
      return false;
    }

    // 验证文件格式：仅允许 PDF、DOC、DOCX、TXT、MD
    const isValid =
      file.type === 'application/pdf' ||
      file.name.endsWith('.pdf') ||
      file.name.endsWith('.doc') ||
      file.name.endsWith('.docx') ||
      file.name.endsWith('.txt') ||
      file.name.endsWith('.md');

    if (!isValid) {
      antMessage.error('只支持 PDF、DOC、DOCX、TXT、MD 格式文件');
      return false;
    }

    // PDF 不限制大小；其它文档保留 50MB 限制。
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    const isWithinNonPdfLimit = file.size / 1024 / 1024 <= 50;
    if (!isPdf && !isWithinNonPdfLimit) {
      antMessage.error('非 PDF 文件大小不能超过 50MB');
      return false;
    }

    setUploading(true); // 开启上传中状态
    try {
      await uploadDocument(selectedKbId, file); // 调用 API 上传文件
      antMessage.success(`${file.name} 上传成功`);
      fetchDocs(selectedKbId); // 刷新当前知识库文档列表
      fetchAllDocs(); // 刷新统计用全量文档列表
    } catch (error: any) {
      antMessage.error('上传失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false); // 关闭上传中状态
    }
    return false; // 阻止 Upload 组件的默认提交行为
  };

  // 批量上传处理：逐个上传文件列表中的所有文件
  const handleBatchUpload = async () => {
    if (uploadFileList.length === 0) {
      antMessage.warning('请先选择文件');
      return;
    }
    if (!selectedKbId) {
      antMessage.warning('请先选择知识库');
      return;
    }

    setUploading(true);
    let successCount = 0;
    let failCount = 0;

    // 遍历文件列表逐一上传
    for (const file of uploadFileList) {
      try {
        if (file.originFileObj) { // 确保文件对象存在
          await uploadDocument(selectedKbId, file.originFileObj);
          successCount++;
        }
      } catch {
        failCount++;
      }
    }

    antMessage.info(`上传完成：成功 ${successCount} 个，失败 ${failCount} 个`);
    setUploadFileList([]); // 清空文件列表
    setUploading(false);
    fetchDocs(selectedKbId); // 刷新文档列表
    fetchAllDocs(); // 刷新统计
  };

  // 处理删除文档
  const handleDelete = async (id: number, filename: string) => {
    try {
      await deleteDocument(id); // 调用 API 删除文档
      antMessage.success(`「${filename}」已删除`);
      fetchDocs(selectedKbId); // 刷新文档列表
      fetchAllDocs(); // 刷新统计
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleRetry = async (doc: Document) => {
    setRetryingDocumentIds((ids) => [...ids, doc.id]);
    try {
      await retryDocumentProcessing(doc.id);
      antMessage.success(`「${doc.filename}」已进入重试队列，将复用已有解析结果`);
      await Promise.all([fetchDocs(selectedKbId, true), fetchAllDocs()]);
    } catch (error: any) {
      antMessage.error('重试失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setRetryingDocumentIds((ids) => ids.filter((id) => id !== doc.id));
    }
  };

  const handleVectorStoreRebuild = () => {
    if (!selectedKbId) {
      antMessage.warning('请先选择知识库');
      return;
    }
    const selectedKb = kbs.find((kb) => kb.id === selectedKbId);
    Modal.confirm({
      title: '使用新版 PDF 能力迭代向量库？',
      content: (
        <div>
          <p>
            将重新解析「{selectedKb?.name || `知识库 ${selectedKbId}`}」中的文档，抽取结构化表格并分析复杂图表，
            然后重新生成向量。处理期间旧向量继续可用，只有新向量完整写入后才会替换。
          </p>
          <Text type="secondary">正在处理的文档会自动跳过，可稍后再次更新。</Text>
        </div>
      ),
      okText: '开始迭代更新',
      cancelText: '取消',
      onOk: async () => {
        setRebuildingVectorStore(true);
        try {
          const result = await rebuildKnowledgeBaseVectors(selectedKbId);
          if (result.scheduled > 0) {
            antMessage.success(result.message);
          } else {
            antMessage.info(result.message);
          }
          await Promise.all([fetchDocs(selectedKbId, true), fetchAllDocs()]);
        } catch (error: any) {
          antMessage.error('向量库更新失败: ' + (error.response?.data?.detail || error.message));
          throw error;
        } finally {
          setRebuildingVectorStore(false);
        }
      },
    });
  };

  // 处理文档预览
  const handlePreview = async (doc: Document) => {
    setPreviewDoc(doc); // 设置当前预览文档
    setPreviewVisible(true); // 显示预览弹窗
    setPreviewLoading(true); // 开启预览加载
    setPreviewContent(''); // 清空之前的内容
    setPreviewBlobUrl(null); // 清空之前的 Blob URL

    try {
      if (doc.file_type === 'pdf') {
        // PDF 文件：获取 Blob URL 用于 iframe 内嵌预览
        const blobUrl = await getDocumentFileBlobUrl(doc.id);
        setPreviewBlobUrl(blobUrl);
      } else {
        // 文本类文件：获取文本内容
        const data: DocumentPreviewData = await getDocumentPreview(doc.id);
        setPreviewContent(data.content);
      }
    } catch (err: any) {
      antMessage.error('加载预览失败: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPreviewLoading(false); // 关闭预览加载
    }
  };

  // 关闭预览弹窗并清理资源
  const handleClosePreview = () => {
    setPreviewVisible(false);
    setPreviewDoc(null);
    setPreviewContent('');
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl); // 释放 Blob URL 避免内存泄漏
      setPreviewBlobUrl(null);
    }
  };

  // 组件卸载时清理 Blob URL 引用的副作用
  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  // 根据解析状态返回对应颜色
  const getStatusColor = (status: string) => {
    const colorMap: Record<string, string> = {
      pending: 'default',      // 待处理：默认灰色
      processing: 'processing', // 处理中：蓝色（processing 状态）
      success: 'success',      // 成功：绿色
      completed: 'success',    // 完成（同义词）：绿色
      failed: 'error',         // 失败：红色
      error: 'error',          // 错误：红色
      review_required: 'warning',
      approved: 'success',
      rejected: 'error',
    };
    return colorMap[status?.toLowerCase()] || 'default';
  };

  // 根据解析状态返回中文标签
  const getStatusLabel = (status: string) => {
    const labelMap: Record<string, string> = {
      pending: '待处理',       // 待处理
      processing: '处理中',     // 正在处理
      success: '已完成',       // 已完成
      completed: '已完成',     // 已完成
      failed: '失败',          // 处理失败
      error: '错误',           // 出错
      review_required: '待质检',
      approved: '已批准',
      rejected: '已拒绝',
    };
    return labelMap[status?.toLowerCase()] || status;
  };

  // 根据解析状态返回对应的图标
  const getStatusIcon = (status: string) => {
    const s = status?.toLowerCase();
    if (s === 'success' || s === 'completed') return <CheckCircleOutlined />; // 成功：勾选
    if (s === 'failed' || s === 'error') return <CloseCircleOutlined />;      // 失败：叉号
    if (s === 'processing') return <SyncOutlined spin />;                     // 处理中：旋转同步
    return null;                                                              // 其他状态无图标
  };

  // 根据文件名后缀返回对应的文件图标
  const getFileIcon = (filename: string) => {
    const ext = filename?.split('.').pop()?.toLowerCase(); // 获取文件扩展名
    if (ext === 'pdf') return <FilePdfOutlined style={{ color: token.colorError, fontSize: 20 }} />; // PDF 红色图标
    return <FileTextOutlined style={{ color: token.colorPrimary, fontSize: 20 }} />; // 其他文件蓝色图标
  };

  // 格式化文件大小：将字节转换为可读格式（B / KB / MB）
  const getFileSizeText = (size?: number) => {
    if (!size) return '-';
    if (size < 1024) return `${size} B`;               // 小于 1KB 显示字节
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`; // 小于 1MB 显示 KB
    return `${(size / (1024 * 1024)).toFixed(1)} MB`; // 大于等于 1MB 显示 MB
  };

  // 构建现有知识库的 ID 集合，用于过滤全量文档
  const existingKbIds = new Set(kbs.map(kb => kb.id));
  // 从全量文档中筛选出属于现有知识库的文档
  const visibleDocs = kbs.length > 0 ? allDocs.filter(d => existingKbIds.has(d.kb_id)) : allDocs;
  // 统计数据：文档总数、处理成功、处理中、处理失败
  const stats = {
    uploaded: visibleDocs.length,                                                      // 文档总数
    success: visibleDocs.filter((d) => getDocumentPipelineStatus(d) === 'success').length,
    processing: visibleDocs.filter((d) => ['pending', 'processing'].includes(getDocumentPipelineStatus(d))).length,
    failed: visibleDocs.filter((d) => getDocumentPipelineStatus(d) === 'failed').length,
  };

  // 定义文档表格列配置
  const columns = [
    {
      title: '文件名',          // 列标题：文件名
      dataIndex: 'filename',
      key: 'filename',
      // 自定义渲染：文件类型图标 + 文件名
      render: (filename: string) => (
        <Space>
          {getFileIcon(filename)}  {/* 根据扩展名显示不同图标 */}
          <Text>{filename}</Text>  {/* 文件名 */}
        </Space>
      ),
    },
    {
      title: '类型',            // 列标题：文件类型
      dataIndex: 'file_type',
      key: 'file_type',
      width: 90,
      // 自定义渲染：无类型显示 "-"
      render: (type: string) => {
        if (!type) return <Tag>-</Tag>;
        return <Tag>{type}</Tag>;
      },
    },
    {
      title: '大小',            // 列标题：文件大小
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      // 显示格式化后的文件大小
      render: (size: number) => (
        <Text type="secondary">{getFileSizeText(size)}</Text>
      ),
    },
    {
      title: '状态',            // 列标题：解析状态
      key: 'status',
      width: 120,
      // 显示带图标和颜色的状态标签，鼠标悬停显示错误信息
      render: (_: any, record: Document) => {
        const value = getDocumentPipelineStatus(record);
        return (
          <Tooltip title={record.error_message || ''}>
            <Tag icon={getStatusIcon(value)} color={getStatusColor(value)}>
              {getStatusLabel(value)}
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '处理进度',
      key: 'progress',
      width: 230,
      render: (_: any, record: Document) => {
        const progress = getDocumentProgress(record);
        const pipelineStatus = getDocumentPipelineStatus(record);
        const failed = pipelineStatus === 'failed';
        const completed = pipelineStatus === 'success';
        const message = getDocumentProgressMessage(record);
        return (
          <div style={{ minWidth: 180 }}>
            <Progress
              percent={progress}
              size="small"
              status={failed ? 'exception' : completed ? 'success' : 'active'}
              format={(percent) => `${percent ?? 0}%`}
              style={{ marginBottom: 0 }}
            />
            <Tooltip title={message}>
              <Text
                type="secondary"
                ellipsis
                style={{ display: 'block', maxWidth: 210, fontSize: 12 }}
              >
                {message}
              </Text>
            </Tooltip>
          </div>
        );
      },
    },
    {
      title: '时间',            // 列标题：创建时间
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      // 格式化为中文本地时间
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',            // 列标题：操作按钮
      key: 'actions',
      width: 230,
      // 预览和删除两个操作按钮
      render: (_: any, record: Document) => (
        <Space>
          {/* 预览按钮：点击触发 handlePreview */}
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record)}>
            预览
          </Button>
          {getDocumentPipelineStatus(record) === 'failed' && (
            <Button
              type="link"
              size="small"
              icon={<ReloadOutlined />}
              loading={retryingDocumentIds.includes(record.id)}
              onClick={() => handleRetry(record)}
            >
              重试处理
            </Button>
          )}
          {/* 删除按钮：带 Popconfirm 二次确认弹窗 */}
          <Popconfirm
            title="确认删除"
            description={`确定要删除「${record.filename}」吗？`}
            onConfirm={() => handleDelete(record.id, record.filename)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }} // 确认按钮显示为危险样式
          >
            <Button type="link" danger icon={<DeleteOutlined />} size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  // 拖拽上传组件的配置属性
  const uploadProps: UploadProps = {
    name: 'file',              // 上传字段名
    multiple: true,            // 允许同时选择多个文件
    fileList: uploadFileList,  // 当前文件列表
    accept: '.pdf,.doc,.docx,.txt,.md', // 限制可选文件类型
    beforeUpload: (file) => {
      // 上传前验证文件格式
      const isValid =
        file.type === 'application/pdf' ||
        file.name.endsWith('.pdf') ||
        file.name.endsWith('.doc') ||
        file.name.endsWith('.docx') ||
        file.name.endsWith('.txt') ||
        file.name.endsWith('.md');

      if (!isValid) {
        antMessage.error('只支持 PDF、DOC、DOCX、TXT、MD 格式文件');
        return Upload.LIST_IGNORE; // 忽略该文件，不加入列表
      }

      // PDF 不限制大小；其它文档保留 50MB 限制。
      const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
      const isWithinNonPdfLimit = file.size / 1024 / 1024 <= 50;
      if (!isPdf && !isWithinNonPdfLimit) {
        antMessage.error('非 PDF 文件大小不能超过 50MB');
        return Upload.LIST_IGNORE;
      }

      return false; // 返回 false 阻止自动上传，由外部按钮控制上传
    },
    onChange: ({ fileList: newFileList }) => {
      setUploadFileList(newFileList); // 更新文件列表状态
    },
    onRemove: (file) => {
      // 移除文件时从列表中过滤掉该文件
      setUploadFileList((prev) => prev.filter((f) => f.uid !== file.uid));
    },
  };

  // 组件 JSX 渲染
  return (
    <div className="page-shell document-page">
      {/*
        页面头部区域：
        - 左侧"文档管理"标题
        - 右侧：知识库选择器 + 单文件上传按钮 + 刷新按钮
      */}
      <div
        className="page-toolbar document-toolbar"
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <div className="page-title-group">
          <div className="page-title-icon"><FolderOpenOutlined /></div>
          <div>
            <Title level={3} style={{ margin: 0 }}>文档管理</Title>
            <Text type="secondary">集中管理医学资料，实时查看解析与向量化进度</Text>
          </div>
        </div>
        <Space wrap className="page-toolbar-actions">
          {/*
            知识库选择器：
            - 下拉选择后切换选中知识库
            - 同步更新 URL 路径（/documents/:kbId 或 /documents）
            - 可清空选择
          */}
          <Select
            placeholder="选择知识库"
            value={selectedKbId}
            onChange={(val) => {
              setSelectedKbId(val);
              if (val) {
                navigate(`/documents/${val}`); // 跳转到带 kbId 的路径
              } else {
                navigate('/documents'); // 跳转到无 kbId 的路径
              }
            }}
            style={{ width: 250 }}
            allowClear                    // 允许清空
            loading={kbLoading}           // 加载中显示旋转
            notFoundContent={<Empty description="暂无知识库" />} // 空数据提示
            options={kbs.map((kb) => ({
              label: kb.name,
              value: kb.id,
            }))}
          />
          {/*
            单文件上传按钮：
            - 使用 Upload 组件包裹按钮
            - 未选择知识库时禁用
            - beforeUpload 传入 handleUpload 处理逻辑
          */}
          <Upload
            accept=".pdf,.docx,.doc,.txt,.md"
            showUploadList={false}         // 不显示上传列表
            beforeUpload={handleUpload}    // 上传前处理
            disabled={!selectedKbId || uploading}
          >
            <Button
              type="primary"
              icon={<UploadOutlined />}
              loading={uploading}
              disabled={!selectedKbId}
            >
              上传文档
            </Button>
          </Upload>
          <Tooltip title="用最新版表格抽取和图表视觉分析重新解析文档，再安全替换向量">
            <Button
              icon={<SyncOutlined spin={rebuildingVectorStore} />}
              loading={rebuildingVectorStore}
              disabled={!selectedKbId || rebuildingVectorStore}
              onClick={handleVectorStoreRebuild}
            >
              迭代更新向量库
            </Button>
          </Tooltip>
          {/*
            刷新按钮：重新加载当前知识库的文档列表
          */}
          <Tooltip title="刷新">
            <Button
              icon={<ReloadOutlined />}
              onClick={() => fetchDocs(selectedKbId)}
            />
          </Tooltip>
        </Space>
      </div>

      {/*
        统计卡片区域：展示所有知识库的文档统计数据
        包括文档总数、处理完成、处理中、失败
      */}
      <Row gutter={[16, 16]} className="document-stats" style={{ marginBottom: 20 }}>
        <Col xs={12} sm={6} md={4}>
          <Card size="small" className="metric-card metric-card-primary">
            <Statistic title="文档总数" value={stats.uploaded} suffix="个" valueStyle={{ color: token.colorPrimary }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small" className="metric-card metric-card-success">
            <Statistic title="处理完成" value={stats.success} valueStyle={{ color: token.colorSuccess }} suffix="个" />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small" className="metric-card metric-card-processing">
            <Statistic title="处理中" value={stats.processing} valueStyle={{ color: token.colorPrimary }} suffix="个" />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small" className="metric-card metric-card-error">
            <Statistic title="失败" value={stats.failed} valueStyle={{ color: token.colorError }} suffix="个" />
          </Card>
        </Col>
      </Row>

      {/*
        批量上传区域：
        - 仅当选中有知识库时显示
        - 使用 Dragger 拖拽组件，支持点击或拖拽选择多个文件
        - 选择文件后显示已选数量和操作按钮（清空 / 开始上传）
      */}
      {selectedKbId && (
        <Card size="small" className="document-upload-card" style={{ marginBottom: 20, background: token.colorBgLayout }}>
          <Dragger {...uploadProps} style={{ background: token.colorBgContainer }}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域批量上传</p>
            <p className="ant-upload-hint">
              支持 PDF、DOC、DOCX、TXT、MD 格式；PDF 不限制大小，其他文件最大 50MB
            </p>
          </Dragger>
          {uploadFileList.length > 0 && (
            <div
              style={{
                marginTop: 12,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <Text type="secondary">
                已选择 {uploadFileList.length} 个文件  {/* 显示已选文件数 */}
              </Text>
              <Space>
                <Button size="small" onClick={() => setUploadFileList([])}>
                  清空          {/* 清空文件选择 */}
                </Button>
                <Button
                  type="primary"
                  size="small"
                  onClick={handleBatchUpload}   // 触发批量上传
                  loading={uploading}
                >
                  开始上传
                </Button>
              </Space>
            </div>
          )}
        </Card>
      )}

      {/*
        文档列表卡片区域：
        - 加载中：显示 Spin 动画
        - 未选知识库：提示"请先选择知识库"
        - 无文档：提示"暂无文档，请上传"
        - 有数据：显示文档表格
      */}
      <Card
        className="document-table-card"
        title={<Space><FileOutlined /><span>文档列表</span></Space>}
        extra={selectedKbId ? <Text type="secondary">共 {docs.length} 个文档</Text> : null}
      >
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : !selectedKbId ? (
          <Empty description="请先选择知识库" />
        ) : docs.length === 0 ? (
          <Empty description="暂无文档，请上传" />
        ) : (
          <Table
            className="document-table"
            dataSource={docs}
            columns={columns}
            rowKey="id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个文档`,
            }}
            scroll={{ x: 1180 }}
          />
        )}
      </Card>

      {/*
        文档预览弹窗 (Modal)：
        - 标题为文档文件名
        - 宽度 800px
        - 底部提供关闭按钮，PDF 文件额外提供下载按钮
        - destroyOnClose 确保关闭时销毁内部状态
      */}
      <Modal
        title={previewDoc?.filename || '文档预览'}
        open={previewVisible}
        onCancel={handleClosePreview}
        width={800}
        footer={
          <Space>
            <Button onClick={handleClosePreview}>关闭</Button>
            {previewDoc?.file_type === 'pdf' && previewBlobUrl && (
              <Button type="primary" href={previewBlobUrl} download={previewDoc.filename}>
                下载            {/* PDF 下载按钮，使用 Blob URL 下载 */}
              </Button>
            )}
          </Space>
        }
        destroyOnClose
      >
        {previewLoading ? (
          // 预览加载中：居中 Spin
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载预览中..." />
          </div>
        ) : previewDoc?.file_type === 'pdf' && previewBlobUrl ? (
          // PDF 预览：使用 iframe 嵌入 Blob URL
          <div style={{ height: '70vh', width: '100%' }}>
            <iframe
              src={previewBlobUrl}
              style={{ width: '100%', height: '100%', border: 'none' }}
              title={previewDoc.filename}
            />
          </div>
        ) : previewDoc?.file_type === 'md' || previewDoc?.file_type === 'markdown' ? (
          // Markdown 预览：使用 ReactMarkdown 渲染，支持 GFM 和原始 HTML
          <div
            style={{
              maxHeight: '70vh',
              overflow: 'auto',
              padding: 16,
              background: token.colorBgContainer,
              borderRadius: 6,
            }}
            className="markdown-content"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeRaw]}>
              {previewContent}
            </ReactMarkdown>
          </div>
        ) : (
          // 纯文本预览：等宽字体显示，支持滚动
          <div
            style={{
              maxHeight: '70vh',
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              padding: 16,
              fontFamily: "'Courier New', monospace",
              fontSize: 14,
              lineHeight: 1.6,
              background: token.colorBgContainer,
              borderRadius: 6,
            }}
          >
            {previewContent || '（无预览内容）'}
          </div>
        )}
      </Modal>
    </div>
  );
};

// 默认导出 DocumentManagement 组件
export default DocumentManagement;
