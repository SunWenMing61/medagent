from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str = Field(default="general", pattern=r"^(general|drug|paper|chat_history)$")
    visibility: str = Field(default="private", pattern=r"^(private|public)$")


class KBUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    visibility: Optional[str] = None


class KBResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    type: str
    owner_id: int
    visibility: str
    status: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
