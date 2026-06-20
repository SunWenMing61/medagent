from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DocumentResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    parse_status: str
    vector_status: str
    uploader_id: int
    source_id: Optional[int] = None
    source_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentPreviewResponse(BaseModel):
    filename: str
    file_type: str
    content: str
    total_length: int


class DocumentStatusResponse(BaseModel):
    id: int
    parse_status: str
    vector_status: str
    error_message: Optional[str] = None
