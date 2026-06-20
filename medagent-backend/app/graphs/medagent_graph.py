from typing import Dict, List, Optional, Generator

from app.graphs.graph_state import MedAgentState
from app.graphs.nodes import (
    classify_question_node,
    sub_agent_retrieve_node,
    sub_agent_generate_and_aggregate,
    safety_check_node,
    format_response_node,
)


class MedAgentWorkflow:
    """
    MedAgent multi-agent workflow orchestrator.

    Pipeline:
      1. Classify question (or skip if force_type is set)
      2. Per-KB retrieval — each KB searched independently
      3. Per-KB sub-agent generation (parallel) + main aggregator
      4. Safety check
      5. Format response with per-KB references
    """

    def __init__(self):
        pass

    def run(
        self,
        question: str,
        user_id: int = 0,
        session_id: int = 0,
        kb_ids: Optional[List[int]] = None,
        kb_name_map: Optional[Dict[int, str]] = None,
        history_messages: Optional[List[dict]] = None,
        force_type: Optional[str] = None,
        attachments: Optional[List[dict]] = None,
        web_search_enabled: bool = False,
        deep_thinking_enabled: bool = False,
    ) -> dict:
        """
        Run the full multi-agent workflow.

        Args:
            question: User's question
            user_id: User ID
            session_id: Chat session ID
            kb_ids: Knowledge base IDs to search
            kb_name_map: Mapping from kb_id to human-readable name
            history_messages: Previous chat messages for context
            force_type: Force question type (skip classification)
            attachments: Optional list of file attachments (images/docs)
            web_search_enabled: Whether to augment with web search results
            deep_thinking_enabled: Whether to generate step-by-step reasoning before answer

        Returns:
            Dict with final_response, references, safety_flag
        """
        state = MedAgentState(
            question=question,
            user_id=user_id,
            session_id=session_id,
            kb_ids=kb_ids or [],
            kb_name_map=kb_name_map or {},
            history_messages=history_messages or [],
            attachments=attachments or [],
            web_search_enabled=web_search_enabled,
            deep_thinking_enabled=deep_thinking_enabled,
        )

        # Step 1: Classify question (unless forced)
        if force_type:
            state.question_type = force_type
        else:
            state = self._run_node(classify_question_node, state, "classify")

        # Step 2: Per-KB retrieval (multi-agent)
        state = self._run_node(sub_agent_retrieve_node, state, "retrieve")

        # Step 3: Sub-agent generation + main-aggregator (multi-agent)
        state = self._run_node(sub_agent_generate_and_aggregate, state, "generate")

        # Step 4: Safety check
        state = self._run_node(safety_check_node, state, "safety")

        # Step 5: Format response
        state = self._run_node(format_response_node, state, "format")

        return state.to_dict()

    def _run_node(self, node_func, state: MedAgentState, node_name: str) -> MedAgentState:
        """Execute a single node with error handling."""
        try:
            return node_func(state)
        except Exception as e:
            state.safety_flag = f"error_{node_name}"
            state.final_response = (
                f"I encountered an error during the {node_name} step. "
                f"Please try again or contact support. Error: {str(e)}"
            )
            return state
