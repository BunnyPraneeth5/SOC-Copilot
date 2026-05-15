"""Tests for ReputationAgent — AbuseIPDB and VirusTotal lookups.

All httpx calls are mocked so tests run without network access or API
keys.  Tests cover success, HTTP errors (404, 429), missing API keys,
and partial failures.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from soc_copilot.mcp.exceptions import AgentLookupError, APIKeyMissingError
from soc_copilot.mcp.models import (
    AbuseIPDBResult,
    AgentResult,
    AgentStatus,
    ReputationResult,
    VirusTotalResult,
)
from soc_copilot.mcp.reputation_agent import ReputationAgent


# ------------------------------------------------------------------ #
# Fixtures & constants
# ------------------------------------------------------------------ #

TARGET_IP = "198.51.100.42"

FAKE_ABUSEIPDB_RESPONSE = {
    "data": {
        "ipAddress": TARGET_IP,
        "abuseConfidenceScore": 87,
        "totalReports": 154,
        "usageType": "Data Center/Web Hosting/Transit",
        "isp": "Example Hosting Inc.",
        "isWhitelisted": False,
        "domain": "example-hosting.com",
    }
}

FAKE_VIRUSTOTAL_RESPONSE = {
    "data": {
        "id": TARGET_IP,
        "attributes": {
            "last_analysis_stats": {
                "malicious": 12,
                "suspicious": 3,
                "harmless": 65,
                "undetected": 10,
            }
        },
    }
}


@pytest.fixture
def agent() -> ReputationAgent:
    return ReputationAgent(timeout=5.0)


@pytest.fixture
def env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set both API keys in the environment for tests that need them."""
    monkeypatch.setenv("ABUSEIPDB_API_KEY", "test-abuse-key-12345")
    monkeypatch.setenv("VIRUSTOTAL_API_KEY", "test-vt-key-67890")
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")


def _mock_httpx_client(response_json: dict, status_code: int = 200) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns a canned response."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    mock_resp.json.return_value = response_json

    if status_code >= 400:
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}",
            request=MagicMock(),
            response=mock_resp,
        )
    else:
        mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ------------------------------------------------------------------ #
# AbuseIPDB unit tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_abuseipdb_lookup_success(
    agent: ReputationAgent, env_keys: None
) -> None:
    """Successful AbuseIPDB lookup returns populated AbuseIPDBResult."""
    mock_client = _mock_httpx_client(FAKE_ABUSEIPDB_RESPONSE)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        result = await agent._abuseipdb_lookup(TARGET_IP)

    assert isinstance(result, AbuseIPDBResult)
    assert result.confidence_score == 87
    assert result.total_reports == 154
    assert result.usage_type == "Data Center/Web Hosting/Transit"
    assert result.isp == "Example Hosting Inc."


@pytest.mark.asyncio
async def test_abuseipdb_missing_api_key(agent: ReputationAgent, monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ABUSEIPDB_API_KEY raises APIKeyMissingError."""
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")
    monkeypatch.delenv("ABUSEIPDB_API_KEY", raising=False)

    with pytest.raises(APIKeyMissingError, match="ABUSEIPDB_API_KEY"):
        await agent._abuseipdb_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_abuseipdb_http_429_rate_limit(
    agent: ReputationAgent, env_keys: None
) -> None:
    """AbuseIPDB returns 429 → AgentLookupError."""
    mock_client = _mock_httpx_client({}, status_code=429)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AgentLookupError, match="HTTP 429"):
            await agent._abuseipdb_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_abuseipdb_http_404_not_found(
    agent: ReputationAgent, env_keys: None
) -> None:
    """AbuseIPDB returns 404 → AgentLookupError."""
    mock_client = _mock_httpx_client({}, status_code=404)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AgentLookupError, match="HTTP 404"):
            await agent._abuseipdb_lookup(TARGET_IP)


# ------------------------------------------------------------------ #
# VirusTotal unit tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_virustotal_lookup_success(
    agent: ReputationAgent, env_keys: None
) -> None:
    """Successful VirusTotal lookup returns populated VirusTotalResult."""
    mock_client = _mock_httpx_client(FAKE_VIRUSTOTAL_RESPONSE)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        result = await agent._virustotal_lookup(TARGET_IP)

    assert isinstance(result, VirusTotalResult)
    assert result.malicious == 12
    assert result.suspicious == 3
    assert result.harmless == 65
    assert result.undetected == 10
    # detection_ratio = (12 + 3) / (12 + 3 + 65 + 10) = 15/90
    assert abs(result.detection_ratio - 0.1667) < 0.001


@pytest.mark.asyncio
async def test_virustotal_missing_api_key(
    agent: ReputationAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing VIRUSTOTAL_API_KEY raises APIKeyMissingError."""
    monkeypatch.delenv("VIRUSTOTAL_API_KEY", raising=False)

    with pytest.raises(APIKeyMissingError, match="VIRUSTOTAL_API_KEY"):
        await agent._virustotal_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_virustotal_http_429_rate_limit(
    agent: ReputationAgent, env_keys: None
) -> None:
    """VirusTotal returns 429 → AgentLookupError."""
    mock_client = _mock_httpx_client({}, status_code=429)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AgentLookupError, match="HTTP 429"):
            await agent._virustotal_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_virustotal_http_404_not_found(
    agent: ReputationAgent, env_keys: None
) -> None:
    """VirusTotal returns 404 → AgentLookupError."""
    mock_client = _mock_httpx_client({}, status_code=404)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(AgentLookupError, match="HTTP 404"):
            await agent._virustotal_lookup(TARGET_IP)


