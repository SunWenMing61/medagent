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
  message as antMessage,
  Spin,
  Empty,
  Tooltip,
  Badge,
  Switch,
  InputNumber,
  Row,
  Col,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ReloadOutlined,
  SyncOutlined,
  GlobalOutlined,
  SearchOutlined,
  DatabaseOutlined,
  LinkOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  getSources,
  createSource,
  updateSource,
  deleteSource,
  triggerSourceSync,
  getSourceStatus,
  getSourceSchemas,
  getKnowledgeBases,
  type KnowledgeSource,
  type CreateSourceParams,
  type SourceSchemaInfo,
  type KnowledgeBase,
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

/** Render dynamic form fields from a JSON Schema */
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
      // Select dropdown
      const options = prop.enum.map((val: string, idx: number) => ({
        label: prop.enumNames?.[idx] || val,
        value: val,
      }));
      component = (
        <Select
          value={value}
          onChange={(v) => onChange(key, v)}
          options={options}
          style={{ width: '100%' }}
        />
      );
    } else if (prop.type === 'boolean') {
      component = (
        <Switch
          checked={!!value}
          onChange={(v) => onChange(key, v)}
        />
      );
    } else if (prop.type === 'integer' || prop.format === 'number') {
      component = (
        <InputNumber
          value={value}
          onChange={(v) => onChange(key, v)}
          min={prop.minimum}
          max={prop.maximum}
          style={{ width: '100%' }}
        />
      );
    } else if (prop.type === 'string' && prop.format === 'date') {
      component = (
        <Input
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          placeholder={prop.description || key}
          type="date"
        />
      );
    } else if (prop.type === 'string') {
      component = (
        <Input
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          placeholder={prop.description || key}
        />
      );
    } else {
      component = (
        <Input
          value={typeof value === 'object' ? JSON.stringify(value) : String(value)}
          onChange={(e) => onChange(key, e.target.value)}
        />
      );
    }

    fields.push(
      <Form.Item
        key={key}
        label={
          <Space size={4}>
            <span>{prop.title || key}</span>
            {isRequired && <Text type="danger">*</Text>}
          </Space>
        }
        help={prop.description}
      >
        {component}
      </Form.Item>,
    );
  }

  return fields;
}

