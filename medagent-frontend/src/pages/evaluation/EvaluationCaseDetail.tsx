import { Alert, Card, Descriptions, Empty, Space, Tag, Typography } from 'antd';
import { useEffect,useState } from 'react';
import { Link,useParams } from 'react-router-dom';
import { AgentTraceTimeline,RagRetrievalPanel,ToolCallPanel } from '../../components/evaluation/TracePanels';
import { PageState,score100,statusColor } from '../../components/evaluation/EvaluationShared';
import { evaluationApi } from '../../services/evaluationApi';
import type { EvaluationCaseResult,EvaluationTrace } from '../../types/evaluation';
import '../../styles/evaluation.css';

const pretty=(v:unknown)=><Typography.Paragraph className="long-text" copyable code>{typeof v==='string'?v:JSON.stringify(v,null,2)}</Typography.Paragraph>;
const yn=(value:unknown)=><Tag color={value?'orange':'default'}>{value?'YES':'NO'}</Tag>;

export default function EvaluationCaseDetail(){
  const {resultId=''}=useParams();const [item,setItem]=useState<EvaluationCaseResult>();const [trace,setTrace]=useState<EvaluationTrace>();const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  const load=async()=>{setLoading(true);try{const row=await evaluationApi.getCaseDetail(Number(resultId));setItem(row);if(row.trace_id)setTrace(await evaluationApi.getTrace(row.run_id,row.trace_id))}catch(e){setError(e instanceof Error?e.message:'加载失败')}finally{setLoading(false)}};
  useEffect(()=>{load()},[resultId]);
  const meta=trace?.metadata??{};
  return <div className="evaluation-page"><div className="evaluation-heading"><div><Typography.Title level={2}>{item?.name??'Case Detail'}</Typography.Title>{item&&<Space><Tag color={statusColor(item.status)}>{item.status.toUpperCase()}</Tag><Tag>{item.category}</Tag><Tag>{item.difficulty}</Tag></Space>}</div>{item&&<Link to={`/evaluation/runs/${item.run_id}`}>Back to Run</Link>}</div><PageState loading={loading} error={error} onRetry={load}>{item&&<>
    <div className="case-grid"><Card title="User Input">{pretty(item.input)}</Card><Card title="Expected Result"><Descriptions column={1} size="small" items={[{key:'mode',label:'Expected execution mode',children:pretty(item.expected.execution_mode??'-')},{key:'complexity',label:'Expected complexity',children:item.expected.complexity??'-'},{key:'facts',label:'Expected facts',children:pretty(item.expected.facts??[])},{key:'docs',label:'Expected docs',children:pretty(item.expected.documents??[])},{key:'agents',label:'Expected agents',children:pretty(item.expected.agents??[])},{key:'tools',label:'Expected tools',children:pretty(item.expected.tools??[])},{key:'required',label:'Required content',children:pretty(item.expected.required_content??[])}]}/></Card></div>
    <Card title="Routing Debug" style={{marginBottom:16}}><Descriptions bordered size="small" column={{xs:1,sm:2,lg:3}} items={[{key:'expected',label:'Expected Mode',children:pretty(item.expected.execution_mode??'-')},{key:'actual',label:'Actual Mode',children:<Tag color="blue">{String(meta.execution_mode??'-')}</Tag>},{key:'level',label:'Complexity Level',children:String(meta.complexity_level??'-')},{key:'score',label:'Complexity Score',children:Number(meta.complexity_score??meta.router_score??0).toFixed(4)},{key:'confidence',label:'Router Confidence',children:Number(meta.router_confidence??0).toFixed(4)},{key:'signals',label:'Router Signals',children:pretty(meta.router_signals??{})},{key:'escalated',label:'Escalated?',children:yn(meta.escalated)},{key:'reason',label:'Escalation Reason',children:String(meta.escalation_reason??'-')},{key:'tokens',label:'Token Usage',children:trace?.total_tokens??0},{key:'llm',label:'LLM Calls',children:trace?.llm_calls.length??0},{key:'tools',label:'Tool Calls',children:trace?.tool_calls.length??0}]}/></Card>
    <Card title="Actual Answer" style={{marginBottom:16}}>{pretty(item.actual_output??'')}</Card><Card title="Scores" style={{marginBottom:16}}><div className="score-strip">{Object.entries(item.scores).map(([key,value])=><div className="score-pill" key={key}><span>{key}</span><strong>{score100(value)}</strong></div>)}</div></Card>
    {!item.passed&&<Alert type={item.critical?'error':'warning'} showIcon message="Failure Reason" description={<Descriptions column={1} size="small" items={[{key:'failure',label:'Failure Reason',children:item.failure_reason??'-'},{key:'judge',label:'Judge Reason',children:item.judge_reason??'Deterministic evaluation - no LLM judge used'},{key:'detail',label:'Evaluation Details',children:pretty(item.details)}]}/>} style={{marginBottom:16}}/>}
    <Card title="Trace Timeline" style={{marginBottom:16}}>{trace?<AgentTraceTimeline trace={trace}/>:<Empty description="Trace not available"/>}</Card>{trace&&<div className="case-grid"><ToolCallPanel trace={trace} expected={item.expected}/><RagRetrievalPanel trace={trace} expected={item.expected} metrics={item.details.rag}/></div>}
  </>}</PageState></div>;
}
