# 受控多 Agent 架构

系统采用一个且仅一个 Supervisor。专业 Agent 只返回严格 Pydantic 结构，不能选择下一个 Agent；工具只能通过显式白名单调用。

```mermaid
flowchart TD
    U["用户请求"] --> IS["规则优先的输入安全检查"]
    IS -->|急症/自伤| F["固定应急响应"]
    IS --> T["Input Triage Agent"]
    T -->|信息不足| C["Clarification Agent / 中断"]
    T -->|超范围| F
    T --> Q["Retrieval Planner Agent"]
    Q --> R["并行检索子图"]
    R --> L["本地授权知识库"]
    R --> O["PubMed / FDA / MSD"]
    R --> M["隔离的会话记忆"]
    L --> N["标准化 / 去重 / 融合 / 重排"]
    O --> N
    M -. "仅上下文，不作证据" .-> N
    N --> V["Evidence Verifier Agent"]
    V -->|不足且未重试| R
    V -->|冲突/高风险| H["Human Review / 中断"]
    V -->|充分| A["Answer Generator Agent"]
    A --> S["Output Safety Agent"]
    S -->|安全改写最多一次| A
    S -->|通过| F
    S -->|需审核| H
    H --> F
    F --> X["引用绑定答案 + 公开事件"]
```

Supervisor 是唯一的路由决策点。急症路径在规则层直接短路，Agent 和 Tool 调用数均为 0。证据不足只允许一次检索重试；答案只能看到 `verified_evidence`，引用 ID 由后端绑定。

## 隔离边界

- 本地检索输入必须包含 `user_id`、`tenant_id` 和非空授权 KB 范围；工具在数据库层再次验证。
- 在线证据使用服务端 HMAC ID，并保留来源、URL、检索时间和权威等级。
- 会话记忆按用户、租户、线程和 TTL 隔离，永远设置为非医学证据。
- Prompt、Agent 版本、模型/规则执行方式、延迟、Token、成本和错误码写入 Trace。
