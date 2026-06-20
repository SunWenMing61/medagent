from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any


class SourceCreateRequest(BaseModel):
    kb_id: int = Field(..., description="Knowledge base ID")
    source_type: str = Field(..., description="Source type: pubmed, msd_manual, drug_label")
    name: str = Field(..., min_length=1, max_length=255, description="Display name")
    config: dict = Field(default_factory=dict, description="Adapter-specific configuration")


class SourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    config: Optional[dict] = None
    kb_id: Optional[int] = Field(None, description="New knowledge base ID to associate with")


class SourceResponse(BaseModel):
    id: int
    kb_id: int
    source_type: str
    name: str
    config: str
    sync_status: str
    document_count: int = 0
    last_sync_at: Optional[datetime] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SourceStatusResponse(BaseModel):
    id: int
    sync_status: str
    last_sync_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SourceSyncResponse(BaseModel):
    source_id: int
    sync_status: str = "syncing"
    message: str = "同步已启动"


class SourceSchemaResponse(BaseModel):
    source_type: str
    display_name: str
    config_schema: dict
    defaults: dict

    class Config:
        populate_by_name = True
        # schema_extra / json_schema_extra is not needed; "schema" is fine in JSON
