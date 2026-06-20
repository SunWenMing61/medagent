from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.user import User
from app.models.feedback import Feedback
from app.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.schemas.common import MessageResponse

router = APIRouter()


@router.post("", response_model=MessageResponse)
def submit_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    fb = Feedback(
        user_id=current_user.id,
        message_id=req.message_id,
        feedback_type=req.feedback_type,
        comment=req.comment,
    )
    db.add(fb)
    db.commit()
    return {"message": "Feedback submitted"}
