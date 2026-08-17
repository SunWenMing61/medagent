# RAG architecture before the refactor

## Ingestion

`upload -> MySQL Document -> RQ job -> file_utils.extract_text -> character splitter -> one embedding HTTP request per chunk -> PostgreSQL document_chunk`

The parser returned `(text, page_number)` tuples. Native and scanned pages had no common typed representation, OCR confidence and coordinates were discarded, table/layout structure was lost, and chunk boundaries were character based. Embeddings were fixed at 1,024 dimensions and partial failures were not represented explicitly.

## Retrieval and answering

`question -> LLM/rule classification -> per-KB dense vector search -> optional rerank -> prompt aggregation -> answer + shallow references`

Dense search accepted missing `kb_ids`, which could mean an unscoped search. Retrieval errors were converted to empty results, making outages indistinguishable from genuinely absent evidence. There was no lexical retrieval, RRF, parent/child context expansion, adaptive threshold, evidence budget, or server-validated citation contract.

## Trust boundaries

- MySQL stores users, ACL-bearing knowledge bases, documents, sessions, and messages.
- PostgreSQL/pgvector stores chunks and embeddings.
- Redis/RQ stores asynchronous task state.
- External embedding, LLM, OCR, and optional web-search services are untrusted dependencies.

ACL checks were inconsistent across chat endpoints. The generic endpoint derived accessible KBs, while specialized endpoints could accept caller-supplied IDs without the same authorization gate. Retrieved text was inserted into prompts without a strong untrusted-data boundary.

## Primary failure modes

- Scanned PDFs could outlive RQ's default 180-second timeout and appear frozen at 95%.
- Empty retrieval represented both “no evidence” and infrastructure failure.
- Fixed dimensions and weak cache keys made embedding upgrades unsafe.
- Startup `create_all()` and manual schema changes bypassed migration history.
- Private model reasoning could be streamed/persisted as “deep thinking”.
- Docker defaults exposed databases and used placeholder secrets.

