# 从 FastAPI 导入路由、依赖注入、HTTP 异常
from fastapi import APIRouter, Depends, HTTPException
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session
# 导入类型提示：列表
from typing import List

# 导入获取当前用户和管理员权限验证的依赖函数
from app.core.dependencies import get_current_user, require_admin
# 导入数据库会话工厂（MySQL 和 PostgreSQL）
from app.db.session import get_mysql_db, get_pg_db
# 导入用户模型
from app.models.user import User
# 导入知识库模型
from app.models.knowledge_base import KnowledgeBase
# 导入文档模型
from app.models.document import Document
# 导入文档块（切片）模型
from app.models.document_chunk import DocumentChunk
# 导入知识库相关的 Pydantic 请求/响应模型
from app.schemas.knowledge_base import KBCreateRequest, KBUpdateRequest, KBResponse

# 创建知识库路由实例
router = APIRouter()


def _kb_to_response(kb: KnowledgeBase) -> KBResponse:
    """将 KnowledgeBase ORM 模型转换为 KBResponse 响应模型。"""
    return KBResponse(
        id=kb.id,                       # 知识库 ID
        name=kb.name,                   # 知识库名称
        description=kb.description,     # 知识库描述
        type=kb.type,                   # 知识库类型（general/drug/paper 等）
        owner_id=kb.owner_id,           # 拥有者用户 ID
        visibility=kb.visibility,        # 可见性（public/private）
        status=kb.status,               # 状态（1=启用，0=禁用）
        created_at=kb.created_at,       # 创建时间
        updated_at=kb.updated_at,       # 更新时间
    )


# 创建知识库接口：POST /api/kb，返回 KBResponse 类型
@router.post("", response_model=KBResponse)
def create_kb(
    req: KBCreateRequest,                         # 创建请求体（名称、描述、类型、可见性）
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 创建知识库对象
    kb = KnowledgeBase(
        tenant_id=getattr(current_user, "tenant_id", 1),
        name=req.name,                           # 知识库名称
        description=req.description or "",       # 描述，可选，默认为空
        type=req.type,                           # 类型
        owner_id=current_user.id,                # 拥有者为当前用户
        visibility=req.visibility,               # 可见性
        status=1,                                # 初始状态为启用
    )
    # 保存到数据库
    mysql_db.add(kb)
    mysql_db.commit()
    mysql_db.refresh(kb)
    # 返回创建的知识库信息
    return _kb_to_response(kb)


# 获取知识库列表接口：GET /api/kb，返回 KBResponse 列表
@router.get("", response_model=List[KBResponse])
def list_kb(
    mysql_db: Session = Depends(get_mysql_db),    # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    if current_user.role == "admin":
        # 管理员可以看到：自己拥有的 + 所有公开的知识库
        kbs = mysql_db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | (KnowledgeBase.visibility == "public")
        ).all()
    else:
        # 普通用户可以看到：自己拥有的 + 公开且启用的知识库
        kbs = mysql_db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1))
        ).all()
    # 将 ORM 对象列表转换为响应模型列表
    return [_kb_to_response(kb) for kb in kbs]


# 获取单个知识库详情接口：GET /api/kb/{kb_id}
@router.get("/{kb_id}", response_model=KBResponse)
def get_kb(
    kb_id: int,                                       # 知识库 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),         # MySQL 数据库会话
    current_user: User = Depends(get_current_user),    # 当前已认证用户
):
    # 按 ID 查询知识库
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    # 权限检查：知识库必须属于当前用户，或者是公开的，或者当前用户是管理员
    if kb.owner_id != current_user.id and kb.visibility != "public" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return _kb_to_response(kb)


# 更新知识库接口：PUT /api/kb/{kb_id}
@router.put("/{kb_id}", response_model=KBResponse)
def update_kb(
    kb_id: int,                                       # 知识库 ID（路径参数）
    req: KBUpdateRequest,                             # 更新请求体（可选字段）
    mysql_db: Session = Depends(get_mysql_db),         # MySQL 数据库会话
    current_user: User = Depends(get_current_user),    # 当前已认证用户
):
    # 查询知识库
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    # 权限检查：只有知识库拥有者或管理员可以更新
    if kb.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    # 逐个字段更新（只更新请求中提供的字段）
    if req.name:
        kb.name = req.name
    if req.description:
        kb.description = req.description
    if req.type:
        kb.type = req.type
    if req.visibility:
        kb.visibility = req.visibility
    # 提交更改
    mysql_db.commit()
    mysql_db.refresh(kb)
    return _kb_to_response(kb)


# 删除知识库接口：DELETE /api/kb/{kb_id}
@router.delete("/{kb_id}")
def delete_kb(
    kb_id: int,                                       # 知识库 ID（路径参数）
    mysql_db: Session = Depends(get_mysql_db),         # MySQL 数据库会话
    pg_db: Session = Depends(get_pg_db),               # PostgreSQL 数据库会话
    current_user: User = Depends(get_current_user),    # 当前已认证用户
):
    # 查询知识库
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    # 权限检查：只有知识库拥有者或管理员可以删除
    if kb.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # 从 PostgreSQL 中删除该知识库关联的所有向量切片
    pg_db.query(DocumentChunk).filter(DocumentChunk.kb_id == kb_id).delete()
    pg_db.commit()

    # 从 MySQL 中删除该知识库关联的所有文档记录
    mysql_db.query(Document).filter(Document.kb_id == kb_id).delete()
    # 删除知识库本身
    mysql_db.delete(kb)
    mysql_db.commit()
    return {"message": "Knowledge base deleted"}
