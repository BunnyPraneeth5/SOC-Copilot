"""Tests for ShodanAgent host intelligence lookup.

All httpx calls are mocked so tests run without network access or API
keys. Tests cover success, empty host data, HTTP errors, missing API key,
and offline enrichment mode.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from soc_copilot.mcp.exceptions import AgentLookupError, APIKeyMissingError
from soc_copilot.mcp.models import AgentStatus, ShodanResult
from soc_copilot.mcp.shodan_agent import ShodanAgent


TARGET_IP = "198.51.100.42"

FAKE_SHODAN_RESPONSE = {
    "ip_str": TARGET_IP,
    "ports": [22, 443],
    "os": "Linux",
    "hostnames": ["example-host.example"],
    "data": [
        {
            "port": 22,
            "transport": "tcp",
            "product": "OpenSSH",
            "version": "8.9p1",
            "data": "SSH-2.0-OpenSSH_8.9p1",
            "vulns": {"CVE-2023-38408": {"verified": True}},
        },
        {
            "port": 443,
            "transport": "tcp",
            "product": "nginx",
            "title": "Example HTTPS",
            "vulns": ["CVE-2021-23017"],
        },
    ],
}


@pytest.fixture
def agent() -> ShodanAgent:
    return ShodanAgent(timeout=5.0)


@pytest.fixture
def env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHODAN_API_KEY", "test-shodan-key-12345")
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


@pytest.mark.asyncio
async def test_shodan_lookup_success(agent: ShodanAgent, env_key: None) -> None:
    """Successful Shodan lookup returns parsed ShodanResult."""
    mock_client = _mock_httpx_client(FAKE_SHODAN_RESPONSE)

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await agent._shodan_lookup(TARGET_IP)

    assert isinstance(result, ShodanResult)
    assert result.ip == TARGET_IP
    assert result.open_ports == [22, 443]
    assert result.os == "Linux"
    assert result.hostnames == ["example-host.example"]
    assert result.cves == ["CVE-2021-23017", "CVE-2023-38408"]
    assert result.services[0]["product"] == "OpenSSH"


@pytest.mark.asyncio
async def test_shodan_lookup_empty_host_data(
    agent: ShodanAgent, env_key: None
) -> None:
    """Empty data arrays produce clean defaults, not parser failures."""
    mock_client = _mock_httpx_client({"data": [], "ports": []})

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await agent._shodan_lookup(TARGET_IP)

    assert result == ShodanResult(ip=TARGET_IP)


@pytest.mark.asyncio
async def test_shodan_missing_api_key(
    agent: ShodanAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing SHODAN_API_KEY raises APIKeyMissingError."""
    monkeypatch.delenv("SHODAN_API_KEY", raising=False)

    with pytest.raises(APIKeyMissingError, match="SHODAN_API_KEY"):
        await agent._shodan_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_shodan_http_429_rate_limit(
    agent: ShodanAgent, env_key: None
) -> None:
    """Shodan returns 429 -> AgentLookupError with rate limit context."""
    mock_client = _mock_httpx_client({}, status_code=429)

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(AgentLookupError, match="HTTP 429 rate limit"):
            await agent._shodan_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_shodan_http_404_not_found(
    agent: ShodanAgent, env_key: None
) -> None:
    """Shodan returns 404 -> AgentLookupError."""
    mock_client = _mock_httpx_client({}, status_code=404)

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        with pytest.raises(AgentLookupError, match="HTTP 404"):
            await agent._shodan_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_execute_success(agent: ShodanAgent, env_key: None) -> None:
    """Successful Shodan API lookup returns AgentStatus.SUCCESS."""
    mock_client = _mock_httpx_client(FAKE_SHODAN_RESPONSE)

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.SUCCESS
    assert result.error is None
    assert isinstance(result.data, ShodanResult)
    assert result.data.open_ports == [22, 443]


@pytest.mark.asyncio
async def test_execute_failure(agent: ShodanAgent, env_key: None) -> None:
    """Failed Shodan API lookup returns AgentStatus.FAILED with default data."""
    mock_client = _mock_httpx_client({}, status_code=500)

    with patch(
        "soc_copilot.mcp.shodan_agent.httpx.AsyncClient",
        return_value=mock_client,
    ):
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "Shodan" in result.error
    assert isinstance(result.data, ShodanResult)
    assert result.data == ShodanResult(ip=TARGET_IP)


@pytest.mark.asyncio
async def test_execute_online_enrichment_disabled_by_default(
    agent: ShodanAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default offline mode blocks external Shodan calls."""
    monkeypatch.delenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", raising=False)

    with patch("soc_copilot.mcp.shodan_agent.httpx.AsyncClient") as mock_client:
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "Online enrichment is disabled" in result.error
    mock_client.assert_not_called()
