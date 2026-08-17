# 从 FastAPI 导入路由、依赖注入
from fastapi import APIRouter, Depends, HTTPException
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session

# 导入获取当前用户的依赖函数
from app.core.dependencies import get_current_user
# 导入 MySQL 数据库会话获取函数
from app.db.session import get_mysql_db
# 导入用户模型
from app.models.user import User
# 导入反馈模型
from app.models.feedback import Feedback
# 导入反馈相关的 Pydantic 请求/响应模型
from app.schemas.feedback import (
    AnswerPreferenceRequest, AnswerPreferenceResponse, FeedbackRequest, FeedbackResponse,
)
# 导入通用消息响应模型
from app.schemas.common import MessageResponse
from app.services.answer_preference_service import answer_preference_service

# 创建反馈路由实例
router = APIRouter()


def _tenant(user: User) -> int:
    return int(getattr(user, "tenant_id", 1) or 1)


# 提交反馈接口：POST /api/feedback，返回 MessageResponse 类型
@router.post("", response_model=MessageResponse)
def submit_feedback(
    req: FeedbackRequest,                         # 反馈请求体（包含消息 ID、反馈类型、评论）
    db: Session = Depends(get_mysql_db),          # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 创建反馈记录对象
    fb = Feedback(
        user_id=current_user.id,   # 反馈用户 ID（当前登录用户）
        message_id=req.message_id, # 关联的消息 ID（用户对哪条消息进行反馈）
        feedback_type=req.feedback_type,  # 反馈类型（如 thumbs_up/thumbs_down）
        comment=req.comment,       # 用户评论内容（可选）
    )
    # 将反馈记录添加到数据库
    db.add(fb)
    # 提交事务
    db.commit()
    # 返回提交成功的消息
    return {"message": "Feedback submitted"}


@router.post("/preference", response_model=AnswerPreferenceResponse)
def choose_answer_variant(
    req: AnswerPreferenceRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    try:
        result = answer_preference_service.record_choice(
            db,
            tenant_id=_tenant(current_user),
            user_id=current_user.id,
            message_id=req.message_id,
            chosen_variant_id=req.chosen_variant_id,
        )
        db.commit()
        return result
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/preference/profile")
def get_answer_preference_profile(
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    return answer_preference_service.get_profile(
        db, tenant_id=_tenant(current_user), user_id=current_user.id,
    )
