# 导入操作系统模块，用于文件和路径操作
import os
import hashlib
import logging
# 导入 UUID 模块，用于生成唯一的文件名
import uuid
# 导入类型提示：列表
from typing import List

# 从 FastAPI 导入路由、依赖注入、HTTP 异常、文件上传、表单字段等
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
# 导入文件响应类，用于直接返回文件内容
from fastapi.responses import FileResponse
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session

# 导入应用配置
from app.core.config import settings
# 导入获取当前用户的依赖函数
from app.core.dependencies import get_current_user
# 导入数据库会话工厂（MySQL 和 PostgreSQL）
from app.db.session import get_mysql_db, get_pg_db
# 导入用户模型
from app.models.user import User
# 导入文档模型
from app.models.document import Document
# 导入文档块（切片）模型
from app.models.document_chunk import DocumentChunk
# 导入文档相关的 Pydantic 响应模型
from app.schemas.document import (
    DocumentResponse, DocumentStatusResponse, DocumentPreviewResponse,
    DocumentQualityDetailResponse, DocumentQualityReviewRequest,
    VectorStoreRebuildResponse,
)
from app.models.document_processing import (
    DocumentPage, DocumentRawBlock, DocumentCleanBlock, DocumentTable,
    DocumentQualityReportRecord, DocumentCleaningActionRecord,
)
# 导入文档处理任务和任务队列
from app.services.access_control_service import (
    KnowledgeBaseAccessDenied,
    require_kb_write_access,
    resolve_authorized_kb_ids,
)
from app.services.outbox_service import add_document_outbox, dispatch_outbox_event
from app.services.task_manager import task_manager
from app.services.embedding_service import EmbeddingError, embedding_service

# 创建文档路由实例
router = APIRouter()
logger = logging.getLogger(__name__)

# 允许上传的文件扩展名集合
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}
UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024


async def _stream_upload_to_disk(
    upload: UploadFile,
    file_path: str,
    *,
    max_bytes: int | None,
) -> tuple[int, str]:
    """Stream an upload to disk and return its byte count and SHA-256.

    PDF uploads pass ``max_bytes=None`` and therefore have no application-level
    size limit.  A temporary file prevents interrupted uploads from being
    mistaken for complete source documents.
    """
    temporary_path = f"{file_path}.part"
    digest = hashlib.sha256()
    file_size = 0
    try:
        with open(temporary_path, "wb") as target:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if max_bytes is not None and file_size > max_bytes:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large; non-PDF files are limited to {settings.MAX_UPLOAD_SIZE_MB}MB",
                    )
                digest.update(chunk)
                target.write(chunk)
        os.replace(temporary_path, file_path)
        return file_size, digest.hexdigest()
    except Exception:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise


def _require_document_read(doc: Document, user: User, db: Session) -> None:
    try:
        resolve_authorized_kb_ids(user, [doc.kb_id], db)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc


def _require_document_write(doc: Document, user: User, db: Session) -> None:
    try:
        require_kb_write_access(user, doc.kb_id, db)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc


def _document_progress(doc: Document) -> tuple[int, str | None]:
    """读取处理进度，并以数据库中的终态为最终事实来源。"""
    task = task_manager.get_task(doc.processing_task_id) if doc.processing_task_id else None
    if doc.vector_status == "success":
        return 100, "处理完成"
    if doc.parse_status == "failed" or doc.vector_status == "failed":
        progress = int(task.get("progress") or 0) if task else 0
        return min(max(progress, 0), 99), doc.error_message or "文档处理失败，请重试"
    if task and task.get("status") not in {"completed", "failed", "canceled"}:
        return int(task.get("progress") or 0), task.get("message")
    if doc.vector_status == "processing":
        return 65, "正在生成并写入向量"
    if doc.parse_status == "success":
        return 60, "文本解析完成，即将自动向量化"
    if doc.parse_status == "processing":
        return 2, "正在解析文档"
    return 0, None


def _document_task_active(doc: Document) -> bool:
    if doc.processing_task_id:
        task = task_manager.get_task(doc.processing_task_id)
        if task and task.get("status") not in {"completed", "failed", "canceled"}:
            return True
    return doc.parse_status == "processing" or doc.vector_status == "processing"


