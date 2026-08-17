"""使用 RQ 处理文档解析、扫描 PDF OCR 和向量化。"""

import logging
import os
import sys
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from redis import Redis
from rq import Queue, Retry, Worker
from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.services.embedding_service import EmbeddingTransientError, embedding_service
from app.services.task_manager import task_manager
from app.services.document_processing_service import document_processing_service
from app.services.medical_metadata_service import extract_medical_metadata
from app.chunking.structural_splitter import StructuralSplitter
from app.parsers.layout_parser import parse_document

logger = logging.getLogger(__name__)

redis_conn = Redis.from_url(settings.REDIS_URL)
doc_queue = Queue("default", connection=redis_conn)
_local_executor = ThreadPoolExecutor(
    max_workers=max(int(settings.DOCUMENT_INLINE_MAX_WORKERS), 1),
    thread_name_prefix="document-vectorizer",
)
_local_jobs: dict[str, Future] = {}
_local_jobs_lock = threading.Lock()


def _normalise_rq_state(value) -> str:
    return str(getattr(value, "value", value) or "").lower()


def _rq_workers_available() -> bool:
    """仅把仍处于可消费状态的 RQ Worker 视为可用。"""
    try:
        return any(
            _normalise_rq_state(worker.state) in {"idle", "busy", "started"}
            for worker in Worker.all(connection=redis_conn)
        )
    except Exception as exc:
        logger.warning("Unable to inspect RQ workers; using local fallback: %s", exc)
        return False


def _rq_job_is_active(task_id: str) -> bool:
    try:
        job = doc_queue.fetch_job(task_id)
        if not job:
            return False
        return _normalise_rq_state(job.get_status(refresh=True)) in {
            "queued", "started", "deferred", "scheduled",
        }
    except Exception:
        return False


def _run_document_locally(
    document_id: int,
    task_id: str,
    force_reparse: bool = False,
) -> dict:
    """在没有独立 Worker 时可靠执行同一条解析、分块、向量化流水线。"""
    lock_db: Session | None = None
    lock_acquired = False
    try:
        try:
            # MySQL named locks are connection-scoped and are released immediately
            # when an API process exits. Unlike a long Redis TTL, this cannot block
            # document recovery for hours after a restart during OCR.
            lock_db = MySQLSessionLocal()
            lock_name = f"medagent_document_{document_id}"
            lock_acquired = int(
                lock_db.execute(
                    text("SELECT GET_LOCK(:lock_name, 0)"),
                    {"lock_name": lock_name},
                ).scalar() or 0
            ) == 1
            if not lock_acquired:
                return {"status": "already_processing", "document_id": document_id}
        except Exception as exc:
            if lock_db is not None:
                lock_db.close()
                lock_db = None
            logger.warning("MySQL inline document lock unavailable: %s", exc)

        maximum = max(int(settings.DOCUMENT_PROCESS_MAX_ATTEMPTS), 1)
        for attempt in range(1, maximum + 1):
            try:
                # 首次解析成功后会持久化页面和清洗层。后续瞬时网络错误重试
                # 会从检查点恢复，只重新执行分块/Embedding/pgvector 写入。
                return process_document(
                    document_id,
                    task_id,
                    # A forced rebuild only needs one fresh parse. If embedding
                    # fails afterwards, retry from the newly persisted checkpoint.
                    force_reparse=force_reparse and attempt == 1,
                )
            except EmbeddingTransientError as exc:
                if attempt < maximum:
                    delay = max(float(settings.DOCUMENT_RETRY_DELAY_SECONDS), 0.0) * attempt
                    task_manager.record_attempt_failure(task_id, str(exc))
                    logger.warning(
                        "Retrying document vectorization from checkpoint: "
                        "document_id=%s attempt=%s/%s delay=%.1fs error=%s",
                        document_id,
                        attempt + 1,
                        maximum,
                        delay,
                        exc,
                    )
                    if delay:
                        time.sleep(delay)
                    continue
                error = f"文档自动处理失败: {exc}"
                task_manager.fail_task(task_id, error)
                _mark_document_failed(document_id, error)
                raise RuntimeError(error) from exc
            except Exception as exc:
                error = f"文档自动处理失败: {exc}"
                task_manager.fail_task(task_id, error)
                _mark_document_failed(document_id, error)
                raise RuntimeError(error) from exc

        raise AssertionError("unreachable")
    finally:
        if lock_db is not None:
            try:
                if lock_acquired:
                    lock_db.execute(
                        text("SELECT RELEASE_LOCK(:lock_name)"),
                        {"lock_name": f"medagent_document_{document_id}"},
                    )
            except Exception:
                logger.debug("Inline document MySQL lock already released: %s", task_id)
            finally:
                lock_db.close()


