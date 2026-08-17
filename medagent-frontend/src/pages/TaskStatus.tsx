/**
 * TaskStatus 页面 —— 后台任务状态监控。
 *
 * 功能：
 * - 显示当前用户的所有后台任务列表
 * - 实时进度条更新（每 3 秒轮询）
 * - 任务完成/失败通知
 * - 一键清除已完成/失败的任务
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Table, Tag, Progress, Button, Space, Typography, message as antMessage,
  Empty, Spin, Alert,
} from 'antd';
import {
  ReloadOutlined, ClearOutlined, ClockCircleOutlined,
  CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import { api } from '../services/api';

const { Title, Text } = Typography;

/** 任务状态接口 */
interface TaskInfo {
  task_id: string;
  user_id: number;
  task_type: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;        // 0-100
  message: string;
  created_at: string;
  updated_at: string;
  result?: any;
  error?: string;
  attempt?: number;
  max_attempts?: number;
}

const TaskStatus: React.FC = () => {
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  /** 获取任务列表 */
  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get('/tasks');
      setTasks(response.data || []);
      setLoadError(null);
    } catch (error: any) {
      setLoadError(error?.response?.data?.detail || '任务状态加载失败，请检查网络后重试');
    } finally {
      setLoading(false);
    }
  }, []);

  // 组件挂载时加载，之后每 3 秒轮询
  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 3000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  /** 清除已完成/失败的任务 */
  const handleClearCompleted = async () => {
    setClearing(true);
    try {
      const completed = tasks.filter(t => t.status === 'completed' || t.status === 'failed');
      for (const task of completed) {
        try {
          await api.delete(`/tasks/${task.task_id}`);
        } catch { /* 静默 */ }
      }
      antMessage.success(`已清除 ${completed.length} 个任务`);
      fetchTasks();
    } catch {
      antMessage.error('清除失败');
    } finally {
      setClearing(false);
    }
  };

  const handleRetry = async (taskId: string) => {
    try {
      await api.post(`/tasks/${taskId}/retry`);
      antMessage.success('重试任务已加入队列');
      fetchTasks();
    } catch (error: any) {
      antMessage.error(error?.response?.data?.detail || '重试失败');
    }
  };

  /** 任务类型对应的中文名 */
  const taskTypeName: Record<string, string> = {
    'document_process': '文档处理',
    'source_sync': '知识源同步',
    'document_parse': '文档解析',
    'embedding': '向量化',
    'entity_extraction': '实体抽取',
    'graph_sync': '图谱同步',
  };

  /** 状态标签渲染 */
  const renderStatus = (status: string) => {
    const config: Record<string, { color: string; icon: React.ReactNode; text: string }> = {
      pending:    { color: 'default', icon: <ClockCircleOutlined />, text: '等待中' },
      processing: { color: 'processing', icon: <SyncOutlined spin />, text: '处理中' },
      completed:  { color: 'success', icon: <CheckCircleOutlined />, text: '已完成' },
      failed:     { color: 'error', icon: <CloseCircleOutlined />, text: '失败' },
    };
    const c = config[status] || config.pending;
    return <Tag icon={c.icon} color={c.color}>{c.text}</Tag>;
  };

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'task_id',
      key: 'task_id',
      render: (id: string) => <Text code style={{ fontSize: 12 }}>{id.substring(0, 12)}...</Text>,
      width: 120,
    },
    {
      title: '类型',
      dataIndex: 'task_type',
      key: 'task_type',
      render: (type: string) => taskTypeName[type] || type,
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: renderStatus,
      width: 100,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      render: (progress: number, record: TaskInfo) => (
        <Progress
          percent={progress}
          size="small"
          status={record.status === 'failed' ? 'exception' : record.status === 'completed' ? 'success' : 'active'}
          style={{ marginBottom: 0, minWidth: 120 }}
        />
      ),
      width: 180,
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
    {
      title: '时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
      width: 160,
    },
    {
      title: '操作',
      key: 'actions',
      width: 90,
      render: (_: unknown, record: TaskInfo) => record.status === 'failed' ? (
        <Button size="small" onClick={() => handleRetry(record.task_id)}>重试</Button>
      ) : null,
    },
  ];

  return (
    <div>
      {/* 页面标题和操作栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          ⚙️ 后台任务
        </Title>
        <Space>
          <Text type="secondary">
            共 {tasks.length} 个任务 · 自动刷新中
          </Text>
          <Button icon={<ReloadOutlined />} onClick={fetchTasks} loading={loading}>
            刷新
          </Button>
          <Button icon={<ClearOutlined />} onClick={handleClearCompleted} loading={clearing}>
            清除已完成
          </Button>
        </Space>
      </div>

      {/* 正在处理的任务提示 */}
      {loadError && (
        <Alert message="无法加载任务状态" description={loadError} type="error" showIcon closable onClose={() => setLoadError(null)} style={{ marginBottom: 16 }} />
      )}
      {tasks.some(t => t.status === 'processing') && (
        <Alert
          message="有任务正在处理中"
          description="部分后台任务正在执行，进度条将自动更新"
          type="info"
          showIcon
          icon={<SyncOutlined spin />}
          style={{ marginBottom: 16 }}
        />
      )}

      {/* 任务列表 */}
      <Card>
        {loading && tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" tip="加载中..." /></div>
        ) : tasks.length === 0 ? (
          <Empty description="暂无后台任务" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            dataSource={tasks}
            columns={columns}
            rowKey="task_id"
            pagination={false}
            size="small"
          />
        )}
      </Card>
    </div>
  );
};

export default TaskStatus;
