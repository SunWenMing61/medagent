// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）、useCallback（回调缓存）、useRef（引用）钩子
import React, { useState, useEffect, useCallback, useRef } from 'react';
// 从 Ant Design 导入大量 UI 组件：Table（表格）、Button（按钮）、Modal（模态框）、Form（表单）、Input（输入框）、Select（选择器）、Space（间距）、Tag（标签）、Typography（排版）、Card（卡片）、Popconfirm（确认弹窗）、Tabs（标签页）、message（消息提示）、Spin（加载）、Empty（空状态）、Tooltip（提示）、Badge（徽标）、Switch（开关）、InputNumber（数字输入）、Row（行）、Col（列）、theme（主题）
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
// 从 Ant Design 图标库导入：加号、编辑、删除、数据库、搜索、刷新、文件夹、同步、地球、警告等图标
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
// 从 react-router-dom 导入 useNavigate（编程式导航）和 useLocation（获取当前 URL 信息）
import { useNavigate, useLocation } from 'react-router-dom';
// 从 API 服务层导入大量函数和类型定义：知识库 CRUD、文档、知识源、同步等
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

// 解构 Typography 中的 Title（标题）、Text（文本）、Paragraph（段落）组件
const { Title, Text, Paragraph } = Typography;
// 解构 Input 中的 TextArea 多行文本输入组件
const { TextArea } = Input;

// 知识源类型显示配置：每个类型对应的中文标签和颜色
const SOURCE_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  pubmed: { label: 'PubMed', color: 'blue' },             // PubMed 文献数据源
  msd_manual: { label: '默沙东诊疗手册', color: 'green' }, // 默沙东诊疗手册数据源
  drug_label: { label: '药品说明书', color: 'purple' },   // 药品说明书数据源
};

// 同步状态显示配置：每个状态对应的中文标签、颜色和是否旋转
const SYNC_STATUS_CONFIG: Record<string, { label: string; color: string; spinning?: boolean }> = {
  idle: { label: '待同步', color: 'default' },                 // 空闲待同步
  syncing: { label: '同步中', color: 'processing', spinning: true }, // 同步中，图标旋转
  success: { label: '同步成功', color: 'success' },            // 同步成功
  failed: { label: '同步失败', color: 'error' },               // 同步失败
};

// ========== JSON Schema 动态表单渲染器 ==========
// 根据 JSON Schema 定义动态生成表单字段，支持枚举、布尔、数字、日期、字符串等类型
function renderSchemaFields(
  schema: Record<string, any>,       // JSON Schema 定义
  configValues: Record<string, any>, // 当前配置值
  onChange: (key: string, value: any) => void, // 值变更回调
): React.ReactNode[] {
  const fields: React.ReactNode[] = [];
  const properties = schema?.properties || {}; // 获取所有字段属性
  const required = schema?.required || [];     // 获取必填字段列表

  // 遍历所有属性字段
  for (const [key, prop] of Object.entries<any>(properties)) {
    const isRequired = required.includes(key); // 判断是否为必填
    const value = configValues[key] ?? prop.default ?? ''; // 取当前值，无则用默认值或空

    let component: React.ReactNode;

    // 根据 Schema 类型渲染对应控件
    if (prop.enum) {
      // 枚举类型：渲染为 Select 下拉选择器
      const options = prop.enum.map((val: string, idx: number) => ({
        label: prop.enumNames?.[idx] || val, // 优先使用枚举显示名
        value: val,
      }));
      component = (
        <Select value={value} onChange={(v) => onChange(key, v)} options={options} style={{ width: '100%' }} />
      );
    } else if (prop.type === 'boolean') {
      // 布尔类型：渲染为 Switch 开关
      component = <Switch checked={!!value} onChange={(v) => onChange(key, v)} />;
    } else if (prop.type === 'integer' || prop.format === 'number') {
      // 整数/数字类型：渲染为 InputNumber 数字输入框
      component = (
        <InputNumber value={value} onChange={(v) => onChange(key, v)} min={prop.minimum} max={prop.maximum} style={{ width: '100%' }} />
      );
    } else if (prop.type === 'string' && prop.format === 'date') {
      // 日期字符串：渲染为 type="date" 的输入框
      component = <Input value={value} onChange={(e) => onChange(key, e.target.value)} placeholder={prop.description || key} type="date" />;
    } else if (prop.type === 'string') {
      // 普通字符串：渲染为 Input 输入框
      component = <Input value={value} onChange={(e) => onChange(key, e.target.value)} placeholder={prop.description || key} />;
    } else {
      // 其他类型兜底：转换为字符串后渲染为 Input
      component = <Input value={typeof value === 'object' ? JSON.stringify(value) : String(value)} onChange={(e) => onChange(key, e.target.value)} />;
    }

    // 将字段添加到表单元素列表中
    fields.push(
      <Form.Item key={key} label={<Space size={4}><span>{prop.title || key}</span>{isRequired && <Text type="danger">*</Text>}</Space>} help={prop.description}>
        {component}
      </Form.Item>,
    );
  }
  return fields;
}