# ------------------------------------------------------------------ #
# execute() integration tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_execute_both_succeed(
    agent: ReputationAgent, env_keys: None
) -> None:
    """Both APIs succeed → AgentStatus.SUCCESS with full ReputationResult."""
    abuse_client = _mock_httpx_client(FAKE_ABUSEIPDB_RESPONSE)
    vt_client = _mock_httpx_client(FAKE_VIRUSTOTAL_RESPONSE)

    # We need to return different clients for the two calls
    call_count = 0

    def _client_factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return abuse_client
        return vt_client

    with patch(
        "soc_copilot.mcp.reputation_agent.httpx.AsyncClient",
        side_effect=_client_factory,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.SUCCESS
    assert result.error is None
    assert isinstance(result.data, ReputationResult)
    assert result.data.ip == TARGET_IP
    assert result.data.abuseipdb.confidence_score == 87
    assert result.data.virustotal.malicious == 12


@pytest.mark.asyncio
async def test_execute_partial_failure_abuseipdb_down(
    agent: ReputationAgent, env_keys: None
) -> None:
    """AbuseIPDB fails, VT succeeds → AgentStatus.PARTIAL."""
    abuse_client = _mock_httpx_client({}, status_code=500)
    vt_client = _mock_httpx_client(FAKE_VIRUSTOTAL_RESPONSE)

    call_count = 0

    def _client_factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return abuse_client
        return vt_client

    with patch(
        "soc_copilot.mcp.reputation_agent.httpx.AsyncClient",
        side_effect=_client_factory,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.PARTIAL
    assert "AbuseIPDB" in result.error
    assert isinstance(result.data, ReputationResult)
    # AbuseIPDB defaults
    assert result.data.abuseipdb.confidence_score == 0
    # VT populated
    assert result.data.virustotal.malicious == 12


@pytest.mark.asyncio
async def test_execute_partial_failure_virustotal_down(
    agent: ReputationAgent, env_keys: None
) -> None:
    """VT fails, AbuseIPDB succeeds → AgentStatus.PARTIAL."""
    abuse_client = _mock_httpx_client(FAKE_ABUSEIPDB_RESPONSE)
    vt_client = _mock_httpx_client({}, status_code=503)

    call_count = 0

    def _client_factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return abuse_client
        return vt_client

    with patch(
        "soc_copilot.mcp.reputation_agent.httpx.AsyncClient",
        side_effect=_client_factory,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.PARTIAL
    assert "VirusTotal" in result.error
    assert result.data.abuseipdb.confidence_score == 87
    assert result.data.virustotal.malicious == 0  # default


@pytest.mark.asyncio
async def test_execute_both_fail(
    agent: ReputationAgent, env_keys: None
) -> None:
    """Both APIs fail → AgentStatus.FAILED."""
    failing_client = _mock_httpx_client({}, status_code=500)

    with patch(
        "soc_copilot.mcp.reputation_agent.httpx.AsyncClient",
        return_value=failing_client,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "AbuseIPDB" in result.error
    assert "VirusTotal" in result.error
    assert isinstance(result.data, ReputationResult)


@pytest.mark.asyncio
async def test_execute_missing_both_keys(
    agent: ReputationAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both API keys missing → AgentStatus.FAILED (both raise APIKeyMissingError)."""
    monkeypatch.delenv("ABUSEIPDB_API_KEY", raising=False)
    monkeypatch.delenv("VIRUSTOTAL_API_KEY", raising=False)
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "ABUSEIPDB_API_KEY" in result.error
    assert "VIRUSTOTAL_API_KEY" in result.error


@pytest.mark.asyncio
async def test_execute_zero_detections(
    agent: ReputationAgent, env_keys: None
) -> None:
    """IP with zero detections → detection_ratio is 0.0."""
    clean_vt = {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 0,
                    "suspicious": 0,
                    "harmless": 80,
                    "undetected": 5,
                }
            }
        }
    }
    abuse_client = _mock_httpx_client(FAKE_ABUSEIPDB_RESPONSE)
    vt_client = _mock_httpx_client(clean_vt)

    call_count = 0

    def _client_factory(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return abuse_client
        return vt_client

    with patch(
        "soc_copilot.mcp.reputation_agent.httpx.AsyncClient",
        side_effect=_client_factory,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.SUCCESS
    assert result.data.virustotal.detection_ratio == 0.0
    assert result.data.virustotal.harmless == 80


@pytest.mark.asyncio
async def test_execute_online_enrichment_disabled_by_default(
    agent: ReputationAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default offline mode blocks external reputation calls."""
    monkeypatch.delenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", raising=False)

    with patch("soc_copilot.mcp.reputation_agent.httpx.AsyncClient") as mock_client:
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "Online enrichment is disabled" in result.error
    mock_client.assert_not_called()
