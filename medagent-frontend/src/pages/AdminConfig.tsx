import React, { useState, useEffect } from 'react';
import {
  Card,
  Form,
  Input,
  InputNumber,
  Button,
  message as antMessage,
  Typography,
  Spin,
  Divider,
  Space,
  Alert,
  Tooltip,
  theme,
} from 'antd';
import {
  SaveOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  RobotOutlined,
  KeyOutlined,
  ApiOutlined,
  SlidersOutlined,
} from '@ant-design/icons';
import { getModelConfig, updateModelConfig, type ModelConfig } from '../services/api';

const { Title, Text } = Typography;

const AdminConfig: React.FC = () => {
  const { token } = theme.useToken();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchConfig();
  }, []);

  const fetchConfig = async () => {
    setLoading(true);
    try {
      const data = await getModelConfig();
      form.setFieldsValue(data);
    } catch (err: any) {
      antMessage.error('获取配置失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (values: ModelConfig) => {
    setSaving(true);
    try {
      await updateModelConfig(values);
      antMessage.success('配置已保存');
    } catch (err: any) {
      antMessage.error(err.response?.data?.detail || '保存配置失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" tip="加载配置中..." />
      </div>
    );
  }

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
          系统配置
        </Title>
        <Tooltip title="重置为当前配置">
          <Button icon={<ReloadOutlined />} onClick={fetchConfig}>
            重置
          </Button>
        </Tooltip>
      </div>

      <Alert
        message="配置说明"
        description="修改模型配置后，系统将使用新的配置处理后续的问答请求。部分配置项可能需要重启服务才能生效。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      <Card style={{ maxWidth: 640 }}>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleSave}
          initialValues={{
            temperature: 0.7,
            max_tokens: 2048,
            top_k: 5,
            similarity_threshold: 0.75,
          }}
        >
          <Divider orientation="left" plain>
            <Space>
              <RobotOutlined />
              <Text strong>模型配置</Text>
            </Space>
          </Divider>

          <Form.Item
            name="model_name"
            label={
              <Space>
                <span>模型名称</span>
                <Tooltip title="使用的 LLM 模型名称，如 gpt-4o-mini、claude-3-sonnet 等">
                  <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
                </Tooltip>
              </Space>
            }
          >
            <Input placeholder="gpt-4o-mini" prefix={<RobotOutlined />} />
          </Form.Item>

          <Form.Item
            name="api_key"
            label={
              <Space>
                <span>API 密钥</span>
                <Tooltip title="LLM 服务的 API 密钥">
                  <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
                </Tooltip>
              </Space>
            }
          >
            <Input.Password
              placeholder="sk-..."
              prefix={<KeyOutlined />}
            />
          </Form.Item>

          <Form.Item
            name="api_base"
            label={
              <Space>
                <span>API 地址</span>
                <Tooltip title="LLM 服务的 API 基础地址">
                  <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
                </Tooltip>
              </Space>
            }
          >
            <Input
              placeholder="https://api.openai.com/v1"
              prefix={<ApiOutlined />}
            />
          </Form.Item>

          <Divider orientation="left" plain>
            <Space>
              <SlidersOutlined />
              <Text strong>生成参数</Text>
            </Space>
          </Divider>

          <Form.Item
            name="temperature"
            label="温度 (Temperature)"
            tooltip="控制输出的随机性，值越高输出越多样，值越低越确定"
          >
            <InputNumber
              min={0}
              max={2}
              step={0.1}
              style={{ width: '100%' }}
              addonAfter={form.getFieldValue('temperature') !== undefined ? String(form.getFieldValue('temperature')) : ''}
            />
          </Form.Item>

          <Form.Item
            name="max_tokens"
            label="最大Token数 (Max Tokens)"
            tooltip="每次生成的最大 Token 数量"
          >
            <InputNumber
              min={256}
              max={32768}
              step={256}
              style={{ width: '100%' }}
              formatter={(value) => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
              parser={(value) => value?.replace(/,/g, '') as any}
            />
          </Form.Item>

          <Divider orientation="left" plain>
            <Space>
              <InfoCircleOutlined />
              <Text strong>检索参数</Text>
            </Space>
          </Divider>

          <Form.Item
            name="top_k"
            label="Top-K 检索数量"
            tooltip="检索时返回的最相关文档片段数量"
          >
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>

          <Form.Item
            name="similarity_threshold"
            label="相似度阈值"
            tooltip="文档检索的相似度最低阈值，低于此值的文档将被过滤"
          >
            <InputNumber
              min={0}
              max={1}
              step={0.05}
              style={{ width: '100%' }}
              formatter={(value) => `${(Number(value) * 100).toFixed(0)}%`}
              parser={(value) => (Number(value?.replace('%', '')) / 100) as 0 | 1}
            />
          </Form.Item>

          <Divider />

          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button
                type="primary"
                htmlType="submit"
                loading={saving}
                icon={<SaveOutlined />}
                size="large"
              >
                保存配置
              </Button>
              <Button onClick={() => form.resetFields()}>
                撤销修改
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

export default AdminConfig;
