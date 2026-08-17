import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Space, Switch, Table, Tag, Typography, message } from 'antd';
import { ReloadOutlined, ToolOutlined } from '@ant-design/icons';
import {
  getGovernedTools,
  setGovernedToolEnabled,
  type GovernedTool,
} from '../services/api';

const { Title, Text } = Typography;

const ToolMonitoring: React.FC = () => {
  const [tools, setTools] = useState<GovernedTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setTools(await getGovernedTools());
    } catch (error: any) {
      message.error(error.response?.data?.detail || '加载工具状态失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (tool: GovernedTool, enabled: boolean) => {
    setUpdating(tool.name);
    try {
      await setGovernedToolEnabled(tool.name, enabled);
      message.success(`${tool.name} 已${enabled ? '启用' : '停用'}`);
      await load();
    } catch (error: any) {
      message.error(error.response?.data?.detail || '更新工具状态失败');
    } finally {
      setUpdating(null);
    }
  };

  const healthColor = (status: string) => ({
    healthy: 'success', degraded: 'warning', unavailable: 'error', disabled: 'default',
  }[status] || 'default');

  return (
    <div>
      <Space style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <Title level={4} style={{ margin: 0 }}><ToolOutlined /> 工具治理与监控</Title>
          <Text type="secondary">注册元数据、权限范围、限流策略、熔断与最近健康状态</Text>
        </div>
        <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
      </Space>
      <Card>
        <Table
          rowKey="name"
          loading={loading}
          dataSource={tools}
          scroll={{ x: 1200 }}
          pagination={false}
          columns={[
            {
              title: '工具', key: 'tool', fixed: 'left', width: 210,
              render: (_: unknown, row: GovernedTool) => (
                <div><Text strong>{row.name}</Text><br /><Text type="secondary">v{row.version} · {row.category}</Text></div>
              ),
            },
            {
              title: '健康', key: 'health', width: 130,
              render: (_: unknown, row: GovernedTool) => (
                <Space direction="vertical" size={0}>
                  <Tag color={healthColor(row.health.status)}>{row.health.status}</Tag>
                  <Text type="secondary">熔断：{row.health.circuit_state}</Text>
                </Space>
              ),
            },
            {
              title: 'P95 / 错误率', key: 'metrics', width: 160,
              render: (_: unknown, row: GovernedTool) => (
                <span>{row.health.p95_latency_ms.toFixed(1)} ms / {(row.health.error_rate_5m * 100).toFixed(1)}%</span>
              ),
            },
            {
              title: '权限范围', dataIndex: 'required_scopes', key: 'scopes', width: 190,
              render: (values: string[]) => values.length ? values.map(value => <Tag key={value}>{value}</Tag>) : '-',
            },
            {
              title: '允许 Agent', dataIndex: 'allowed_agents', key: 'agents', width: 180,
              render: (values: string[]) => values.map(value => <Tag key={value} color="blue">{value}</Tag>),
            },
            {
              title: '执行策略', key: 'policy', width: 220,
              render: (_: unknown, row: GovernedTool) => (
                <Text>超时 {row.timeout_seconds}s · 重试 {row.max_retries} · 单次上限 {row.max_calls_per_run} · 缓存 {row.cache_ttl_seconds ?? 0}s</Text>
              ),
            },
            {
              title: '风险', key: 'risk', width: 100,
              render: (_: unknown, row: GovernedTool) => <Tag color={row.risk_level === 'high' ? 'red' : row.risk_level === 'medium' ? 'orange' : 'green'}>{row.risk_level}</Tag>,
            },
            {
              title: '启用', key: 'enabled', fixed: 'right', width: 90,
              render: (_: unknown, row: GovernedTool) => (
                <Switch checked={row.enabled} loading={updating === row.name} onChange={checked => toggle(row, checked)} />
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default ToolMonitoring;