def _schedule_local_document(
    document_id: int,
    task_id: str,
    force_reparse: bool = False,
) -> None:
    """幂等地提交本地兜底任务，防止列表轮询或恢复线程重复执行。"""
    with _local_jobs_lock:
        existing = _local_jobs.get(task_id)
        if existing and not existing.done():
            return
        future = _local_executor.submit(
            _run_document_locally,
            document_id,
            task_id,
            force_reparse,
        )
        _local_jobs[task_id] = future

    def forget(completed: Future) -> None:
        with _local_jobs_lock:
            if _local_jobs.get(task_id) is completed:
                _local_jobs.pop(task_id, None)
        try:
            completed.result()
        except Exception:
            logger.exception("Local document task ended in failure: task_id=%s", task_id)

    future.add_done_callback(forget)


def _dispatch_document_execution(
    document_id: int,
    task_id: str,
    force_reparse: bool = False,
) -> None:
    """优先交给 RQ；没有 Worker 时自动切换到进程内后台执行。"""
    with _local_jobs_lock:
        local = _local_jobs.get(task_id)
        if local and not local.done():
            return
    if _rq_job_is_active(task_id):
        return

    if not _rq_workers_available() and settings.DOCUMENT_INLINE_FALLBACK_ENABLED:
        logger.warning(
            "No active RQ worker; processing document %s in API fallback executor",
            document_id,
        )
        _schedule_local_document(document_id, task_id, force_reparse)
        return

    doc_queue.enqueue(
        process_document,
        document_id,
        task_id,
        force_reparse,
        job_timeout=settings.DOCUMENT_PROCESS_TIMEOUT_SECONDS,
        result_ttl=86400,
        failure_ttl=86400,
        on_failure=document_job_failure,
        retry=Retry(
            max=max(int(settings.DOCUMENT_PROCESS_MAX_ATTEMPTS), 1) - 1,
            interval=[
                max(int(settings.DOCUMENT_RETRY_DELAY_SECONDS * attempt), 1)
                for attempt in range(1, max(int(settings.DOCUMENT_PROCESS_MAX_ATTEMPTS), 1))
            ],
        ) if int(settings.DOCUMENT_PROCESS_MAX_ATTEMPTS) > 1 else None,
        job_id=task_id,
    )


def _ensure_pgvector_extension() -> None:
    pg_db = PgSessionLocal()
    try:
        from sqlalchemy import text

        pg_db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        pg_db.commit()
    except Exception as exc:
        logger.warning("Failed to create vector extension: %s", exc)
        pg_db.rollback()
    finally:
        pg_db.close()


def _mark_document_failed(document_id: int, error: str) -> None:
    """尽最大努力把 RQ 超时/进程退出等队列级失败同步到文档表。"""
    mysql_db = MySQLSessionLocal()
    try:
        document = mysql_db.query(Document).filter(Document.id == document_id).first()
        if document:
            if document.parse_status in ("pending", "processing"):
                document.parse_status = "failed"
            if document.vector_status in ("pending", "processing"):
                document.vector_status = "failed"
            document.error_message = str(error)[:2000]
            mysql_db.commit()
    except Exception:
        mysql_db.rollback()
        logger.exception("Failed to persist document failure for document_id=%s", document_id)
    finally:
        mysql_db.close()


def _mark_document_dispatch_pending(document_id: int, error: str) -> None:
    """队列暂时不可用时保留待处理状态，交给 transactional outbox 自动重试。"""
    mysql_db = MySQLSessionLocal()
    try:
        document = mysql_db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.parse_status = "pending"
            document.vector_status = "pending"
            document.error_message = f"后台任务暂未派发，将自动重试: {error}"[:2000]
            mysql_db.commit()
    except Exception:
        mysql_db.rollback()
        logger.exception("Failed to persist pending dispatch for document_id=%s", document_id)
    finally:
        mysql_db.close()


def document_job_failure(job, connection, exception_type, exception_value, traceback) -> None:
    """RQ 失败回调：即使任务被超时终止，也不能让前端永久停在 95%。"""
    del connection, exception_type, traceback
    document_id = int(job.args[0]) if job.args else 0
    task_id = str(job.args[1]) if len(job.args) > 1 else str(job.id)
    error = f"后台文档任务异常终止: {exception_value}"
    task_manager.fail_task(task_id, error)
    if document_id:
        _mark_document_failed(document_id, error)


