from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_mysql_db, get_pg_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.knowledge_base import KBCreateRequest, KBUpdateRequest, KBResponse

router = APIRouter()


def _kb_to_response(kb: KnowledgeBase) -> KBResponse:
    return KBResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description,
        type=kb.type,
        owner_id=kb.owner_id,
        visibility=kb.visibility,
        status=kb.status,
        created_at=kb.created_at,
        updated_at=kb.updated_at,
    )


@router.post("", response_model=KBResponse)
def create_kb(
    req: KBCreateRequest,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    kb = KnowledgeBase(
        name=req.name,
        description=req.description or "",
        type=req.type,
        owner_id=current_user.id,
        visibility=req.visibility,
        status=1,
    )
    mysql_db.add(kb)
    mysql_db.commit()
    mysql_db.refresh(kb)
    return _kb_to_response(kb)


@router.get("", response_model=List[KBResponse])
def list_kb(
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "admin":
        kbs = mysql_db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | (KnowledgeBase.visibility == "public")
        ).all()
    else:
        kbs = mysql_db.query(KnowledgeBase).filter(
            (KnowledgeBase.owner_id == current_user.id)
            | ((KnowledgeBase.visibility == "public") & (KnowledgeBase.status == 1))
        ).all()
    return [_kb_to_response(kb) for kb in kbs]


@router.get("/{kb_id}", response_model=KBResponse)
def get_kb(
    kb_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if kb.owner_id != current_user.id and kb.visibility != "public" and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return _kb_to_response(kb)


@router.put("/{kb_id}", response_model=KBResponse)
def update_kb(
    kb_id: int,
    req: KBUpdateRequest,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if kb.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if req.name:
        kb.name = req.name
    if req.description:
        kb.description = req.description
    if req.type:
        kb.type = req.type
    if req.visibility:
        kb.visibility = req.visibility
    mysql_db.commit()
    mysql_db.refresh(kb)
    return _kb_to_response(kb)


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    pg_db: Session = Depends(get_pg_db),
    current_user: User = Depends(get_current_user),
):
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if kb.type == "chat_history":
        raise HTTPException(status_code=400, detail="对话历史知识库不可删除")
    if kb.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete chunks from PostgreSQL
    pg_db.query(DocumentChunk).filter(DocumentChunk.kb_id == kb_id).delete()
    pg_db.commit()

    # Delete related documents and KB from MySQL
    mysql_db.query(Document).filter(Document.kb_id == kb_id).delete()
    mysql_db.delete(kb)
    mysql_db.commit()
    return {"message": "Knowledge base deleted"}
