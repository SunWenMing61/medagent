import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Typography,
  Card,
  Popconfirm,
  Tabs,
  message as antMessage,
  Spin,
  Empty,
  Tooltip,
  Badge,
  Switch,
  InputNumber,
  Row,
  Col,
  theme,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  DatabaseOutlined,
  SearchOutlined,
  ReloadOutlined,
  FolderOpenOutlined,
  SyncOutlined,
  GlobalOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  getKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getDocuments,
  getSources,
  createSource,
  updateSource,
  deleteSource,
  triggerSourceSync,
  getSourceStatus,
  getSourceSchemas,
  type KnowledgeBase,
  type CreateKBParams,
  type KnowledgeSource,
  type CreateSourceParams,
  type SourceSchemaInfo,
} from '../services/api';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

// Source type display config
const SOURCE_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  pubmed: { label: 'PubMed', color: 'blue' },
  msd_manual: { label: '默沙东诊疗手册', color: 'green' },
  drug_label: { label: '药品说明书', color: 'purple' },
};

const SYNC_STATUS_CONFIG: Record<string, { label: string; color: string; spinning?: boolean }> = {
  idle: { label: '待同步', color: 'default' },
  syncing: { label: '同步中', color: 'processing', spinning: true },
  success: { label: '同步成功', color: 'success' },
  failed: { label: '同步失败', color: 'error' },
};

// ========== JSON Schema dynamic form renderer ==========
function renderSchemaFields(
  schema: Record<string, any>,
  configValues: Record<string, any>,
  onChange: (key: string, value: any) => void,
): React.ReactNode[] {
  const fields: React.ReactNode[] = [];
  const properties = schema?.properties || {};
  const required = schema?.required || [];

  for (const [key, prop] of Object.entries<any>(properties)) {
    const isRequired = required.includes(key);
    const value = configValues[key] ?? prop.default ?? '';

    let component: React.ReactNode;

    if (prop.enum) {
      const options = prop.enum.map((val: string, idx: number) => ({
        label: prop.enumNames?.[idx] || val,
        value: val,
      }));
      component = (
        <Select value={value} onChange={(v) => onChange(key, v)} options={options} style={{ width: '100%' }} />
      );
    } else if (prop.type === 'boolean') {
      component = <Switch checked={!!value} onChange={(v) => onChange(key, v)} />;
    } else if (prop.type === 'integer' || prop.format === 'number') {
      component = (
        <InputNumber value={value} onChange={(v) => onChange(key, v)} min={prop.minimum} max={prop.maximum} style={{ width: '100%' }} />
      );
    } else if (prop.type === 'string' && prop.format === 'date') {
      component = <Input value={value} onChange={(e) => onChange(key, e.target.value)} placeholder={prop.description || key} type="date" />;
    } else if (prop.type === 'string') {
      component = <Input value={value} onChange={(e) => onChange(key, e.target.value)} placeholder={prop.description || key} />;
    } else {
      component = <Input value={typeof value === 'object' ? JSON.stringify(value) : String(value)} onChange={(e) => onChange(key, e.target.value)} />;
    }

    fields.push(
      <Form.Item key={key} label={<Space size={4}><span>{prop.title || key}</span>{isRequired && <Text type="danger">*</Text>}</Space>} help={prop.description}>
        {component}
      </Form.Item>,
    );
  }
  return fields;
}

/** Simple stat number display */
const StatNumber: React.FC<{ value: number; label: string; color: string }> = ({ value, label, color }) => {
  const { token } = theme.useToken();
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>
      <div style={{ fontSize: 13, color: token.colorTextSecondary }}>{label}</div>
    </div>
  );
};

