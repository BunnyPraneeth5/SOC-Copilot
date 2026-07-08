"""Tests for the MCP ThreatReport cache wrapper."""

from __future__ import annotations

import time

import pytest

from soc_copilot.mcp.cache import MCPCache
from soc_copilot.mcp.models import ThreatReport, ThreatSeverity


def _report(target: str = "Example.COM") -> ThreatReport:
    return ThreatReport(
        target=target,
        severity=ThreatSeverity.HIGH,
        summary="Suspicious reputation and exposed services.",
        recommendations=["Review recent traffic."],
        llm_model="mock-model",
    )


def test_key_for_target_uses_normalized_target_prefix() -> None:
    assert MCPCache.key_for_target(" Example.COM ") == "target:example.com"


def test_key_for_target_rejects_empty_target() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        MCPCache.key_for_target("  ")


def test_set_and_get_report_round_trips_copy(tmp_path) -> None:
    cache = MCPCache(tmp_path)
    report = _report()

    cache.set_report(" example.com ", report)
    cached = cache.get_report("EXAMPLE.COM")

    assert cached == report
    assert cached is not report

    cached.summary = "mutated locally"
    assert cache.get_report("example.com").summary == report.summary

    cache.close()


def test_stale_report_behaves_like_cache_miss(tmp_path) -> None:
    cache = MCPCache(tmp_path)
    cache.set_report("example.com", _report(), ttl=1)

    assert cache.get_report("example.com") is not None

    time.sleep(1.1)

    assert cache.get_report("example.com") is None
    cache.close()
