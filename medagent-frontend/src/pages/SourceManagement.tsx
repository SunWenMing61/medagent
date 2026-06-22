// 导入 React 核心库和 useState、useEffect、useCallback（缓存回调）、useRef（引用）钩子
import React, { useState, useEffect, useCallback, useRef } from 'react';
// 从 Ant Design 导入 UI 组件：Table（表格）、Button（按钮）、Modal（模态框）、Form（表单）、Input（输入框）、Select（选择器）、Space（间距）、Tag（标签）、Typography（排版）、Card（卡片）、Popconfirm（确认弹窗）、message（消息提示）、Spin（加载）、Empty（空状态）、Tooltip（提示）、Badge（徽标）、Switch（开关）、InputNumber（数字输入）、Row（行）、Col（列）
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
// 从 Ant Design 图标库导入：加号、编辑、删除、刷新、同步、地球、搜索、数据库、链接、警告等图标
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
// 从 react-router-dom 导入 useNavigate（编程式导航）
import { useNavigate } from 'react-router-dom';
// 从 API 服务层导入知识源相关的所有函数和类型定义
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

// 解构 Typography 中的 Title（标题）、Text（文本）、Paragraph（段落）组件
const { Title, Text, Paragraph } = Typography;
// 解构 Input 中的 TextArea 多行文本输入组件
const { TextArea } = Input;

// 知识源类型显示配置：每个类型对应的中文标签和颜色
const SOURCE_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  pubmed: { label: 'PubMed', color: 'blue' },             // PubMed 医学文献数据源
  msd_manual: { label: '默沙东诊疗手册', color: 'green' }, // 默沙东诊疗手册
  drug_label: { label: '药品说明书', color: 'purple' },   // 药品说明书
};

// 同步状态显示配置：每个状态对应的中文标签、颜色和是否旋转
const SYNC_STATUS_CONFIG: Record<string, { label: string; color: string; spinning?: boolean }> = {
  idle: { label: '待同步', color: 'default' },                 // 空闲待同步
  syncing: { label: '同步中', color: 'processing', spinning: true }, // 同步中（图标旋转）
  success: { label: '同步成功', color: 'success' },            // 同步成功
  failed: { label: '同步失败', color: 'error' },               // 同步失败
};

