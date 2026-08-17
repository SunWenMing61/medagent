# Agent 状态与生命周期

## 状态

`AgentGraphState` 包含请求身份、用户/租户、授权知识库、分诊、检索计划、原始与核验证据、结构化答案、引用、安全/HITL、调用计数、错误和公开事件。`state_version` 当前为 `ma-v1`。

## 生命周期

```text
running
  ├─ waiting_for_user ── clarification ── running
  ├─ waiting_for_review ── approve/edit ── running/completed
  │                    └─ reject ── rejected
  ├─ completed
  ├─ failed
  └─ cancelled
```

每个节点和 Supervisor 决策后都保存 checkpoint。读取、取消和澄清恢复必须同时匹配 `request_id + user_id + tenant_id`。审核接口仅管理员可调用；人工编辑答案仍必须通过确定性安全检查，并且只能引用已核验证据 ID。

## 故障语义

- 检索系统错误与“没有结果”分开记录，前者返回安全失败。
- 输出安全 Agent 异常时 fail closed。
- 超过 Agent/Tool/总时限时停止图并写入结构化错误。
- checkpoint 默认数据库持久化并按 `CHECKPOINT_TTL` 设置过期时间。
