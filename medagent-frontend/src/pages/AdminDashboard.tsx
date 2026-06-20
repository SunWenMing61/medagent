import React, { useState, useEffect } from 'react';
import {
  Row,
  Col,
  Card,
  Statistic,
  Typography,
  Spin,
  Button,
  Space,
  theme,
} from 'antd';
import {
  UserOutlined,
  DatabaseOutlined,
  FileOutlined,
  MessageOutlined,
  TeamOutlined,
  SafetyCertificateOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { getAdminStats, type AdminStats } from '../services/api';

const { Title } = Typography;

const AdminDashboard: React.FC = () => {
  const { token } = theme.useToken();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStats();
    // Auto-poll every 30 seconds for real-time updates
    const timer = setInterval(fetchStats, 30000);
    return () => clearInterval(timer);
  }, []);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const data = await getAdminStats();
      setStats(data);
    } catch {
      // Stats load silently
    } finally {
      setLoading(false);
    }
  };

  const statCards = [
    {
      title: '用户总数',
      value: stats?.total_users ?? stats?.user_count ?? 0,
      icon: <UserOutlined />,
      color: token.colorPrimary,
      bgColor: token.colorPrimaryBg,
    },
    {
      title: '知识库数量',
      value: stats?.total_kbs ?? stats?.kb_count ?? 0,
      icon: <DatabaseOutlined />,
      color: token.colorSuccess,
      bgColor: token.colorSuccessBg,
    },
    {
      title: '线下文档总数',
      value: stats?.uploaded_documents ?? stats?.total_documents ?? stats?.doc_count ?? 0,
      icon: <FileOutlined />,
      color: token.colorWarning,
      bgColor: token.colorWarningBg,
    },
    {
      title: '总会话数',
      value: stats?.total_sessions ?? 0,
      icon: <MessageOutlined />,
      color: token.colorPrimary,
      bgColor: token.colorPrimaryBg,
    },
    {
      title: '总消息数',
      value: stats?.total_messages ?? 0,
      icon: <SafetyCertificateOutlined />,
      color: token.colorSuccess,
      bgColor: token.colorSuccessBg,
    },
    {
      title: '今日活跃用户',
      value: stats?.active_users_today ?? 0,
      icon: <TeamOutlined />,
      color: token.colorWarning,
      bgColor: token.colorWarningBg,
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          管理概览
        </Title>
        <Button icon={<ReloadOutlined />} onClick={fetchStats} loading={loading}>
          刷新
        </Button>
      </div>

      <Row gutter={[16, 16]}>
        {statCards.map((card, index) => (
          <Col xs={24} sm={12} lg={8} key={index}>
            <Card
              hoverable
              style={{ background: card.bgColor, border: 'none', borderRadius: 8 }}
            >
              {loading ? (
                <div style={{ textAlign: 'center', padding: 12 }}>
                  <Spin />
                </div>
              ) : (
                <Statistic
                  title={
                    <Space>
                      <span style={{ color: card.color }}>{card.icon}</span>
                      <span>{card.title}</span>
                    </Space>
                  }
                  value={card.value}
                  valueStyle={{ color: card.color, fontSize: 28 }}
                />
              )}
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
};

export default AdminDashboard;
