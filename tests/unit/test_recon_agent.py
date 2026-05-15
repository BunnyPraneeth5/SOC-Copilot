"""Tests for ReconAgent — WHOIS, reverse DNS, ASN, and geo-IP lookups.

All external calls (ipwhois, socket, httpx) are mocked so tests run
without network access.
"""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    AsnInfo,
    DnsInfo,
    GeoInfo,
    ReconResult,
    WhoisInfo,
)
from soc_copilot.mcp.recon_agent import ReconAgent


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def agent() -> ReconAgent:
    return ReconAgent(timeout=5.0)


@pytest.fixture
def online_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")


TARGET_IP = "8.8.8.8"

FAKE_RDAP = {
    "asn": "15169",
    "asn_description": "GOOGLE",
    "asn_cidr": "8.8.8.0/24",
    "asn_country_code": "US",
    "network": {
        "name": "GOGL",
        "country": "US",
        "remarks": [{"description": "Google LLC"}],
    },
}

FAKE_GEOIP_JSON = {
    "status": "success",
    "country": "United States",
    "countryCode": "US",
    "regionName": "Virginia",
    "city": "Ashburn",
    "lat": 39.0438,
    "lon": -77.4874,
    "isp": "Google LLC",
    "org": "Google Public DNS",
}


# ------------------------------------------------------------------ #
# Happy-path tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_successful_full_recon(agent: ReconAgent, online_enabled: None) -> None:
    """All four lookups succeed → AgentStatus.SUCCESS."""
    with (
        patch("soc_copilot.mcp.recon_agent.IPWhois") as mock_ipwhois,
        patch("soc_copilot.mcp.recon_agent.socket.gethostbyaddr") as mock_dns,
        patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_httpx_cls,
    ):
        # ipwhois mock (used by both whois and asn)
        mock_obj = MagicMock()
        mock_obj.lookup_rdap.return_value = FAKE_RDAP
        mock_ipwhois.return_value = mock_obj

        # reverse DNS
        mock_dns.return_value = ("dns.google", [], ["8.8.8.8"])

        # httpx geo-IP
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = FAKE_GEOIP_JSON
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.SUCCESS
    assert result.error is None
    assert isinstance(result.data, ReconResult)
    assert result.data.ip == TARGET_IP
    assert result.data.dns.hostname == "dns.google"
    assert result.data.geo.city == "Ashburn"
    assert result.data.asn.asn == "15169"


@pytest.mark.asyncio
async def test_whois_lookup_success(agent: ReconAgent) -> None:
    """_whois_lookup returns WhoisInfo on success."""
    with patch("soc_copilot.mcp.recon_agent.IPWhois") as mock_ipwhois:
        mock_obj = MagicMock()
        mock_obj.lookup_rdap.return_value = FAKE_RDAP
        mock_ipwhois.return_value = mock_obj

        info = await agent._whois_lookup(TARGET_IP)

    assert isinstance(info, WhoisInfo)
    assert info.country == "US"
    assert info.org == "GOGL"


@pytest.mark.asyncio
async def test_reverse_dns_success(agent: ReconAgent) -> None:
    """_reverse_dns returns DnsInfo on success."""
    with patch(
        "soc_copilot.mcp.recon_agent.socket.gethostbyaddr",
        return_value=("dns.google", ["dns.google.com"], ["8.8.8.8"]),
    ):
        info = await agent._reverse_dns(TARGET_IP)

    assert isinstance(info, DnsInfo)
    assert info.hostname == "dns.google"
    assert "dns.google.com" in info.aliases


@pytest.mark.asyncio
async def test_geoip_lookup_success(agent: ReconAgent) -> None:
    """_geoip_lookup returns GeoInfo on success."""
    with patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_cls:
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_GEOIP_JSON
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        info = await agent._geoip_lookup(TARGET_IP)

    assert isinstance(info, GeoInfo)
    assert info.country == "United States"
    assert info.latitude == 39.0438


