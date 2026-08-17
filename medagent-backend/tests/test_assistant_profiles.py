from app.services.assistant_profile_service import assistant_profile_service
from app.graphs.graph_state import new_agent_state


def test_general_and_memory_assistants_have_distinct_memory_policies():
    general = assistant_profile_service.get("general_qa")
    memory = assistant_profile_service.get("memory_qa")
    assert not general.session_memory_enabled
    assert general.auto_web_search is True
    assert memory.session_memory_enabled
    assert memory.auto_web_search is False
    state = new_agent_state(
        raw_query="继续上轮咨询", user_id=1, tenant_id=1, authorized_kb_ids=[7],
        assistant_profile=general.profile_id, persistent_memory_enabled=general.session_memory_enabled,
    )
    assert state["assistant_profile"] == "general_qa"
    assert state["persistent_memory_enabled"] is False
