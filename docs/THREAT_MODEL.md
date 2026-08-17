# RAG threat model

## Assets

Private medical documents, user identity, knowledge-base ACLs, chat history, model/provider credentials, system prompts, retrieval evidence, and audit records.

## Adversaries and entry points

- An authenticated user attempts to enumerate another user's KB, chunks, citations, sessions, or task IDs.
- A document or web page contains prompt injection telling the model to reveal prompts, secrets, or unrelated records.
- An unauthenticated client abuses upload, websocket/SSE, task-status, or administrative endpoints.
- A compromised external provider returns malformed vectors or captures sensitive content.
- Oversized/corrupt PDFs exhaust CPU, memory, disk, worker time, or OCR GPU resources.

## Required controls

1. Resolve authorized KB IDs server-side for every endpoint; an empty/missing scope must fail closed, never mean “all”.
2. Bind sessions, messages, tasks, documents, chunks, citations, and downloads to the authenticated principal and KB ACL.
3. Treat retrieved content as quoted untrusted data. It cannot override system/developer policy or request secrets/tool use.
4. Issue opaque evidence IDs on the server and validate all generated citations against the authorized evidence set.
5. Enforce MIME, size, page-count and decompression limits; isolate long OCR in bounded workers with heartbeats.
6. Redact credentials, authorization headers, raw document bodies and private reasoning from logs and client streams.
7. Use explicit medical-risk categories. Emergency responses are conservative and locale-neutral unless location is known.
8. Fail fast on default production secrets, wildcard credentialed CORS, unavailable schema migrations, or incompatible embedding dimensions.

## Residual risks

OCR may misread medical dosage or negation; rerankers and LLMs may still be biased; provider-side data handling depends on deployment contracts; lexical/dense indexes may lag during recovery. These risks require visible degraded states, auditability, human review for high-risk advice, and operational runbooks rather than silent fallback.

