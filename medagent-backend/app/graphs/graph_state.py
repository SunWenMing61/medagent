from typing import Dict, List, Optional, Any


class MedAgentState:
    """State object for the MedAgent multi-agent workflow."""

    def __init__(
        self,
        question: str = "",
        user_id: int = 0,
        session_id: int = 0,
        kb_ids: Optional[List[int]] = None,
        kb_name_map: Optional[Dict[int, str]] = None,
        history_messages: Optional[List[dict]] = None,
        question_type: str = "unknown",
        retrieved_chunks: Optional[List[dict]] = None,
        references: Optional[List[dict]] = None,
        per_kb_chunks: Optional[Dict[int, List[dict]]] = None,
        sub_answers: Optional[List[dict]] = None,
        raw_answer: str = "",
        safe_answer: str = "",
        safety_flag: Optional[str] = None,
        final_response: str = "",
        attachments: Optional[List[dict]] = None,
        web_search_enabled: bool = False,
        web_search_results: Optional[List[dict]] = None,
        deep_thinking_enabled: bool = False,
        thinking_content: str = "",
    ):
        self.question = question
        self.user_id = user_id
        self.session_id = session_id
        self.kb_ids = kb_ids or []
        self.kb_name_map = kb_name_map or {}
        self.history_messages = history_messages or []
        self.question_type = question_type
        self.retrieved_chunks = retrieved_chunks or []
        self.references = references or []
        self.per_kb_chunks = per_kb_chunks or {}
        self.sub_answers = sub_answers or []
        self.raw_answer = raw_answer
        self.safe_answer = safe_answer
        self.safety_flag = safety_flag
        self.final_response = final_response
        self.attachments = attachments or []
        self.web_search_enabled = web_search_enabled
        self.web_search_results = web_search_results or []
        self.deep_thinking_enabled = deep_thinking_enabled
        self.thinking_content = thinking_content

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "kb_ids": self.kb_ids,
            "kb_name_map": self.kb_name_map,
            "question_type": self.question_type,
            "retrieved_chunks": self.retrieved_chunks,
            "references": self.references,
            "sub_answers": self.sub_answers,
            "raw_answer": self.raw_answer,
            "safe_answer": self.safe_answer,
            "safety_flag": self.safety_flag,
            "final_response": self.final_response,
        }

    def get_kb_name(self, kb_id: int) -> str:
        """Resolve KB name from kb_name_map, falling back to a generic label."""
        return self.kb_name_map.get(kb_id, f"知识库 #{kb_id}")

    def get_kb_name(self, kb_id: int) -> str:
        """Resolve KB name from kb_name_map, falling back to a generic label."""
        return self.kb_name_map.get(kb_id, f"知识库 #{kb_id}")