const SourceManagement: React.FC = () => {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [schemas, setSchemas] = useState<Record<string, SourceSchemaInfo>>({});
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set());

  // Form state
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();

  // Dynamic config for create form
  const [selectedSourceType, setSelectedSourceType] = useState<string>('pubmed');
  const [configValues, setConfigValues] = useState<Record<string, any>>({});
  const [editConfigValues, setEditConfigValues] = useState<Record<string, any>>({});

  const pollRef = useRef<Map<number, NodeJS.Timeout>>(new Map());
  const notifiedRef = useRef<Set<number>>(new Set());

  const navigate = useNavigate();

  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSources();
      // Check if any are still syncing and start polling
      const newSyncingIds = new Set<number>();
      for (const s of data) {
        if (s.sync_status === 'syncing') {
          newSyncingIds.add(s.id);
        }
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
    } catch (error: any) {
      antMessage.error('获取源配置模板失败: ' + (error.response?.data?.detail || error.message));
    }
  }, []);

  const fetchKBs = useCallback(async () => {
    try {
      const data = await getKnowledgeBases();
      setKbs(data);
    } catch {
      // silent
    }
  }, []);

  useEffect(() => {
    fetchSources();
    fetchSchemas();
    fetchKBs();
  }, [fetchSources, fetchSchemas, fetchKBs]);

  // Poll sync status for syncing sources
  const pollStatus = useCallback(async (sourceId: number) => {
    const check = async () => {
      try {
        const status = await getSourceStatus(sourceId);
        if (status.sync_status !== 'syncing') {
          setSyncingIds((prev) => {
            const next = new Set(prev);
            next.delete(sourceId);
            return next;
          });
          fetchSources();
          // Only notify once per source per sync cycle
          if (!notifiedRef.current.has(sourceId)) {
            notifiedRef.current.add(sourceId);
            if (status.sync_status === 'success') {
              antMessage.success(`知识源同步完成`);
            } else if (status.sync_status === 'failed') {
              antMessage.error(`同步失败: ${status.error_message || '未知错误'}`);
            }
          }
          return true; // done
        }
      } catch {
        // continue polling
      }
      return false;
    };

    // Check immediately
    const done = await check();
    if (!done) {
      // Set up interval
      const interval = setInterval(async () => {
        const finished = await check();
        if (finished && pollRef.current.has(sourceId)) {
          clearInterval(interval);
          pollRef.current.delete(sourceId);
        }
      }, 3000);
      pollRef.current.set(sourceId, interval);
    }
  }, [fetchSources]);

  // Start polling when syncingIds changes
  useEffect(() => {
    syncingIds.forEach((id) => {
      if (!pollRef.current.has(id)) {
        pollStatus(id);
      }
    });
  }, [syncingIds, pollStatus]);

  // Cleanup intervals on unmount
  useEffect(() => {
    return () => {
      pollRef.current.forEach((interval) => clearInterval(interval));
      pollRef.current.clear();
    };
  }, []);

  // When source type changes in create form, reset config
  const handleSourceTypeChange = (type: string) => {
    setSelectedSourceType(type);
    const defaults = schemas[type]?.defaults || {};
    setConfigValues(defaults);
    form.setFieldsValue({ source_type: type });
  };

  const handleCreate = async (values: any) => {
    setSubmitting(true);
    try {
      const params: CreateSourceParams = {
        kb_id: values.kb_id,
        source_type: values.source_type,
        name: values.name,
        config: configValues,
      };
      await createSource(params);
      antMessage.success('知识源创建成功');
      setCreateModalVisible(false);
      form.resetFields();
      setConfigValues({});
      fetchSources();
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
    try {
      parsedConfig = typeof source.config === 'string' ? JSON.parse(source.config) : source.config;
    } catch {
      parsedConfig = {};
    }
    setEditConfigValues(parsedConfig);

    editForm.setFieldsValue({
      name: source.name,
      source_type: source.source_type,
    });
    setEditModalVisible(true);
  };

  const handleEditSubmit = async (values: any) => {
    if (!editingSource) return;
    setSubmitting(true);
    try {
      await updateSource(editingSource.id, {
        name: values.name,
        config: editConfigValues,
      });
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
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleSync = async (id: number) => {
    try {
      await triggerSourceSync(id);
      antMessage.info('同步已启动');
      // Reset notified flag so completion message shows once for this new sync
      notifiedRef.current.delete(id);
      setSyncingIds((prev) => new Set(prev).add(id));
      fetchSources();
    } catch (error: any) {
      antMessage.error('同步启动失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleConfigChange = (key: string, value: any) => {
    setConfigValues((prev) => ({ ...prev, [key]: value }));
  };

  const handleEditConfigChange = (key: string, value: any) => {
    setEditConfigValues((prev) => ({ ...prev, [key]: value }));
  };

  const filteredSources = sources.filter(
    (s) =>
      s.name.toLowerCase().includes(searchText.toLowerCase()) ||
      s.source_type.toLowerCase().includes(searchText.toLowerCase()),
  );

  const getSourceTypeTag = (type: string) => {
    const cfg = SOURCE_TYPE_CONFIG[type] || { label: type, color: 'default' };
    return <Tag color={cfg.color}>{cfg.label}</Tag>;
  };

  const getSyncStatusBadge = (status: string) => {
    const cfg = SYNC_STATUS_CONFIG[status] || { label: status, color: 'default' };
    return (
      <Badge
        status={cfg.color as any}
        text={
          <Space size={4}>
            {cfg.spinning && <SyncOutlined spin />}
            <span>{cfg.label}</span>
          </Space>
        }
      />
    );
  };

  const getKbName = (kbId: number) => {
    const kb = kbs.find((k) => k.id === kbId);
    return kb?.name || `知识库 #${kbId}`;
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: KnowledgeSource) => (
        <Space>
          <GlobalOutlined style={{ color: '#1677ff' }} />
          <span>{name}</span>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 140,
      render: (type: string) => getSourceTypeTag(type),
    },
    {
      title: '所属知识库',
      key: 'kb_id',
      width: 180,
      render: (_: any, record: KnowledgeSource) => (
        <Space>
          <DatabaseOutlined />
          <a onClick={() => navigate(`/documents/${record.kb_id}`)}>
            {getKbName(record.kb_id)}
          </a>
        </Space>
      ),
    },
    {
      title: '同步状态',
      dataIndex: 'sync_status',
      key: 'sync_status',
      width: 130,
      render: (status: string, record: KnowledgeSource) => (
        <Space>
          {getSyncStatusBadge(status)}
          {status === 'failed' && record.error_message && (
            <Tooltip title={record.error_message}>
              <WarningOutlined style={{ color: '#ff4d4f' }} />
            </Tooltip>
          )}
        </Space>
      ),
    },
    {
      title: '文档数',
      key: 'documentCount',
      width: 80,
      render: (_: any, record: KnowledgeSource) => (
        <Tag>{record.document_count ?? 0}</Tag>
      ),
    },
    {
      title: '上次同步',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      width: 180,
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: KnowledgeSource) => {
        const isSyncing = syncingIds.has(record.id);
        return (
          <Space>
            <Button
              type="link"
              size="small"
              icon={<SyncOutlined spin={isSyncing} />}
              onClick={() => handleSync(record.id)}
              disabled={isSyncing}
            >
              同步
            </Button>
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            >
              编辑
            </Button>
            <Popconfirm
              title="确认删除"
              description={`确定要删除知识源「${record.name}」吗？同步的文档也会被清理。`}
              onConfirm={() => handleDelete(record.id, record.name)}
              okText="确认删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  // Current create form schema
  const currentSchema = schemas[selectedSourceType];

  // Stats
  const totalSources = sources.length;
  const syncedCount = sources.filter((s) => s.sync_status === 'success').length;
  const failedCount = sources.filter((s) => s.sync_status === 'failed').length;
  const totalDocs = sources.reduce((sum, s) => sum + (s.document_count || 0), 0);

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
          知识源管理
        </Title>
        <Space>
          <Input
            placeholder="搜索知识源..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Tooltip title="刷新">
            <Button icon={<ReloadOutlined />} onClick={fetchSources} />
          </Tooltip>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              form.resetFields();
              const firstType = Object.keys(schemas)[0] || 'pubmed';
              setSelectedSourceType(firstType);
              setConfigValues(schemas[firstType]?.defaults || {});
              setCreateModalVisible(true);
            }}
          >
            添加知识源
          </Button>
        </Space>
      </div>

      {/* Stats cards */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <StatNumber value={totalSources} label="知识源总数" color="#1677ff" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <StatNumber value={syncedCount} label="同步成功" color="#52c41a" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <StatNumber value={failedCount} label="同步失败" color="#ff4d4f" />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <StatNumber value={totalDocs} label="同步文档数" color="#722ed1" />
          </Card>
        </Col>
      </Row>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : filteredSources.length === 0 ? (
          <Empty
            description={
              searchText ? '未找到匹配的知识源' : '暂无知识源，点击上方按钮添加'
            }
          />
        ) : (
          <Table
            dataSource={filteredSources}
            columns={columns}
            rowKey="id"
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个知识源`,
            }}
            scroll={{ x: 1100 }}
          />
        )}
      </Card>

      {/* Create Modal */}
      <Modal
        title={
          <Space>
            <PlusOutlined />
            添加知识源
          </Space>
        }
        open={createModalVisible}
        onCancel={() => setCreateModalVisible(false)}
        footer={null}
        width={600}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{
            source_type: selectedSourceType,
          }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[
              { required: true, message: '请输入知识源名称' },
              { max: 100, message: '名称不超过100个字符' },
            ]}
          >
            <Input placeholder="例如：高血压研究文献、心血管疾病诊疗指南" />
          </Form.Item>

          <Form.Item
            name="source_type"
            label="数据源类型"
            rules={[{ required: true, message: '请选择数据源类型' }]}
          >
            <Select
              onChange={handleSourceTypeChange}
              options={Object.entries(SOURCE_TYPE_CONFIG).map(([key, cfg]) => ({
                label: cfg.label,
                value: key,
              }))}
            />
          </Form.Item>

          <Form.Item
            name="kb_id"
            label="目标知识库"
            rules={[{ required: true, message: '请选择目标知识库' }]}
          >
            <Select
              placeholder="选择要将内容同步到的知识库"
              options={kbs.map((kb) => ({
                label: `${kb.name} (${kb.type})`,
                value: kb.id,
              }))}
            />
          </Form.Item>

          {/* Dynamic config fields */}
          {currentSchema && (
            <Card
              size="small"
              title={currentSchema.display_name + ' 配置'}
              style={{ marginBottom: 16 }}
            >
              {renderSchemaFields(currentSchema.config_schema, configValues, handleConfigChange)}
            </Card>
          )}

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setCreateModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>
                创建
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title={
          <Space>
            <EditOutlined />
            编辑知识源
          </Space>
        }
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        footer={null}
        width={600}
        destroyOnClose
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={handleEditSubmit}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[
              { required: true, message: '请输入知识源名称' },
              { max: 100, message: '名称不超过100个字符' },
            ]}
          >
            <Input placeholder="请输入知识源名称" />
          </Form.Item>

          <Form.Item name="source_type" label="数据源类型">
            <Input disabled />
          </Form.Item>

          {/* Edit dynamic config fields */}
          {currentSchema && editingSource && (
            <Card
              size="small"
              title={currentSchema.display_name + ' 配置'}
              style={{ marginBottom: 16 }}
            >
              {renderSchemaFields(currentSchema.config_schema, editConfigValues, handleEditConfigChange)}
            </Card>
          )}

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setEditModalVisible(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>
                保存
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

/** Simple stat number display */
const StatNumber: React.FC<{ value: number; label: string; color: string }> = ({
  value,
  label,
  color,
}) => (
  <div style={{ textAlign: 'center' }}>
    <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>
    <div style={{ fontSize: 13, color: '#666' }}>{label}</div>
  </div>
);

export default SourceManagement;
