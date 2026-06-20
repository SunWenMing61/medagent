import React, { useState, useEffect } from 'react';
import {
  Table,
  Tag,
  Typography,
  message as antMessage,
  Card,
  Spin,
  Empty,
  Button,
  Space,
  Tooltip,
} from 'antd';
import {
  ReloadOutlined,
  LikeOutlined,
  DislikeOutlined,
  WarningOutlined,
  QuestionCircleOutlined,
  MessageOutlined,
} from '@ant-design/icons';
import { getAdminFeedback, type AdminFeedback } from '../services/api';

const { Title, Text } = Typography;

const feedbackConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  like: { label: '有帮助', color: 'green', icon: <LikeOutlined /> },
  helpful: { label: '有帮助', color: 'green', icon: <LikeOutlined /> },
  dislike: { label: '无帮助', color: 'red', icon: <DislikeOutlined /> },
  inaccurate: { label: '不准确', color: 'red', icon: <DislikeOutlined /> },
  irrelevant: { label: '不相关', color: 'orange', icon: <QuestionCircleOutlined /> },
  incomplete: { label: '不完整', color: 'gold', icon: <MessageOutlined /> },
  risk_warning: { label: '风险警告', color: 'purple', icon: <WarningOutlined /> },
};

const AdminFeedbackPage: React.FC = () => {
  const [feedback, setFeedback] = useState<AdminFeedback[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchFeedback();
  }, []);

  const fetchFeedback = async () => {
    setLoading(true);
    try {
      const data = await getAdminFeedback();
      setFeedback(data);
    } catch (err: any) {
      antMessage.error('获取反馈列表失败');
    } finally {
      setLoading(false);
    }
  };

  const getFeedbackInfo = (type: string) => {
    return feedbackConfig[type] || {
      label: type,
      color: 'default',
      icon: <QuestionCircleOutlined />,
    };
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
      width: 120,
      render: (_: any, record: AdminFeedback) => (
        <Text>{record.username || `用户 #${record.user_id || '?'}`}</Text>
      ),
    },
    {
      title: '消息 ID',
      dataIndex: 'message_id',
      key: 'message_id',
      width: 90,
    },
    {
      title: '反馈类型',
      dataIndex: 'feedback_type',
      key: 'feedback_type',
      width: 130,
      render: (type: string) => {
        const info = getFeedbackInfo(type);
        return (
          <Tag color={info.color} icon={info.icon}>
            {info.label}
          </Tag>
        );
      },
    },
    {
      title: '评价内容',
      dataIndex: 'comment',
      key: 'comment',
      ellipsis: true,
      render: (comment: string) =>
        comment || <Text type="secondary">-</Text>,
    },
    {
      title: '提交时间',
      dataIndex: 'created_at',
      key: 'created_at',
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
          反馈管理
        </Title>
        <Tooltip title="刷新">
          <Button icon={<ReloadOutlined />} onClick={fetchFeedback} loading={loading}>
            刷新
          </Button>
        </Tooltip>
      </div>

      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : feedback.length === 0 ? (
          <Empty description="暂无用户反馈" />
        ) : (
          <Table
            dataSource={feedback}
            columns={columns}
            rowKey="id"
            loading={loading}
            pagination={{
              pageSize: 10,
              showSizeChanger: true,
              showTotal: (total) => `共 ${total} 条反馈`,
            }}
          />
        )}
      </Card>
    </div>
  );
};

export { AdminFeedbackPage as AdminFeedback };
export default AdminFeedbackPage;
