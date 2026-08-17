import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { DeleteOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  clearAgentMemory, createAgentMemory, deleteAgentMemory, getAgentMemories, getMemorySettings,
  setLongTermMemory, setMedicalSensitiveMemory, type AgentMemoryItem, type MemorySettings,
} from '../services/api';

const { Title, Text } = Typography;

const MemoryManagement: React.FC = () => {
  const [items, setItems] = useState<AgentMemoryItem[]>([]);
  const [settings, setSettings] = useState<MemorySettings>();
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [memory, currentSettings] = await Promise.all([getAgentMemories(), getMemorySettings()]);
      setItems(memory); setSettings(currentSettings);
    } catch (error: any) { message.error(error.response?.data?.detail || '加载 Memory 失败'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    try {
      const values = await form.validateFields();
      await createAgentMemory(values); message.success('已写入用户确认的长期 Memory');
      setOpen(false); form.resetFields(); await load();
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(error.response?.data?.detail || '写入失败');
    }
  };

  return <div>
    <Space style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
      <div><Title level={4} style={{ margin: 0 }}>Agent Memory 管理</Title>
        <Text type="secondary">Memory 只用于个性化与上下文，不作为医学结论证据。</Text></div>
      <Space><Button icon={<ReloadOutlined />} onClick={load}>刷新</Button><Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>添加</Button></Space>
    </Space>
    <Card style={{ marginBottom: 16 }}>
      <Space size="large" wrap>
        <Space>长期 Memory <Switch checked={settings?.long_term_memory_enabled} onChange={async checked => { await setLongTermMemory(checked); await load(); }} /></Space>
        <Space>医学敏感信息 <Switch checked={settings?.medical_sensitive_memory_enabled} onChange={async checked => { await setMedicalSensitiveMemory(checked); await load(); }} /></Space>
        <Popconfirm title="清空全部长期 Memory？" description="该操作会保留审计记录。" onConfirm={async () => { const r = await clearAgentMemory(); message.success(`已清除 ${r.deleted_count} 条`); await load(); }}>
          <Button danger>清空长期 Memory</Button>
        </Popconfirm>
      </Space>
    </Card>
    <Card><Table rowKey="memory_id" loading={loading} dataSource={items} scroll={{ x: 1000 }} columns={[
      { title: '主题', key: 'fact', width: 280, render: (_, row) => <><Text strong>{row.subject}</Text><br/><Text type="secondary">{row.predicate}</Text></> },
      { title: '内容', dataIndex: 'value', render: value => typeof value === 'string' ? value : JSON.stringify(value) },
      { title: '类别', dataIndex: 'category', width: 150, render: value => <Tag>{value}</Tag> },
      { title: '敏感度', dataIndex: 'sensitivity', width: 130, render: value => <Tag color={value === 'normal' ? 'green' : 'orange'}>{value}</Tag> },
      { title: '状态/版本', width: 130, render: (_, row) => <>{row.status} · v{row.version}</> },
      { title: '操作', width: 80, fixed: 'right', render: (_, row) => <Popconfirm title="删除这条 Memory？" onConfirm={async () => { await deleteAgentMemory(row.memory_id); await load(); }}><Button danger type="text" icon={<DeleteOutlined />}/></Popconfirm> },
    ]}/></Card>
    <Modal title="添加明确的用户 Memory" open={open} onOk={create} onCancel={() => setOpen(false)} destroyOnClose>
      <Form form={form} layout="vertical" initialValues={{ category: 'preference', sensitivity: 'normal' }}>
        <Form.Item name="category" label="类别" rules={[{ required: true }]}><Select options={['preference','profile','project_context','communication_style','explicit_user_fact'].map(value => ({ value, label: value }))}/></Form.Item>
        <Form.Item name="subject" label="主题" rules={[{ required: true }]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="predicate" label="关系" rules={[{ required: true }]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="value" label="内容" rules={[{ required: true }]}><Input.TextArea rows={4}/></Form.Item>
        <Form.Item name="sensitivity" label="敏感度"><Select options={['normal','personal','medical_sensitive'].map(value => ({ value, label: value }))}/></Form.Item>
      </Form>
    </Modal>
  </div>;
};

export default MemoryManagement;
