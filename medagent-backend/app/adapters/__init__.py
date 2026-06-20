"""Adapter registry for online knowledge sources."""
from typing import Optional

_registry: dict[str, type["BaseSourceAdapter"]] = {}


def register_adapter(adapter_cls: type["BaseSourceAdapter"]) -> None:
    """Register an adapter class by its source_type."""
    _registry[adapter_cls.source_type] = adapter_cls


def get_adapter(source_type: str) -> "BaseSourceAdapter":
    """Get an adapter instance by source_type."""
    cls = _registry.get(source_type)
    if not cls:
        raise ValueError(f"Unknown source type: '{source_type}'. Available: {list(_registry.keys())}")
    return cls()


def list_adapter_types() -> list[dict]:
    """List all registered adapter types."""
    return [
        {"source_type": cls.source_type, "display_name": cls.display_name}
        for cls in _registry.values()
    ]


def get_config_schema(source_type: str) -> Optional[dict]:
    """Get the config JSON Schema for a given source type."""
    try:
        return get_adapter(source_type).get_config_schema()
    except ValueError:
        return None


# Import adapters to trigger registration
from app.adapters.pubmed import PubMedAdapter          # noqa: E402, F811
from app.adapters.msd_manual import MSDManualAdapter   # noqa: E402, F811
from app.adapters.drug_label import DrugLabelAdapter    # noqa: E402, F811
