# Migration guide

## Prerequisites

Back up MySQL and PostgreSQL independently, stop ingestion workers, record the current embedding model/dimensions, and verify Redis has no active document jobs. Never run both database targets against the same URL.

## Commands

```powershell
cd medagent-backend
python -m alembic -x database=postgres upgrade head
python -m alembic -x database=mysql upgrade head
```

Use `downgrade -1` only after reading the revision's data-loss notes. Schema downgrade does not convert or restore embeddings produced by a different model.

## Rollout sequence

1. Deploy additive schema fields and indexes.
2. Deploy code that can read legacy and new rows but writes the new versioned shape.
3. Run the idempotent backfill/re-embedding job by KB, recording counts and failures.
4. Validate chunk counts, page provenance, dimensions, model/version metadata and sampled retrieval.
5. Validate mandatory hybrid retrieval, citation validation and the controlled UI.
6. Confirm legacy workflow modules are absent after all rows validate.

For the controlled Supervisor rollout and revision `0004`, also follow
[MULTI_AGENT_MIGRATION_GUIDE.md](MULTI_AGENT_MIGRATION_GUIDE.md). The runtime no
longer has a feature flag or legacy workflow fallback.

Revision `0005_pdf_tooling_v2` adds PDF trace/quality tables and governed-tool
audit tables to MySQL, and adds source block, content type, cleaning, OCR and
quality provenance to PostgreSQL chunks. After applying it, reprocess a small
knowledge base first and verify that cleaned documents proceed directly to vectorization
instead of waiting for manual review. Existing documents remain readable, but they do
not gain Raw/Clean trace rows until rebuilt. CPU and GPU OCR dependency sets are
separate; install exactly one appropriate set before enabling OCR workers.

## Dual-database notes

PostgreSQL revisions own `document_chunk`, vectors and lexical indexes. MySQL revisions own users, KB/document lifecycle and task metadata. Alembic receives the selected target as `database` so a revision can branch on dialect/target without importing a second ad-hoc migration system.

## Recovery

If a rollout fails, stop workers, retain the additive columns, revert application traffic to the previous reader, and resume from the recorded idempotency/version keys. Do not mark partially embedded documents successful; do not delete legacy chunks until new retrieval evaluation passes.