/** 简单的统计数字展示组件 */
const StatNumber: React.FC<{ value: number; label: string; color: string }> = ({ value, label, color }) => {
  const { token } = theme.useToken();
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>     {/* 大号加粗数字 */}
      <div style={{ fontSize: 13, color: token.colorTextSecondary }}>{label}</div> {/* 底部标签文字 */}
    </div>
  );
};

// ========== 线下知识库标签页（OfflineKB Tab） ==========
const OfflineKBTab: React.FC<{
  searchText: string;       // 搜索文本，用于过滤
  refreshTrigger: number;   // 刷新触发器，变化时重新加载数据
  onRefresh: () => void;    // 通知父组件刷新的回调
}> = ({ searchText, refreshTrigger, onRefresh }) => {
  const { token } = theme.useToken();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);       // 知识库列表
  const [loading, setLoading] = useState(false);             // 加载状态
  const [createModalVisible, setCreateModalVisible] = useState(false); // 创建弹窗可见性
  const [submitting, setSubmitting] = useState(false);       // 提交中状态
  const [docCountMap, setDocCountMap] = useState<Record<number, number>>({}); // 各知识库文档数映射
  const [form] = Form.useForm();     // 创建表单引用
  const navigate = useNavigate();    // 编程式导航

  // 获取所有知识库及其文档数量的回调
  const fetchKBs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getKnowledgeBases(); // 调用 API 获取所有知识库
      setKbs(data);
      // 并发获取每个知识库的文档数量
      const countMap: Record<number, number> = {};
      await Promise.all(
        data.map(async (kb) => {
          try {
            const docs = await getDocuments(kb.id); // 获取该知识库下的文档
            countMap[kb.id] = docs.length;          // 记录文档数量
          } catch {
            countMap[kb.id] = 0; // 获取失败设为 0
          }
        }),
      );
      setDocCountMap(countMap); // 更新文档数映射
    } catch (error: any) {
      antMessage.error('获取知识库列表失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  }, []);

  // 组件挂载时获取数据，并设置 30 秒自动轮询
  useEffect(() => {
    fetchKBs();
    const timer = setInterval(fetchKBs, 30000); // 每 30 秒自动刷新
    return () => clearInterval(timer); // 卸载时清除定时器
  }, [fetchKBs, refreshTrigger]);

  // 处理创建知识库表单提交
  const handleCreate = async (values: CreateKBParams) => {
    setSubmitting(true);
    try {
      await createKnowledgeBase(values); // 调用 API 创建知识库
      antMessage.success('知识库创建成功');
      setCreateModalVisible(false); // 关闭创建弹窗
      form.resetFields();           // 重置表单
      fetchKBs();                   // 刷新列表
      onRefresh();                  // 通知父组件刷新
    } catch (error: any) {
      antMessage.error('创建失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  // 处理删除知识库
  const handleDelete = async (id: number, name: string) => {
    try {
      await deleteKnowledgeBase(id); // 调用 API 删除
      antMessage.success(`知识库「${name}」已删除`);
      fetchKBs();
      onRefresh();
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 根据类型返回中文标签
  const getTypeLabel = (type: string) => {
    const m: Record<string, string> = { general: '通用', drug: '药品', paper: '文献', health: '健康', medical: '医学', chat_history: '对话历史' };
    return m[type.toLowerCase()] || type;
  };

  // 根据类型返回标签颜色
  const getTypeColor = (type: string) => {
    const m: Record<string, string> = { general: 'blue', drug: 'green', paper: 'purple', health: 'orange', medical: 'red', chat_history: 'cyan' };
    return m[type.toLowerCase()] || 'default';
  };

  // 根据搜索文本过滤知识库列表（按名称或描述匹配）
  const filteredKBs = kbs.filter(
    (kb) =>
      kb.name.toLowerCase().includes(searchText.toLowerCase()) ||
      kb.description.toLowerCase().includes(searchText.toLowerCase()),
  );

  // 表格列配置
  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    {
      title: '名称', dataIndex: 'name', key: 'name',
      render: (name: string, record: KnowledgeBase) => (
        <Space>
          {/*
            显示不同图标：对话历史知识库使用同步图标，其他使用数据库图标
            点击非对话历史的知识库名称可导航到对应文档页面
          */}
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
            // 对话历史为内置知识库，不可操作
            <Text type="secondary" style={{ fontSize: 12 }}>内置知识库</Text>
          ) : (
            <>
              {/* 文档按钮：导航到对应文档管理页面 */}
              <Button type="link" size="small" icon={<FolderOpenOutlined />} onClick={() => navigate(`/documents/${record.id}`)}>
                文档
              </Button>
              {/* 删除按钮：带 Popconfirm 二次确认 */}
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

  // 线下知识库标签页 JSX
  return (
    <div>
      {/* 头部：标题 + 操作按钮（刷新 + 创建） */}
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

      {/*
        表格卡片区域：
        - 加载中显示 Spin
        - 过滤后无数据提示"未找到匹配的知识库"
        - 全部无数据提示"暂无线下知识库"
      */}
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

      {/*
        创建知识库弹窗：
        - 表单包含：名称（必填）、描述、类型、可见性
        - 默认值：类型=通用、可见性=私有
      */}
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

// ========== 线上知识源标签页（OnlineSource Tab） ==========
const OnlineSourceTab: React.FC<{
  searchText: string;
  refreshTrigger: number;
  onRefresh: () => void;
}> = ({ searchText, refreshTrigger, onRefresh }) => {
  const { token } = theme.useToken();
  const [sources, setSources] = useState<KnowledgeSource[]>([]);     // 知识源列表
  const [loading, setLoading] = useState(false);                     // 加载状态
  const [createModalVisible, setCreateModalVisible] = useState(false); // 创建弹窗可见性
  const [editModalVisible, setEditModalVisible] = useState(false);   // 编辑弹窗可见性
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null); // 正在编辑的知识源
  const [submitting, setSubmitting] = useState(false);               // 提交中状态
  const [schemas, setSchemas] = useState<Record<string, SourceSchemaInfo>>({}); // 各类型数据源的配置模板
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);               // 知识库列表
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set()); // 正在同步的知识源 ID 集合
  const [form] = Form.useForm();           // 创建表单
  const [editForm] = Form.useForm();       // 编辑表单
  const [selectedSourceType, setSelectedSourceType] = useState<string>('pubmed'); // 创建表单中当前选中的数据源类型
  const [configValues, setConfigValues] = useState<Record<string, any>>({});       // 创建表单动态配置值
  const [editConfigValues, setEditConfigValues] = useState<Record<string, any>>({}); // 编辑表单动态配置值
  const pollRef = useRef<Map<number, NodeJS.Timeout>>(new Map());    // 存储轮询定时器的引用，用于清理
  const navigate = useNavigate();

  // 获取知识源列表的回调
  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSources();
      // 检查哪些知识源正在同步中，记录到 syncingIds
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

  // 获取各类型数据源的配置模板
  const fetchSchemas = useCallback(async () => {
    try {
      const data = await getSourceSchemas();
      setSchemas(data);
    } catch { /* 静默失败 */ }
  }, []);

  // 获取知识库列表
  const fetchKBs = useCallback(async () => {
    try {
      const data = await getKnowledgeBases();
      setKbs(data);
    } catch { /* 静默失败 */ }
  }, []);

  // 组件挂载时及 refreshTrigger 变化时加载数据
  useEffect(() => { fetchSources(); fetchSchemas(); fetchKBs(); }, [fetchSources, fetchSchemas, fetchKBs, refreshTrigger]);

  // 轮询指定知识源的同步状态，直到同步完成或失败
  const pollStatus = useCallback(async (sourceId: number) => {
    const check = async () => {
      try {
        const status = await getSourceStatus(sourceId); // 获取同步状态
        if (status.sync_status !== 'syncing') {         // 如果不再同步中
          setSyncingIds((prev) => { const next = new Set(prev); next.delete(sourceId); return next; }); // 移除同步集合
          fetchSources(); // 刷新列表
          if (status.sync_status === 'success') antMessage.success('知识源同步完成');
          else if (status.sync_status === 'failed') antMessage.error('同步失败: ' + (status.error_message || '未知错误'));
          return true; // 轮询完成
        }
      } catch { /* 继续轮询 */ }
      return false;
    };
    const done = await check(); // 立即检查一次
    if (!done) {
      // 未完成则每 3 秒轮询一次
      const interval = setInterval(async () => {
        const finished = await check();
        if (finished && pollRef.current.has(sourceId)) { clearInterval(interval); pollRef.current.delete(sourceId); }
      }, 3000);
      pollRef.current.set(sourceId, interval);
    }
  }, [fetchSources]);

  // 对同步中的知识源启动轮询
  useEffect(() => {
    syncingIds.forEach((id) => { if (!pollRef.current.has(id)) pollStatus(id); });
  }, [syncingIds, pollStatus]);

  // 组件卸载时清理所有轮询定时器
  useEffect(() => {
    return () => { pollRef.current.forEach((interval) => clearInterval(interval)); pollRef.current.clear(); };
  }, []);

  // 创建表单中数据源类型切换时，更新动态配置的默认值
  const handleSourceTypeChange = (type: string) => {
    setSelectedSourceType(type);
    setConfigValues(schemas[type]?.defaults || {}); // 使用该类型的默认配置
    form.setFieldsValue({ source_type: type });
  };

  // 处理创建知识源表单提交
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

  // 打开编辑弹窗并填充现有数据
  const handleEdit = (source: KnowledgeSource) => {
    setEditingSource(source);
    setSelectedSourceType(source.source_type);
    // 解析配置对象（可能是 JSON 字符串或对象）
    let parsedConfig: Record<string, any> = {};
    try { parsedConfig = typeof source.config === 'string' ? JSON.parse(source.config) : source.config; } catch { parsedConfig = {}; }
    setEditConfigValues(parsedConfig);
    editForm.setFieldsValue({ name: source.name, source_type: source.source_type, kb_id: source.kb_id });
    setEditModalVisible(true);
  };

  // 处理编辑知识源表单提交
  const handleEditSubmit = async (values: any) => {
    if (!editingSource) return;
    setSubmitting(true);
    try {
      const params: any = { name: values.name, config: editConfigValues };
      if (values.kb_id && values.kb_id !== editingSource.kb_id) {
        params.kb_id = values.kb_id; // 如果修改了关联知识库，一并提交
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

  // 处理删除知识源
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

  // 触发知识源同步
  const handleSync = async (id: number) => {
    try {
      await triggerSourceSync(id);
      antMessage.info('同步已启动');
      setSyncingIds((prev) => new Set(prev).add(id)); // 加入同步集合，启动轮询
      fetchSources();
    } catch (error: any) {
      antMessage.error('同步启动失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 创建表单配置值变更处理
  const handleConfigChange = (key: string, value: any) => setConfigValues((prev) => ({ ...prev, [key]: value }));
  // 编辑表单配置值变更处理
  const handleEditConfigChange = (key: string, value: any) => setEditConfigValues((prev) => ({ ...prev, [key]: value }));

  // 根据搜索文本过滤知识源列表
  const filteredSources = sources.filter(
    (s) => s.name.toLowerCase().includes(searchText.toLowerCase()) || s.source_type.toLowerCase().includes(searchText.toLowerCase()),
  );
  const currentSchema = schemas[selectedSourceType]; // 当前选中类型的配置模板
  // 统计数据
  const totalSources = sources.length;
  const syncedCount = sources.filter((s) => s.sync_status === 'success').length;
  const failedCount = sources.filter((s) => s.sync_status === 'failed').length;
  const totalDocs = sources.reduce((sum, s) => sum + (s.document_count || 0), 0);

  // 根据数据源类型渲染标签
  const getSourceTypeTag = (type: string) => {
    const cfg = SOURCE_TYPE_CONFIG[type] || { label: type, color: 'default' };
    return <Tag color={cfg.color}>{cfg.label}</Tag>;
  };

  // 根据同步状态渲染徽标
  const getSyncStatusBadge = (status: string) => {
    const cfg = SYNC_STATUS_CONFIG[status] || { label: status, color: 'default' };
    return <Badge status={cfg.color as any} text={<Space size={4}>{cfg.spinning && <SyncOutlined spin />}<span>{cfg.label}</span></Space>} />;
  };

  // 根据知识库 ID 获取知识库名称
  const getKbName = (kbId: number) => {
    const kb = kbs.find((k) => k.id === kbId);
    return kb?.name || `知识库 #${kbId}`;
  };

  // 表格列配置
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
        const isSyncing = syncingIds.has(record.id); // 判断是否在同步中
        return (
          <Space>
            {/*
              同步按钮：
              - 同步中显示旋转图标并禁用
              - 点击触发 handleSync
            */}
            <Button type="link" size="small" icon={<SyncOutlined spin={isSyncing} />} onClick={() => handleSync(record.id)} disabled={isSyncing}>同步</Button>
            {/*
              编辑按钮：打开编辑弹窗
            */}
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
            {/*
              删除按钮：带 Popconfirm 二次确认
            */}
            <Popconfirm title="确认删除" description={`确定要删除知识源「${record.name}」吗？同步的文档也会被清理。`}
              onConfirm={() => handleDelete(record.id, record.name)} okText="确认删除" cancelText="取消" okButtonProps={{ danger: true }}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  // 线上知识源标签页 JSX
  return (
    <div>
      {/*
        统计卡片行：知识源总数、同步成功数、同步失败数、同步文档数
      */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card size="small"><StatNumber value={totalSources} label="知识源总数" color={token.colorPrimary} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={syncedCount} label="同步成功" color={token.colorSuccess} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={failedCount} label="同步失败" color={token.colorError} /></Card></Col>
        <Col span={6}><Card size="small"><StatNumber value={totalDocs} label="同步文档数" color={token.colorPrimary} /></Card></Col>
      </Row>

      {/*
        头部：标题 + 操作按钮（刷新 + 添加知识源）
      */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={5} style={{ margin: 0 }}>线上知识源</Title>
        <Space>
          <Tooltip title="刷新"><Button icon={<ReloadOutlined />} onClick={fetchSources} /></Tooltip>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => {
            form.resetFields();
            const firstType = Object.keys(schemas)[0] || 'pubmed'; // 默认选择第一个数据源类型
            setSelectedSourceType(firstType);
            setConfigValues(schemas[firstType]?.defaults || {});
            setCreateModalVisible(true);
          }}>
            添加知识源
          </Button>
        </Space>
      </div>

      {/*
        表格卡片区域
      */}
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

      {/*
        创建知识源弹窗：
        - 包含名称、数据源类型、目标知识库、动态配置字段
        - 数据源类型切换时动态更新配置字段
      */}
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
          {/*
            动态配置字段区域：根据所选数据源类型的 JSON Schema 动态渲染
          */}
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

      {/*
        编辑知识源弹窗：
        - 与创建类似但预填充现有数据
        - 数据源类型为只读（不可变更）
      */}
      <Modal title={<Space><EditOutlined />编辑知识源</Space>} open={editModalVisible}
        onCancel={() => setEditModalVisible(false)} footer={null} width={600} destroyOnClose>
        <Form form={editForm} layout="vertical" onFinish={handleEditSubmit}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入知识源名称' }, { max: 100 }]}>
            <Input placeholder="请输入知识源名称" />
          </Form.Item>
          <Form.Item name="source_type" label="数据源类型"><Input disabled /></Form.Item> {/* 类型不可修改 */}
          <Form.Item name="kb_id" label="关联知识库" rules={[{ required: true, message: '请选择关联知识库' }]}>
            <Select
              placeholder="选择关联的知识库"
              options={kbs.map((kb) => ({
                label: `${kb.name} (${kb.type})`,
                value: kb.id,
              }))}
            />
          </Form.Item>
          {/*
            编辑模式下的动态配置字段
          */}
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

// ========== 主页面 KBManagement（两个标签页） ==========
const KBManagement: React.FC = () => {
  const [searchText, setSearchText] = useState('');         // 搜索文本
  const [refreshTrigger, setRefreshTrigger] = useState(0); // 刷新触发器（递增计数触发刷新）
  const location = useLocation();                            // 获取当前 URL 信息

  // 检查 URL 查询参数是否指定了 ?tab=online，用于默认选中线上标签页
  const getDefaultTab = () => {
    const params = new URLSearchParams(location.search);
    return params.get('tab') === 'online' ? 'online' : 'offline';
  };

  // 触发子组件刷新的函数，递增计数器使依赖此值的 useEffect 重新执行
  const triggerRefresh = () => setRefreshTrigger((prev) => prev + 1);

  // 主页面 JSX
  return (
    <div>
      {/*
        页面头部：标题 + 搜索框
      */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>知识库管理</Title>
        <Input
          placeholder="搜索..."
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          style={{ width: 200 }}
          allowClear             // 允许一键清空
        />
      </div>

      {/*
        标签页组件：
        - "线下知识库"标签页：展示和管理本地创建的知识库
        - "线上知识源"标签页：展示和管理从外部数据源同步的知识源
        - 默认选中标签由 URL 参数 ?tab=online 控制
      */}
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

// 默认导出 KBManagement 组件
export default KBManagement;
