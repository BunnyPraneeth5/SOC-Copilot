"""Persistent cache helpers for MCP investigation reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from diskcache import Cache

from soc_copilot.mcp.models import ThreatReport


class MCPCache:
    """Small typed wrapper around diskcache for ThreatReport entries."""

    def __init__(
        self,
        cache_dir: str | Path = ".cache/mcp",
        *,
        default_ttl: int = 21_600,
    ) -> None:
        self.default_ttl = default_ttl
        self._cache = Cache(str(cache_dir))

    @staticmethod
    def normalize_target(target: str) -> str:
        """Normalize investigation targets before cache-key generation."""
        normalized = target.strip().lower()
        if not normalized:
            raise ValueError("Cache target must not be empty")
        return normalized

    @classmethod
    def key_for_target(cls, target: str) -> str:
        """Return the stable cache key for an investigation target."""
        return f"target:{cls.normalize_target(target)}"

    def get_report(self, target: str) -> ThreatReport | None:
        """Return a cached ThreatReport for target, if present and valid."""
        cached = self._cache.get(self.key_for_target(target))
        if cached is None:
            return None
        if isinstance(cached, ThreatReport):
            return cached.model_copy(deep=True)
        if isinstance(cached, dict):
            return ThreatReport.model_validate(cached)
        raise TypeError(f"Unexpected cached report type: {type(cached).__name__}")

    def set_report(
        self,
        target: str,
        report: ThreatReport,
        *,
        ttl: int | None = None,
    ) -> None:
        """Cache a successful ThreatReport for target."""
        self._cache.set(
            self.key_for_target(target),
            report.model_dump(mode="json"),
            expire=self.default_ttl if ttl is None else ttl,
        )

    def close(self) -> None:
        """Close the underlying diskcache handle."""
        self._cache.close()

    def __enter__(self) -> MCPCache:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
