import React, { useState, useEffect, useCallback } from 'react';
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
  theme,
} from 'antd';
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
} from '@ant-design/icons';
import type { UploadFile, UploadProps } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getDocuments,
  getKnowledgeBases,
  uploadDocument,
  deleteDocument,
  getDocumentFileBlobUrl,
  getDocumentPreview,
  type Document,
  type KnowledgeBase,
  type DocumentPreviewData,
} from '../services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';

const { Title, Text } = Typography;
const { Dragger } = Upload;

const DocumentManagement: React.FC = () => {
  const { token } = theme.useToken();
  const [docs, setDocs] = useState<Document[]>([]);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedKbId, setSelectedKbId] = useState<number | undefined>(undefined);
  const [uploading, setUploading] = useState(false);
  const [kbLoading, setKbLoading] = useState(false);
  const [allDocs, setAllDocs] = useState<Document[]>([]);
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);

  // Preview state
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);
  const [previewContent, setPreviewContent] = useState('');
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);

  const { kbId } = useParams<{ kbId: string }>();
  const navigate = useNavigate();

  const fetchKBs = useCallback(async () => {
    setKbLoading(true);
    try {
      const data = await getKnowledgeBases();
      setKbs(data);

      // Auto-select if kbId param exists
      if (kbId) {
        const id = Number(kbId);
        if (data.some((kb) => kb.id === id)) {
          setSelectedKbId(id);
        }
      }
    } catch {
      antMessage.error('获取知识库列表失败');
    } finally {
      setKbLoading(false);
    }
  }, [kbId]);

  const fetchDocs = useCallback(async (kbId?: number) => {
    setLoading(true);
    try {
      const data = await getDocuments(kbId);
      setDocs(data);
    } catch {
      antMessage.error('获取文档列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAllDocs = useCallback(async () => {
    try {
      const data = await getDocuments();
      setAllDocs(data);
    } catch {
      // stats silently use whatever we have
    }
  }, []);

  useEffect(() => {
    fetchKBs();
    fetchAllDocs();
  }, [fetchKBs, fetchAllDocs]);

  useEffect(() => {
    fetchDocs(selectedKbId);
  }, [selectedKbId, fetchDocs]);

  const handleUpload = async (file: File) => {
    if (!selectedKbId) {
      antMessage.warning('请先选择知识库');
      return false;
    }

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

    const isLessThan20M = file.size / 1024 / 1024 < 20;
    if (!isLessThan20M) {
      antMessage.error('文件大小不能超过 20MB');
      return false;
    }

    setUploading(true);
    try {
      await uploadDocument(selectedKbId, file);
      antMessage.success(`${file.name} 上传成功`);
      fetchDocs(selectedKbId);
      fetchAllDocs();
    } catch (error: any) {
      antMessage.error('上传失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
    return false;
  };

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

    for (const file of uploadFileList) {
      try {
        if (file.originFileObj) {
          await uploadDocument(selectedKbId, file.originFileObj);
          successCount++;
        }
      } catch {
        failCount++;
      }
    }

    antMessage.info(`上传完成：成功 ${successCount} 个，失败 ${failCount} 个`);
    setUploadFileList([]);
    setUploading(false);
    fetchDocs(selectedKbId);
    fetchAllDocs();
  };

  const handleDelete = async (id: number, filename: string) => {
    try {
      await deleteDocument(id);
      antMessage.success(`「${filename}」已删除`);
      fetchDocs(selectedKbId);
      fetchAllDocs();
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handlePreview = async (doc: Document) => {
    setPreviewDoc(doc);
    setPreviewVisible(true);
    setPreviewLoading(true);
    setPreviewContent('');
    setPreviewBlobUrl(null);

    try {
      if (doc.file_type === 'pdf') {
        const blobUrl = await getDocumentFileBlobUrl(doc.id);
        setPreviewBlobUrl(blobUrl);
      } else {
        const data: DocumentPreviewData = await getDocumentPreview(doc.id);
        setPreviewContent(data.content);
      }
    } catch (err: any) {
      antMessage.error('加载预览失败: ' + (err.response?.data?.detail || err.message));
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleClosePreview = () => {
    setPreviewVisible(false);
    setPreviewDoc(null);
    setPreviewContent('');
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
  };

  // Cleanup blob URL on unmount
  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  const getStatusColor = (status: string) => {
    const colorMap: Record<string, string> = {
      pending: 'default',
      processing: 'processing',
      success: 'success',
      completed: 'success',
      failed: 'error',
      error: 'error',
    };
    return colorMap[status?.toLowerCase()] || 'default';
  };

  const getStatusLabel = (status: string) => {
    const labelMap: Record<string, string> = {
      pending: '待处理',
      processing: '处理中',
      success: '已完成',
      completed: '已完成',
      failed: '失败',
      error: '错误',
    };
    return labelMap[status?.toLowerCase()] || status;
  };

  const getStatusIcon = (status: string) => {
    const s = status?.toLowerCase();
    if (s === 'success' || s === 'completed') return <CheckCircleOutlined />;
    if (s === 'failed' || s === 'error') return <CloseCircleOutlined />;
    if (s === 'processing') return <SyncOutlined spin />;
    return null;
  };

  const getFileIcon = (filename: string) => {
    const ext = filename?.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return <FilePdfOutlined style={{ color: token.colorError, fontSize: 20 }} />;
    return <FileTextOutlined style={{ color: token.colorPrimary, fontSize: 20 }} />;
  };

  const getFileSizeText = (size?: number) => {
    if (!size) return '-';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isUploaded = (d: Document) => !d.source_id || d.source_id === 0;
  const existingKbIds = new Set(kbs.map(kb => kb.id));
  const visibleDocs = kbs.length > 0 ? allDocs.filter(d => existingKbIds.has(d.kb_id)) : allDocs;
  const uploadedDocs = visibleDocs.filter(isUploaded);
  const stats = {
    online: visibleDocs.filter((d) => d.source_id != null && d.source_id > 0).length,
    uploaded: uploadedDocs.length,
    success: uploadedDocs.filter((d) => (d.parse_status || d.status) === 'success' || (d.parse_status || d.status) === 'completed').length,
    processing: uploadedDocs.filter((d) => (d.parse_status || d.status) === 'processing').length,
    failed: uploadedDocs.filter((d) => (d.parse_status || d.status) === 'failed' || (d.parse_status || d.status) === 'error').length,
  };

  const columns = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      render: (filename: string) => (
        <Space>
          {getFileIcon(filename)}
          <Text>{filename}</Text>
        </Space>
      ),
    },
    {
      title: '来源',
      key: 'source',
      width: 100,
      render: (_: any, record: Document) => {
        if (record.source_id != null && record.source_id > 0) {
          return <Tag icon={<SyncOutlined />} color="blue">线上</Tag>;
        }
        return <Tag icon={<UploadOutlined />} color="green">上传</Tag>;
      },
    },
    {
      title: '类型',
      dataIndex: 'file_type',
      key: 'file_type',
      width: 90,
      render: (type: string) => {
        if (!type) return <Tag>-</Tag>;
        return <Tag>{type === 'source_text' ? '文本' : type}</Tag>;
      },
    },
    {
      title: '大小',
      dataIndex: 'file_size',
      key: 'file_size',
      width: 100,
      render: (size: number) => (
        <Text type="secondary">{getFileSizeText(size)}</Text>
      ),
    },
    {
      title: '状态',
      key: 'status',
      width: 120,
      render: (_: any, record: Document) => {
        const value = record.parse_status || record.status || 'pending';
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
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 150,
      render: (_: any, record: Document) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handlePreview(record)}>
            预览
          </Button>
          <Popconfirm
            title="确认删除"
            description={`确定要删除「${record.filename}」吗？`}
            onConfirm={() => handleDelete(record.id, record.filename)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" danger icon={<DeleteOutlined />} size="small">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    fileList: uploadFileList,
    accept: '.pdf,.doc,.docx,.txt,.md',
    beforeUpload: (file) => {
      const isValid =
        file.type === 'application/pdf' ||
        file.name.endsWith('.pdf') ||
        file.name.endsWith('.doc') ||
        file.name.endsWith('.docx') ||
        file.name.endsWith('.txt') ||
        file.name.endsWith('.md');

      if (!isValid) {
        antMessage.error('只支持 PDF、DOC、DOCX、TXT、MD 格式文件');
        return Upload.LIST_IGNORE;
      }

      const isLessThan20M = file.size / 1024 / 1024 < 20;
      if (!isLessThan20M) {
        antMessage.error('文件大小不能超过 20MB');
        return Upload.LIST_IGNORE;
      }

      return false;
    },
    onChange: ({ fileList: newFileList }) => {
      setUploadFileList(newFileList);
    },
    onRemove: (file) => {
      setUploadFileList((prev) => prev.filter((f) => f.uid !== file.uid));
    },
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          文档管理
        </Title>
        <Space>
          <Select
            placeholder="选择知识库"
            value={selectedKbId}
            onChange={(val) => {
              setSelectedKbId(val);
              if (val) {
                navigate(`/documents/${val}`);
              } else {
                navigate('/documents');
              }
            }}
            style={{ width: 250 }}
            allowClear
            loading={kbLoading}
            notFoundContent={<Empty description="暂无知识库" />}
            options={kbs.map((kb) => ({
              label: kb.name,
              value: kb.id,
            }))}
          />
          <Upload
            accept=".pdf,.docx,.doc,.txt,.md"
            showUploadList={false}
            beforeUpload={handleUpload}
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
          <Tooltip title="刷新">
            <Button
              icon={<ReloadOutlined />}
              onClick={() => fetchDocs(selectedKbId)}
            />
          </Tooltip>
        </Space>
      </div>

      {/* Stats — all existing KBs combined */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="线上文档" value={stats.online} suffix="个" valueStyle={{ color: token.colorPrimary }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="线下文档" value={stats.uploaded} suffix="个" valueStyle={{ color: token.colorSuccess }} />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="处理完成" value={stats.success} valueStyle={{ color: token.colorSuccess }} suffix="个" />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="处理中" value={stats.processing} valueStyle={{ color: token.colorPrimary }} suffix="个" />
          </Card>
        </Col>
        <Col xs={12} sm={6} md={4}>
          <Card size="small">
            <Statistic title="失败" value={stats.failed} valueStyle={{ color: token.colorError }} suffix="个" />
          </Card>
        </Col>
      </Row>

      {/* Batch upload area */}
      {selectedKbId && (
        <Card size="small" style={{ marginBottom: 16, background: token.colorBgLayout }}>
          <Dragger {...uploadProps} style={{ background: token.colorBgContainer }}>
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域批量上传</p>
            <p className="ant-upload-hint">
              支持 PDF、DOC、DOCX、TXT、MD 格式，单个文件不超过 20MB
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
                已选择 {uploadFileList.length} 个文件
              </Text>
              <Space>
                <Button size="small" onClick={() => setUploadFileList([])}>
                  清空
                </Button>
                <Button
                  type="primary"
                  size="small"
                  onClick={handleBatchUpload}
                  loading={uploading}
                >
                  开始上传
                </Button>
              </Space>
            </div>
          )}
        </Card>
      )}

      {/* Document table */}
      <Card>
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
            dataSource={docs}
            columns={columns}
            rowKey="id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个文档`,
            }}
          />
        )}
      </Card>

      {/* Document Preview Modal */}
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
                下载
              </Button>
            )}
          </Space>
        }
        destroyOnClose
      >
        {previewLoading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载预览中..." />
          </div>
        ) : previewDoc?.file_type === 'pdf' && previewBlobUrl ? (
          <div style={{ height: '70vh', width: '100%' }}>
            <iframe
              src={previewBlobUrl}
              style={{ width: '100%', height: '100%', border: 'none' }}
              title={previewDoc.filename}
            />
          </div>
        ) : previewDoc?.file_type === 'md' || previewDoc?.file_type === 'markdown' ? (
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

export default DocumentManagement;