def enqueue_document(
    document_id: int,
    user_id: int,
    idempotency_key: str | None = None,
    force_reparse: bool = False,
) -> str:
    """先创建可见任务记录，再入队，并为扫描件配置足够的执行时间。"""
    if idempotency_key:
        existing = task_manager.get_by_idempotency_key(idempotency_key)
        if existing and existing.get("status") not in {"completed", "failed", "canceled"}:
            existing_task_id = str(existing["task_id"])
            _dispatch_document_execution(document_id, existing_task_id, force_reparse)
            return existing_task_id
    suffix = uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:12] if idempotency_key else uuid.uuid4().hex[:8]
    task_id = f"doc_{document_id}_{suffix}"
    task = task_manager.start_task(
        task_id=task_id,
        user_id=user_id,
        task_type="document_process",
        total_steps=100,
        message="文档已进入处理队列",
        idempotency_key=idempotency_key,
        max_attempts=settings.DOCUMENT_PROCESS_MAX_ATTEMPTS,
    )
    if task["task_id"] != task_id:
        existing_task_id = str(task["task_id"])
        _dispatch_document_execution(document_id, existing_task_id, force_reparse)
        return existing_task_id
    try:
        _dispatch_document_execution(document_id, task_id, force_reparse)
    except Exception as exc:
        task_manager.fail_task(task_id, f"文档任务入队失败: {exc}")
        # 文件和 outbox 事件已经在同一个 MySQL 事务中提交。此处不能把文档
        # 标记为最终失败，否则 Redis 恢复后虽然能重放事件，前端却会提前显示失败。
        _mark_document_dispatch_pending(document_id, str(exc))
        raise
    return task_id


def recover_pending_vectorization(limit: int = 100) -> dict[str, int]:
    """恢复服务重启前未完成的文档，以及基础设施异常留下的失败记录。"""
    mysql_db = MySQLSessionLocal()
    try:
        documents = mysql_db.query(Document).filter(
            Document.parse_status.in_(("pending", "processing", "success")),
            Document.file_path.is_not(None),
            Document.file_type.in_(("pdf", "docx", "txt", "md", "markdown")),
            or_(
                Document.vector_status.in_(("pending", "processing")),
                and_(
                    Document.vector_status == "failed",
                    or_(
                        Document.error_message.contains("后台文档任务异常终止"),
                        Document.error_message.contains("Task exceeded maximum timeout"),
                    ),
                ),
            ),
        ).order_by(Document.id.asc()).limit(limit).all()
        candidates = [
            (
                int(document.id),
                int(document.uploader_id),
                document.processing_task_id,
                document.normalized_text_sha256 or document.content_sha256 or "unknown",
            )
            for document in documents
        ]
    finally:
        mysql_db.close()

    scheduled = failed = 0
    for document_id, user_id, task_id, content_hash in candidates:
        try:
            task = task_manager.get_task(task_id) if task_id else None
            if task and task.get("status") not in {"completed", "failed", "canceled"}:
                _dispatch_document_execution(document_id, str(task_id))
            else:
                enqueue_document(
                    document_id,
                    user_id,
                    idempotency_key=f"document.auto-vectorize:{document_id}:{content_hash}",
                )
            scheduled += 1
        except Exception:
            failed += 1
            logger.exception("Failed to recover vectorization for document_id=%s", document_id)
    return {"scheduled": scheduled, "failed": failed}


