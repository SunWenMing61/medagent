# Target RAG architecture

## Ingestion pipeline

`upload -> durable RQ task -> parser router -> typed ParsedDocument -> cleaner -> structural parent/child chunker -> batch embedding -> transactional persistence -> validation -> complete`

Every page carries origin, page number, extraction method, OCR confidence, warnings, and optional blocks/tables. The native PDF parser uses PyMuPDF; sparse/mixed pages fall back to EasyOCR page by page. Chunk IDs and embedding cache keys include document content, parser/chunker versions, model, and dimensions so reprocessing is deterministic and upgrades cannot reuse incompatible vectors.

## Query pipeline

`authenticated KB scope -> query normalization -> dense + lexical candidates -> RRF -> optional rerank -> deduplicate -> parent/neighbor expansion -> evidence budget -> answer -> citation validator`

The retriever requires an explicit, already-authorized KB scope. It returns a structured status: `ok`, `no_evidence`, `degraded`, or `error`. A response may only cite evidence IDs present in the server-built context; missing evidence produces an explicit insufficient-evidence answer rather than invented support.

## Control plane

- MySQL: users, ACLs, document/task lifecycle, conversation ownership, audit events.
- PostgreSQL: versioned chunks, dense vectors, lexical search fields, retrieval provenance.
- Redis/RQ: idempotent jobs, progress heartbeats, retries, failure callbacks, outbox dispatch.
- Metrics/logging: correlation ID, task ID, document ID, KB ID, durations and external-call status, with secrets and document bodies excluded.

Both databases are migrated through Alembic using `-x database=postgres` or `-x database=mysql`. API startup validates schema/configuration; it does not silently mutate production schemas.

## Degraded behavior

- OCR unavailable: native pages continue; OCR pages fail with an actionable parser status.
- Embedding unavailable during ingestion: task retries and never publishes incomplete vector state as successful.
- Dense search unavailable: lexical results may serve a labeled degraded response.
- Reranker unavailable: deterministic fused ordering is retained.
- No trustworthy evidence: the answer states that evidence is insufficient and provides no fabricated citation.

