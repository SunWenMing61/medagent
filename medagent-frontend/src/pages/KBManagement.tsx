// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）、useCallback（回调缓存）钩子
import React, { useState, useEffect, useCallback } from 'react';
// 从 Ant Design 导入大量 UI 组件：Table（表格）、Button（按钮）、Modal（模态框）、Form（表单）、Input（输入框）、Select（选择器）、Space（间距）、Tag（标签）、Typography（排版）、Card（卡片）、Popconfirm（确认弹窗）、message（消息提示）、Spin（加载）、Empty（空状态）、Tooltip（提示）、Badge（徽标）、theme（主题）
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
  theme,
} from 'antd';
// 从 Ant Design 图标库导入：加号、编辑、删除、数据库、搜索、刷新、文件夹等图标
import {
  PlusOutlined,
  DeleteOutlined,
  DatabaseOutlined,
  SearchOutlined,
  ReloadOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
// 从 react-router-dom 导入 useNavigate（编程式导航）
import { useNavigate } from 'react-router-dom';
// 从 API 服务层导入函数和类型定义：知识库 CRUD、文档
import {
  getKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  getDocuments,
  type KnowledgeBase,
  type CreateKBParams,
} from '../services/api';

// 解构 Typography 中的 Title（标题）、Text（文本）组件
const { Title, Text } = Typography;
// 解构 Input 中的 TextArea 多行文本输入组件
const { TextArea } = Input;

// ========== 知识库管理页面（单列表，无标签页） ==========
const KBManagement: React.FC = () => {
  const { token } = theme.useToken();
  const [searchText, setSearchText] = useState('');       // 搜索文本
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
  }, [fetchKBs]);

  // 处理创建知识库表单提交
  const handleCreate = async (values: CreateKBParams) => {
    setSubmitting(true);
    try {
      await createKnowledgeBase(values); // 调用 API 创建知识库
      antMessage.success('知识库创建成功');
      setCreateModalVisible(false); // 关闭创建弹窗
      form.resetFields();           // 重置表单
      fetchKBs();                   // 刷新列表
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
    } catch (error: any) {
      antMessage.error('删除失败: ' + (error.response?.data?.detail || error.message));
    }
  };

  // 根据类型返回中文标签
  const getTypeLabel = (type: string) => {
    const m: Record<string, string> = { general: '通用', drug: '药品', paper: '文献', health: '健康', medical: '医学' };
    return m[type.toLowerCase()] || type;
  };

  // 根据类型返回标签颜色
  const getTypeColor = (type: string) => {
    const m: Record<string, string> = { general: 'blue', drug: 'green', paper: 'purple', health: 'orange', medical: 'red' };
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
          <DatabaseOutlined style={{ color: token.colorPrimary }} />
          <a onClick={() => navigate(`/documents/${record.id}`)}>{name}</a>
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
        </Space>
      ),
    },
  ];

  // 主页面 JSX
  return (
    <div>
      {/*
        页面头部：标题 + 搜索框 + 操作按钮（刷新 + 创建）
      */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <Title level={4} style={{ margin: 0 }}>知识库管理</Title>
        <Space>
          <Input
            placeholder="搜索..."
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear             // 允许一键清空
          />
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
        - 全部无数据提示"暂无知识库"
      */}
      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip="加载中..." /></div>
        ) : filteredKBs.length === 0 ? (
          <Empty description={searchText ? '未找到匹配的知识库' : '暂无知识库，点击上方按钮创建'} />
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

// 默认导出 KBManagement 组件
export default KBManagement;
