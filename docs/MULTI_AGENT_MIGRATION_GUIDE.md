# 多 Agent 迁移状态

迁移已经完成。系统只保留受控 Supervisor 工作流，不再提供 `ENABLE_MULTI_AGENT` 开关，也不能回退到旧 `MedAgentWorkflow`。

发布前必须完成 MySQL/PostgreSQL Alembic 升级，并验证文档入库、混合检索、引用校验、clarification/HITL 和 Agent lifecycle API。回滚应回滚整个应用版本；不要通过环境变量恢复已删除的旧工作流。

关键配置见 `.env.example`：调用/工具上限、总超时、Token 预算、重试次数、HITL、checkpoint TTL、会话记忆 TTL、在线医学检索和 Trace。
