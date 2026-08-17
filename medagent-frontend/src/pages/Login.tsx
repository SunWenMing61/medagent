// 引入 React 核心库及 useState 状态管理 Hook
import React, { useState } from 'react';
// 从 Ant Design 组件库引入表单、输入框、按钮、卡片、排版、间距、消息提示、分割线、主题等 UI 组件
import {
  Form,
  Input,
  Button,
  Card,
  Typography,
  Space,
  message,
  Divider,
  theme,
} from 'antd';
// 引入 Ant Design 图标：用户图标、锁图标、安全证书图标
import {
  UserOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
// 引入 React Router 的导航和链接组件，用于页面跳转
import { useNavigate, Link } from 'react-router-dom';
// 引入后端登录 API 调用函数
import { login } from '../services/api';

// 从 Typography 中解构出 Title 和 Text 组件，用于展示标题和文本
const { Title, Text } = Typography;

// Local development convenience only. Vite excludes this block from production
// behavior because import.meta.env.DEV is false in production builds. Values come
// from the git-ignored .env.local file and are never hard-coded in source control.
const devAdminUsername = import.meta.env.DEV
  ? import.meta.env.VITE_DEV_ADMIN_USERNAME
  : undefined;
const devAdminPassword = import.meta.env.DEV
  ? import.meta.env.VITE_DEV_ADMIN_PASSWORD
  : undefined;
const hasLocalDevCredentials = Boolean(devAdminUsername && devAdminPassword);

// 定义 Login 组件，类型为 React.FC（函数式组件）
const Login: React.FC = () => {
  // loading 状态：控制登录按钮的加载中动画，初始值为 false
  const [loading, setLoading] = useState(false);
  // navigate 函数：用于编程式导航跳转到其他路由页面
  const navigate = useNavigate();
  // 创建表单实例，用于管理表单字段的值和校验状态
  const [form] = Form.useForm();
  // 获取当前 Ant Design 主题的 token（颜色、间距等设计变量）
  const { token } = theme.useToken();

  // 处理表单提交的异步函数，接收用户名和密码作为参数
  const handleSubmit = async (values: { username: string; password: string }) => {
    // 提交时设置 loading 为 true，显示按钮的加载转圈效果
    setLoading(true);
    try {
      // 调用后端登录 API，传入用户名和密码，等待响应
      const response = await login({
        username: values.username,
        password: values.password,
      });

      // 登录成功后，将 access_token（JWT 令牌）保存到浏览器 localStorage
      localStorage.setItem('access_token', response.access_token);
      // 将用户角色（如 admin/user）保存到 localStorage
      localStorage.setItem('user_role', response.role);
      // 将用户 ID（转为字符串）保存到 localStorage
      localStorage.setItem('user_id', String(response.user_id));
      // 将用户名保存到 localStorage
      localStorage.setItem('username', response.username);

      // 弹出成功提示消息，显示欢迎语和用户名
      message.success(`欢迎回来，${response.username}！`);
      // 跳转到工作台页面，replace: true 表示替换当前路由历史记录（不可回退到登录页）
      navigate('/dashboard', { replace: true });
    } catch (error: any) {
      // 如果登录出错，从错误对象中提取后端返回的详细错误信息
      const errorMsg =
        error.response?.data?.detail ||      // 优先使用后端返回的 detail 字段
        error.response?.data?.message ||       // 其次使用 message 字段
        '登录失败，请检查用户名和密码';           // 兜底默认错误消息
      // 弹出错误提示消息
      message.error(errorMsg);
    } finally {
      // 无论成功还是失败，最终都将 loading 恢复为 false
      setLoading(false);
    }
  };

  // 快速填充管理员登录凭据的函数
  const fillAdminCredentials = () => {
    // 使用表单实例的 setFieldsValue 方法设置表单字段值
    form.setFieldsValue({
      username: devAdminUsername || 'admin',
      password: devAdminPassword || '',
    });
  };

  // 返回组件的 JSX 渲染内容
  return (
    // 最外层容器 div：占满全屏视口高度，使用 Flex 居中，渐变紫色背景，内边距 24px
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
      {/* Card 卡片组件：固定宽度 420px，带有阴影和圆角 */}
      <Card
        style={{
          width: 420,
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          borderRadius: 12,
        }}
      >
        {/* 头部区域：居中对齐，底部留出 32px 间距 */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          {/* 安全证书图标：48px 大小，使用主题主色，底部留 8px 间距 */}
          <SafetyCertificateOutlined
            style={{ fontSize: 48, color: token.colorPrimary, marginBottom: 8 }}
          />
          {/* 标题 Level 3：显示平台名称 MedAgent */}
          <Title level={3} style={{ margin: 0 }}>
            MedAgent
          </Title>
          {/* 次要文本：平台描述 "医学知识库智能问答平台" */}
          <Text type="secondary">医学知识库智能问答平台</Text>
        </div>

        {/* Ant Design 表单：关联 form 实例，垂直布局，提交时触发 handleSubmit */}
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          autoComplete="off"
          size="large"
        >
          {/* 用户名表单项：必填校验（至少2个字符） */}
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 2, message: '用户名至少2个字符' },
            ]}
          >
            {/* 输入框：前置用户图标，占位提示文字，自动聚焦 */}
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoFocus
            />
          </Form.Item>

          {/* 密码表单项：必填校验（至少4个字符） */}
          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 4, message: '密码至少4个字符' },
            ]}
          >
            {/* 密码输入框（带切换可见性按钮）：前置锁图标 */}
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          {/* 登录按钮表单项：底部间距 12px */}
          <Form.Item style={{ marginBottom: 12 }}>
            {/* 主色调按钮，type="submit" 提交表单，loading 状态与 state 绑定，满宽显示 */}
            <Button
              type="primary"
              htmlType="submit"
              loading={loading}
              block
            >
              登录
            </Button>
          </Form.Item>
        </Form>

        {/* 垂直方向的间距容器：全宽居中显示 */}
        <Space
          direction="vertical"
          style={{ width: '100%', textAlign: 'center' }}
        >
          {/* 注册入口提示文本：链接跳转到 /register 注册页面 */}
          <Text type="secondary">
            还没有账号？ <Link to="/register">立即注册</Link>
          </Text>

          {/* 分割线：上下间距 12px */}
          <Divider style={{ margin: '12px 0' }} />

          {hasLocalDevCredentials ? (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text type="warning" strong>仅本机开发环境临时凭据</Text>
              <Text>账号：<Text code copyable>{devAdminUsername}</Text></Text>
              <Text>密码：<Text code copyable>{devAdminPassword}</Text></Text>
              <Button type="link" size="small" onClick={fillAdminCredentials}>
                填充管理员账号和密码
              </Button>
            </Space>
          ) : (
            <>
              <Button type="link" size="small" onClick={fillAdminCredentials}>
                管理员快速登录
              </Button>
              <Text type="secondary" style={{ fontSize: 12 }}>
                管理员账号：admin（密码请向管理员获取）
              </Text>
            </>
          )}
        </Space>
      </Card>
    </div>
  );
};

// 导出 Login 组件供路由使用
export default Login;
