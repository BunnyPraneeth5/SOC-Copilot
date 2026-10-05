"""Provider registry — status and connectivity checks for threat-intel providers.

``get_provider_statuses()`` is purely local (env inspection only, no
network). ``check_connectivity()`` probes each usable provider's host
concurrently; probes never send API keys or investigated targets.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, replace
from enum import Enum

import httpx

from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.report_agent import resolve_report_llm_settings
from soc_copilot.security.network import online_enrichment_enabled

_PROBE_TTL_SECONDS = 60


class ProviderState(str, Enum):
    """Live status of an external provider."""

    CONFIGURED = "Configured"  # key present (or no key needed), not probed
    AVAILABLE = "Available"  # connectivity probe succeeded
    MISSING_KEY = "Missing key"
    OFFLINE = "Offline"  # probe failed
    DISABLED = "Disabled"  # online enrichment off


@dataclass(frozen=True)
class ProviderStatus:
    """Status of one external threat-intelligence provider."""

    key: str  # "whois" | "geoip" | "abuseipdb" | "virustotal" | "shodan" | "report_llm"
    display_name: str
    agent: str  # "ReconAgent" | "ReputationAgent" | "ShodanAgent" | "ReportAgent"
    state: ProviderState
    detail: str = ""

    @property
    def usable(self) -> bool:
        return self.state in (ProviderState.CONFIGURED, ProviderState.AVAILABLE)


_STATIC_PROBE_URLS = {
    "whois": "https://rdap.arin.net/registry/",
    "geoip": "https://ipwho.is/",
    "abuseipdb": "https://api.abuseipdb.com/",
    "virustotal": "https://www.virustotal.com/",
    "shodan": "https://api.shodan.io/",
}


def _key_state(env_var: str, key: str) -> tuple[ProviderState, str]:
    """CONFIGURED if env var is set, else MISSING_KEY with detail."""
    if os.environ.get(env_var):
        return ProviderState.CONFIGURED, ""
    return ProviderState.MISSING_KEY, f"{env_var} not set"


def get_provider_statuses() -> list[ProviderStatus]:
    """Return local provider statuses (env inspection only, no network)."""
    if not online_enrichment_enabled():
        return [
            ProviderStatus("whois", "WHOIS (RDAP)", "ReconAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
            ProviderStatus("geoip", "GeoIP (ipwho.is)", "ReconAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
            ProviderStatus("abuseipdb", "AbuseIPDB", "ReputationAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
            ProviderStatus("virustotal", "VirusTotal", "ReputationAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
            ProviderStatus("shodan", "Shodan", "ShodanAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
            ProviderStatus("report_llm", "Report LLM", "ReportAgent",
                           ProviderState.DISABLED, "Enrichment disabled"),
        ]

    statuses: list[ProviderStatus] = [
        ProviderStatus("whois", "WHOIS (RDAP)", "ReconAgent",
                       ProviderState.CONFIGURED, "rdap.arin.net, no key required"),
        ProviderStatus("geoip", "GeoIP (ipwho.is)", "ReconAgent",
                       ProviderState.CONFIGURED, "ipwho.is, no key required"),
    ]

    for key, display, env_var in (
        ("abuseipdb", "AbuseIPDB", "ABUSEIPDB_API_KEY"),
        ("virustotal", "VirusTotal", "VIRUSTOTAL_API_KEY"),
        ("shodan", "Shodan", "SHODAN_API_KEY"),
    ):
        state, detail = _key_state(env_var, key)
        agent = "ShodanAgent" if key == "shodan" else "ReputationAgent"
        statuses.append(ProviderStatus(key, display, agent, state, detail))

    try:
        settings = resolve_report_llm_settings()
    except AgentLookupError as exc:
        statuses.append(
            ProviderStatus(
                "report_llm", "Report LLM", "ReportAgent",
                ProviderState.MISSING_KEY, str(exc),
            )
        )
    else:
        api_key_env = settings.api_key_env
        model = os.environ.get(settings.model_env, settings.default_model)
        if os.environ.get(api_key_env):
            statuses.append(
                ProviderStatus(
                    "report_llm", "Report LLM", "ReportAgent",
                    ProviderState.CONFIGURED,
                    f"{settings.provider} ({model})",
                )
            )
        else:
            statuses.append(
                ProviderStatus(
                    "report_llm", "Report LLM", "ReportAgent",
                    ProviderState.MISSING_KEY,
                    f"{api_key_env} not set ({settings.provider})",
                )
            )

    return statuses


_probe_cache: list[ProviderStatus] | None = None
_probe_cache_at: float = 0.0


def clear_cache() -> None:
    """Reset the connectivity probe cache (mainly for tests)."""
    global _probe_cache, _probe_cache_at
    _probe_cache = None
    _probe_cache_at = 0.0


def _probe_url(status: ProviderStatus) -> str | None:
    """Return the connectivity probe URL for a provider (no key/target sent)."""
    if status.key == "report_llm":
        try:
            return resolve_report_llm_settings().base_url
        except AgentLookupError:
            return None
    return _STATIC_PROBE_URLS.get(status.key)


async def check_connectivity(timeout: float = 3.0) -> list[ProviderStatus]:
    """Probe each usable provider's host concurrently.

    Results are cached for ``_PROBE_TTL_SECONDS``. DISABLED/MISSING_KEY
    providers are returned unchanged and never probed.
    """
    global _probe_cache, _probe_cache_at

    now = time.monotonic()
    if _probe_cache is not None and now - _probe_cache_at < _PROBE_TTL_SECONDS:
        return _probe_cache

    statuses = get_provider_statuses()
    usable = [s for s in statuses if s.usable]

    async def _probe(status: ProviderStatus) -> ProviderStatus:
        url = _probe_url(status)
        if not url:
            return status
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                await client.get(url)
            # Any HTTP response means the host is reachable.
            return replace(status, state=ProviderState.AVAILABLE)
        except httpx.HTTPError as exc:
            return replace(
                status,
                state=ProviderState.OFFLINE,
                detail=f"{type(exc).__name__}: {exc}"[:200],
            )

    probed = {s.key: s for s in await asyncio.gather(*(_probe(s) for s in usable))}
    result = [probed.get(s.key, s) for s in statuses]

    _probe_cache = result
    _probe_cache_at = now
    return result
