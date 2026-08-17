import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Descriptions, Input, Row, Statistic, Table, Tag, Typography, message } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import {
  getHybridRetrievalComparison, getRetrievalMetrics, getRetrievalTrace,
  getStandardAnswerCacheMetrics,
  type HybridRetrievalComparison, type StandardAnswerCacheMetrics,
} from '../services/api';

const { Title, Text, Paragraph } = Typography;

const categoryLabels: Record<string, string> = {
  emergency: '急诊急救', cardiovascular: '心血管', respiratory: '呼吸', pediatrics: '儿科',
  obstetrics: '产科', geriatrics: '老年医学', medication_safety: '用药安全', laboratory: '检验',
  imaging: '影像', oncology: '肿瘤', infectious_disease: '感染', mental_health: '精神心理',
  traditional_medicine: '中医药', rehabilitation: '康复', preventive_care: '预防保健',
  rare_disease: '罕见病', critical_care: '重症医学', nursing: '护理', clinical_research: '临床研究',
};

const metricLabels: Record<string, string> = {
  accuracy_at_1: '检索准确率@1', hit_rate_at_1: 'Hit Rate@1', hit_rate_at_3: 'Hit Rate@3',
  hit_rate_at_5: 'Hit Rate@5', precision_at_3: 'Precision@3', precision_at_5: 'Precision@5',
  recall_at_3: 'Recall@3', recall_at_5: 'Recall@5', f1_at_5: 'F1@5', mrr: 'MRR',
  ndcg_at_5: 'nDCG@5', map_at_5: 'MAP@5',
};

