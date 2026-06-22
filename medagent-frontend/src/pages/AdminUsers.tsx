// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）钩子
import React, { useState, useEffect } from 'react';
// 从 Ant Design 导入 UI 组件：Table（表格）、Tag（标签）、Button（按钮）、Space（间距）、message（消息提示）、Typography（排版）、Switch（开关）、Card（卡片）、Spin（加载）、Empty（空状态）、Tooltip（提示）、Avatar（头像）、theme（主题）
import {
  Table,
  Tag,
  Button,
  Space,
  message as antMessage,
  Typography,
  Switch,
  Card,
  Spin,
  Empty,
  Tooltip,
  Avatar,
  theme,
} from 'antd';
// 从 Ant Design 图标库导入：用户、刷新、皇冠、停止、勾选等图标
import {
  UserOutlined,
  ReloadOutlined,
  CrownOutlined,
  StopOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
// 从 API 服务层导入获取用户列表、更新用户状态的函数以及 AdminUser 类型定义
import { getAdminUsers, updateUserStatus, type AdminUser } from '../services/api';

// 解构 Typography 中的 Title（标题）和 Text（文本）组件
const { Title, Text } = Typography;

// 定义 AdminUsers 用户管理组件，类型为 React.FC（函数式组件）
const AdminUsers: React.FC = () => {
  // 使用 Ant Design 的 theme token 获取当前主题的设计变量
  const { token } = theme.useToken();
  // 管理用户列表数据，初始为空数组
  const [users, setUsers] = useState<AdminUser[]>([]);
  // 管理表格加载状态
  const [loading, setLoading] = useState(false);
  // 管理正在更新状态切换的用户 ID，用于禁用该行的操作按钮以避免并发操作
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  // 组件挂载时自动获取用户列表
  useEffect(() => {
    fetchUsers();
  }, []);

  // 异步获取用户列表数据
  const fetchUsers = async () => {
    setLoading(true); // 开启加载状态
    try {
      const data = await getAdminUsers(); // 调用 API 获取用户列表
      setUsers(data); // 更新用户列表状态
    } catch (err: any) {
      antMessage.error('获取用户列表失败'); // 错误提示
    } finally {
      setLoading(false); // 关闭加载状态
    }
  };

  // 处理用户状态切换（启用/禁用）
  const handleStatusToggle = async (userId: number, currentStatus: string) => {
    // 根据当前状态计算新状态：'1' 或 'active' 视为启用，切换为禁用 '0'；否则切换为启用 '1'
    const newStatus = currentStatus === '1' || currentStatus === 'active' ? '0' : '1';
    setUpdatingId(userId); // 记录正在更新的用户 ID
    try {
      await updateUserStatus(userId, newStatus); // 调用 API 更新用户状态
      antMessage.success('用户状态已更新'); // 成功提示
      fetchUsers(); // 刷新用户列表
    } catch (err: any) {
      // 失败时优先显示后端错误详情，否则显示通用错误
      antMessage.error(err.response?.data?.detail || '更新状态失败');
    } finally {
      setUpdatingId(null); // 清除更新中状态
    }
  };

  // 根据状态码返回中文标签
  const getStatusLabel = (status: string) => {
    if (status === '1' || status === 'active') return '正常';
    return '已禁用';
  };

  // 判断用户是否为激活状态
  const isActive = (status: string) => {
    return status === '1' || status === 'active';
  };

  // 定义 Ant Design Table 的列配置
  const columns = [
    {
      title: 'ID',        // 列标题：用户 ID
      dataIndex: 'id',    // 对应数据字段
      key: 'id',
      width: 60,          // 列宽 60px
    },
    {
      title: '用户',      // 列标题：用户信息
      key: 'user',
      // 自定义渲染：头像 + 用户名 + 管理员标签 + 邮箱
      render: (_: any, record: AdminUser) => (
        <Space>
          {/*
            用户头像：
            - 管理员的头像背景为红色，普通用户为主色
          */}
          <Avatar
            icon={<UserOutlined />}
            style={{
              backgroundColor: record.role === 'admin' ? token.colorError : token.colorPrimary,
            }}
          />
          <div>
            <Space>
              <Text strong>{record.username}</Text> {/* 加粗显示用户名 */}
              {record.role === 'admin' && (
                // 如果是管理员，显示红色皇冠标签
                <Tag icon={<CrownOutlined />} color="red" style={{ marginRight: 0 }}>
                  管理员
                </Tag>
              )}
            </Space>
            <div>
              {/* 显示用户邮箱，无邮箱则显示"无邮箱" */}
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.email || '无邮箱'}
              </Text>
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: '角色',            // 列标题：角色
      dataIndex: 'role',
      key: 'role',
      width: 100,
      // 自定义渲染：管理员用红色标签，普通用户用蓝色标签
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>
          {role === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '状态',            // 列标题：用户状态
      dataIndex: 'status',
      key: 'status',
      width: 140,
      // 自定义渲染：Switch 开关 + 状态标签
      render: (status: string, record: AdminUser) => (
        <Space>
          {/*
            状态开关：
            - checked 根据当前状态是否激活
            - 管理员不可禁用（disabled）
            - 正在更新的行禁用开关
          */}
          <Switch
            checked={isActive(status)}
            disabled={record.role === 'admin' || updatingId === record.id}
            onChange={() => handleStatusToggle(record.id, status)}
            checkedChildren="正常"    // 开启时显示文字
            unCheckedChildren="禁用"  // 关闭时显示文字
            loading={updatingId === record.id} // 正在更新时显示加载
          />
          {/*
            状态标签：
            - 激活为绿色（success），已禁用为红色（error）
            - 显示对应图标和中文状态文字
          */}
          <Tag
            color={isActive(status) ? 'success' : 'error'}
            style={{ margin: 0 }}
          >
            {isActive(status) ? (
              <CheckCircleOutlined />  // 激活显示勾选图标
            ) : (
              <StopOutlined />         // 禁用显示停止图标
            )}
            {getStatusLabel(status)}   // 显示"正常"或"已禁用"
          </Tag>
        </Space>
      ),
    },
    {
      title: '注册时间',           // 列标题
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      // 格式化日期为中文本地时间，无日期显示 "-"
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
    {
      title: '最后登录',           // 列标题
      dataIndex: 'last_login',
      key: 'last_login',
      width: 180,
      // 同注册时间，格式化显示最后登录时间
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
  ];

  // 组件 JSX 渲染
  return (
    <div>
      {/*
        页面头部区域：
        - 左侧"用户管理"标题
        - 右侧刷新按钮
      */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          用户管理
        </Title>
        <Tooltip title="刷新">
          <Button icon={<ReloadOutlined />} onClick={fetchUsers} loading={loading}>
            刷新
          </Button>
        </Tooltip>
      </div>

      {/*
        用户列表卡片区域：
        - 加载中：显示居中 Spin 动画
        - 无数据：显示 Empty 空状态
        - 有数据：显示 Table 表格
      */}
      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : users.length === 0 ? (
          <Empty description="暂无用户数据" />
        ) : (
          <Table
            dataSource={users}       // 数据源
            columns={columns}        // 列配置
            rowKey="id"              // 以 id 作为行唯一键
            loading={loading}        // 加载状态
            pagination={{            // 分页配置
              pageSize: 10,          // 每页 10 条
              showSizeChanger: true, // 允许切换每页条数
              showTotal: (total) => `共 ${total} 个用户`, // 总条数显示
            }}
          />
        )}
      </Card>
    </div>
  );
};

// 默认导出 AdminUsers 组件
export default AdminUsers;
