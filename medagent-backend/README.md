# MedAgent backend

The backend is a FastAPI service with MySQL application data, PostgreSQL +
pgvector retrieval data, Redis/RQ jobs, and Alembic-managed schemas.

It also contains a feature-flagged, controlled LangGraph Supervisor workflow.
Specialist agents have strict Pydantic outputs, retrieval is tenant/ACL scoped,
answers can use only verified evidence, and clarification/human review states are
database-checkpointed. See [architecture](../docs/MULTI_AGENT_ARCHITECTURE.md),
[API](../docs/AGENT_API.md), and [evaluation](../docs/MULTI_AGENT_EVALUATION.md).

## Local setup

1. Copy `.env.example` to `.env` and provide unique local credentials.
2. Install dependencies with `pip install -r requirements.txt`.
3. Upgrade both schemas:

   ```powershell
   python -m alembic -x database=postgres upgrade head
   python -m alembic -x database=mysql upgrade head
   ```

4. Create the first administrator explicitly (there is no default account or
   password):

   ```powershell
   python -m app.cli.create_admin --username admin --email admin@example.com
   ```

5. Start the API and worker in separate terminals:

   ```powershell
   uvicorn app.main:app --reload --port 8000
   python worker.py
   ```

Uploading a PDF, DOCX, TXT, or Markdown file automatically creates a durable
outbox event. The worker extracts native text (or runs OCR for scanned PDF
pages), cleans and structurally chunks it, creates embeddings, and persists the
searchable child chunks in PostgreSQL/pgvector. Keep at least one worker running;
`GET /health/document-processing` reports queue depth and active workers.

When Redis is temporarily unavailable, the upload remains `pending` and the
worker retries undispatched outbox events automatically. In Docker Compose, the
worker is started as a separate service and EasyOCR models are retained in the
`ocr_model_data` volume.

For production deployment, migration, rollback, task recovery, and evaluation
instructions, see the repository [README](../README.md),
[migration guide](../docs/MIGRATION_GUIDE.md), and
[operations runbook](../docs/OPERATIONS_RUNBOOK.md).

Do not use ORM `create_all`, place secrets in source control, or expose database
and Redis ports publicly. Production startup validates schema heads and refuses
unsafe default secrets/CORS settings.