const RetrievalDebug: React.FC = () => {
  const [requestId, setRequestId] = useState('');
  const [trace, setTrace] = useState<Record<string, any>>();
  const [metrics, setMetrics] = useState<any>();
  const [comparison, setComparison] = useState<HybridRetrievalComparison>();
  const [evaluating, setEvaluating] = useState(false);
  const [cacheMetrics, setCacheMetrics] = useState<StandardAnswerCacheMetrics>();
  const loadComparison = async () => {
    setEvaluating(true);
    try { setComparison(await getHybridRetrievalComparison()); }
    catch { message.error('混合检索评测加载失败'); }
    finally { setEvaluating(false); }
  };
  useEffect(() => {
    getRetrievalMetrics().then(setMetrics).catch(() => undefined);
    getStandardAnswerCacheMetrics().then(setCacheMetrics).catch(() => undefined);
    loadComparison();
  }, []);
  const search = async () => {
    if (!requestId.trim()) return;
    try { setTrace(await getRetrievalTrace(requestId.trim())); }
    catch (error: any) { message.error(error.response?.data?.detail || '未找到检索追踪'); }
  };
  return <div>
    <Title level={4}>检索调试与可观测性</Title>
    <Text type="secondary">查询文本会脱敏，原始查询仅保存 SHA-256；结果内容仅保留短预览与哈希。</Text>
    <Row gutter={16} style={{ marginTop: 16, marginBottom: 16 }}>
      <Col span={6}><Card><Statistic title="样本数" value={metrics?.sample_size || 0}/></Card></Col>
      <Col span={6}><Card><Statistic title="P95 延迟" value={metrics?.p95_latency_ms || 0} suffix="ms" precision={1}/></Card></Col>
      <Col span={6}><Card><Statistic title="平均证据数" value={metrics?.average_evidence_count || 0} precision={2}/></Card></Col>
      <Col span={6}><Card>{Object.entries(metrics?.status_counts || {}).map(([key, value]) => <Tag key={key}>{key}: {String(value)}</Tag>)}</Card></Col>
    </Row>
    <Card title="Redis 高频标准答案缓存" style={{ marginBottom: 16 }} extra={<Tag color={cacheMetrics?.backend === 'redis' ? 'green' : 'orange'}>{cacheMetrics?.backend || '等待数据'}</Tag>}>
      <Text type="secondary">仅缓存普通助手的新会话标准问题；记忆问答、个体医疗数据和安全未通过的回答会自动绕过。</Text>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}><Statistic title="缓存命中率" value={(cacheMetrics?.hit_rate || 0) * 100} suffix="%" precision={2}/></Col>
        <Col span={6}><Statistic title="核心链路实测提速" value={(cacheMetrics?.response_speed_improvement || 0) * 100} suffix="%" precision={2}/></Col>
        <Col span={6}><Statistic title="估算模型调用减少" value={(cacheMetrics?.estimated_model_call_reduction || 0) * 100} suffix="%" precision={2}/></Col>
        <Col span={6}><Statistic title="避免模型调用" value={cacheMetrics?.model_calls_avoided || 0} suffix="次"/></Col>
      </Row>
      <Row gutter={16} style={{ marginTop: 12 }}>
        <Col span={6}><Statistic title="冷请求平均耗时" value={cacheMetrics?.average_cold_latency_ms || 0} suffix="ms" precision={1}/></Col>
        <Col span={6}><Statistic title="命中平均耗时" value={cacheMetrics?.average_hit_latency_ms || 0} suffix="ms" precision={1}/></Col>
        <Col span={6}><Statistic title="累计节省耗时" value={(cacheMetrics?.estimated_latency_saved_ms || 0) / 1000} suffix="秒" precision={1}/></Col>
        <Col span={6}><Statistic title="并发等待复用" value={cacheMetrics?.stampede_wait_hits || 0} suffix="次"/></Col>
      </Row>
    </Card>
    <Card
      title="医学 RAG 固定评测集：Dense 基线 vs 当前混合检索"
      extra={<Button loading={evaluating} onClick={loadComparison}>重新测试</Button>}
      style={{ marginBottom: 16 }}
    >
      <Text type="secondary">
        固定合成医学检索难例，不包含患者数据；用于工程回归，不代表临床有效性。准确率@1表示首条即相关，Hit Rate@K表示前K条至少命中一条相关证据，MRR衡量第一条相关证据的平均排名。
      </Text>
      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col span={6}><Statistic title="固定病例数" value={comparison?.dataset.case_count || 0} suffix="条"/></Col>
        <Col span={6}><Statistic title="医学场景" value={comparison?.dataset.category_count || 0} suffix="类"/></Col>
        <Col span={6}><Statistic title="当前 Hit Rate@5" value={(comparison?.candidate.metrics.hit_rate_at_5 || 0) * 100} suffix="%" precision={2}/></Col>
        <Col span={6}><Statistic title="当前 MRR" value={(comparison?.candidate.metrics.mrr || 0) * 100} suffix="%" precision={2}/></Col>
      </Row>
      <Table
        size="small" pagination={false} rowKey="metric" style={{ marginTop: 16 }}
        dataSource={[
          'accuracy_at_1', 'hit_rate_at_1', 'hit_rate_at_3', 'hit_rate_at_5',
          'precision_at_3', 'recall_at_3', 'precision_at_5', 'recall_at_5',
          'f1_at_5', 'mrr', 'ndcg_at_5', 'map_at_5',
        ].map(metric => ({
          metric,
          label: metricLabels[metric] || metric,
          baseline: comparison?.baseline.metrics[metric] || 0,
          hybrid: comparison?.candidate.metrics[metric] || 0,
          delta: comparison?.improvement.absolute[metric] || 0,
        }))}
        columns={[
          { title: '指标', dataIndex: 'label' },
          { title: 'Dense 基线', dataIndex: 'baseline', render: value => `${(value * 100).toFixed(2)}%` },
          { title: '混合检索', dataIndex: 'hybrid', render: value => `${(value * 100).toFixed(2)}%` },
          { title: '提升', dataIndex: 'delta', render: value => <Tag color={value >= 0 ? 'green' : 'red'}>{value >= 0 ? '+' : ''}{(value * 100).toFixed(2)} 个百分点</Tag> },
        ]}
      />
      <Paragraph style={{ marginTop: 20 }}><Text strong>分医学场景表现</Text></Paragraph>
      <Table
        size="small"
        pagination={{ pageSize: 9, showSizeChanger: false }}
        rowKey="category"
        dataSource={(comparison?.dataset.categories || []).map(category => ({
          category,
          label: categoryLabels[category] || category,
          count: comparison?.per_case.filter(item => item.category === category).length || 0,
          hit5: comparison?.candidate.by_category[category]?.hit_rate_at_5 || 0,
          mrr: comparison?.candidate.by_category[category]?.mrr || 0,
          recall5: comparison?.candidate.by_category[category]?.recall_at_5 || 0,
          ndcg5: comparison?.candidate.by_category[category]?.ndcg_at_5 || 0,
        }))}
        columns={[
          { title: '医学场景', dataIndex: 'label' },
          { title: '病例数', dataIndex: 'count' },
          { title: 'Hit Rate@5', dataIndex: 'hit5', render: value => `${(value * 100).toFixed(2)}%` },
          { title: 'MRR', dataIndex: 'mrr', render: value => `${(value * 100).toFixed(2)}%` },
          { title: 'Recall@5', dataIndex: 'recall5', render: value => `${(value * 100).toFixed(2)}%` },
          { title: 'nDCG@5', dataIndex: 'ndcg5', render: value => `${(value * 100).toFixed(2)}%` },
        ]}
      />
    </Card>
    <Card>
      <Input.Search value={requestId} onChange={event => setRequestId(event.target.value)} onSearch={search} enterButton={<><SearchOutlined/> 查询</>} placeholder="输入 request_id" />
      {trace && <>
        <Descriptions bordered column={2} style={{ marginTop: 16 }} items={[
          { key: 'id', label: 'Request ID', children: trace.request_id },
          { key: 'status', label: '状态', children: <Tag>{trace.status}</Tag> },
          { key: 'query', label: '独立查询', children: trace.standalone_query, span: 2 },
          { key: 'routes', label: '路由', children: JSON.stringify(trace.routes) },
          { key: 'timings', label: '耗时', children: JSON.stringify(trace.timings_ms) },
        ]}/>
        <Paragraph style={{ marginTop: 16 }}><Text strong>候选、过滤与最终证据</Text></Paragraph>
        <pre style={{ maxHeight: 520, overflow: 'auto', padding: 12, background: 'rgba(127,127,127,.08)' }}>{JSON.stringify({ rankings: trace.rankings, filtered: trace.filtered, final_evidence: trace.final_evidence, error: trace.error }, null, 2)}</pre>
      </>}
    </Card>
  </div>;
};

export default RetrievalDebug;
