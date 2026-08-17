# RAG refactor plan

Each phase must leave the repository runnable and add regression coverage before the next phase begins.

| Phase | Scope | Acceptance gate |
|---|---|---|
| 0 | Audit, reproducible baselines, architecture and migration entry point | Backend tests collect under Windows locale; frontend config is valid; Alembic reads both targets. |
| 1 | Typed parsing, mixed-PDF OCR, cleaning, structural parent/child chunks, metadata migrations | Native, scanned, and mixed PDFs preserve page provenance; deterministic chunk tests pass. |
| 2 | Reusable embedding client, batching, retry/backoff, dimensions/versioning, idempotency | Partial failures are explicit; incompatible vectors cannot be mixed; reprocessing is safe. |
| 3 | Mandatory ACL scope, dense + lexical retrieval, RRF, rerank, dedupe, context expansion and evidence budget | Retrieval failures differ from no evidence; retrieval evaluation emits Recall@K, MRR and nDCG. |
| 4 | Server-issued citations, citation validation, endpoint-wide ACL and conversation-memory isolation | Cross-user/KB tests fail closed; every citation resolves to authorized evidence. |
| 5 | Medical risk triage, emergency templates, prompt-injection defenses, safe-output policy | Emergency and injection suites pass; system prompt/private reasoning is never exposed. |
| 6 | Unified RQ task lifecycle, retry policy, outbox/idempotency, secure Docker startup | No thread-only background path; interrupted tasks reconcile; services fail fast on unsafe config. |
| 7 | Structured telemetry, evaluation runner, progress/retry UI, runbooks and final docs | CI-equivalent checks pass and results are recorded without fabricated metrics. |

## Completion status

All eight phases are implemented in the current worktree. The final local gate is 146 passing backend tests, a successful frontend production build, a valid linear Alembic history, and a successful Compose YAML parse. Three integration tests remain skipped because no live login stack is available; Docker runtime and live retrieval-dataset measurements are explicitly documented as environment-dependent follow-ups rather than reported as successful.

## Compatibility policy

Public API fields are extended rather than silently repurposed. Legacy extraction and reference shapes remain behind adapters during migration. Database changes are additive first, backfilled in an explicit job, validated, and only then made mandatory. Rollback downgrades schema but never pretends newer vectors are compatible with an older model.