// ========== Offline (本地) KB Tab ==========
const OfflineKBTab: React.FC<{
  searchText: string;
  refreshTrigger: number;
  onRefresh: () => void;
}> = ({ searchText, refreshTrigger, onRefresh }) => {
  const { token } = theme.useToken();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [docCountMap, setDocCountMap] = useState<Record<number, number>>({});
  const [form] = Form.useForm();
  const navigate = useNavigate();

  const fetchKBs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getKnowledgeBases();
      setKbs(data);
      const countMap: Record<number, number> = {};
      await Promise.all(
        data.map(async (kb) => {
          try {
            const docs = await getDocuments(kb.id);
            countMap[kb.id] = docs.length;
          } catch {
            countMap[kb.id] = 0;
          }
        }),
      );
      setDocCountMap(countMap);
    } catch (error: any) {
      antMessage.error('获取知识库列表失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKBs();
    const timer = setInterval(fetchKBs, 30000);
    return () => clearInterval(timer);
  }, [fetchKBs, refreshTrigger]);

  const handleCreate = async (values: CreateKBParams) => {
    setSubmitting(true);
    try {
      await createKnowledgeBase(values);
      antMessage.success('知识库创建成功');
      setCreateModalVisible(false);
      form.resetFields();
      fetchKBs();
      onRefresh();
    } catch (error: any) {
      antMessage.error('创建失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    try {
      await deleteKnowledgeBase(id);
      antMessage.success(`知识库「${name}」已删除`);
      fetchKBs();
      onRefresh();
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getTypeLabel = (type: string) => {
    const m: Record<string, string> = { general: '通用', drug: '药品', paper: '文献', health: '健康', medical: '医学', chat_history: '对话历史' };
    return m[type.toLowerCase()] || type;
  };

  const getTypeColor = (type: string) => {
    const m: Record<string, string> = { general: 'blue', drug: 'green', paper: 'purple', health: 'orange', medical: 'red', chat_history: 'cyan' };
    return m[type.toLowerCase()] || 'default';
  };

  const filteredKBs = kbs.filter(
    (kb) =>
      kb.name.toLowerCase().includes(searchText.toLowerCase()) ||
      kb.description.toLowerCase().includes(searchText.toLowerCase()),
  );

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: KnowledgeBase) => (
        <Space>
          {record.type === 'chat_history' ? (
            <SyncOutlined style={{ color: '#13c2c2' }} />
          ) : (
            <DatabaseOutlined style={{ color: token.colorPrimary }} />
          )}
          {record.type === 'chat_history' ? (
            <span>{name}<Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>（自动记录所有对话，实时更新）</Text></span>
          ) : (
            <a onClick={() => navigate(`/documents/${record.id}`)}>{name}</a>
          )}
        </Space>
      ),
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, width: 250 },
    { title: '类型', dataIndex: 'type', key: 'type', width: 100, render: (type: string) => <Tag color={getTypeColor(type)}>{getTypeLabel(type)}</Tag> },
    {
      title: '可见性', dataIndex: 'visibility', key: 'visibility', width: 80,
      render: (vis: string) => <Badge status={vis === 'public' ? 'success' : 'default'} text={vis === 'public' ? '公开' : '私有'} />,
    },
    { title: '文档数', key: 'docCount', width: 80, render: (_: any, record: KnowledgeBase) => <Tag>{docCountMap[record.id] ?? 0}</Tag> },
    {
      title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180,
      render: (date: string) => (date ? new Date(date).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '操作', key: 'actions', width: 200,
      render: (_: any, record: KnowledgeBase) => (
        <Space>
          {record.type === 'chat_history' ? (
            <Text type="secondary" style={{ fontSize: 12 }}>内置知识库</Text>
          ) : (
            <>
              <Button type="link" size="small" icon={<FolderOpenOutlined />} onClick={() => navigate(`/documents/${record.id}`)}>
                文档
              </Button>
              <Popconfirm
                title="确认删除"
                description={`确定要删除知识库「${record.name}」吗？关联的文档将被永久删除。`}
                onConfirm={() => handleDelete(record.id, record.name)}
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                  删除
                </Button>
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={5} style={{ margin: 0 }}>线下知识库</Title>
        <Space>
          <Tooltip title="刷新">
            <Button icon={<ReloadOutlined />} onClick={fetchKBs} />
          </Tooltip>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.resetFields(); setCreateModalVisible(true); }}>
            创建知识库
          </Button>
        </Space>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载中..." /></div>
        ) : filteredKBs.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的知识库' : '暂无线下知识库，点击上方按钮创建'} />
        ) : (
          <Table dataSource={filteredKBs} columns={columns} rowKey="id"
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 个知识库` }}
            scroll={{ x: 900 }}
          />
        )}
      </Card>

      <Modal title={<Space><PlusOutlined />创建知识库</Space>} open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)} footer={null} width={520} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={handleCreate}
          initialValues={{ type: 'general', visibility: 'private' }}>
          <Form.Item name="name" label="知识库名称" rules={[{ required: true, message: '请输入知识库名称' }, { max: 100 }]}>
            <Input placeholder="请输入知识库名称" />
          </Form.Item>
          <Form.Item name="description" label="描述" rules={[{ max: 500 }]}>
            <TextArea rows={3} placeholder="请输入知识库描述" />
          </Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true, message: '请选择知识库类型' }]}>
            <Select options={[
              { label: '通用', value: 'general' }, { label: '药品', value: 'drug' },
              { label: '文献', value: 'paper' }, { label: '健康', value: 'health' }, { label: '医学', value: 'medical' },
            ]} />
          </Form.Item>
          <Form.Item name="visibility" label="可见性" rules={[{ required: true, message: '请选择可见性' }]}>
            <Select options={[{ label: '公开', value: 'public' }, { label: '私有', value: 'private' }]} />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setCreateModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>创建</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ========== Online (线上) Source Tab ==========
const OnlineSourceTab: React.FC<{
  searchText: string;
  refreshTrigger: number;
  onRefresh: () => void;
}> = ({ searchText, refreshTrigger, onRefresh }) => {
  const { token } = theme.useToken();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [schemas, setSchemas] = useState<Record<string, SourceSchemaInfo>>({});
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set());
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [selectedSourceType, setSelectedSourceType] = useState<string>('pubmed');
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [editConfigValues, setEditConfigValues] = useState<Record<string, any>>({});
  const pollRef = useRef<Map<number, NodeJS.Timeout>>(new Map());
  const navigate = useNavigate();

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSources();
      const newSyncingIds = new Set<number>();
      for (const s of data) {
        if (s.sync_status === 'syncing') newSyncingIds.add(s.id);
      }
      setSyncingIds(newSyncingIds);
      setSources(data);
    } catch (error: any) {
      antMessage.error('获取知识源列表失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSchemas = useCallback(async () => {
    try {
      const data = await getSourceSchemas();
      setSchemas(data);
    } catch { /* silent */ }
  }, []);

  const fetchKBs = useCallback(async () => {
    try {
      const data = await getKnowledgeBases();
      setKbs(data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchSources(); fetchSchemas(); fetchKBs(); }, [fetchSources, fetchSchemas, fetchKBs, refreshTrigger]);

  const pollStatus = useCallback(async (sourceId: number) => {
    const check = async () => {
      try {
        const status = await getSourceStatus(sourceId);
        if (status.sync_status !== 'syncing') {
          setSyncingIds((prev) => { const next = new Set(prev); next.delete(sourceId); return next; });
          fetchSources();
          if (status.sync_status === 'success') antMessage.success('知识源同步完成');
          else if (status.sync_status === 'failed') antMessage.error('同步失败: ' + (status.error_message || '未知错误'));
          return true;
        }
      } catch { /* continue */ }
      return false;
    };
    const done = await check();
    if (!done) {
      const interval = setInterval(async () => {
        const finished = await check();
        if (finished && pollRef.current.has(sourceId)) { clearInterval(interval); pollRef.current.delete(sourceId); }
      }, 3000);
      pollRef.current.set(sourceId, interval);
    }
  }, [fetchSources]);

  useEffect(() => {
    syncingIds.forEach((id) => { if (!pollRef.current.has(id)) pollStatus(id); });
  }, [syncingIds, pollStatus]);

  useEffect(() => {
    return () => { pollRef.current.forEach((interval) => clearInterval(interval)); pollRef.current.clear(); };
  }, []);

  const handleSourceTypeChange = (type: string) => {
    setSelectedSourceType(type);
    setConfigValues(schemas[type]?.defaults || {});
    form.setFieldsValue({ source_type: type });
  };

  const handleCreate = async (values: any) => {
    setSubmitting(true);
    try {
      await createSource({ kb_id: values.kb_id, source_type: values.source_type, name: values.name, config: configValues });
      antMessage.success('知识源创建成功');
      setCreateModalVisible(false);
      form.resetFields();
      setConfigValues({});
      fetchSources();
      onRefresh();
    } catch (error: any) {
      antMessage.error('创建失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (source: KnowledgeSource) => {
    setEditingSource(source);
    setSelectedSourceType(source.source_type);
    let parsedConfig: Record<string, any> = {};
    try { parsedConfig = typeof source.config === 'string' ? JSON.parse(source.config) : source.config; } catch { parsedConfig = {}; }
    setEditConfigValues(parsedConfig);
    editForm.setFieldsValue({ name: source.name, source_type: source.source_type, kb_id: source.kb_id });
    setEditModalVisible(true);
  };

  const handleEditSubmit = async (values: any) => {
    if (!editingSource) return;
    setSubmitting(true);
    try {
      const params: any = { name: values.name, config: editConfigValues };
      if (values.kb_id && values.kb_id !== editingSource.kb_id) {
        params.kb_id = values.kb_id;
      }
      await updateSource(editingSource.id, params);
      antMessage.success('知识源更新成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingSource(null);
      fetchSources();
    } catch (error: any) {
      antMessage.error('更新失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number, name: string) => {
    try {
      const result = await deleteSource(id);
      antMessage.success(`已删除知识源「${name}」，共清理 ${result.deleted_documents} 个文档`);
      fetchSources();
      onRefresh();
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleSync = async (id: number) => {
    try {
      await triggerSourceSync(id);
      antMessage.info('同步已启动');
      setSyncingIds((prev) => new Set(prev).add(id));
      fetchSources();
    } catch (error: any) {
      antMessage.error('同步启动失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleConfigChange = (key: string, value: any) => setConfigValues((prev) => ({ ...prev, [key]: value }));
  const handleEditConfigChange = (key: string, value: any) => setEditConfigValues((prev) => ({ ...prev, [key]: value }));

  const filteredSources = sources.filter(
    (s) => s.name.toLowerCase().includes(searchText.toLowerCase()) || s.source_type.toLowerCase().includes(searchText.toLowerCase()),
  );
  const currentSchema = schemas[selectedSourceType];
  const totalSources = sources.length;
  const syncedCount = sources.filter((s) => s.sync_status === 'success').length;
  const failedCount = sources.filter((s) => s.sync_status === 'failed').length;
  const totalDocs = sources.reduce((sum, s) => sum + (s.document_count || 0), 0);

  const getSourceTypeTag = (type: string) => {
    const cfg = SOURCE_TYPE_CONFIG[type] || { label: type, color: 'default' };
    return <Tag color={cfg.color}>{cfg.label}</Tag>;
  };

  const getSyncStatusBadge = (status: string) => {
    const cfg = SYNC_STATUS_CONFIG[status] || { label: status, color: 'default' };
    return <Badge status={cfg.color as any} text={<Space size={4}>{cfg.spinning && <SyncOutlined spin />}<span>{cfg.label}</span></Space>} />;
  };

  const getKbName = (kbId: number) => {
    const kb = kbs.find((k) => k.id === kbId);
    return kb?.name || `知识库 #${kbId}`;
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string) => <Space><GlobalOutlined style={{ color: token.colorPrimary }} /><span>{name}</span></Space>,
    },
    { title: '类型', dataIndex: 'source_type', key: 'source_type', width: 140, render: (type: string) => getSourceTypeTag(type) },
    {
      title: '目标知识库', key: 'kb_id', width: 180,
      render: (_: any, record: KnowledgeSource) => (
        <Space><DatabaseOutlined /><a onClick={() => navigate(`/documents/${record.kb_id}`)}>{getKbName(record.kb_id)}</a></Space>
      ),
    },
    { title: '同步状态', dataIndex: 'sync_status', key: 'sync_status', width: 130,
      render: (status: string, record: KnowledgeSource) => (
        <Space>{getSyncStatusBadge(status)}{status === 'failed' && record.error_message && <Tooltip title={record.error_message}><WarningOutlined style={{ color: token.colorError }} /></Tooltip>}</Space>
      ),
    },
    { title: '文档数', key: 'documentCount', width: 80, render: (_: any, record: KnowledgeSource) => <Tag>{record.document_count ?? 0}</Tag> },
    { title: '上次同步', dataIndex: 'last_sync_at', key: 'last_sync_at', width: 180, render: (date: string) => date ? new Date(date).toLocaleString('zh-CN') : '-' },
    {
      title: '操作', key: 'actions', width: 220,
      render: (_: any, record: KnowledgeSource) => {
        const isSyncing = syncingIds.has(record.id);
        return (
          <Space>
            <Button type="link" size="small" icon={<SyncOutlined spin={isSyncing} />} onClick={() => handleSync(record.id)} disabled={isSyncing}>同步</Button>
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
            <Popconfirm title="确认删除" description={`确定要删除知识源「${record.name}」吗？同步的文档也会被清理。`}
              onConfirm={() => handleDelete(record.id, record.name)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <div>
      {/* Stats cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><StatNumber value={totalSources} label="知识源总数" color={token.colorPrimary} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={syncedCount} label="同步成功" color={token.colorSuccess} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={failedCount} label="同步失败" color={token.colorError} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={totalDocs} label="同步文档数" color={token.colorPrimary} /></Card></Col>
      </Row>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={5} style={{ margin: 0 }}>线上知识源</Title>
        <Space>
          <Tooltip title="刷新"><Button icon={<ReloadOutlined />} onClick={fetchSources} /></Tooltip>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            form.resetFields();
            const firstType = Object.keys(schemas)[0] || 'pubmed';
            setSelectedSourceType(firstType);
            setConfigValues(schemas[firstType]?.defaults || {});
            setCreateModalVisible(true);
          }}>
            添加知识源
          </Button>
        </Space>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载中..." /></div>
        ) : filteredSources.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的知识源' : '暂无线上知识源，点击上方按钮添加'} />
        ) : (
          <Table dataSource={filteredSources} columns={columns} rowKey="id"
            pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 个知识源` }}
            scroll={{ x: 1100 }}
          />
        )}
      </Card>

      {/* Create Source Modal */}
      <Modal title={<Space><PlusOutlined />添加知识源</Space>} open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)} footer={null} width={600} destroyOnClose>
        <Form form={form} layout="vertical" onFinish={handleCreate} initialValues={{ source_type: selectedSourceType }}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入知识源名称' }, { max: 100 }]}>
            <Input placeholder="例如：高血压研究文献、心血管疾病诊疗指南" />
          </Form.Item>
          <Form.Item name="source_type" label="数据源类型" rules={[{ required: true, message: '请选择数据源类型' }]}>
            <Select onChange={handleSourceTypeChange}
              options={Object.entries(SOURCE_TYPE_CONFIG).map(([key, cfg]) => ({ label: cfg.label, value: key }))} />
          </Form.Item>
          <Form.Item name="kb_id" label="目标知识库" rules={[{ required: true, message: '请选择目标知识库' }]}>
            <Select placeholder="选择要将内容同步到的知识库"
              options={kbs.map((kb) => ({ label: `${kb.name} (${kb.type})`, value: kb.id }))} />
          </Form.Item>
          {currentSchema && (
            <Card size="small" title={currentSchema.display_name + ' 配置'} style={{ marginBottom: 16 }}>
              {renderSchemaFields(currentSchema.config_schema, configValues, handleConfigChange)}
            </Card>
          )}
          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setCreateModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>创建</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Source Modal */}
      <Modal title={<Space><EditOutlined />编辑知识源</Space>} open={editModalVisible}
        onCancel={() => setEditModalVisible(false)} footer={null} width={600} destroyOnClose>
        <Form form={editForm} layout="vertical" onFinish={handleEditSubmit}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入知识源名称' }, { max: 100 }]}>
            <Input placeholder="请输入知识源名称" />
          </Form.Item>
          <Form.Item name="source_type" label="数据源类型"><Input disabled /></Form.Item>
          <Form.Item name="kb_id" label="关联知识库" rules={[{ required: true, message: '请选择关联知识库' }]}>
            <Select
              placeholder="选择关联的知识库"
              options={kbs.map((kb) => ({
                label: `${kb.name} (${kb.type})`,
                value: kb.id,
              }))}
            />
          </Form.Item>
          {currentSchema && editingSource && (
            <Card size="small" title={currentSchema.display_name + ' 配置'} style={{ marginBottom: 16 }}>
              {renderSchemaFields(currentSchema.config_schema, editConfigValues, handleEditConfigChange)}
            </Card>
          )}
          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setEditModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>保存</Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

// ========== Main KBManagement Page (two tabs) ==========
const KBManagement: React.FC = () => {
  const [searchText, setSearchText] = useState('');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const location = useLocation();

  // Check if URL query has ?tab=online to switch to online tab
  const getDefaultTab = () => {
    const params = new URLSearchParams(location.search);
    return params.get('tab') === 'online' ? 'online' : 'offline';
  };

  const triggerRefresh = () => setRefreshTrigger((prev) => prev + 1);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>知识库管理</Title>
        <Input
          placeholder="搜索..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 200 }}
          allowClear
        />
      </div>

      <Tabs defaultActiveKey={getDefaultTab()} items={[
        {
          key: 'offline',
          label: <Space><DatabaseOutlined />线下知识库</Space>,
          children: <OfflineKBTab searchText={searchText} refreshTrigger={refreshTrigger} onRefresh={triggerRefresh} />,
        },
        {
          key: 'online',
          label: <Space><GlobalOutlined />线上知识源</Space>,
          children: <OnlineSourceTab searchText={searchText} refreshTrigger={refreshTrigger} onRefresh={triggerRefresh} />,
        },
      ]} />
    </div>
  );
};

export default KBManagement;
