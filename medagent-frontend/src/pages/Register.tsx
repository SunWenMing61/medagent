// 引入 React 核心库及 useState 状态管理 Hook
import React, { useState } from 'react';
// 从 Ant Design 组件库引入表单、输入框、按钮、卡片、排版、消息提示、主题等 UI 组件
import {
  Form,
  Input,
  Button,
  Card,
  Typography,
  message,
  theme,
} from 'antd';
// 引入 Ant Design 图标：用户、锁、邮箱、安全证书图标
import {
  UserOutlined,
  LockOutlined,
  MailOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
// 引入 React Router 的导航和链接组件，用于页面跳转
import { useNavigate, Link } from 'react-router-dom';
// 引入后端注册 API 调用函数
import { register } from '../services/api';

// 从 Typography 中解构出 Title 和 Text 组件
const { Title, Text } = Typography;

// 定义 Register 组件，类型为 React.FC（函数式组件）
const Register: React.FC = () => {
  // loading 状态：控制注册按钮的加载中动画，初始值为 false
  const [loading, setLoading] = useState(false);
  // navigate 函数：用于编程式导航跳转到登录页面
  const navigate = useNavigate();
  // 创建表单实例，用于管理表单字段的值和校验
  const [form] = Form.useForm();
  // 获取当前 Ant Design 主题的 token（颜色、间距等设计变量）
  const { token } = theme.useToken();

  // 处理表单提交的异步函数，接收用户名、密码、确认密码和邮箱
  const handleSubmit = async (values: {
    username: string;
    password: string;
    confirmPassword: string;
    email: string;
  }) => {
    // 提交时设置 loading 为 true，显示按钮加载转圈
    setLoading(true);
    try {
      // 调用后端注册 API，传入用户名、密码和邮箱（confirmPassword 不发给后端）
      await register({
        username: values.username,
        password: values.password,
        email: values.email,
      });

      // 注册成功后弹出成功提示
      message.success('注册成功！请登录');
      // 跳转到登录页面，replace: true 替换当前路由历史，不可回退到注册页
      navigate('/login', { replace: true });
    } catch (error: any) {
      // 注册出错时，从错误对象中提取后端返回的详细错误信息
      const errorMsg =
        error.response?.data?.detail ||       // 优先使用后端 detail 字段
        error.response?.data?.message ||        // 其次使用 message 字段
        '注册失败，请稍后重试';                    // 兜底默认错误消息
      // 弹出错误提示
      message.error(errorMsg);
    } finally {
      // 无论成功还是失败，最终将 loading 恢复为 false
      setLoading(false);
    }
  };

  // 返回组件的 JSX 渲染内容
  return (
    // 最外层容器：全屏高度 Flex 居中，渐变紫色背景，内边距 24px
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: 24,
      }}
    >
      {/* Card 卡片组件：固定宽度 420px，带阴影和圆角 */}
      <Card
        style={{
          width: 420,
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          borderRadius: 12,
        }}
      >
        {/* 头部图标和标题区域：居中对齐，底部留 32px 间距 */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          {/* 安全证书图标：48px 大小，使用主题主色 */}
          <SafetyCertificateOutlined
            style={{ fontSize: 48, color: token.colorPrimary, marginBottom: 8 }}
          />
          {/* 标题：显示 "创建账号" */}
          <Title level={3} style={{ margin: 0 }}>
            创建账号
          </Title>
          {/* 次要文本：提示注册平台名称 */}
          <Text type="secondary">注册 MedAgent 医学知识库问答平台</Text>
        </div>

        {/* Ant Design 表单：关联 form 实例，垂直布局，提交时触发 handleSubmit */}
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          autoComplete="off"
          size="large"
        >
          {/* 用户名字段：带标签 "用户名"，必填 + 长度 + 正则校验 */}
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true, message: '请输入用户名' },           // 必填校验
              { min: 2, message: '用户名至少2个字符' },                // 最小长度 2
              { max: 50, message: '用户名最多50个字符' },              // 最大长度 50
              // 正则校验：只允许字母、数字、下划线和中文（一-龥 覆盖所有中文字符）
              { pattern: /^[a-zA-Z0-9_一-龥]+$/, message: '用户名只能包含字母、数字、下划线和中文' },
            ]}
          >
            {/* 输入框：前置用户图标，占位提示，自动聚焦 */}
            <Input
              prefix={<UserOutlined />}
              placeholder="请输入用户名"
              autoFocus
            />
          </Form.Item>

          {/* 邮箱字段：带标签 "邮箱"，必填 + 邮箱格式校验 */}
          <Form.Item
            name="email"
            label="邮箱"
            rules={[
              { required: true, message: '请输入邮箱' },             // 必填校验
              { type: 'email', message: '请输入有效的邮箱地址' },      // 内置 email 格式校验
            ]}
          >
            {/* 输入框：前置邮箱图标 */}
            <Input
              prefix={<MailOutlined />}
              placeholder="请输入邮箱"
            />
          </Form.Item>

          {/* 密码字段：带标签 "密码"，必填 + 最小长度 6 */}
          <Form.Item
            name="password"
            label="密码"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 6, message: '密码至少6个字符' },
            ]}
          >
            {/* 密码输入框（带切换可见性按钮）：前置锁图标 */}
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入密码"
            />
          </Form.Item>

          {/* 确认密码字段：带标签 "确认密码"，依赖 password 字段做二次输入一致性校验 */}
          <Form.Item
            name="confirmPassword"
            label="确认密码"
            dependencies={['password']} // 声明依赖 password，当 password 变化时重新校验本字段
            rules={[
              { required: true, message: '请确认密码' },              // 必填校验
              // 自定义校验器：校验两次输入的密码是否一致
              ({ getFieldValue }) => ({
                validator(_, value) {
                  // 如果 value 为空或与 password 字段值相等，则校验通过
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  // 否则返回错误："两次输入的密码不一致"
                  return Promise.reject(new Error('两次输入的密码不一致'));
                },
              }),
            ]}
          >
            {/* 密码输入框：前置锁图标，用于确认密码 */}
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请再次输入密码"
            />
          </Form.Item>

          {/* 注册按钮表单项：底部间距 12px */}
          <Form.Item style={{ marginBottom: 12 }}>
            {/* 主色调按钮，type="submit" 提交表单，loading 状态绑定，满宽 */}
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
            >
              注册
            </Button>
          </Form.Item>
        </Form>

        {/* 底部链接区域：居中对齐 */}
        <div style={{ textAlign: 'center' }}>
          {/* 提示已有账号，链接跳转到登录页 */}
          <Text type="secondary">
            已有账号？ <Link to="/login">立即登录</Link>
          </Text>
        </div>
      </Card>
    </div>
  );
};

// 导出 Register 组件供路由使用
export default Register;