def _doc_to_response(doc: Document) -> DocumentResponse:
    """将 Document ORM 模型转换为 DocumentResponse 响应模型。"""
    progress, progress_message = _document_progress(doc)
    return DocumentResponse(
        id=doc.id,                       # 文档 ID
        kb_id=doc.kb_id,                 # 所属知识库 ID
        filename=doc.filename,           # 文件名
        file_type=doc.file_type,         # 文件类型（pdf/docx/txt/md）
        file_size=doc.file_size or 0,    # 文件大小（字节），默认为 0
        parse_status=doc.parse_status,   # 解析状态
        vector_status=doc.vector_status, # 向量化状态
        uploader_id=doc.uploader_id,     # 上传者 ID
        source_url=doc.source_url,       # 来源 URL
        error_message=doc.error_message, # 错误信息
        cleaning_version=doc.cleaning_version,
        quality_status=doc.quality_status,
        processing_task_id=doc.processing_task_id,
        processing_progress=progress,
        processing_message=progress_message,
        created_at=doc.created_at,       # 创建时间
        updated_at=doc.updated_at,       # 更新时间
    )


# 上传文档接口：POST /api/documents/upload
@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    kb_id: int = Form(...),                       # 知识库 ID（必填表单字段）
    file: UploadFile = File(...),                  # 上传的文件（必填）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    try:
        require_kb_write_access(current_user, kb_id, mysql_db)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail="Knowledge base access denied") from exc
    # 获取文件扩展名并转为小写
    ext = os.path.splitext(file.filename)[1].lower()
    # 检查文件类型是否在允许的范围内
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    # 文件扩展名到文件类型的映射（统一类型名称）
    allowed_types = {"pdf": ".pdf", "docx": ".docx", "txt": ".txt", "md": ".md", "markdown": ".md"}
    # 根据扩展名获取标准化文件类型，默认为 txt
    file_type = next((k for k, v in allowed_types.items() if v == ext), "txt")

    # 获取上传目录路径，确保目录存在
    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    # 使用 UUID 生成唯一文件名，防止冲突
    saved_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, saved_name)

    # PDF 不设应用层大小上限；其它文档仍受配置项保护。所有上传均分块
    # 写入磁盘，避免大型 PDF 被一次性加载到 API 进程内存。
    max_bytes = None if ext == ".pdf" else settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_size, content_sha256 = await _stream_upload_to_disk(
        file,
        file_path,
        max_bytes=max_bytes,
    )

    # 在数据库中创建文档记录
    doc = Document(
        kb_id=kb_id,                    # 所属知识库 ID
        filename=file.filename,         # 原始文件名
        file_type=file_type,            # 文件类型
        file_size=file_size,            # 文件大小
        file_path=file_path,            # 磁盘存储路径
        parse_status="pending",         # 初始解析状态：待处理
        vector_status="pending",        # 初始向量化状态：待处理
        uploader_id=current_user.id,    # 上传者 ID
        content_sha256=content_sha256,
    )
    mysql_db.add(doc)
    mysql_db.flush()
    outbox = add_document_outbox(mysql_db, doc.id, current_user.id, content_sha256)
    mysql_db.commit()
    mysql_db.refresh(doc)  # 刷新以获取数据库生成的 ID
    mysql_db.refresh(outbox)

    # 先创建跨进程可见的任务记录，再加入后台队列。这样即使 worker 尚未
    # 开始执行，前端也能看到“等待中”；入队失败则立即返回明确错误。
    try:
        dispatch_outbox_event(outbox.id)
    except Exception as exc:
        # 文档和 outbox 已可靠提交。Redis 短暂不可用不应让上传请求看起来失败，
        # 常驻 worker 会周期性重放该事件，恢复后自动进入解析和向量化流程。
        logger.warning("Document %s is waiting for outbox retry: %s", doc.id, exc)
    finally:
        # dispatch 使用独立会话写入 processing_task_id，刷新后上传响应可立即
        # 携带 0% 的任务进度，前端无需等待下一次列表轮询。
        mysql_db.refresh(doc)

    # 返回文档响应
    return _doc_to_response(doc)


