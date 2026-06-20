from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    status: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None


class AdminUserStatusRequest(BaseModel):
    status: int
