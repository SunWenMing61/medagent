"""Deterministic minimal-team task planning for controlled multi-agent runs."""

from __future__ import annotations


def build_minimal_task_graph(state: dict) -> list[dict]:
    """Plan only the specialist stages required by the current shared state."""
    tasks: list[dict] = []

    def add(task_id: str, agent: str, depends_on: list[str] | None = None) -> None:
        tasks.append({"id": task_id, "agent": agent, "depends_on": list(depends_on or [])})

    add("T1", "input_safety")
    add("T2", "input_triage", ["T1"])
    intent = state.get("intent", "unknown")
    if state.get("need_emergency_response") or intent == "out_of_scope":
        add("T3", "finalize", ["T2"])
        return tasks
    if state.get("need_clarification"):
        add("T3", "medical_clarification", ["T2"])
        return tasks
    if intent == "general_knowledge":
        add("T3", "answer_generator_concise", ["T2"])
        add("T4", "output_safety", ["T3"])
        add("T5", "finalize", ["T4"])
        return tasks
    add("T3", "retrieval_planner", ["T2"])
    add("T4", "retrieval_subgraph", ["T3"])
    add("T5", "evidence_verifier", ["T4"])
    style = state.get("answer_style_preference", "concise_evidence")
    add("T6", "answer_generator_detailed" if style == "detailed_guidance" else "answer_generator_concise", ["T5"])
    add("T7", "output_safety", ["T6"])
    add("T8", "finalize", ["T7"])
    return tasks


def update_task_progress(state: dict) -> None:
    completed_agents = set(state.get("completed_agents", []))
    aliases = {
        "input_safety": {"input_safety_rules"},
        "input_triage": {"input_triage"},
        "retrieval_subgraph": {"retrieval_subgraph"},
        "medical_clarification": {"medical_clarification"},
    }
    completed: list[str] = []
    remaining: list[str] = []
    for task in state.get("task_graph", []):
        names = aliases.get(task["agent"], {task["agent"]})
        (completed if names & completed_agents else remaining).append(task["id"])
    state["completed_tasks"] = completed
    state["remaining_tasks"] = remaining
