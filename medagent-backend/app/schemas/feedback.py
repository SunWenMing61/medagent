from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class FeedbackRequest(BaseModel):
    message_id: int
    feedback_type: str = Field(..., pattern=r"^(like|dislike|none)$")
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    user_id: int
    message_id: int
    feedback_type: str
    comment: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
