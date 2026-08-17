# Agent 生命周期 API

所有普通接口需要 Bearer 登录；审核接口还要求管理员角色。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/agent-runs` | 创建并执行受控工作流 |
| GET | `/api/agent-runs/{request_id}` | 获取当前状态和公开结果 |
| POST | `/api/agent-runs/{request_id}/clarification` | 提交补充信息并恢复 |
| POST | `/api/agent-runs/{request_id}/review` | 管理员批准、编辑或拒绝 |
| DELETE | `/api/agent-runs/{request_id}` | 取消非终态任务 |
| GET | `/api/agent-runs/{request_id}/trace` | 获取无原始医疗文本的步骤/工具 Trace |
| GET | `/api/agent-runs/{request_id}/events` | 获取 SSE 公开事件 |

创建示例：

```json
{
  "query": "高血压的一般管理原则是什么？",
  "kb_ids": [1],
  "thread_id": "consultation-42",
  "conversation_summary": ""
}
```

可能的状态包括 `running`、`waiting_for_user`、`waiting_for_review`、`completed`、`failed`、`cancelled` 和 `rejected`。前端只应展示公开事件，不展示 Trace 内部信息或思维链。
