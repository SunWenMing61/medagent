// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）钩子
import React, { useState, useEffect } from 'react';
// 从 Ant Design 导入 UI 组件：Table（表格）、Tag（标签）、Typography（排版）、message（消息提示）、Card（卡片）、Spin（加载）、Empty（空状态）、Button（按钮）、Space（间距）、Tooltip（提示）
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
// 从 Ant Design 图标库导入：刷新、点赞（有帮助）、点踩（无帮助）、警告、疑问、消息等图标
import {
  ReloadOutlined,
  LikeOutlined,
  DislikeOutlined,
  WarningOutlined,
  QuestionCircleOutlined,
  MessageOutlined,
} from '@ant-design/icons';
// 从 API 服务层导入获取管理反馈列表的函数和 AdminFeedback 类型定义
import { getAdminFeedback, type AdminFeedback } from '../services/api';

// 解构 Typography 中的 Title（标题）和 Text（文本）组件
const { Title, Text } = Typography;

// 反馈类型的显示配置映射表：每个类型对应中文标签、颜色和图标
const feedbackConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  like: { label: '有帮助', color: 'green', icon: <LikeOutlined /> },            // 点赞/有帮助 -> 绿色
  helpful: { label: '有帮助', color: 'green', icon: <LikeOutlined /> },          // helpful 同义词 -> 绿色
  dislike: { label: '无帮助', color: 'red', icon: <DislikeOutlined /> },         // 点踩/无帮助 -> 红色
  inaccurate: { label: '不准确', color: 'red', icon: <DislikeOutlined /> },       // 内容不准确 -> 红色
  irrelevant: { label: '不相关', color: 'orange', icon: <QuestionCircleOutlined /> }, // 答案与问题不相关 -> 橙色
  incomplete: { label: '不完整', color: 'gold', icon: <MessageOutlined /> },       // 回答不完整 -> 金色
  risk_warning: { label: '风险警告', color: 'purple', icon: <WarningOutlined /> }, // 安全/风险警告 -> 紫色
};

// 定义 AdminFeedbackPage 反馈管理页面组件，类型为 React.FC
const AdminFeedbackPage: React.FC = () => {
  // 管理反馈列表数据，初始为空数组
  const [feedback, setFeedback] = useState<AdminFeedback[]>([]);
  // 管理表格加载状态
  const [loading, setLoading] = useState(false);

  // 组件挂载时自动获取反馈列表
  useEffect(() => {
    fetchFeedback();
  }, []);

  // 异步获取反馈列表数据
  const fetchFeedback = async () => {
    setLoading(true); // 开启加载状态
    try {
      const data = await getAdminFeedback(); // 调用 API 获取所有反馈数据
      setFeedback(data); // 更新反馈列表状态
    } catch (err: any) {
      antMessage.error('获取反馈列表失败'); // 错误提示
    } finally {
      setLoading(false); // 关闭加载状态
    }
  };

  // 根据反馈类型获取对应的配置信息（标签、颜色、图标）
  const getFeedbackInfo = (type: string) => {
    return feedbackConfig[type] || {
      label: type,                 // 如果类型不在配置中，直接显示类型名
      color: 'default',            // 默认颜色
      icon: <QuestionCircleOutlined />, // 默认使用疑问图标
    };
  };

  // 定义 Ant Design Table 的列配置
  const columns = [
    {
      title: 'ID',          // 列标题：反馈 ID
      dataIndex: 'id',
      key: 'id',
      width: 60,
    },
    {
      title: '用户',        // 列标题：用户信息
      key: 'user',
      width: 120,
      // 自定义渲染：优先显示用户名，否则显示"用户 #ID"
      render: (_: any, record: AdminFeedback) => (
        <Text>{record.username || `用户 #${record.user_id || '?'}`}</Text>
      ),
    },
    {
      title: '消息 ID',     // 列标题：被反馈的消息 ID
      dataIndex: 'message_id',
      key: 'message_id',
      width: 90,
    },
    {
      title: '反馈类型',    // 列标题：反馈类型
      dataIndex: 'feedback_type',
      key: 'feedback_type',
      width: 130,
      // 自定义渲染：根据反馈类型显示不同颜色和图标标签
      render: (type: string) => {
        const info = getFeedbackInfo(type); // 获取类型配置
        return (
          <Tag color={info.color} icon={info.icon}>
            {info.label}          {/* 显示中文标签 */}
          </Tag>
        );
      },
    },
    {
      title: '评价内容',    // 列标题：用户评价文字
      dataIndex: 'comment',
      key: 'comment',
      ellipsis: true,       // 文本过长时省略显示
      // 自定义渲染：有评论显示评论，无评论显示 "-"
      render: (comment: string) =>
        comment || <Text type="secondary">-</Text>,
    },
    {
      title: '提交时间',    // 列标题：反馈提交时间
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      // 格式化日期为中文本地时间，无日期显示 "-"
      render: (date: string) =>
        date ? new Date(date).toLocaleString('zh-CN') : '-',
    },
  ];

  // 组件 JSX 渲染
  return (
    <div>
      {/*
        页面头部区域：
        - 左侧"反馈管理"标题
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
          反馈管理
        </Title>
        <Tooltip title="刷新">
          <Button icon={<ReloadOutlined />} onClick={fetchFeedback} loading={loading}>
            刷新
          </Button>
        </Tooltip>
      </div>

      {/*
        反馈列表卡片区域：
        - 加载中：显示居中 Spin 动画
        - 无数据：显示 Empty 空状态（"暂无用户反馈"）
        - 有数据：显示 Table 表格
      */}
      <Card>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60 }}>
            <Spin size="large" tip="加载中..." />
          </div>
        ) : feedback.length === 0 ? (
          <Empty description="暂无用户反馈" />
        ) : (
          <Table
            dataSource={feedback}  // 数据源
            columns={columns}      // 列配置
            rowKey="id"            // 以 id 作为行唯一键
            loading={loading}      // 加载状态
            pagination={{          // 分页配置
              pageSize: 10,        // 每页 10 条
              showSizeChanger: true, // 允许切换每页条数
              showTotal: (total) => `共 ${total} 条反馈`, // 总条数显示
            }}
          />
        )}
      </Card>
    </div>
  );
};

// 具名导出 AdminFeedbackPage 别名为 AdminFeedback，兼容两种导入方式
export { AdminFeedbackPage as AdminFeedback };
// 默认导出 AdminFeedbackPage 组件
export default AdminFeedbackPage;
