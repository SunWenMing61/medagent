from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    kb_ids: Optional[List[int]] = None
    session_id: Optional[int] = None
    web_search_enabled: bool = False
    deep_thinking_enabled: bool = False


class AskResponse(BaseModel):
    session_id: int
    question: str
    answer: str
    references: Optional[List[dict]] = None
    safety_flag: Optional[str] = None
    disclaimer: Optional[str] = None


class SessionResponse(BaseModel):
    id: int
    user_id: int
    title: Optional[str] = None
    session_type: str
    summary: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    kb_ids: Optional[List[int]] = None

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    references_json: Optional[Any] = None
    safety_flag: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: List[MessageResponse]
