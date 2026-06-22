// 引入 React 核心库及 useState、useEffect Hook
import React, { useState, useEffect } from 'react';
// 从 Ant Design 引入布局（栅格）、卡片、排版、统计数值、间距、列表、标签、加载中、空状态、按钮、消息提示、主题等组件
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
// 引入 Ant Design 图标：数据库、文件、消息、问号、爱心、右箭头、团队
import {
  DatabaseOutlined,
  FileOutlined,
  MessageOutlined,
  QuestionCircleOutlined,
  HeartOutlined,
  RightOutlined,
  TeamOutlined,
} from '@ant-design/icons';
// 引入 React Router 的导航函数，用于页面跳转
import { useNavigate } from 'react-router-dom';
// 引入后端 API 函数：获取知识库列表、获取文档列表、获取会话列表；同时引入数据类型 KnowledgeBase 和 Session
import { getKnowledgeBases, getDocuments, getSessions, type KnowledgeBase, type Session } from '../services/api';

// 从 Typography 中解构出 Title 和 Text 组件
const { Title, Text } = Typography;

// 定义 Dashboard 组件，类型为 React.FC
const Dashboard: React.FC = () => {
  // 获取 Ant Design 主题的 token（颜色变量等）
  const { token } = theme.useToken();
  // 知识库数量统计，初始值为 0
  const [kbCount, setKbCount] = useState(0);
  // 文档数量统计，初始值为 0
  const [docCount, setDocCount] = useState(0);
  // 最近会话列表，存储 Session 对象数组
  const [recentSessions, setRecentSessions] = useState<Session[]>([]);
  // 最近知识库列表，存储 KnowledgeBase 对象数组
  const [recentKbs, setRecentKbs] = useState<KnowledgeBase[]>([]);
  // 加载状态，初始为 true（页面加载时显示 Spin 组件）
  const [loading, setLoading] = useState(true);
  // navigate 函数：用于点击卡片时的页面跳转
  const navigate = useNavigate();

  // 组件挂载时调用 fetchDashboardData 获取数据
  useEffect(() => {
    fetchDashboardData();
  }, []); // 空依赖数组表示仅在组件挂载时执行一次

  // 异步函数：获取仪表盘所需的全部数据
  const fetchDashboardData = async () => {
    // 开始加载数据，设置 loading 为 true
    setLoading(true);
    try {
      // 使用 Promise.all 并发请求知识库列表和会话列表，提高加载效率
      const [kbs, sessions] = await Promise.all([
        getKnowledgeBases(), // 获取所有知识库
        getSessions(),       // 获取所有会话
      ]);

      // 设置知识库总数
      setKbCount(kbs.length);
      // 取前 5 个知识库作为"最近知识库"展示
      setRecentKbs(kbs.slice(0, 5));
      // 取前 5 个会话作为"最近会话"展示
      setRecentSessions(sessions.slice(0, 5));

      // 遍历每个知识库，统计所有文档总数
      let totalDocs = 0;
      try {
        // 为每个知识库调用 getDocuments 获取其文档列表，返回 Promise 数组
        const docPromises = kbs.map((kb) => getDocuments(kb.id));
        // 等待所有文档请求完成，得到二维数组
        const docResults = await Promise.all(docPromises);
        // 使用 reduce 将所有知识库的文档数量累加
        totalDocs = docResults.reduce((sum, docs) => sum + docs.length, 0);
      } catch {
        // 如果文档计数请求失败（比如某些知识库无权限），静默失败，totalDocs 保持为 0
      }
      // 设置文档总数
      setDocCount(totalDocs);
    } catch (error: any) {
      // 如果请求整体失败，弹出错误提示消息
      antMessage.error('获取数据失败');
    } finally {
      // 无论成功或失败，最终将 loading 设为 false，隐藏加载界面
      setLoading(false);
    }
  };

  // 功能模块卡片数据配置（通用问答和健康咨询两个入口）
  const featureCards = [
    {
      title: '通用问答',
      description: '基于知识库的智能问答系统，快速获取准确答案',
      icon: <QuestionCircleOutlined style={{ fontSize: 48, color: token.colorPrimary }} />, // 问号图标，主色
      path: '/qa',                        // 点击后跳转的路由路径
      color: token.colorPrimaryBg,        // 卡片背景色（主色背景）
      accentColor: token.colorPrimary,    // 强调色（主色）
      features: ['自动检索所有知识库', '支持文档/图片上传', '联网搜索能力', '深度思考模式'],
    },
    {
      title: '健康咨询',
      description: '提供健康建议和医疗信息查询服务',
      icon: <HeartOutlined style={{ fontSize: 48, color: token.colorError }} />, // 爱心图标，错误色（红色警示）
      path: '/health',                      // 点击后跳转的路由路径
      color: token.colorErrorBg,            // 卡片背景色（错误色背景）
      accentColor: token.colorError,        // 强调色（红色）
      features: ['专业健康知识库', '智能症状分析', '用药查询', '安全提醒与免责'],
    },
  ];

  // 如果处于加载状态，渲染全屏居中 Spin 加载器
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        {/* 大号加载中 Spin，带 "加载中..." 提示文字 */}
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  // 正常渲染仪表盘页面内容
  return (
    <div>
      {/* 页面主标题：Level 4，底部 24px 间距 */}
      <Title level={4} style={{ marginBottom: 24 }}>
        工作台
      </Title>

      {/* 统计数据卡片行：24px 栅格间距和行间距，底部 24px */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {/* 知识库数量卡片：在小屏占满整行（24列），sm 断点起占 8 列（1/3） */}
        <Col xs={24} sm={8}>
          {/* 可悬停卡片，点击跳转到 /kb（知识库管理页面） */}
          <Card hoverable onClick={() => navigate('/kb')}>
            <Statistic
              title="知识库数量"                                    // 统计标题
              value={kbCount}                                      // 统计数值
              prefix={<DatabaseOutlined />}                        // 前置数据库图标
              valueStyle={{ color: token.colorPrimary }}           // 数值颜色使用主题主色
            />
          </Card>
        </Col>
        {/* 文档数量卡片 */}
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => navigate('/documents')}>
            <Statistic
              title="文档数量"
              value={docCount}
              prefix={<FileOutlined />}
              valueStyle={{ color: token.colorSuccess }}           // 数值颜色使用成功色（绿色）
            />
          </Card>
        </Col>
        {/* 会话数量卡片 */}
        <Col xs={24} sm={8}>
          <Card hoverable onClick={() => navigate('/qa')}>
            <Statistic
              title="会话数量"
              value={recentSessions.length}
              prefix={<MessageOutlined />}
              valueStyle={{ color: token.colorWarning }}           // 数值颜色使用警告色（橙色）
            />
          </Card>
        </Col>
      </Row>

      {/* 快速问答功能入口卡片：Level 5 副标题，底部 16px */}
      <Title level={5} style={{ marginBottom: 16 }}>
        快速问答
      </Title>
      {/* 两列栅格布局，24px 间距 */}
      <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
        {/* 遍历 featureCards 数组，动态渲染每个功能卡片 */}
        {featureCards.map((feature) => (
          // 在小屏占满整行，中等屏幕起占 12 列（一半）
          <Col xs={24} md={12} key={feature.path}>
            {/* 可悬停卡片，自定义类名，圆角边框，点击跳转到对应功能路径 */}
            <Card
              hoverable
              className="dashboard-feature-card"
              style={{
                borderRadius: 12,
                border: `1px solid ${token.colorBorderSecondary}`,
                overflow: 'hidden',
                height: '100%',
              }}
              styles={{ body: { padding: 0, height: '100%' } }}  // 去除默认内边距，让自定义布局占满
              onClick={() => navigate(feature.path)}
            >
              {/* 卡片内部弹性布局：水平排列图标区 + 内容区，带渐变背景 */}
              <div style={{
                display: 'flex',
                height: '100%',
                background: `linear-gradient(135deg, ${feature.color} 0%, color-mix(in srgb, ${feature.color} 30%, ${token.colorBgContainer}) 100%)`,
              }}>
                {/* 左侧图标区域：100px 固定宽度，Flex 居中，纯色背景 */}
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
                {/* 右侧内容区域：flex:1 自适应，内边距 18px 20px，垂直弹性布局，居中对齐 */}
                <div style={{ flex: 1, padding: '18px 20px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10 }}>
                  {/* 标题行 */}
                  <div>
                    {/* 功能标题，Level 5，无外边距 */}
                    <Title level={5} style={{ margin: 0 }}>{feature.title}</Title>
                    {/* 功能描述，次要文本，小号字体 */}
                    <Text type="secondary" style={{ fontSize: 13, display: 'block', marginTop: 4 }}>
                      {feature.description}
                    </Text>
                  </div>
                  {/* 功能特性标签列表：flex 换行显示 */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 12px' }}>
                    {feature.features.map((feat: string, i: number) => (
                      // 每个特性项：横向弹性布局，小字号，次要文本颜色
                      <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: token.colorTextSecondary }}>
                        {/* 装饰性的星号点，使用强调色 */}
                        <span style={{ color: feature.accentColor, fontSize: 14, lineHeight: 1 }}>✦</span>
                        {feat}
                      </div>
                    ))}
                  </div>
                  {/* "开始使用"跳转链接区域 */}
                  <div style={{ marginTop: 2 }}>
                    {/* 文字链接按钮，带右箭头图标，使用强调色 */}
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

      {/* 最近数据区：知识库和会话两个列表 */}
      <Row gutter={[16, 16]}>
        {/* 最近知识库列表：小屏占满，中屏占 12 列 */}
        <Col xs={24} md={12}>
          <Card
            // 卡片标题：带数据库图标和文字 "最近知识库"
            title={
              <Space>
                <DatabaseOutlined />
                <span>最近知识库</span>
              </Space>
            }
            // 右上角 "查看全部" 按钮，点击跳转到 /kb
            extra={<Button type="link" onClick={() => navigate('/kb')}>查看全部</Button>}
          >
            {/* 如果 recentKbs 为空，渲染空状态组件 */}
            {recentKbs.length === 0 ? (
              <Empty description="暂无知识库" />
            ) : (
              // 使用 Ant Design List 组件渲染知识库列表
              <List
                dataSource={recentKbs}
                renderItem={(kb) => (
                  <List.Item>
                    {/* 列表项的 Meta 信息：标题为知识库名称，描述包含类型标签和可见性 */}
                    <List.Item.Meta
                      title={kb.name}
                      description={
                        <Space>
                          {/* 知识库类型标签：如 "QA"、"RAG" 等，蓝色 */}
                          <Tag color="blue">{kb.type}</Tag>
                          {/* 可见性显示：public 显示"公开"，其他显示"私有" */}
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
        {/* 最近会话列表：小屏占满，中屏占 12 列 */}
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
            {/* 如果 recentSessions 为空，渲染空状态组件 */}
            {recentSessions.length === 0 ? (
              <Empty description="暂无会话记录" />
            ) : (
              // 使用 List 组件渲染会话列表，每个列表项可点击跳转到 QA 页面并携带会话 ID
              <List
                dataSource={recentSessions}
                renderItem={(session) => (
                  // 列表项：点击跳转到 /qa?s=会话ID，鼠标悬停显示指针
                  <List.Item
                    onClick={() => navigate(`/qa?s=${session.id}`)}
                    style={{ cursor: 'pointer' }}
                  >
                    <List.Item.Meta
                      // 标题优先显示 session.title，如果为空则截取 ID 前 8 位作为显示名
                      title={session.title || `会话 ${session.id.substring(0, 8)}...`}
                      // 描述区域：显示创建时间和消息数量
                      description={
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {/* 如果有 created_at 字段，格式化为中文区域日期时间字符串 */}
                          {session.created_at
                            ? new Date(session.created_at).toLocaleString('zh-CN')
                            : ''}
                          {/* 如果有 message_count，显示消息条数 */}
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
      {/* 自定义 CSS 样式：功能卡片悬停动效，0.25s 过渡，上移 3px 并加深阴影 */}
      <style>{`
        .dashboard-feature-card { transition: all 0.25s ease !important; }
        .dashboard-feature-card:hover { transform: translateY(-3px) !important; box-shadow: 0 8px 24px rgba(0,0,0,0.10) !important; }
      `}</style>
    </div>
  );
};

// 导出 Dashboard 组件供路由使用
export default Dashboard;
