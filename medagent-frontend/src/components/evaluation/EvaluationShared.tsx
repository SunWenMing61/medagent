import React from 'react';
import { Alert, Card, Empty, Result, Skeleton, Statistic, Tag, Typography, theme } from 'antd';
import type { EvaluationMetricMap, ReleaseGateResult } from '../../types/evaluation';

export const score100 = (value?: number) => value === undefined ? 0 : Math.round(value * 1000) / 10;
export const duration = (ms?: number) => ms === undefined ? '-' : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
export const statusColor = (status: string) => ({ completed: 'success', pass: 'success', running: 'processing', queued: 'default', failed: 'error', fail: 'error', critical: 'error' }[status] ?? 'default');

export function PageState({ loading, error, empty, children, onRetry }: { loading: boolean; error?: string; empty?: boolean; children: React.ReactNode; onRetry?: () => void }) {
  if (loading) return <Skeleton active paragraph={{ rows: 8 }} />;
  if (error) return <Result status="error" title="加载评测数据失败" subTitle={error} extra={onRetry && <a onClick={onRetry}>重试</a>} />;
  if (empty) return <Empty description="暂无评测数据，请先运行一次评测" />;
  return <>{children}</>;
}

export function EvaluationMetricCard({ title, value, delta, suffix, lowerIsBetter = false }: { title: string; value: number; delta?: number; suffix?: string; lowerIsBetter?: boolean }) {
  const { token } = theme.useToken();
  const effectiveLowerIsBetter = lowerIsBetter || /latency|cost|token/i.test(title);
  const worse = effectiveLowerIsBetter ? (delta ?? 0) > 0 : (delta ?? 0) < 0;
  return <Card size="small" className="evaluation-metric-card"><Statistic title={title} value={value} precision={1} suffix={suffix} valueStyle={{ color: worse ? token.colorError : undefined }} />{delta !== undefined && <Typography.Text type={worse ? 'danger' : delta !== 0 ? 'success' : 'secondary'}>{delta > 0 ? '↑' : delta < 0 ? '↓' : '—'} {Math.abs(delta).toFixed(1)} vs Baseline</Typography.Text>}</Card>;
}

export function GateCard({ gate }: { gate: ReleaseGateResult | null | undefined }) {
  if (!gate) return <Card title="Release Gate"><Tag>等待评测</Tag></Card>;
  return <Card title="Release Gate" className={`gate-card gate-${gate.status}`}><Tag color={gate.status === 'pass' ? 'success' : 'error'} className="gate-tag">{gate.status.toUpperCase()}</Tag>{gate.reasons?.length > 0 && <Alert type="error" showIcon message="发布被阻止" description={<ul>{gate.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>} />}</Card>;
}

export function RadarChart({ metrics }: { metrics: EvaluationMetricMap }) {
  const { token } = theme.useToken();
  const names: Array<[string, string]> = [['Task','task_completion'],['Answer','answer_quality'],['RAG','rag'],['Tool','tool'],['Routing','routing'],['Trajectory','trajectory'],['Safety','safety'],['Efficiency','efficiency']];
  const center = 160, radius = 112;
  const point = (index: number, scale = 1) => { const angle = -Math.PI / 2 + index * Math.PI * 2 / names.length; return [center + Math.cos(angle) * radius * scale, center + Math.sin(angle) * radius * scale]; };
  const polygon = (scale: number) => names.map((_, i) => point(i, scale).join(',')).join(' ');
  const data = names.map(([, key], i) => point(i, Math.max(0, Math.min(1, metrics[key] ?? 0))).join(',')).join(' ');
  return <svg className="eval-chart" viewBox="0 0 320 320" role="img" aria-label="AI Capability Radar">{[.25,.5,.75,1].map(x => <polygon key={x} points={polygon(x)} fill="none" stroke={token.colorBorderSecondary} />)}{names.map((_, i) => { const [x,y]=point(i); return <line key={i} x1={center} y1={center} x2={x} y2={y} stroke={token.colorBorderSecondary}/>})}<polygon points={data} fill={`${token.colorPrimary}35`} stroke={token.colorPrimary} strokeWidth="3"/>{names.map(([label], i) => { const [x,y]=point(i,1.18); return <text key={label} x={x} y={y} textAnchor="middle" dominantBaseline="middle" fill={token.colorTextSecondary} fontSize="11">{label}</text>})}</svg>;
}

export function TrendChart({ data, metric }: { data: Array<Record<string, number | string>>; metric: string }) {
  const { token } = theme.useToken();
  if (!data.length) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  const values = data.map(row => Number(row[metric] ?? 0)); const points = values.map((v,i) => `${30 + i * 540 / Math.max(1, values.length-1)},${190-v*160}`).join(' ');
  return <svg className="trend-chart" viewBox="0 0 600 220" role="img" aria-label="Evaluation Trend"><line x1="30" y1="190" x2="570" y2="190" stroke={token.colorBorder}/>{[0,.25,.5,.75,1].map(v => <g key={v}><line x1="30" y1={190-v*160} x2="570" y2={190-v*160} stroke={token.colorBorderSecondary}/><text x="2" y={194-v*160} fill={token.colorTextSecondary} fontSize="10">{v*100}</text></g>)}<polyline points={points} fill="none" stroke={token.colorPrimary} strokeWidth="3"/>{values.map((v,i)=><circle key={i} cx={30+i*540/Math.max(1,values.length-1)} cy={190-v*160} r="4" fill={token.colorPrimary}><title>{data[i].name}: {(v*100).toFixed(1)}</title></circle>)}</svg>;
}
