import React, { useState, useEffect } from 'react';
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
import {
  UserOutlined,
  ReloadOutlined,
  CrownOutlined,
  StopOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { getAdminUsers, updateUserStatus, type AdminUser } from '../services/api';

const { Title, Text } = Typography;

const AdminUsers: React.FC = () => {
  const { token } = theme.useToken();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await getAdminUsers();
      setUsers(data);
    } catch (err: any) {
      antMessage.error('获取用户列表失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStatusToggle = async (userId: number, currentStatus: string) => {
    const newStatus = currentStatus === '1' || currentStatus === 'active' ? '0' : '1';
    setUpdatingId(userId);
    try {
      await updateUserStatus(userId, newStatus);
      antMessage.success('用户状态已更新');
      fetchUsers();
    } catch (err: any) {
      antMessage.error(err.response?.data?.detail || '更新状态失败');
    } finally {
      setUpdatingId(null);
    }
  };

  const getStatusLabel = (status: string) => {
    if (status === '1' || status === 'active') return '正常';
    return '已禁用';
  };

  const isActive = (status: string) => {
    return status === '1' || status === 'active';
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '用户',
      key: 'user',
      render: (_: any, record: AdminUser) => (
        <Space>
          <Avatar
            icon={<UserOutlined />}
            style={{
              backgroundColor: record.role === 'admin' ? token.colorError : token.colorPrimary,
            }}
          />
          <div>
            <Space>
              <Text strong>{record.username}</Text>
              {record.role === 'admin' && (
                <Tag icon={<CrownOutlined />} color="red" style={{ marginRight: 0 }}>
                  管理员
                </Tag>
              )}
            </Space>
            <div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.email || '无邮箱'}
              </Text>
            </div>
          </div>
        </Space>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      width: 100,
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>
          {role === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 140,
      render: (status: string, record: AdminUser) => (
        <Space>
          <Switch
            checked={isActive(status)}
            disabled={record.role === 'admin' || updatingId === record.id}
            onChange={() => handleStatusToggle(record.id, status)}
            checkedChildren="正常"
            unCheckedChildren="禁用"
            loading={updatingId === record.id}
          />
          <Tag
            color={isActive(status) ? 'success' : 'error'}
            style={{ margin: 0 }}
          >
            {isActive(status) ? (
              <CheckCircleOutlined />
            ) : (
              <StopOutlined />
            )}
            {getStatusLabel(status)}
          </Tag>
        </Space>
      ),
    },
    {
      title: '注册时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
    {
      title: '最后登录',
      dataIndex: 'last_login',
      key: 'last_login',
      width: 180,
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
  ];

  return (
    <div>
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

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : users.length === 0 ? (
          <Empty description="暂无用户数据" />
        ) : (
          <Table
            dataSource={users}
            columns={columns}
            rowKey="id"
            loading={loading}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 个用户`,
            }}
          />
        )}
      </Card>
    </div>
  );
};

export default AdminUsers;
