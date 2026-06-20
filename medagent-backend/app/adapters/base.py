"""Base adapter interface for online knowledge sources."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional
from datetime import datetime


@dataclass
class SourceDocument:
    """Represents a single piece of content fetched from an online source.

    This is the universal data structure returned by all adapters.
    The SourceService consumes these and stores them as Documents + Chunks.
    """
    title: str
    content: str
    source_url: str = ""
    source_id_field: str = ""
    authors: list = field(default_factory=list)
    publication_date: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)


class BaseSourceAdapter(ABC):
    """Abstract base class for online source adapters.

    Each adapter implements fetching logic for one type of online source
    (e.g. PubMed, MSD Manuals, Drug Label API).
    """

    source_type: str = ""
    display_name: str = ""

    @abstractmethod
    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        """Validate adapter configuration.

        Returns (is_valid, error_message).
        """
        ...

    @abstractmethod
    def get_config_schema(self) -> dict:
        """Return JSON Schema describing the expected config structure.

        Used by the frontend to render dynamic configuration forms.
        Must include at least: type, properties, required.
        """
        ...

    @abstractmethod
    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """Fetch content from the online source.

        Yields SourceDocument objects asynchronously.
        Must handle rate limiting internally.
        """
        ...

        # To make Python < 3.12 happy with empty abstract generator:
        if False:  # pragma: no cover
            yield

    def get_default_config(self) -> dict:
        """Return default configuration values."""
        return {}
