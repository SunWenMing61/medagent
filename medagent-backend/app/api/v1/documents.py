# 导入操作系统模块，用于文件和路径操作
import os
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
from app.schemas.document import DocumentResponse, DocumentStatusResponse, DocumentPreviewResponse
# 导入文档处理任务和任务队列
from app.tasks.document_tasks import process_document, doc_queue

# 创建文档路由实例
router = APIRouter()

# 允许上传的文件扩展名集合
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


def _doc_to_response(doc: Document) -> DocumentResponse:
    """将 Document ORM 模型转换为 DocumentResponse 响应模型。"""
    return DocumentResponse(
        id=doc.id,                       # 文档 ID
        kb_id=doc.kb_id,                 # 所属知识库 ID
        filename=doc.filename,           # 文件名
        file_type=doc.file_type,         # 文件类型（pdf/docx/txt/md）
        file_size=doc.file_size or 0,    # 文件大小（字节），默认为 0
        parse_status=doc.parse_status,   # 解析状态
        vector_status=doc.vector_status, # 向量化状态
        uploader_id=doc.uploader_id,     # 上传者 ID
        source_id=doc.source_id,         # 来源 ID（在线知识源同步时使用）
        source_url=doc.source_url,       # 来源 URL
        error_message=doc.error_message, # 错误信息
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

    # 读取上传文件内容
    content = await file.read()
    file_size = len(content)
    # 检查文件大小是否超过最大限制
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(status_code=400, detail="File too large")

    # 将文件内容写入磁盘
    with open(file_path, "wb") as f:
        f.write(content)

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
    )
    mysql_db.add(doc)
    mysql_db.commit()
    mysql_db.refresh(doc)  # 刷新以获取数据库生成的 ID

    # 将文档处理任务加入后台任务队列（异步解析 + 向量化）
    doc_queue.enqueue(process_document, doc.id)

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
    query = mysql_db.query(Document)
    if kb_id:
        # 如果传入了知识库 ID，按知识库过滤
        query = query.filter(Document.kb_id == kb_id)
    if current_user.role != "admin":
        # 非管理员只能看到自己上传的文档 + 系统同步的来源文档（uploader_id == 0 表示系统自动同步）
        query = query.filter(
            (Document.uploader_id == current_user.id) |
            (Document.uploader_id == 0)
        )
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
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
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
    # 返回包含解析状态、向量化状态和错误信息的状态响应
    return DocumentStatusResponse(
        id=doc.id,
        parse_status=doc.parse_status,
        vector_status=doc.vector_status,
        error_message=doc.error_message,
    )


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
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

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
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
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
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

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


# 重建文档处理接口：POST /api/documents/{document_id}/rebuild
@router.post("/{document_id}/rebuild", response_model=DocumentStatusResponse)
def rebuild_document(
    document_id: int,                             # 文档 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    pg_db: Session = Depends(get_pg_db),          # PostgreSQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 查询文档
    doc = mysql_db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 权限检查
    if doc.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # 删除 PostgreSQL 中该文档的所有向量切片（旧数据）
    pg_db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    pg_db.commit()

    # 重置文档的解析和向量化状态为待处理
    doc.parse_status = "pending"
    doc.vector_status = "pending"
    doc.error_message = None  # 清除之前的错误信息
    mysql_db.commit()

    # 重新将文档加入处理队列
    doc_queue.enqueue(process_document, doc.id)

    # 返回新的状态
    return DocumentStatusResponse(
        id=doc.id,
        parse_status="pending",
        vector_status="pending",
    )
