// 导入 React 核心库和 useState（状态管理）、useEffect（副作用处理）钩子
import React, { useState, useEffect } from 'react';
// 从 Ant Design 导入大量 UI 组件：Card（卡片）、Form（表单）、Input（输入框）、InputNumber（数字输入）、Button（按钮）、message（消息提示）、Typography（排版）、Spin（加载）、Divider（分割线）、Space（间距）、Alert（警告提示）、Tooltip（提示信息）、theme（主题）
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
// 从 Ant Design 图标库导入：保存、重置、信息、机器人、密钥、API 接口、滑块等图标
import {
  SaveOutlined,
  ReloadOutlined,
  InfoCircleOutlined,
  RobotOutlined,
  KeyOutlined,
  ApiOutlined,
  SlidersOutlined,
} from '@ant-design/icons';
// 从 API 服务层导入获取和更新模型配置的函数，以及 ModelConfig 类型定义
import { getModelConfig, updateModelConfig, type ModelConfig } from '../services/api';

// 解构 Typography 中的 Title（标题）和 Text（文本）组件
const { Title, Text } = Typography;

// 定义 AdminConfig 系统配置组件，类型为 React.FC（函数式组件）
const AdminConfig: React.FC = () => {
  // 使用 Ant Design 的 theme token 获取当前主题的设计变量
  const { token } = theme.useToken();
  // 创建表单实例引用，用于表单数据的获取、设置和重置
  const [form] = Form.useForm();
  // 加载状态，控制初始化时的加载动画
  const [loading, setLoading] = useState(false);
  // 保存状态，控制提交保存时的按钮加载动画
  const [saving, setSaving] = useState(false);

  // 组件挂载时自动获取当前配置
  useEffect(() => {
    fetchConfig();
  }, []);

  // 异步获取模型配置并填充表单
  const fetchConfig = async () => {
    setLoading(true); // 开启加载状态
    try {
      const data = await getModelConfig(); // 调用 API 获取当前配置数据
      form.setFieldsValue(data); // 将获取到的数据填充到表单字段中
    } catch (err: any) {
      // 获取失败时显示错误提示消息
      antMessage.error('获取配置失败');
    } finally {
      setLoading(false); // 无论成功失败都关闭加载状态
    }
  };

  // 处理表单保存操作：将表单值提交到后端
  const handleSave = async (values: ModelConfig) => {
    setSaving(true); // 开启保存中状态
    try {
      await updateModelConfig(values); // 调用 API 更新模型配置
      antMessage.success('配置已保存'); // 成功提示
    } catch (err: any) {
      // 失败时优先显示后端返回的错误详情，否则显示通用错误信息
      antMessage.error(err.response?.data?.detail || '保存配置失败');
    } finally {
      setSaving(false); // 关闭保存中状态
    }
  };

  // 如果正在加载，显示全屏居中的加载动画
  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" tip="加载配置中..." /> {/* 大号 Spin 动画，附带加载提示文字 */}
      </div>
    );
  }

  // 正常渲染组件 UI
  return (
    <div>
      {/*
        页面头部：
        - 左侧显示"系统配置"标题
        - 右侧提供重置按钮，点击后重新获取当前配置（放弃未保存的改动）
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
          系统配置              {/* 页面主标题 */}
        </Title>
        <Tooltip title="重置为当前配置">
          <Button icon={<ReloadOutlined />} onClick={fetchConfig}>
            重置                    {/* 重置按钮，重新拉取后端配置 */}
          </Button>
        </Tooltip>
      </div>

      {/*
        配置说明提示条：
        - 蓝色 info 类型 Alert
        - 提醒用户修改配置后的影响范围和注意事项
      */}
      <Alert
        message="配置说明"
        description="修改模型配置后，系统将使用新的配置处理后续的问答请求。部分配置项可能需要重启服务才能生效。"
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
      />

      {/*
        配置表单卡片：
        - 最大宽度 640px，居中显示
        - 使用垂直布局（label 在上，控件在下）
      */}
      <Card style={{ maxWidth: 640 }}>
        <Form
          form={form}
          layout="vertical"           // 垂直布局模式
          onFinish={handleSave}       // 提交时触发 handleSave
          initialValues={{            // 表单的默认值（当后端无数据时使用）
            temperature: 0.7,         // 默认温度参数 0.7
            max_tokens: 2048,         // 默认最大 Token 数 2048
            top_k: 5,                 // 默认 Top-K 检索数量 5
            similarity_threshold: 0.75, // 默认相似度阈值 0.75
          }}
        >
          {/*
            第一部分：模型配置
            包含模型名称、API 密钥、API 地址三个字段
          */}
          <Divider orientation="left" plain>
            <Space>
              <RobotOutlined />       {/* 机器人图标 */}
              <Text strong>模型配置</Text> {/* 加粗标题 */}
            </Space>
          </Divider>

          {/*
            模型名称字段：
            - 带 Tooltip 提示信息，用 info 图标说明
            - 前置机器人图标
          */}
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

          {/*
            API 密钥字段：
            - 使用 Password 输入框，输入内容不可见
            - 带密钥图标前缀
          */}
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

          {/*
            API 地址字段：
            - 支持自定义 API Base URL（兼容各类代理/中转服务）
            - 带 API 接口图标前缀
          */}
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

          {/*
            第二部分：生成参数
            包含温度（temperature）和最大 Token 数（max_tokens）
          */}
          <Divider orientation="left" plain>
            <Space>
              <SlidersOutlined />     {/* 滑块图标 */}
              <Text strong>生成参数</Text>
            </Space>
          </Divider>

          {/*
            温度参数（Temperature）：
            - 范围 0~2，步长 0.1
            - 控制输出随机性，值越高越多样
            - 后缀显示当前值
          */}
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

          {/*
            最大 Token 数（Max Tokens）：
            - 范围 256~32768，步长 256
            - 使用千分位格式化显示（如 2,048）
          */}
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
              formatter={(value) => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')} // 千分位逗号格式化
              parser={(value) => value?.replace(/,/g, '') as any} // 解析时去掉逗号还原数字
            />
          </Form.Item>

          {/*
            第三部分：检索参数
            包含 Top-K 检索数量和相似度阈值
          */}
          <Divider orientation="left" plain>
            <Space>
              <InfoCircleOutlined />  {/* 信息图标 */}
              <Text strong>检索参数</Text>
            </Space>
          </Divider>

          {/*
            Top-K 检索数量：
            - 范围 1~50
            - 控制检索时返回的最相关文档片段数量
          */}
          <Form.Item
            name="top_k"
            label="Top-K 检索数量"
            tooltip="检索时返回的最相关文档片段数量"
          >
            <InputNumber min={1} max={50} style={{ width: '100%' }} />
          </Form.Item>

          {/*
            相似度阈值：
            - 范围 0~1，步长 0.05
            - 以百分比显示（如 75%），低于此值的文档将被过滤
          */}
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
              formatter={(value) => `${(Number(value) * 100).toFixed(0)}%`} // 显示为百分比格式
              parser={(value) => (Number(value?.replace('%', '')) / 100) as 0 | 1} // 从百分比解析回小数
            />
          </Form.Item>

          {/*
            表单底部分割线
          */}
          <Divider />

          {/*
            表单操作按钮区域：
            - 左侧为"保存配置"主按钮，带保存图标，提交时显示加载
            - 右侧为"撤销修改"按钮，点击恢复表单初始值
          */}
          <Form.Item style={{ marginBottom: 0 }}>
            <Space>
              <Button
                type="primary"        // 主按钮样式（蓝色）
                htmlType="submit"     // 触发表单提交行为
                loading={saving}      // 保存中显示加载状态
                icon={<SaveOutlined />}
                size="large"          // 大号按钮
              >
                保存配置
              </Button>
              <Button onClick={() => form.resetFields()}>
                撤销修改              {/* 重置表单到初始值 */}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
};

// 默认导出 AdminConfig 组件
export default AdminConfig;