/** 根据 JSON Schema 动态渲染表单字段 */
function renderSchemaFields(
  schema: Record<string, any>,       // JSON Schema 定义
  configValues: Record<string, any>, // 当前配置值
  onChange: (key: string, value: any) => void, // 值变更回调
): React.ReactNode[] {
  const fields: React.ReactNode[] = [];
  const properties = schema?.properties || {}; // 获取所有属性定义
  const required = schema?.required || [];     // 获取必填字段列表

  // 遍历 Schema 中的每个字段
  for (const [key, prop] of Object.entries<any>(properties)) {
    const isRequired = required.includes(key); // 是否必填
    const value = configValues[key] ?? prop.default ?? ''; // 取当前值或默认值

    let component: React.ReactNode;

    if (prop.enum) {
      // 枚举类型：渲染为 Select 下拉选择器
      const options = prop.enum.map((val: string, idx: number) => ({
        label: prop.enumNames?.[idx] || val, // 优先使用显示名称
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
      // 布尔类型：渲染为 Switch 开关
      component = (
        <Switch
          checked={!!value}
          onChange={(v) => onChange(key, v)}
        />
      );
    } else if (prop.type === 'integer' || prop.format === 'number') {
      // 整数/数字：渲染为 InputNumber 数字输入框
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
      // 日期字符串：渲染为 type="date" 的输入框
      component = (
        <Input
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          placeholder={prop.description || key}
          type="date"
        />
      );
    } else if (prop.type === 'string') {
      // 普通字符串：渲染为 Input 文本输入框
      component = (
        <Input
          value={value}
          onChange={(e) => onChange(key, e.target.value)}
          placeholder={prop.description || key}
        />
      );
    } else {
      // 其他类型兜底：转换为字符串显示
      component = (
        <Input
          value={typeof value === 'object' ? JSON.stringify(value) : String(value)}
          onChange={(e) => onChange(key, e.target.value)}
        />
      );
    }

    // 将字段添加到表单元素数组中
    fields.push(
      <Form.Item
        key={key}
        label={
          <Space size={4}>
            <span>{prop.title || key}</span>
            {isRequired && <Text type="danger">*</Text>} {/* 必填字段显示红色星号 */}
          </Space>
        }
        help={prop.description} // 字段描述作为帮助提示
      >
        {component}
      </Form.Item>,
    );
  }

  return fields;
}

// 定义 SourceManagement 知识源管理主组件，类型为 React.FC
const SourceManagement: React.FC = () => {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);     // 知识源列表
  const [loading, setLoading] = useState(false);                     // 列表加载中
  const [createModalVisible, setCreateModalVisible] = useState(false); // 创建弹窗可见
  const [editModalVisible, setEditModalVisible] = useState(false);   // 编辑弹窗可见
  const [editingSource, setEditingSource] = useState<KnowledgeSource | null>(null); // 正在编辑的知识源
  const [submitting, setSubmitting] = useState(false);               // 提交中
  const [searchText, setSearchText] = useState('');                   // 搜索文本
  const [schemas, setSchemas] = useState<Record<string, SourceSchemaInfo>>({}); // 各类型数据源的配置模板
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);               // 知识库列表（用作关联目标）
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set()); // 正在同步的知识源 ID 集合

  // 表单状态
  const [form] = Form.useForm();     // 创建表单
  const [editForm] = Form.useForm(); // 编辑表单

  // 动态配置：创建表单
  const [selectedSourceType, setSelectedSourceType] = useState<string>('pubmed'); // 当前选中的数据源类型
  const [configValues, setConfigValues] = useState<Record<string, any>>({});       // 创建表单的动态配置值
  const [editConfigValues, setEditConfigValues] = useState<Record<string, any>>({}); // 编辑表单的动态配置值

  const pollRef = useRef<Map<number, NodeJS.Timeout>>(new Map());    // 轮询定时器引用映射，用于清理
  const notifiedRef = useRef<Set<number>>(new Set());                // 已通知过的同步 ID（避免重复提示）

  const navigate = useNavigate(); // 编程式导航

  // 获取知识源列表的回调
  const fetchSources = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getSources(); // 调用 API 获取所有知识源
      // 检查哪些知识源正在同步中
      const newSyncingIds = new Set<number>();
      for (const s of data) {
        if (s.sync_status === 'syncing') {
          newSyncingIds.add(s.id);
        }
      }
      setSyncingIds(newSyncingIds);
      setSources(data); // 更新列表
    } catch (error: any) {
      antMessage.error('获取知识源列表失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  }, []);

  // 获取各类型数据源的配置模板
  const fetchSchemas = useCallback(async () => {
    try {
      const data = await getSourceSchemas(); // 调用 API 获取配置模板
      setSchemas(data);
    } catch (error: any) {
      antMessage.error('获取源配置模板失败: ' + (error.response?.data?.detail || error.message));
    }
  }, []);

  // 获取知识库列表（用于关联选择）
  const fetchKBs = useCallback(async () => {
    try {
      const data = await getKnowledgeBases();
      setKbs(data);
    } catch {
      // 静默失败
    }
  }, []);

  // 组件挂载时加载所有数据
  useEffect(() => {
    fetchSources();
    fetchSchemas();
    fetchKBs();
  }, [fetchSources, fetchSchemas, fetchKBs]);

  // 轮询指定知识源的同步状态
  const pollStatus = useCallback(async (sourceId: number) => {
    const check = async () => {
      try {
        const status = await getSourceStatus(sourceId); // 获取当前同步状态
        if (status.sync_status !== 'syncing') {         // 如果同步已完成
          setSyncingIds((prev) => {
            const next = new Set(prev);
            next.delete(sourceId); // 从同步中集合移除
            return next;
          });
          fetchSources(); // 刷新列表
          // 每个来源在每个同步周期内只通知一次
          if (!notifiedRef.current.has(sourceId)) {
            notifiedRef.current.add(sourceId);
            if (status.sync_status === 'success') {
              antMessage.success(`知识源同步完成`);
            } else if (status.sync_status === 'failed') {
              antMessage.error(`同步失败: ${status.error_message || '未知错误'}`);
            }
          }
          return true; // 轮询完成
        }
      } catch {
        // 出错继续轮询
      }
      return false;
    };

    // 立即检查一次
    const done = await check();
    if (!done) {
      // 未完成则设置每 3 秒轮询一次的定时器
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

  // 当 syncingIds 变化时，对新增的同步中知识源启动轮询
  useEffect(() => {
    syncingIds.forEach((id) => {
      if (!pollRef.current.has(id)) {
        pollStatus(id);
      }
    });
  }, [syncingIds, pollStatus]);

  // 组件卸载时清理所有轮询定时器
  useEffect(() => {
    return () => {
      pollRef.current.forEach((interval) => clearInterval(interval));
      pollRef.current.clear();
    };
  }, []);

  // 创建表单中数据源类型切换时重置动态配置
  const handleSourceTypeChange = (type: string) => {
    setSelectedSourceType(type);
    const defaults = schemas[type]?.defaults || {}; // 使用该类型的默认值
    setConfigValues(defaults);
    form.setFieldsValue({ source_type: type });
  };

  // 处理创建知识源表单提交
  const handleCreate = async (values: any) => {
    setSubmitting(true);
    try {
      const params: CreateSourceParams = {
        kb_id: values.kb_id,
        source_type: values.source_type,
        name: values.name,
        config: configValues, // 动态配置值
      };
      await createSource(params); // 调用 API 创建
      antMessage.success('知识源创建成功');
      setCreateModalVisible(false);
      form.resetFields();
      setConfigValues({});
      fetchSources(); // 刷新列表
    } catch (error: any) {
      antMessage.error('创建失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  // 打开编辑弹窗，填充现有知识源数据
  const handleEdit = (source: KnowledgeSource) => {
    setEditingSource(source);
    setSelectedSourceType(source.source_type);

    // 解析配置：可能是 JSON 字符串或对象
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
      // 注意：编辑时不支持修改 kb_id，保持原有关联
    });
    setEditModalVisible(true);
  };

  // 处理编辑知识源表单提交
  const handleEditSubmit = async (values: any) => {
    if (!editingSource) return;
    setSubmitting(true);
    try {
      await updateSource(editingSource.id, {
        name: values.name,
        config: editConfigValues, // 更新后的配置
      });
      antMessage.success('知识源更新成功');
      setEditModalVisible(false);
      editForm.resetFields();
      setEditingSource(null);
      fetchSources(); // 刷新列表
    } catch (error: any) {
      antMessage.error('更新失败: ' + (error.response?.data?.detail || error.message));
    } finally {
      setSubmitting(false);
    }
  };

  // 处理删除知识源
  const handleDelete = async (id: number, name: string) => {
    try {
      const result = await deleteSource(id); // 调用 API 删除
      antMessage.success(`已删除知识源「${name}」，共清理 ${result.deleted_documents} 个文档`);
      fetchSources(); // 刷新列表
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 触发知识源同步
  const handleSync = async (id: number) => {
    try {
      await triggerSourceSync(id); // 调用 API 触发同步
      antMessage.info('同步已启动');
      // 重置通知标记，使本次同步完成时重新提示
      notifiedRef.current.delete(id);
      setSyncingIds((prev) => new Set(prev).add(id)); // 加入同步集合，启动轮询
      fetchSources();
    } catch (error: any) {
      antMessage.error('同步启动失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 创建表单动态配置值变更
  const handleConfigChange = (key: string, value: any) => {
    setConfigValues((prev) => ({ ...prev, [key]: value }));
  };

  // 编辑表单动态配置值变更
  const handleEditConfigChange = (key: string, value: any) => {
    setEditConfigValues((prev) => ({ ...prev, [key]: value }));
  };

  // 根据搜索文本过滤知识源列表
  const filteredSources = sources.filter(
    (s) =>
      s.name.toLowerCase().includes(searchText.toLowerCase()) ||
      s.source_type.toLowerCase().includes(searchText.toLowerCase()),
  );

  // 根据数据源类型渲染标签
  const getSourceTypeTag = (type: string) => {
    const cfg = SOURCE_TYPE_CONFIG[type] || { label: type, color: 'default' };
    return <Tag color={cfg.color}>{cfg.label}</Tag>;
  };

  // 根据同步状态渲染徽标
  const getSyncStatusBadge = (status: string) => {
    const cfg = SYNC_STATUS_CONFIG[status] || { label: status, color: 'default' };
    return (
      <Badge
        status={cfg.color as any}
        text={
          <Space size={4}>
            {cfg.spinning && <SyncOutlined spin />} {/* 同步中显示旋转图标 */}
            <span>{cfg.label}</span>
          </Space>
        }
      />
    );
  };

  // 根据知识库 ID 获取名称
  const getKbName = (kbId: number) => {
    const kb = kbs.find((k) => k.id === kbId);
    return kb?.name || `知识库 #${kbId}`; // 找不到则回退显示 #ID
  };

  // 表格列配置
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
          <GlobalOutlined style={{ color: '#1677ff' }} /> {/* 地球图标表示线上数据源 */}
          <span>{name}</span>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'source_type',
      key: 'source_type',
      width: 140,
      render: (type: string) => getSourceTypeTag(type), // 显示类型标签
    },
    {
      title: '所属知识库',
      key: 'kb_id',
      width: 180,
      render: (_: any, record: KnowledgeSource) => (
        <Space>
          <DatabaseOutlined />
          {/* 点击可跳转到该知识库的文档管理页面 */}
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
          {getSyncStatusBadge(status)} {/* 状态徽标 */}
          {status === 'failed' && record.error_message && (
            // 同步失败且有错误信息时显示警告图标，鼠标悬停显示详情
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
        <Tag>{record.document_count ?? 0}</Tag> // 显示文档数量
      ),
    },
    {
      title: '上次同步',
      dataIndex: 'last_sync_at',
      key: 'last_sync_at',
      width: 180,
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-', // 格式化时间
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, record: KnowledgeSource) => {
        const isSyncing = syncingIds.has(record.id); // 判断是否同步中
        return (
          <Space>
            {/*
              同步按钮：
              - 同步中显示旋转动画并禁用
              - 点击触发 handleSync
            */}
            <Button
              type="link"
              size="small"
              icon={<SyncOutlined spin={isSyncing} />}
              onClick={() => handleSync(record.id)}
              disabled={isSyncing}
            >
              同步
            </Button>
            {/*
              编辑按钮：打开编辑弹窗
            */}
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => handleEdit(record)}
            >
              编辑
            </Button>
            {/*
              删除按钮：带 Popconfirm 二次确认弹窗
            */}
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

  // 当前创建表单选中的数据源类型的配置模板
  const currentSchema = schemas[selectedSourceType];

  // 统计数据
  const totalSources = sources.length;                                              // 知识源总数
  const syncedCount = sources.filter((s) => s.sync_status === 'success').length;    // 同步成功数
  const failedCount = sources.filter((s) => s.sync_status === 'failed').length;     // 同步失败数
  const totalDocs = sources.reduce((sum, s) => sum + (s.document_count || 0), 0);  // 总文档数

  // 组件 JSX 渲染
  return (
    <div>
      {/*
        页面头部区域：
        - 左侧"知识源管理"标题
        - 右侧：搜索框 + 刷新按钮 + 添加知识源按钮
      */}
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
          {/*
            搜索框：输入文本实时过滤知识源列表
          */}
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
              const firstType = Object.keys(schemas)[0] || 'pubmed'; // 默认选第一个类型
              setSelectedSourceType(firstType);
              setConfigValues(schemas[firstType]?.defaults || {});
              setCreateModalVisible(true);
            }}
          >
            添加知识源
          </Button>
        </Space>
      </div>

      {/*
        统计卡片区域：
        展示知识源总数、同步成功数、同步失败数和同步文档数
      */}
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

      {/*
        表格卡片区域：
        - 加载中显示 Spin
        - 无数据 / 无匹配结果显示 Empty
        - 有数据显示表格
      */}
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
            scroll={{ x: 1100 }} // 水平滚动以适应较多列
          />
        )}
      </Card>

      {/*
        创建知识源弹窗：
        - 表单包含名称、数据源类型、目标知识库、动态配置字段
        - 选择不同数据源类型时动态展示对应的配置字段
      */}
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
        destroyOnClose // 关闭时销毁内部状态
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={handleCreate}
          initialValues={{
            source_type: selectedSourceType,
          }}
        >
          {/* 名称输入 */}
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

          {/* 数据源类型选择 */}
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

          {/* 目标知识库选择 */}
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

          {/*
            动态配置字段区域：
            根据所选数据源类型的 JSON Schema 动态渲染表单字段
          */}
          {currentSchema && (
            <Card
              size="small"
              title={currentSchema.display_name + ' 配置'}
              style={{ marginBottom: 16 }}
            >
              {renderSchemaFields(currentSchema.config_schema, configValues, handleConfigChange)}
            </Card>
          )}

          {/* 底部按钮 */}
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

      {/*
        编辑知识源弹窗：
        - 预填充现有数据
        - 数据源类型为只读，不可修改
        - 关联知识库固定，不支持编辑时更换
      */}
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
          {/* 名称编辑 */}
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

          {/* 数据源类型（只读） */}
          <Form.Item name="source_type" label="数据源类型">
            <Input disabled />
          </Form.Item>

          {/*
            编辑模式下的动态配置字段
          */}
          {currentSchema && editingSource && (
            <Card
              size="small"
              title={currentSchema.display_name + ' 配置'}
              style={{ marginBottom: 16 }}
            >
              {renderSchemaFields(currentSchema.config_schema, editConfigValues, handleEditConfigChange)}
            </Card>
          )}

          {/* 底部按钮 */}
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

/** 简单的统计数字展示组件 */
const StatNumber: React.FC<{ value: number; label: string; color: string }> = ({
  value,
  label,
  color,
}) => (
  <div style={{ textAlign: 'center' }}>
    <div style={{ fontSize: 28, fontWeight: 600, color }}>{value}</div>     {/* 大号加粗数字 */}
    <div style={{ fontSize: 13, color: '#666' }}>{label}</div>              {/* 底部标签文字 */}
  </div>
);

// 默认导出 SourceManagement 组件
export default SourceManagement;