def process_document(
    document_id: int,
    task_id: Optional[str] = None,
    force_reparse: bool = False,
):
    """执行文本提取/OCR、分块、向量化和状态收尾。"""
    if not task_id:
        task_id = f"doc_{document_id}_{uuid.uuid4().hex[:8]}"

    mysql_db: Session = MySQLSessionLocal()
    pg_db: Session = PgSessionLocal()
    try:
        document = mysql_db.query(Document).filter(Document.id == document_id).first()
        if not document:
            if task_manager.get_task(task_id):
                task_manager.fail_task(task_id, "文档不存在")
            return {"error": "Document not found"}

        knowledge_base = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == document.kb_id).first()
        if not knowledge_base:
            raise ValueError("Document knowledge base does not exist")
        tenant_id = int(knowledge_base.tenant_id)

        if not task_manager.get_task(task_id):
            task_manager.start_task(
                task_id=task_id,
                user_id=document.uploader_id,
                task_type="document_process",
                total_steps=100,
                message="开始处理文档",
                max_attempts=settings.DOCUMENT_PROCESS_MAX_ATTEMPTS,
            )

        task_state = task_manager.begin_attempt(task_id, "开始处理文档") or {}
        task_manager.update_percent(task_id, 2, "正在检查文档内容...")
        document.vector_status = "pending"
        document.error_message = None
        document.processing_task_id = task_id
        document.processing_started_at = datetime.utcnow()
        document.processing_completed_at = None
        must_reparse = force_reparse and int(task_state.get("attempt") or 1) <= 1
        parsed = None if must_reparse else document_processing_service.load_parsed_checkpoint(
            mysql_db,
            document,
        )
        if parsed is not None:
            document.parse_status = "success"
            task_manager.update_percent(
                task_id,
                58,
                f"已复用完整文本解析结果（{parsed.page_count} 页），不再重复 OCR",
            )
        else:
            document.parse_status = "processing"
        mysql_db.commit()

        def report_pdf_progress(done: int, total: int, used_ocr: bool) -> None:
            percent = 5 + int(done / max(total, 1) * 50)
            action = "OCR 识别" if used_ocr else "提取文字"
            task_manager.update_percent(
                task_id,
                percent,
                f"正在{action} PDF：第 {done}/{total} 页",
            )

        if parsed is None:
            parsed = parse_document(
                document.file_path,
                document.file_type,
                progress_callback=report_pdf_progress,
            )
            if not parsed.pages:
                raise ValueError("未提取到文本内容")

            document.content_sha256 = parsed.metadata.get("content_sha256")
            document.parser_version = parsed.parser_version
            document.cleaning_version = parsed.cleaning_version
            document.page_count = parsed.page_count
            document.ocr_page_count = parsed.ocr_page_count
            document.processing_warnings = parsed.warnings or None
            document_processing_service.replace_layers(mysql_db, document, parsed)
            mysql_db.commit()

        document_version = document.document_version or document.content_sha256 or "legacy"

        task_manager.update_percent(task_id, 60, "文本提取完成，正在按页面和章节分块...")
        splitter = StructuralSplitter(
            child_tokens=settings.CHILD_CHUNK_TOKENS,
            parent_tokens=settings.PARENT_CHUNK_TOKENS,
            overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
        )
        chunks = splitter.split(parsed)
        child_chunks = [chunk for chunk in chunks if chunk.chunk_type == "child"]
        if not child_chunks:
            raise ValueError("文本清洗后未产生有效分块")

        document.chunker_version = splitter.version
        document.parse_status = "success"
        document.vector_status = "processing"
        mysql_db.commit()

        task_manager.update_percent(
            task_id, 65, f"文本已拆分为 {len(child_chunks)} 个检索块，正在生成向量..."
        )
        batch_result = embedding_service.embed_batch(
            [chunk.content for chunk in child_chunks],
            progress_callback=lambda done, total: task_manager.update_percent(
                task_id,
                65 + int(done / max(total, 1) * 27),
                f"正在批量生成向量：{done}/{total} 块",
            ),
        )
        embeddings = batch_result.require_all()

        _ensure_pgvector_extension()
        # Delete and replacement remain in one PostgreSQL transaction. If persistence
        # fails, rollback keeps the previously searchable version intact.
        pg_db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()
        task_manager.update_percent(task_id, 93, "向量生成完成，正在写入版本化分块...")

        parent_ids = {}
        for chunk in (item for item in chunks if item.chunk_type == "parent"):
            metadata = extract_medical_metadata(chunk.content)
            row = DocumentChunk(
                tenant_id=tenant_id,
                document_id=document_id,
                kb_id=document.kb_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                title=document.filename,
                section_title=" / ".join(chunk.section_path or []) or None,
                page_num=chunk.page_start,
                logical_id=chunk.logical_id,
                chunk_type="parent",
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_path=chunk.section_path,
                token_count=chunk.token_count,
                content_sha256=chunk.content_sha256,
                parser_version=parsed.parser_version,
                chunker_version=splitter.version,
                metadata_json=chunk.metadata or None,
                medical_entities=metadata.medical_entities or None,
                normalized_drug_names=metadata.normalized_drug_names or None,
                disease_names=metadata.disease_names or None,
                medical_codes=metadata.medical_codes or None,
                keywords=metadata.keywords or None,
                source_type="local_knowledge_base",
                authority_level=7,
                document_version=document_version,
                source_block_ids=chunk.metadata.get("source_block_ids") or None,
                content_type=chunk.metadata.get("content_type", "paragraph"),
                cleaning_version=parsed.cleaning_version,
                extraction_method=chunk.metadata.get("extraction_method"),
                ocr_confidence=chunk.metadata.get("ocr_confidence"),
                quality_status=chunk.metadata.get("quality_status", "not_evaluated"),
            )
            pg_db.add(row)
            pg_db.flush()
            parent_ids[chunk.logical_id] = row.id

        successful_chunks = 0
        for chunk, embedding in zip(child_chunks, embeddings):
            metadata = extract_medical_metadata(chunk.content)
            pg_db.add(
                DocumentChunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    kb_id=document.kb_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    title=document.filename,
                    section_title=" / ".join(chunk.section_path or []) or None,
                    page_num=chunk.page_start,
                    logical_id=chunk.logical_id,
                    parent_chunk_id=parent_ids.get(chunk.parent_logical_id),
                    chunk_type="child",
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    section_path=chunk.section_path,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    token_count=chunk.token_count,
                    content_sha256=chunk.content_sha256,
                    parser_version=parsed.parser_version,
                    chunker_version=splitter.version,
                    embedding_model=settings.EMBEDDING_MODEL,
                    embedding_dimensions=len(embedding),
                    embedding_version=f"{settings.EMBEDDING_MODEL}:{len(embedding)}",
                    embedded_at=datetime.utcnow(),
                    metadata_json=chunk.metadata or None,
                    medical_entities=metadata.medical_entities or None,
                    normalized_drug_names=metadata.normalized_drug_names or None,
                    disease_names=metadata.disease_names or None,
                    medical_codes=metadata.medical_codes or None,
                    keywords=metadata.keywords or None,
                    source_type="local_knowledge_base",
                    authority_level=7,
                    document_version=document_version,
                    source_block_ids=chunk.metadata.get("source_block_ids") or None,
                    content_type=chunk.metadata.get("content_type", "paragraph"),
                    cleaning_version=parsed.cleaning_version,
                    extraction_method=chunk.metadata.get("extraction_method"),
                    ocr_confidence=chunk.metadata.get("ocr_confidence"),
                    quality_status=chunk.metadata.get("quality_status", "not_evaluated"),
                    embedding=embedding,
                )
            )
            successful_chunks += 1

            if successful_chunks % 50 == 0:
                pg_db.flush()

        if successful_chunks == 0:
            raise ValueError("没有可写入的有效文本分块")

        # 在同一个 PostgreSQL 事务内验证所有可检索子块都已携带向量，避免
        # 状态被标记为 success，但 pgvector 中只写入了文本或写入数量不完整。
        pg_db.flush()
        persisted_vector_count = pg_db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_type == "child",
            DocumentChunk.embedding.is_not(None),
        ).count()
        if persisted_vector_count != successful_chunks:
            raise RuntimeError(
                "pgvector 写入校验失败: "
                f"expected={successful_chunks}, actual={persisted_vector_count}"
            )

        task_manager.update_percent(task_id, 98, "正在提交向量和文档状态...")
        pg_db.commit()
        document.vector_status = "success"
        document.error_message = None
        document.embedding_model = settings.EMBEDDING_MODEL
        document.embedding_dimensions = len(embeddings[0])
        document.chunker_version = splitter.version
        document.chunk_count = successful_chunks
        document.processing_completed_at = datetime.utcnow()
        mysql_db.commit()

        result = {
            "status": "success",
            "document_id": document_id,
            "chunks": successful_chunks,
        }
        task_manager.complete_task(
            task_id,
            result=result,
            message=f"处理完成：共 {successful_chunks} 个文本块已入库",
        )
        return result

    except Exception as exc:
        mysql_db.rollback()
        pg_db.rollback()
        error = str(exc)
        logger.exception("Document processing failed: document_id=%s", document_id)
        # Synchronous/inline runs do not have an RQ failure callback. Persist a
        # truthful terminal state while the old PostgreSQL index remains intact.
        try:
            failed_document = mysql_db.query(Document).filter(Document.id == document_id).first()
            if failed_document is not None:
                failed_document.vector_status = "failed"
                failed_document.error_message = error[:2000]
                failed_document.processing_completed_at = datetime.utcnow()
                mysql_db.commit()
        except Exception:
            mysql_db.rollback()
            logger.exception("Unable to persist document failure state: document_id=%s", document_id)
        # Do not convert an execution exception into a successful RQ result.
        # RQ owns retry scheduling; its terminal failure callback persists the
        # final task/document failure only after all attempts are exhausted.
        task_manager.record_attempt_failure(task_id, error)
        raise
    finally:
        mysql_db.close()
        pg_db.close()
