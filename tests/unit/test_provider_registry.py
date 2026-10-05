"""Tests for the MCP provider registry and provider-aware dispatch."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import replace
from unittest.mock import Mock

import httpx
import pytest

from soc_copilot.mcp import provider_registry
from soc_copilot.mcp.provider_registry import (
    ProviderState,
    ProviderStatus,
    check_connectivity,
    clear_cache,
    get_provider_statuses,
)

_ALL_ENV_VARS = (
    "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT",
    "ABUSEIPDB_API_KEY",
    "VIRUSTOTAL_API_KEY",
    "SHODAN_API_KEY",
    "NVIDIA_API_KEY",
    "OPENROUTER_API_KEY",
    "REPORT_LLM_PROVIDER",
    "NVIDIA_NIM_BASE_URL",
    "OPENROUTER_BASE_URL",
    "NVIDIA_NIM_MODEL",
    "OPENROUTER_MODEL",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """Isolate provider env state; also reset the probe cache."""
    for var in _ALL_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    clear_cache()
    yield
    clear_cache()


def _by_key(statuses: list[ProviderStatus]) -> dict[str, ProviderStatus]:
    return {s.key: s for s in statuses}


# ---------------------------------------------------------------------------
# get_provider_statuses (local, no network)
# ---------------------------------------------------------------------------

def test_all_disabled_when_enrichment_off():
    statuses = get_provider_statuses()
    assert len(statuses) == 6
    assert all(s.state is ProviderState.DISABLED for s in statuses)
    assert all(not s.usable for s in statuses)


def test_missing_keys_when_enrichment_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    statuses = _by_key(get_provider_statuses())

    assert statuses["whois"].state is ProviderState.CONFIGURED
    assert statuses["geoip"].state is ProviderState.CONFIGURED
    for key, env in (
        ("abuseipdb", "ABUSEIPDB_API_KEY"),
        ("virustotal", "VIRUSTOTAL_API_KEY"),
        ("shodan", "SHODAN_API_KEY"),
        ("report_llm", "NVIDIA_API_KEY"),
    ):
        assert statuses[key].state is ProviderState.MISSING_KEY
        assert env in statuses[key].detail


def test_keys_set_are_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    for env in ("ABUSEIPDB_API_KEY", "VIRUSTOTAL_API_KEY",
                "SHODAN_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.setenv(env, "test-key")
    statuses = _by_key(get_provider_statuses())

    assert all(s.state is ProviderState.CONFIGURED for s in statuses.values())
    assert "nvidia_nim" in statuses["report_llm"].detail
    assert "meta/llama-3.1-8b-instruct" in statuses["report_llm"].detail


def test_openrouter_provider_uses_its_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    monkeypatch.setenv("REPORT_LLM_PROVIDER", "openrouter")
    statuses = _by_key(get_provider_statuses())
    assert statuses["report_llm"].state is ProviderState.MISSING_KEY
    assert "OPENROUTER_API_KEY" in statuses["report_llm"].detail

    monkeypatch.setenv("OPENROUTER_API_KEY", "key")
    statuses = _by_key(get_provider_statuses())
    assert statuses["report_llm"].state is ProviderState.CONFIGURED
    assert "openrouter" in statuses["report_llm"].detail


def test_unsupported_report_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    monkeypatch.setenv("REPORT_LLM_PROVIDER", "bogus")
    statuses = _by_key(get_provider_statuses())
    assert statuses["report_llm"].state is ProviderState.MISSING_KEY
    assert "Unsupported REPORT_LLM_PROVIDER 'bogus'" in statuses["report_llm"].detail


# ---------------------------------------------------------------------------
# check_connectivity (probing, mocked httpx)
# ---------------------------------------------------------------------------

class _FakeResponse:
    status_code = 200


class _FakeClient:
    """httpx.AsyncClient double recording probe URLs."""

    calls: list[str] = []
    fail_urls: set[str] = set()

    def __init__(self, timeout=None, **kwargs):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url: str, **kwargs):
        self.calls.append(url)
        if url in self.fail_urls:
            raise httpx.ConnectError("connection refused")
        return _FakeResponse()


@pytest.fixture(autouse=True)
def _fake_httpx(monkeypatch: pytest.MonkeyPatch):
    _FakeClient.calls = []
    _FakeClient.fail_urls = set()
    monkeypatch.setattr(
        provider_registry.httpx, "AsyncClient", _FakeClient
    )


def _set_all_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    for env in ("ABUSEIPDB_API_KEY", "VIRUSTOTAL_API_KEY",
                "SHODAN_API_KEY", "NVIDIA_API_KEY"):
        monkeypatch.setenv(env, "sekret-" + env.lower())


@pytest.mark.asyncio
async def test_connectivity_marks_available_and_offline(monkeypatch):
    _set_all_keys(monkeypatch)
    _FakeClient.fail_urls = {"https://api.shodan.io/"}

    statuses = _by_key(await check_connectivity())

    assert statuses["shodan"].state is ProviderState.OFFLINE
    assert "ConnectError" in statuses["shodan"].detail
    assert statuses["abuseipdb"].state is ProviderState.AVAILABLE
    assert statuses["whois"].state is ProviderState.AVAILABLE
    # Report LLM probed at its resolved base URL
    assert "https://integrate.api.nvidia.com/v1" in _FakeClient.calls
    # Six usable providers were probed
    assert len(_FakeClient.calls) == 6
    # No API key value ever left the process
    for url in _FakeClient.calls:
        assert "sekret-" not in url


@pytest.mark.asyncio
async def test_missing_key_providers_never_probed(monkeypatch):
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    # Only whois/geoip are usable (no keys needed)

    statuses = _by_key(await check_connectivity())

    assert statuses["whois"].state is ProviderState.AVAILABLE
    assert statuses["geoip"].state is ProviderState.AVAILABLE
    assert statuses["shodan"].state is ProviderState.MISSING_KEY
    assert sorted(_FakeClient.calls) == sorted(
        ["https://rdap.arin.net/registry/", "https://ipwho.is/"]
    )


@pytest.mark.asyncio
async def test_probe_cache_ttl_and_clear(monkeypatch):
    _set_all_keys(monkeypatch)

    await check_connectivity()
    first_call_count = len(_FakeClient.calls)
    await check_connectivity()
    assert len(_FakeClient.calls) == first_call_count  # cached, no new probes

    clear_cache()
    await check_connectivity()
    assert len(_FakeClient.calls) == first_call_count * 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_providers_lists_all(monkeypatch, capsys, tmp_path):
    from soc_copilot import cli

    # cmd_providers loads <cwd>/.env — run from a dir with no .env so the
    # real repo .env can't leak keys into os.environ.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["cli", "providers"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    for name in ("WHOIS", "GeoIP", "AbuseIPDB", "VirusTotal", "Shodan",
                 "Report LLM"):
        assert name in out
    assert "Disabled" in out


def test_cli_providers_reads_dotenv(monkeypatch, capsys, tmp_path):
    """`providers` picks up keys from .env in the current directory."""
    from soc_copilot import cli

    (tmp_path / ".env").write_text(
        "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true\n"
        "SHODAN_API_KEY=x\n"
    )
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["cli", "providers"])
    try:
        assert cli.main() == 0
    finally:
        # load_dotenv wrote these directly to os.environ
        monkeypatch.delenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", raising=False)
        monkeypatch.delenv("SHODAN_API_KEY", raising=False)

    out = capsys.readouterr().out
    shodan_line = next(
        line for line in out.splitlines() if line.startswith("Shodan")
    )
    assert "Configured" in shodan_line


# ---------------------------------------------------------------------------
# ConfigPanel provider indicators (offscreen Qt)
# ---------------------------------------------------------------------------

class TestConfigPanelProviders:
    """ConfigPanel builds a StatusIndicator per provider."""

    def _statuses(self, state: ProviderState, detail: str = ""):
        return [
            ProviderStatus("whois", "WHOIS (RDAP)", "ReconAgent", state, detail),
            ProviderStatus("geoip", "GeoIP (ipwho.is)", "ReconAgent", state, detail),
            ProviderStatus("abuseipdb", "AbuseIPDB", "ReputationAgent", state, detail),
            ProviderStatus("virustotal", "VirusTotal", "ReputationAgent", state, detail),
            ProviderStatus("shodan", "Shodan", "ShodanAgent", state, detail),
            ProviderStatus("report_llm", "Report LLM", "ReportAgent", state, detail),
        ]

    def test_indicators_built_per_provider(self, qapp, tmp_path):
        from soc_copilot.phase4.ui.config_panel import ConfigPanel

        bridge = Mock()
        bridge.get_stats.return_value = {}
        bridge.get_provider_statuses.return_value = self._statuses(
            ProviderState.CONFIGURED
        )

        panel = ConfigPanel(bridge=bridge, project_root=tmp_path)

        assert len(panel._provider_indicators) == 6
        indicator = panel._provider_indicators["shodan"]
        assert "Configured" in indicator.status_label.text()
        assert panel.check_providers_button.isEnabled()

    def test_button_disabled_when_all_disabled(self, qapp, tmp_path):
        from soc_copilot.phase4.ui.config_panel import ConfigPanel

        bridge = Mock()
        bridge.get_stats.return_value = {}
        bridge.get_provider_statuses.return_value = self._statuses(
            ProviderState.DISABLED, "Enrichment disabled"
        )

        panel = ConfigPanel(bridge=bridge, project_root=tmp_path)

        assert not panel.check_providers_button.isEnabled()
        assert "online enrichment" in panel.check_providers_button.toolTip()
        indicator = panel._provider_indicators["abuseipdb"]
        assert "Disabled" in indicator.status_label.text()
