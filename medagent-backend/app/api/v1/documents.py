import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db, get_pg_db
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentResponse, DocumentStatusResponse, DocumentPreviewResponse
from app.tasks.document_tasks import process_document, doc_queue

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def _doc_to_response(doc: Document) -> DocumentResponse:
    return DocumentResponse(
        id=doc.id,
        kb_id=doc.kb_id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size or 0,
        parse_status=doc.parse_status,
        vector_status=doc.vector_status,
        uploader_id=doc.uploader_id,
        source_id=doc.source_id,
        source_url=doc.source_url,
        error_message=doc.error_message,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    kb_id: int = Form(...),
    file: UploadFile = File(...),
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    allowed_types = {"pdf": ".pdf", "docx": ".docx", "txt": ".txt", "md": ".md", "markdown": ".md"}
    file_type = next((k for k, v in allowed_types.items() if v == ext), "txt")

    upload_dir = settings.UPLOAD_DIR
    os.makedirs(upload_dir, exist_ok=True)
    saved_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, saved_name)

    content = await file.read()
    file_size = len(content)
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(status_code=400, detail="File too large")

    with open(file_path, "wb") as f:
        f.write(content)

    doc = Document(
        kb_id=kb_id,
        filename=file.filename,
        file_type=file_type,
        file_size=file_size,
        file_path=file_path,
        parse_status="pending",
        vector_status="pending",
        uploader_id=current_user.id,
    )
    mysql_db.add(doc)
    mysql_db.commit()
    mysql_db.refresh(doc)

    doc_queue.enqueue(process_document, doc.id)

    return _doc_to_response(doc)


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    kb_id: int = None,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    query = mysql_db.query(Document)
    if kb_id:
        query = query.filter(Document.kb_id == kb_id)
    if current_user.role != "admin":
        # Show user's own uploaded documents + system-synced source documents
        query = query.filter(
            (Document.uploader_id == current_user.id) |
            (Document.uploader_id == 0)
        )
    docs = query.order_by(Document.created_at.desc()).all()
    return [_doc_to_response(doc) for doc in docs]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return _doc_to_response(doc)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentStatusResponse(
        id=doc.id,
        parse_status=doc.parse_status,
        vector_status=doc.vector_status,
        error_message=doc.error_message,
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    pg_db: Session = Depends(get_pg_db),
    current_user: User = Depends(get_current_user),
):
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete chunks from PostgreSQL
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()

    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    # Delete document from MySQL
    mysql_db.delete(doc)
    mysql_db.commit()
    return {"message": "Document deleted"}


@router.get("/{document_id}/file")
def get_document_file(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Serve the raw uploaded file."""
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if not doc.file_path or not os.path.isfile(doc.file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

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
    return FileResponse(doc.file_path, media_type=media_type, filename=doc.filename)


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
def preview_document(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Return extracted text content for preview (TXT, MD, DOCX)."""
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    content = ""
    if doc.file_type == "pdf":
        content = "PDF 文件请直接点击「预览」按钮查看"
    elif doc.file_type in ("txt",):
        if doc.file_path and os.path.isfile(doc.file_path):
            with open(doc.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    elif doc.file_type in ("md", "markdown"):
        if doc.file_path and os.path.isfile(doc.file_path):
            with open(doc.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
    elif doc.file_type == "docx":
        if doc.file_path and os.path.isfile(doc.file_path):
            try:
                from docx import Document as DocxDocument
                docx_doc = DocxDocument(doc.file_path)
                content = "\n".join(p.text for p in docx_doc.paragraphs)
            except Exception:
                content = "（无法解析此 DOCX 文件）"
    else:
        content = "（暂不支持预览此文件类型）"

    return DocumentPreviewResponse(
        filename=doc.filename,
        file_type=doc.file_type,
        content=content,
        total_length=len(content),
    )


@router.post("/{document_id}/rebuild", response_model=DocumentStatusResponse)
def rebuild_document(
    document_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    pg_db: Session = Depends(get_pg_db),
    current_user: User = Depends(get_current_user),
):
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete chunks from PostgreSQL
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()

    doc.parse_status = "pending"
    doc.vector_status = "pending"
    doc.error_message = None
    mysql_db.commit()

    doc_queue.enqueue(process_document, doc.id)

    return DocumentStatusResponse(
        id=doc.id,
        parse_status="pending",
        vector_status="pending",
    )
