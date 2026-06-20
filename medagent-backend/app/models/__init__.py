# Import all models so Alembic and create_all can discover them.
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback
from app.models.system_log import SystemLog
from app.models.model_config import ModelConfig
from app.models.knowledge_source import KnowledgeSource

__all__ = [
    "User", "KnowledgeBase", "Document", "DocumentChunk",
    "ChatSession", "ChatMessage", "Feedback", "SystemLog", "ModelConfig",
    "KnowledgeSource",
]
