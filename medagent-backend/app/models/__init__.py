# Import all models so Alembic can discover their metadata.
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback
from app.models.answer_preference import AnswerPreference, UserAnswerPreferenceProfile
from app.models.system_log import SystemLog
from app.models.model_config import ModelConfig
from app.models.knowledge_graph import GraphEntity, GraphRelation
from app.models.task_outbox import TaskOutbox
from app.models.agent_runtime import (
    AgentRun, AgentStep, AgentToolCall, AgentCheckpoint, HumanReview,
)
from app.models.document_processing import (
    DocumentPage, DocumentRawBlock, DocumentCleanBlock, DocumentTable,
    DocumentQualityReportRecord, DocumentCleaningActionRecord,
)
from app.models.tool_runtime import (
    ToolCatalog, ToolCallRecord, ToolHealthRecord, ToolErrorRecord, ToolPolicyAudit,
)
from app.models.memory import (
    AgentSession, AgentMemory, AgentEpisode, AgentProcedure, AgentMemoryAudit,
    UserMemorySetting, MemoryRetrievalTrace, RetrievalTrace, WorkflowCheckpoint,
)
from app.models.evaluation import (
    EvalDataset, EvalCase, EvalRun, EvalCaseResult, EvalMetricResult, EvaluationTrace,
    EvalDatasetVersion, EvaluationCandidate, DatasetChangeLog,
)

__all__ = [
    "User", "KnowledgeBase", "Document", "DocumentChunk",
    "ChatSession", "ChatMessage", "Feedback", "AnswerPreference", "UserAnswerPreferenceProfile", "SystemLog", "ModelConfig",
    "GraphEntity", "GraphRelation",
    "TaskOutbox",
    "AgentRun", "AgentStep", "AgentToolCall", "AgentCheckpoint", "HumanReview",
    "DocumentPage", "DocumentRawBlock", "DocumentCleanBlock", "DocumentTable",
    "DocumentQualityReportRecord", "DocumentCleaningActionRecord",
    "ToolCatalog", "ToolCallRecord", "ToolHealthRecord", "ToolErrorRecord", "ToolPolicyAudit",
    "AgentSession", "AgentMemory", "AgentEpisode", "AgentProcedure", "AgentMemoryAudit",
    "UserMemorySetting", "MemoryRetrievalTrace", "RetrievalTrace", "WorkflowCheckpoint",
    "EvalDataset", "EvalCase", "EvalRun", "EvalCaseResult", "EvalMetricResult", "EvaluationTrace",
    "EvalDatasetVersion", "EvaluationCandidate", "DatasetChangeLog",
]
