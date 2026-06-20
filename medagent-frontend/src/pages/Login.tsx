import React, { useState } from 'react';
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
import {
  UserOutlined,
  LockOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { login } from '../services/api';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const { token } = theme.useToken();

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const response = await login({
        username: values.username,
        password: values.password,
      });

      localStorage.setItem('access_token', response.access_token);
      localStorage.setItem('user_role', response.role);
      localStorage.setItem('user_id', String(response.user_id));
      localStorage.setItem('username', response.username);

      message.success(`欢迎回来，${response.username}！`);
      navigate('/dashboard', { replace: true });
    } catch (error: any) {
      const errorMsg =
        error.response?.data?.detail ||
        error.response?.data?.message ||
        '登录失败，请检查用户名和密码';
      message.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const fillAdminCredentials = () => {
    form.setFieldsValue({
      username: 'admin',
      password: 'admin123',
    });
  };

  return (
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
      <Card
        style={{
          width: 420,
          boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
          borderRadius: 12,
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <SafetyCertificateOutlined
            style={{ fontSize: 48, color: token.colorPrimary, marginBottom: 8 }}
          />
          <Title level={3} style={{ margin: 0 }}>
            MedAgent
          </Title>
          <Text type="secondary">医学知识库智能问答平台</Text>
        </div>

        <Form
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="username"
            rules={[
              { required: true, message: '请输入用户名' },
              { min: 2, message: '用户名至少2个字符' },
            ]}
          >
            <Input
              prefix={<UserOutlined />}
              placeholder="用户名"
              autoFocus
            />
          </Form.Item>

          <Form.Item
            name="password"
            rules={[
              { required: true, message: '请输入密码' },
              { min: 4, message: '密码至少4个字符' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="密码"
            />
          </Form.Item>

          <Form.Item style={{ marginBottom: 12 }}>
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

        <Space
          direction="vertical"
          style={{ width: '100%', textAlign: 'center' }}
        >
          <Text type="secondary">
            还没有账号？ <Link to="/register">立即注册</Link>
          </Text>

          <Divider style={{ margin: '12px 0' }} />

          <Button type="link" size="small" onClick={fillAdminCredentials}>
            管理员快速登录
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            默认管理员: admin / admin123
          </Text>
        </Space>
      </Card>
    </div>
  );
};

export default Login;
