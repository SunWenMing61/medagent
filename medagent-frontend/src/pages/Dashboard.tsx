import React, { useState, useEffect } from 'react';
import {
  Row,
  Col,
  Card,
  Typography,
  Statistic,
  Space,
  List,
  Tag,
  Spin,
  Empty,
  Button,
  message as antMessage,
  theme,
} from 'antd';
import {
  DatabaseOutlined,
  FileOutlined,
  MessageOutlined,
  QuestionCircleOutlined,
  HeartOutlined,
  RightOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { getKnowledgeBases, getDocuments, getSessions, type KnowledgeBase, type Session } from '../services/api';

const { Title, Text } = Typography;

const Dashboard: React.FC = () => {
  const { token } = theme.useToken();
  const [kbCount, setKbCount] = useState(0);
  const [docCount, setDocCount] = useState(0);
  const [recentSessions, setRecentSessions] = useState<Session[]>([]);
  const [recentKbs, setRecentKbs] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    setLoading(true);
    try {
      const [kbs, sessions] = await Promise.all([
        getKnowledgeBases(),
        getSessions(),
      ]);

      setKbCount(kbs.length);
      setRecentKbs(kbs.slice(0, 5));
      setRecentSessions(sessions.slice(0, 5));

      // Count documents across all KBs
      let totalDocs = 0;
      try {
        const docPromises = kbs.map((kb) => getDocuments(kb.id));
        const docResults = await Promise.all(docPromises);
        totalDocs = docResults.reduce((sum, docs) => sum + docs.length, 0);
      } catch {
        // If document count fails, just use 0
      }
      setDocCount(totalDocs);
    } catch (error: any) {
      antMessage.error('获取数据失败');
    } finally {
      setLoading(false);
    }
  };

  const featureCards = [
    {
      title: '通用问答',
      description: '基于知识库的智能问答系统，快速获取准确答案',
      icon: <QuestionCircleOutlined style={{ fontSize: 48, color: token.colorPrimary }} />,
      path: '/qa',
      color: token.colorPrimaryBg,
      accentColor: token.colorPrimary,
      features: ['自动检索所有知识库', '支持文档/图片上传', '联网搜索能力', '深度思考模式'],
    },
    {
      title: '健康咨询',
      description: '提供健康建议和医疗信息查询服务',
      icon: <HeartOutlined style={{ fontSize: 48, color: token.colorError }} />,
      path: '/health',
      color: token.colorErrorBg,
      accentColor: token.colorError,
      features: ['专业健康知识库', '智能症状分析', '用药查询', '安全提醒与免责'],
    },
  ];

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  return (
    <div>
      <Title level={4} style={{ marginBottom: 24 }}>
        工作台
      </Title>

      {/* Stats cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => navigate('/kb')}>
            <Statistic
              title="知识库数量"
              value={kbCount}
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: token.colorPrimary }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => navigate('/documents')}>
            <Statistic
              title="文档数量"
              value={docCount}
              prefix={<FileOutlined />}
              valueStyle={{ color: token.colorSuccess }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => navigate('/qa')}>
            <Statistic
              title="会话数量"
              value={recentSessions.length}
              prefix={<MessageOutlined />}
              valueStyle={{ color: token.colorWarning }}
            />
          </Card>
        </Col>
      </Row>

      {/* Feature cards — optimized two-column layout */}
      <Title level={5} style={{ marginBottom: 16 }}>
        快速问答
      </Title>
      <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
        {featureCards.map((feature) => (
          <Col xs={24} md={12} key={feature.path}>
            <Card
              hoverable
              className="dashboard-feature-card"
              style={{
                borderRadius: 12,
                border: `1px solid ${token.colorBorderSecondary}`,
                overflow: 'hidden',
                height: '100%',
              }}
              styles={{ body: { padding: 0, height: '100%' } }}
              onClick={() => navigate(feature.path)}
            >
              <div style={{
                display: 'flex',
                height: '100%',
                background: `linear-gradient(135deg, ${feature.color} 0%, color-mix(in srgb, ${feature.color} 30%, ${token.colorBgContainer}) 100%)`,
              }}>
                {/* Left: icon area */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 100,
                  flexShrink: 0,
                  background: feature.color,
                }}>
                  {feature.icon}
                </div>
                {/* Right: content area */}
                <div style={{ flex: 1, padding: '18px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10 }}>
                  <div>
                    <Title level={5} style={{ margin: 0 }}>{feature.title}</Title>
                    <Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
                      {feature.description}
                    </Text>
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px' }}>
                    {feature.features.map((feat: string, i: number) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: token.colorTextSecondary }}>
                        <span style={{ color: feature.accentColor, fontSize: 14, lineHeight: 1 }}>✦</span>
                        {feat}
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 2 }}>
                    <Button type="link" icon={<RightOutlined />} style={{ padding: 0, height: 'auto', fontSize: 13, color: feature.accentColor }}>
                      开始使用 →
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      {/* Recent data */}
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card
            title={
              <Space>
                <DatabaseOutlined />
                <span>最近知识库</span>
              </Space>
            }
            extra={<Button type="link" onClick={() => navigate('/kb')}>查看全部</Button>}
          >
            {recentKbs.length === 0 ? (
              <Empty description="暂无知识库" />
            ) : (
              <List
                dataSource={recentKbs}
                renderItem={(kb) => (
                  <List.Item>
                    <List.Item.Meta
                      title={kb.name}
                      description={
                        <Space>
                          <Tag color="blue">{kb.type}</Tag>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {kb.visibility === 'public' ? '公开' : '私有'}
                          </Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card
            title={
              <Space>
                <MessageOutlined />
                <span>最近会话</span>
              </Space>
            }
            extra={<Button type="link" onClick={() => navigate('/qa?show=sessions')}>查看全部</Button>}
          >
            {recentSessions.length === 0 ? (
              <Empty description="暂无会话记录" />
            ) : (
              <List
                dataSource={recentSessions}
                renderItem={(session) => (
                  <List.Item
                    onClick={() => navigate(`/qa?s=${session.id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <List.Item.Meta
                      title={session.title || `会话 ${session.id.substring(0, 8)}...`}
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {session.created_at
                            ? new Date(session.created_at).toLocaleString('zh-CN')
                            : ''}
                          {session.message_count !== undefined &&
                            ` · ${session.message_count} 条消息`}
                        </Text>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
      <style>{`
        .dashboard-feature-card { transition: all 0.25s ease !important; }
        .dashboard-feature-card:hover { transform: translateY(-3px) !important; box-shadow: 0 8px 24px rgba(0,0,0,0.10) !important; }
      `}</style>
    </div>
  );
};

export default Dashboard;
