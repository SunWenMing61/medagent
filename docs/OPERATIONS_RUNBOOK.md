# Operations runbook

## Deploy

Set `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `POSTGRES_PASSWORD`, `SECRET_KEY`, and `EMBEDDING_API_KEY`; never commit the values. From `medagent-backend`, run `docker compose config` and then `docker compose up --build`. The backend container applies both Alembic targets before serving traffic. Only the frontend port is published by the production compose file.

## Health and task recovery

- `/health` is liveness; `/health/ready` verifies both databases.
- A document upload commits a `task_outbox` row with the document. Immediate dispatch is attempted, and the worker replays pending rows on startup.
- Document processing has three total attempts (initial execution plus two retries at 10 and 30 seconds). Intermediate execution failures remain retryable; only the final RQ failure callback makes the task terminal.
- RQ retries document processing three times with 10/30/90-second delays. Task heartbeats older than `TASK_STALE_AFTER_SECONDS` reconcile to failed.
- A failed document task can be retried from the task page. Terminal tasks cannot be overwritten by delayed progress events.

## Scanned PDF triage

Check task `message`, `progress`, `updated_at`, document `parse_status/error_message`, then worker logs by `task_id` and `document_id`. Long OCR jobs are expected to progress page by page. A persistent 95% state now indicates either a recent final commit or a missing heartbeat; stale reconciliation and the RQ failure callback must move it to failed instead of leaving it indefinitely.

## Embedding/retrieval incident

Dimension or model mismatches are hard failures during ingestion. Do not change `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` without re-embedding and recording the new version. Retrieval reports `degraded` if one of dense/lexical paths remains available, and `error` when neither is trustworthy.

## Evaluation

Run `python -m app.evaluation.runner` for the real rule-classifier dataset. For retrieval, capture actual returned document IDs in a JSON mapping of exact question to ID list, then run `python -m app.evaluation.runner --retrieval-run run.json --output report.json`. The tool intentionally refuses to label simulated retrieval as live performance.

Agent runs are persisted in `agent_run` and `agent_checkpoint`. Inspect status,
current node, structured errors, Agent/Tool call counts, and the most recent
checkpoint before retrying. `waiting_for_user` must resume through the
clarification API; `waiting_for_review` must be handled by an administrator and
must never be auto-approved. See [AGENT_STATE_AND_LIFECYCLE.md](AGENT_STATE_AND_LIFECYCLE.md)
and [MULTI_AGENT_EVALUATION.md](MULTI_AGENT_EVALUATION.md).

## Rollback

Stop API and workers, back up both databases, roll application code back, then downgrade each Alembic target only if the relevant revision documents a safe downgrade. Retain outbox rows and uploaded files. Never downgrade a vector schema while serving embeddings from an incompatible model/dimension.