# ------------------------------------------------------------------ #
# Error-handling tests
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_geoip_lookup_http_error(agent: ReconAgent) -> None:
    """_geoip_lookup raises AgentLookupError on HTTP 500."""
    with patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_cls:
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_resp
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client

        from soc_copilot.mcp.exceptions import AgentLookupError

        with pytest.raises(AgentLookupError, match="GeoIP"):
            await agent._geoip_lookup(TARGET_IP)


@pytest.mark.asyncio
async def test_partial_failure(agent: ReconAgent, online_enabled: None) -> None:
    """One lookup fails → AgentStatus.PARTIAL with partial data."""
    with (
        patch("soc_copilot.mcp.recon_agent.IPWhois") as mock_ipwhois,
        patch("soc_copilot.mcp.recon_agent.socket.gethostbyaddr") as mock_dns,
        patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_obj = MagicMock()
        mock_obj.lookup_rdap.return_value = FAKE_RDAP
        mock_ipwhois.return_value = mock_obj

        # DNS fails
        mock_dns.side_effect = socket.herror("Host not found")

        # GeoIP succeeds
        mock_resp = MagicMock()
        mock_resp.json.return_value = FAKE_GEOIP_JSON
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.PARTIAL
    assert result.data is not None
    assert result.data.geo.city == "Ashburn"  # geo succeeded
    assert result.data.dns.hostname is None   # dns failed → default
    assert "DNS" in result.error


@pytest.mark.asyncio
async def test_all_lookups_fail(agent: ReconAgent, online_enabled: None) -> None:
    """All lookups raise → AgentStatus.FAILED."""
    with (
        patch("soc_copilot.mcp.recon_agent.IPWhois") as mock_ipwhois,
        patch("soc_copilot.mcp.recon_agent.socket.gethostbyaddr") as mock_dns,
        patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_obj = MagicMock()
        mock_obj.lookup_rdap.side_effect = Exception("RDAP down")
        mock_ipwhois.return_value = mock_obj

        mock_dns.side_effect = socket.herror("Host not found")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "fail", request=MagicMock(), response=mock_resp
        )
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.error is not None


@pytest.mark.asyncio
async def test_timeout_handling(agent: ReconAgent) -> None:
    """safe_execute returns TIMEOUT when the agent exceeds its deadline."""
    agent.timeout = 0.1  # very short

    async def _slow_execute(target: str) -> AgentResult:
        await asyncio.sleep(5)
        return AgentResult(
            agent_name="ReconAgent", status=AgentStatus.SUCCESS
        )

    with patch.object(agent, "execute", side_effect=_slow_execute):
        result = await agent.safe_execute(TARGET_IP)

    assert result.status == AgentStatus.TIMEOUT
    assert "Timed out" in result.error


@pytest.mark.asyncio
async def test_invalid_ip_format(agent: ReconAgent, online_enabled: None) -> None:
    """Non-IP string triggers failures in lookups → FAILED status."""
    with (
        patch("soc_copilot.mcp.recon_agent.IPWhois") as mock_ipwhois,
        patch("soc_copilot.mcp.recon_agent.socket.gethostbyaddr") as mock_dns,
        patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_httpx_cls,
    ):
        mock_ipwhois.side_effect = ValueError("Invalid IP")
        mock_dns.side_effect = socket.herror("not an IP")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "fail", "message": "invalid query"}
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_httpx_cls.return_value = mock_client

        result = await agent.execute("not-an-ip")

    assert result.status == AgentStatus.FAILED


@pytest.mark.asyncio
async def test_execute_online_enrichment_disabled_by_default(
    agent: ReconAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default offline mode blocks external recon calls."""
    monkeypatch.delenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", raising=False)

    with patch("soc_copilot.mcp.recon_agent.httpx.AsyncClient") as mock_client:
        result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert "Online enrichment is disabled" in result.error
    mock_client.assert_not_called()