# 获取文档列表接口：GET /api/documents
@router.get("", response_model=List[DocumentResponse])
def list_documents(
    kb_id: int = None,                            # 可选的知识库 ID 筛选
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 构建查询
    accessible_kb_ids = resolve_authorized_kb_ids(current_user, None, mysql_db)
    query = mysql_db.query(Document).filter(Document.kb_id.in_(accessible_kb_ids))
    if kb_id:
        try:
            resolve_authorized_kb_ids(current_user, [kb_id], mysql_db)
        except KnowledgeBaseAccessDenied as exc:
            raise HTTPException(status_code=403, detail="Access denied") from exc
        query = query.filter(Document.kb_id == kb_id)
    # 按创建时间降序排列
    docs = query.order_by(Document.created_at.desc()).all()
    # 将 ORM 对象列表转换为响应模型列表
    return [_doc_to_response(doc) for doc in docs]


# 获取单个文档详情接口：GET /api/documents/{document_id}
@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 按 ID 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查：文档必须属于当前用户，或者当前用户是管理员
    _require_document_read(doc, current_user, mysql_db)
    return _doc_to_response(doc)


# 获取文档处理状态接口：GET /api/documents/{document_id}/status
@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _require_document_read(doc, current_user, mysql_db)
    # 返回包含解析状态、向量化状态和错误信息的状态响应
    progress, progress_message = _document_progress(doc)
    return DocumentStatusResponse(
        id=doc.id,
        parse_status=doc.parse_status,
        vector_status=doc.vector_status,
        error_message=doc.error_message,
        processing_task_id=doc.processing_task_id,
        processing_progress=progress,
        processing_message=progress_message,
    )


@router.get("/{document_id}/quality", response_model=DocumentQualityDetailResponse)
def get_document_quality(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _require_document_read(doc, current_user, mysql_db)
    report = mysql_db.query(DocumentQualityReportRecord).filter_by(document_id=document_id).first()
    pages = mysql_db.query(DocumentPage).filter_by(document_id=document_id).order_by(DocumentPage.page_num).all()
    raw = mysql_db.query(DocumentRawBlock).filter_by(document_id=document_id).order_by(DocumentRawBlock.page_num, DocumentRawBlock.reading_order).all()
    clean = mysql_db.query(DocumentCleanBlock).filter_by(document_id=document_id).order_by(DocumentCleanBlock.page_num, DocumentCleanBlock.reading_order).all()
    tables = mysql_db.query(DocumentTable).filter_by(document_id=document_id).order_by(DocumentTable.page_start).all()
    actions = mysql_db.query(DocumentCleaningActionRecord).filter_by(document_id=document_id).order_by(DocumentCleaningActionRecord.id).all()
    return DocumentQualityDetailResponse(
        document_id=document_id,
        cleaning_version=doc.cleaning_version,
        quality_status=doc.quality_status or "pending",
        report=report.report_json if report else {},
        pages=[{
            "page_num": item.page_num, "page_type": item.page_type,
            "extraction_method": item.extraction_method, "raw_text": item.raw_text,
            "cleaned_text": item.cleaned_text, "classification": item.classification_json,
            "ocr_spans": item.ocr_spans_json or [], "ocr_confidence": item.ocr_confidence,
            "quality_score": item.quality_score, "quality_status": item.quality_status,
            "warnings": item.warnings_json or [],
        } for item in pages],
        raw_blocks=[{
            "block_id": item.block_id, "page_num": item.page_num, "block_type": item.block_type,
            "text": item.text, "bbox": item.bbox_json, "spans": item.spans_json or [],
            "reading_order": item.reading_order, "extraction_method": item.extraction_method,
            "confidence": item.confidence,
        } for item in raw],
        clean_blocks=[{
            "block_id": item.block_id, "raw_block_id": item.raw_block_id, "page_num": item.page_num,
            "block_type": item.block_type, "text": item.text, "bbox": item.bbox_json,
            "section_path": item.section_path_json or [], "reading_order": item.reading_order,
        } for item in clean],
        tables=[{
            "table_id": item.table_id, "title": item.title, "page_start": item.page_start,
            "page_end": item.page_end, "headers": item.headers_json or [], "rows": item.rows_json or [],
            "units": item.units_json or [], "footnotes": item.footnotes_json or [],
            "markdown": item.markdown, "confidence": item.confidence,
        } for item in tables],
        cleaning_actions=[{
            "action_type": item.action_type, "page_num": item.page_num, "block_id": item.block_id,
            "original_text": item.original_text, "cleaned_text": item.cleaned_text,
            "rule": item.rule, "confidence": item.confidence,
        } for item in actions],
    )


@router.post("/{document_id}/quality/review", response_model=DocumentStatusResponse)
def review_document_quality(
    document_id: int,
    request: DocumentQualityReviewRequest,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    if request.decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="decision must be approve or reject")
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _require_document_write(doc, current_user, mysql_db)
    report = mysql_db.query(DocumentQualityReportRecord).filter_by(document_id=document_id).first()
    if not report or report.review_status not in {"pending", "approved"}:
        raise HTTPException(status_code=409, detail="Document is not waiting for quality review")
    from datetime import datetime
    report.reviewed_by = current_user.id
    report.review_comment = request.comment
    report.reviewed_at = datetime.utcnow()
    if request.decision == "reject":
        report.review_status = "rejected"
        doc.quality_status = "rejected"
        doc.parse_status = "review_rejected"
        doc.vector_status = "blocked"
    else:
        report.review_status = "approved"
        doc.quality_status = "approved"
        doc.parse_status = "pending"
        doc.vector_status = "pending"
    mysql_db.commit()
    if request.decision == "approve":
        from app.tasks.document_tasks import enqueue_document
        enqueue_document(doc.id, current_user.id, idempotency_key=f"document.quality-approve:{doc.id}:{report.id}")
    return DocumentStatusResponse(id=doc.id, parse_status=doc.parse_status, vector_status=doc.vector_status, error_message=doc.error_message)


# 删除文档接口：DELETE /api/documents/{document_id}
@router.delete("/{document_id}")
def delete_document(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    pg_db: Session = Depends(get_pg_db),          # PostgreSQL 数据库会话（用于删除向量切片）
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查
    _require_document_write(doc, current_user, mysql_db)

    # 从 PostgreSQL 中删除该文档的所有向量切片
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()

    # 如果文件存在磁盘上，删除物理文件
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    # 从 MySQL 中删除文档记录
    mysql_db.delete(doc)
    mysql_db.commit()
    return {"message": "Document deleted"}


# 下载原始文件接口：GET /api/documents/{document_id}/file
@router.get("/{document_id}/file")
def get_document_file(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    """返回原始上传文件供下载。"""
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查
    _require_document_read(doc, current_user, mysql_db)
    # 检查文件是否存在于磁盘上
    if not doc.file_path or not os.path.isfile(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    # 根据文件扩展名确定 MIME 类型
    ext = os.path.splitext(doc.filename)[1].lower()
    media_types = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".txt": "text/plain; charset=utf-8",
        ".md": "text/markdown; charset=utf-8",
        ".markdown": "text/markdown; charset=utf-8",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    # 使用 FileResponse 返回文件流
    return FileResponse(doc.file_path, media_type=media_type, filename=doc.filename)


# 预览文档内容接口：GET /api/documents/{document_id}/preview
@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
def preview_document(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    """返回提取的文本内容供预览（支持 TXT、MD、DOCX 格式）。"""
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查
    _require_document_read(doc, current_user, mysql_db)

    content = ""
    if doc.file_type == "pdf":
        # PDF 文件无法直接提取文本预览，提示用户使用查看功能
        content = "PDF 文件请直接点击「预览」按钮查看"
    elif doc.file_type in ("txt",):
        # TXT 文件直接读取文本内容
        if doc.file_path and os.path.isfile(doc.file_path):
            with open(doc.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    elif doc.file_type in ("md", "markdown"):
        # Markdown 文件直接读取文本内容
        if doc.file_path and os.path.isfile(doc.file_path):
            with open(doc.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    elif doc.file_type == "docx":
        # DOCX 文件使用 python-docx 库提取文本
        if doc.file_path and os.path.isfile(doc.file_path):
            try:
                from docx import Document as DocxDocument
                docx_doc = DocxDocument(doc.file_path)
                content = "\n".join(p.text for p in docx_doc.paragraphs)
            except Exception:
                content = "（无法解析此 DOCX 文件）"
    else:
        content = "（暂不支持预览此文件类型）"

    # 返回预览响应，包含文件名、文件类型、文本内容和总长度
    return DocumentPreviewResponse(
        filename=doc.filename,
        file_type=doc.file_type,
        content=content,
        total_length=len(content),
    )


# 重试文档处理接口：POST /api/documents/{document_id}/retry
@router.post("/{document_id}/retry", response_model=DocumentStatusResponse)
def retry_document_vectorization(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """重试失败的处理流程；解析检查点完整时不会再次读取/OCR 原 PDF。"""
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    _require_document_write(doc, current_user, mysql_db)

    if doc.vector_status == "success":
        return DocumentStatusResponse(
            id=doc.id,
            parse_status=doc.parse_status,
            vector_status=doc.vector_status,
            processing_task_id=doc.processing_task_id,
            processing_progress=100,
            processing_message="处理完成",
        )

    # 保留成功的解析状态和分层清洗数据。process_document 会校验检查点
    # 哈希，只有检查点不完整时才重新读取源文件。
    if doc.parse_status != "success":
        doc.parse_status = "pending"
    doc.vector_status = "pending"
    doc.error_message = None
    doc.processing_task_id = None
    mysql_db.commit()

    try:
        from app.tasks.document_tasks import enqueue_document

        task_id = enqueue_document(
            doc.id,
            current_user.id,
            idempotency_key=f"document.retry:{doc.id}:{uuid.uuid4().hex}",
            force_reparse=False,
        )
        doc.processing_task_id = task_id
        mysql_db.commit()
    except Exception as exc:
        doc.vector_status = "failed"
        doc.error_message = f"文档重试任务入队失败: {exc}"[:2000]
        mysql_db.commit()
        raise HTTPException(status_code=503, detail=doc.error_message) from exc

    return DocumentStatusResponse(
        id=doc.id,
        parse_status=doc.parse_status,
        vector_status=doc.vector_status,
        processing_task_id=doc.processing_task_id,
        processing_progress=0,
        processing_message="已进入重试队列，将复用已有解析结果",
    )


# 重建文档处理接口：POST /api/documents/{document_id}/rebuild
@router.post("/{document_id}/rebuild", response_model=DocumentStatusResponse)
def rebuild_document(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查
    _require_document_write(doc, current_user, mysql_db)

    if _document_task_active(doc):
        raise HTTPException(status_code=409, detail="文档正在处理中，请等待当前任务结束后再更新")

    # 重置文档的解析和向量化状态为待处理
    doc.parse_status = "pending"
    doc.vector_status = "pending"
    doc.error_message = None  # 清除之前的错误信息
    mysql_db.commit()

    # 重新将文档加入处理队列
    try:
        from app.tasks.document_tasks import enqueue_document
        task_id = enqueue_document(
            doc.id,
            current_user.id,
            idempotency_key=f"document.rebuild:{doc.id}:{uuid.uuid4().hex}",
            force_reparse=True,
        )
        doc.processing_task_id = task_id
        mysql_db.commit()
    except Exception as exc:
        doc.parse_status = "failed"
        doc.vector_status = "failed"
        doc.error_message = f"文档任务入队失败: {exc}"[:2000]
        doc.processing_task_id = None
        mysql_db.commit()
        raise HTTPException(status_code=503, detail=doc.error_message) from exc

    # 返回新的状态
    return DocumentStatusResponse(
        id=doc.id,
        parse_status="pending",
        vector_status="pending",
        processing_task_id=doc.processing_task_id,
        processing_progress=0,
        processing_message="已进入新版 PDF 解析与向量库迭代队列",
    )


@router.post("/kb/{kb_id}/rebuild-vectors", response_model=VectorStoreRebuildResponse)
def rebuild_knowledge_base_vectors(
    kb_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Force-reparse all supported documents and atomically replace their vectors."""
    try:
        require_kb_write_access(current_user, kb_id, mysql_db)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    try:
        embedding_service.check_health()
    except EmbeddingError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"向量服务当前不可用，未修改任何文档：{exc}",
        ) from exc

    documents = mysql_db.query(Document).filter(
        Document.kb_id == kb_id,
        Document.file_path.is_not(None),
        Document.file_type.in_(("pdf", "docx", "txt", "md", "markdown")),
    ).order_by(Document.id.asc()).all()
    candidates = [doc for doc in documents if not _document_task_active(doc)]
    skipped_active = len(documents) - len(candidates)
    if not candidates:
        return VectorStoreRebuildResponse(
            kb_id=kb_id,
            scheduled=0,
            skipped_active=skipped_active,
            document_ids=[],
            message="没有可更新的文档；正在处理的文档已跳过",
        )

    scheduled_ids: list[int] = []
    dispatch_failures: list[str] = []
    for doc in candidates:
        doc.parse_status = "pending"
        doc.vector_status = "pending"
        doc.error_message = None
        doc.processing_task_id = None
    mysql_db.commit()

    from app.tasks.document_tasks import enqueue_document

    for doc in candidates:
        try:
            task_id = enqueue_document(
                int(doc.id),
                int(current_user.id),
                idempotency_key=f"kb.vector-rebuild:{kb_id}:{doc.id}:{uuid.uuid4().hex}",
                force_reparse=True,
            )
            doc.processing_task_id = task_id
            scheduled_ids.append(int(doc.id))
        except Exception as exc:
            doc.parse_status = "failed"
            doc.vector_status = "failed"
            doc.error_message = f"向量库迭代任务入队失败: {exc}"[:2000]
            dispatch_failures.append(str(doc.id))
        mysql_db.commit()

    message = f"已安排 {len(scheduled_ids)} 份文档使用最新版解析器重建向量"
    if skipped_active:
        message += f"，跳过 {skipped_active} 份处理中任务"
    if dispatch_failures:
        message += f"；{len(dispatch_failures)} 份文档入队失败"
    return VectorStoreRebuildResponse(
        kb_id=kb_id,
        scheduled=len(scheduled_ids),
        skipped_active=skipped_active,
        document_ids=scheduled_ids,
        message=message,
    )
