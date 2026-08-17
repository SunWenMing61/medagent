"""Query understanding subgraph; planning output contains no tool results."""

from langgraph.graph import END, START, StateGraph

from app.agents.retrieval_planner_agent import retrieval_planner_agent
from app.agents.schemas import InputTriageResult
from app.graphs.graph_state import AgentGraphState
from app.core.config import settings
from app.db.session import MySQLSessionLocal
from app.services.memory_service import agent_memory_service, session_memory_service


def build_query_understanding_subgraph(runtime):
    def planner_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        triage = InputTriageResult.model_validate(updated["triage_result"])
        session_context = {
            "active_topic": updated.get("active_topic"),
            "active_entities": updated.get("active_entities", []),
            "rolling_summary": updated.get("conversation_summary", ""),
        }
        memory_context = list(updated.get("memory_context", []))
        if (
            settings.ENABLE_NEW_MEMORY_ARCHITECTURE
            and settings.MEMORY_ENABLED
            and updated.get("persistent_memory_enabled", True)
            and getattr(runtime, "persist", False)
        ):
            db = MySQLSessionLocal()
            try:
                session = session_memory_service.get(
                    db, tenant_id=updated["tenant_id"], user_id=updated["user_id"],
                    thread_id=updated["thread_id"],
                )
                if session:
                    session_context = session.model_dump(mode="json")
                    updated["conversation_summary"] = session.rolling_summary
                    updated["active_topic"] = session.active_topic
                    updated["active_entities"] = [item.model_dump(mode="json") for item in session.active_entities]
                    updated["unresolved_questions"] = [item.model_dump(mode="json") for item in session.unresolved_questions]
                    updated["confirmed_constraints"] = session.confirmed_constraints
                memories, _ = agent_memory_service.retrieve(
                    db, tenant_id=updated["tenant_id"], user_id=updated["user_id"],
                    query=updated["raw_query"], agent_name="query_understanding",
                    memory_types={"semantic"}, request_id=updated["request_id"],
                )
                memory_context = [item.model_dump(mode="json") for item in memories]
                updated["memory_context"] = memory_context
                episodes = agent_memory_service.retrieve_episodes(
                    db, tenant_id=updated["tenant_id"], user_id=updated["user_id"],
                    query=updated["raw_query"], agent_name="query_understanding",
                    task_type=triage.intent, limit=3,
                )
                procedures = agent_memory_service.retrieve_procedures(
                    db, tenant_id=updated["tenant_id"], agent_name="query_understanding",
                    task_type=triage.intent, limit=3,
                )
                updated["episodic_context"] = [item.model_dump(mode="json") for item in episodes]
                updated["procedural_context"] = [item.model_dump(mode="json") for item in procedures]
                db.commit()
            except Exception as exc:
                db.rollback()
                updated.setdefault("errors", []).append({
                    "agent_name": "query_understanding", "error_code": "MEMORY_RETRIEVAL_ERROR",
                    "message": str(exc)[:500], "retryable": True,
                })
            finally:
                db.close()
        result = runtime.run_agent(
            updated, "retrieval_planner", retrieval_planner_agent.run,
            updated["raw_query"], triage, session_context, memory_context,
        )
        updated["retrieval_plan"] = result.model_dump(mode="json")
        updated["normalized_query"] = result.normalized_query
        updated["standalone_query"] = result.standalone_query or result.normalized_query
        updated["medical_entities"] = [item.model_dump(mode="json") for item in result.entities]
        updated["numeric_constraints"] = result.numeric_constraints
        updated["population_constraints"] = result.population_constraints
        updated["time_constraints"] = result.time_constraints
        updated["negations"] = result.negations
        updated["sub_questions"] = result.sub_questions
        updated["current_agent"] = "query_understanding"
        updated.setdefault("completed_agents", []).append("retrieval_planner")
        runtime.public_event(updated, "retrieval_planned", {"routes": result.retrieval_routes})
        runtime.checkpoint(updated, "query_understanding")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("retrieval_planner_agent", planner_node)
    graph.add_edge(START, "retrieval_planner_agent")
    graph.add_edge("retrieval_planner_agent", END)
    return graph.compile()
