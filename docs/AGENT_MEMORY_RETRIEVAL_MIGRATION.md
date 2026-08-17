# Agent Memory / Retrieval v2 迁移指南

升级对应 Alembic revision `0006_memory_retrieval_v2`，需要分别应用到 PostgreSQL 和 MySQL。生产执行前应先备份两套数据库，并在预发布环境验证 HNSW/GIN 建索引时间和磁盘空间。

部署步骤：

1. 发布代码但先保留三项兼容开关可回退。
2. 按项目现有双数据库 Alembic 入口运行升级到 `head`。
3. 对既有 PostgreSQL chunk 做租户回填：

   ```powershell
   python -m app.cli.backfill_retrieval_tenants
   python -m app.cli.backfill_retrieval_tenants --apply
   ```

4. 先 dry-run 检查旧 conversation memory 的迁移数量，再执行：

   ```powershell
   python -m app.cli.migrate_legacy_memory
   python -m app.cli.migrate_legacy_memory --apply
   ```

   默认仅将明确 preference 提升为长期 Semantic Memory；对话主题/摘要进入 Session Memory；来源不明确的 `user_fact` 会跳过。只有人工确认旧记录确实全部来自用户明确陈述时，才可增加 `--include-user-facts`。

5. 运行 `tests/test_memory_retrieval_v2.py`、混合检索/Agent 生命周期回归和前端构建，再逐租户灰度打开新架构。

回退时可关闭 `ENABLE_NEW_MEMORY_ARCHITECTURE` 或 `ENABLE_EVIDENCE_VERIFICATION`，但混合检索没有回退开关。保留新表及审计数据；只有确认没有新版本数据需要保留后才执行 Alembic downgrade，downgrade 会删除 v2 Memory/trace/checkpoint 表和 PostgreSQL 新索引。

运维任务 `app.tasks.memory_tasks.expire_agent_memory` 应由 RQ/调度器周期执行。它是幂等的，过期记录转为 `expired` 并写审计，不做物理删除。
