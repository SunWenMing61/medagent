import { Card, Collapse, Descriptions, Empty, Progress, Table, Tag, Timeline, Typography } from 'antd';
import type { EvaluationExpected, EvaluationTrace } from '../../types/evaluation';

const json = (value: unknown) => <Typography.Paragraph code copyable ellipsis={{ rows: 4, expandable: true }}>{JSON.stringify(value, null, 2)}</Typography.Paragraph>;

export function AgentTraceTimeline({ trace }: { trace: EvaluationTrace }) {
  if (!trace.agent_steps.length) return <Empty description="没有 Agent Step" />;
  return <Timeline items={trace.agent_steps.map(step => ({ color: step.status === 'success' ? 'green' : 'red', children: <Collapse size="small" items={[{ key: String(step.step_number), label: <><b>{step.step_number}. {step.agent_name}</b> · {step.action} · {step.latency_ms.toFixed(1)} ms</>, children: <Descriptions column={1} size="small" items={[{key:'status',label:'Status',children:<Tag>{step.status}</Tag>},{key:'input',label:'Input',children:json(step.input)},{key:'output',label:'Output',children:json(step.output)}]} /> }]} /> }))} />;
}

export function ToolCallPanel({ trace, expected }: { trace: EvaluationTrace; expected: EvaluationExpected }) {
  return <Card title="Tool Calls"><Table size="small" pagination={false} rowKey={(_,i)=>String(i)} dataSource={trace.tool_calls} columns={[{title:'Tool',dataIndex:'tool_name'},{title:'Expected?',render:(_,x)=><Tag color={expected.tools?.includes(x.tool_name)?'success':'error'}>{expected.tools?.includes(x.tool_name)?'✓ Expected':'Unexpected Tool'}</Tag>},{title:'Success',dataIndex:'success',render:v=><Tag color={v?'success':'error'}>{String(v)}</Tag>},{title:'Latency',dataIndex:'latency_ms',render:v=>`${v} ms`},{title:'Arguments',dataIndex:'arguments',render:json}]} /></Card>;
}

export function RagRetrievalPanel({ trace, expected, metrics }: { trace: EvaluationTrace; expected: EvaluationExpected; metrics?: Record<string, unknown> }) {
  const missing = (expected.documents ?? []).filter(id => !trace.retrievals.some(item => item.document_id === id));
  return <Card title="RAG Retrieval"><div className="rag-metrics">{['precision_at_k','recall_at_k','hit_rate_at_k','mrr','ndcg_at_k'].map(key=><div key={key}><span>{key}</span><Progress percent={Number(metrics?.[key] ?? 0)*100} size="small" /></div>)}</div>{missing.length>0&&<Typography.Text type="danger">Missing Expected Documents: {missing.join(', ')}</Typography.Text>}<Table size="small" pagination={{pageSize:5}} rowKey={(x,i)=>`${x.chunk_id}-${i}`} dataSource={trace.retrievals} expandable={{expandedRowRender:x=>json(x.content)}} columns={[{title:'Rank',dataIndex:'rank'},{title:'Document',dataIndex:'document_id'},{title:'Chunk',dataIndex:'chunk_id'},{title:'Similarity',dataIndex:'similarity_score',render:v=>Number(v).toFixed(3)},{title:'Expected?',render:(_,x)=><Tag color={expected.documents?.includes(x.document_id)?'success':'default'}>{expected.documents?.includes(x.document_id)?'✓ Expected':'Other'}</Tag>}]} /></Card>;
}
