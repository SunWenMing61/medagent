"""Administrator view of governed tool metadata and live health."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import require_admin
from app.models.user import User
from app.tools.health import tool_health_manager
from app.tools.registry import tool_registry


router = APIRouter()


@router.get("")
def list_tools(_admin: User = Depends(require_admin)):
    return [{
        "name": item.name,
        "version": item.version,
        "description": item.description,
        "category": item.category,
        "enabled": tool_registry.is_enabled(item.name),
        "read_only": item.read_only,
        "risk_level": item.risk_level,
        "allowed_agents": sorted(item.allowed_agents),
        "required_scopes": sorted(item.required_scopes),
        "timeout_seconds": item.timeout_seconds,
        "max_retries": item.max_retries,
        "max_calls_per_run": item.max_calls_per_run,
        "cache_ttl_seconds": item.cache_ttl_seconds,
        "health": tool_health_manager.status(item.name).model_dump(mode="json"),
    } for item in tool_registry.definitions(include_disabled=True)]


@router.post("/{tool_name}/enabled")
def set_tool_enabled(tool_name: str, enabled: bool, _admin: User = Depends(require_admin)):
    try:
        tool_registry.set_enabled(tool_name, enabled)
        tool_health_manager.disable(tool_name, not enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Tool not found") from exc
    return {"tool_name": tool_name, "enabled": enabled}
