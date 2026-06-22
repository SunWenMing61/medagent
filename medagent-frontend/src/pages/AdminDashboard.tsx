// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）钩子
import React, { useState, useEffect } from 'react';
// 从 Ant Design 组件库导入布局组件 Row（行）、Col（列）、卡片 Card、统计数值 Statistic、排版 Typography、加载 Spin、按钮 Button、间距 Space、主题 theme
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
// 从 Ant Design 图标库导入用户、数据库、文件、消息、团队、安全证书和刷新图标
import {
  UserOutlined,
  DatabaseOutlined,
  FileOutlined,
  MessageOutlined,
  TeamOutlined,
  SafetyCertificateOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
// 从 API 服务层导入获取管理统计数据的函数和 AdminStats 类型定义
import { getAdminStats, type AdminStats } from '../services/api';

// 解构 Typography 中的 Title 标题组件
const { Title } = Typography;

// 定义 AdminDashboard 管理仪表盘组件，类型为 React.FC（函数式组件）
const AdminDashboard: React.FC = () => {
  // 使用 Ant Design 的 theme token 获取当前主题的设计变量（颜色等）
  const { token } = theme.useToken();
  // 管理统计数据的状态，初始为 null，类型为 AdminStats 或 null
  const [stats, setStats] = useState<AdminStats | null>(null);
  // 管理加载状态的标志，初始为 false，表示不在加载中
  const [loading, setLoading] = useState(false);

  // 组件挂载时执行副作用：首次获取数据，并启动每30秒自动轮询
  useEffect(() => {
    fetchStats();
    // 设置定时器，每30秒自动重新拉取统计数据，实现实时更新
    const timer = setInterval(fetchStats, 30000);
    // 组件卸载时清除定时器，防止内存泄漏
    return () => clearInterval(timer);
  }, []);

  // 异步获取管理统计数据的方法
  const fetchStats = async () => {
    setLoading(true); // 设置加载状态为 true
    try {
      const data = await getAdminStats(); // 调用 API 获取统计数据
      setStats(data); // 将获取到的数据保存到状态中
    } catch {
      // 静默处理错误：统计加载失败不做提示，不影响页面展示
    } finally {
      setLoading(false); // 无论成功或失败，最终都将加载状态设为 false
    }
  };

  // 定义六张统计卡片的数据数组，每项包含标题、数值、图标、颜色和背景色
  const statCards = [
    {
      title: '用户总数', // 卡片标题
      value: stats?.total_users ?? stats?.user_count ?? 0, // 优先取 total_users，其次 user_count，最后默认 0
      icon: <UserOutlined />, // 用户图标
      color: token.colorPrimary, // 文字/图标主色
      bgColor: token.colorPrimaryBg, // 卡片背景色（主色背景）
    },
    {
      title: '知识库数量', // 卡片标题
      value: stats?.total_kbs ?? stats?.kb_count ?? 0, // 优先取 total_kbs，其次 kb_count，最后默认 0
      icon: <DatabaseOutlined />, // 数据库图标
      color: token.colorSuccess, // 成功色（绿色系）
      bgColor: token.colorSuccessBg, // 成功色背景
    },
    {
      title: '线下文档总数', // 卡片标题
      value: stats?.uploaded_documents ?? stats?.total_documents ?? stats?.doc_count ?? 0, // 按优先级取三个字段，兼容不同后端返回格式
      icon: <FileOutlined />, // 文件图标
      color: token.colorWarning, // 警告色（橙色系）
      bgColor: token.colorWarningBg, // 警告色背景
    },
    {
      title: '总会话数', // 卡片标题
      value: stats?.total_sessions ?? 0, // 取总会话数，不存在则默认为 0
      icon: <MessageOutlined />, // 消息图标
      color: token.colorPrimary, // 主色
      bgColor: token.colorPrimaryBg, // 主色背景
    },
    {
      title: '总消息数', // 卡片标题
      value: stats?.total_messages ?? 0, // 取总消息数，不存在则默认为 0
      icon: <SafetyCertificateOutlined />, // 安全证书图标
      color: token.colorSuccess, // 成功色
      bgColor: token.colorSuccessBg, // 成功色背景
    },
    {
      title: '今日活跃用户', // 卡片标题
      value: stats?.active_users_today ?? 0, // 取今日活跃用户数，不存在则默认为 0
      icon: <TeamOutlined />, // 团队图标
      color: token.colorWarning, // 警告色
      bgColor: token.colorWarningBg, // 警告色背景
    },
  ];

  // 组件 JSX 渲染
  return (
    <div>
      {/*
        页面头部区域：
        - 左侧显示"管理概览"标题
        - 右侧放置刷新按钮，点击后重新拉取统计数据
      */}
      <div
        style={{
          display: 'flex',          // 使用弹性布局
          justifyContent: 'space-between', // 左右两端对齐
          alignItems: 'center',      // 垂直居中
          marginBottom: 24,          // 底部留白 24px
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          管理概览               {/* 页面主标题 */}
        </Title>
        <Button icon={<ReloadOutlined />} onClick={fetchStats} loading={loading}>
          刷新                   {/* 刷新按钮，点击触发 fetchStats，loading 状态显示旋转 */}
        </Button>
      </div>

      {/*
        统计卡片网格布局：
        - Row 为行，gutter 设置卡片间距
        - 响应式：超小屏每行1列、小屏每行2列、大屏每行3列
      */}
      <Row gutter={[16, 16]}>
        {statCards.map((card, index) => (
          <Col xs={24} sm={12} lg={8} key={index}>
            {/*
              每张统计卡片：
              - hoverable 允许鼠标悬停效果
              - 背景色使用前面定义的颜色
              - 无边框，圆角 8px
            */}
            <Card
              hoverable
              style={{ background: card.bgColor, border: 'none', borderRadius: 8 }}
            >
              {loading ? (
                // 加载状态下显示居中旋转的 Spin 加载动画
                <div style={{ textAlign: 'center', padding: 12 }}>
                  <Spin />
                </div>
              ) : (
                // 正常状态下显示 Statistic 统计数值组件
                <Statistic
                  title={
                    // 自定义标题：图标 + 文字并排显示
                    <Space>
                      <span style={{ color: card.color }}>{card.icon}</span>
                      <span>{card.title}</span>
                    </Space>
                  }
                  value={card.value}             // 绑定数值
                  valueStyle={{ color: card.color, fontSize: 28 }} // 数值样式：颜色和字号
                />
              )}
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
};

// 默认导出 AdminDashboard 组件，供路由或其他模块引用
export default AdminDashboard;
