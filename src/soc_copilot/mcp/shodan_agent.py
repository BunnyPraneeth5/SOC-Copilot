"""ShodanAgent - Open ports, service banners, and known CVEs.

Queries the Shodan API for host intelligence including open ports,
running services, operating system detection, and associated CVEs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
import structlog

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.exceptions import AgentLookupError, APIKeyMissingError
from soc_copilot.mcp.models import AgentResult, AgentStatus, ShodanResult
from soc_copilot.security.network import online_enrichment_enabled


log = structlog.get_logger(__name__)

_SHODAN_URL = "https://api.shodan.io/shodan/host/{ip}"


class ShodanAgent(BaseAgent):
    """Host intelligence agent backed by the Shodan API.

    Requires the ``SHODAN_API_KEY`` environment variable.

    Attributes:
        name:    ``"ShodanAgent"``
        timeout: Per-agent deadline in seconds (default 10 s).
    """

    name: str = "ShodanAgent"
    timeout: float = 10.0

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Individual lookup
    # ------------------------------------------------------------------ #

    async def _shodan_lookup(self, ip: str) -> ShodanResult:
        """Query Shodan host intelligence for an IP address.

        GET https://api.shodan.io/shodan/host/{ip}
            params: key={SHODAN_API_KEY}

        Returns:
            ShodanResult with open ports, normalized service banners,
            CVE identifiers, OS, and hostnames.

        Raises:
            APIKeyMissingError: If ``SHODAN_API_KEY`` is not set.
            AgentLookupError: On HTTP or API errors.
        """
        api_key = os.environ.get("SHODAN_API_KEY")
        if not api_key:
            raise APIKeyMissingError("SHODAN_API_KEY")

        url = _SHODAN_URL.format(ip=ip)

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, params={"key": api_key})
                resp.raise_for_status()
                body = resp.json()

            return self._parse_host_response(ip, body)

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            log.warning("shodan_http_error", ip=ip, status=status)
            detail = "HTTP 429 rate limit" if status == 429 else f"HTTP {status}"
            raise AgentLookupError(self.name, "Shodan", detail) from exc
        except httpx.HTTPError as exc:
            log.warning("shodan_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(self.name, "Shodan", str(exc)) from exc

    def _parse_host_response(self, ip: str, body: dict[str, Any]) -> ShodanResult:
        """Parse Shodan's host payload into the project result model."""
        banners = body.get("data") or []
        if not isinstance(banners, list):
            banners = []

        ports = body.get("ports") or []
        open_ports = {port for port in ports if isinstance(port, int)}
        services: list[dict[str, Any]] = []
        cves: set[str] = set()

        for banner in banners:
            if not isinstance(banner, dict):
                continue

            port = banner.get("port")
            if isinstance(port, int):
                open_ports.add(port)

            service = {
                "port": port,
                "transport": banner.get("transport"),
                "product": banner.get("product"),
                "version": banner.get("version"),
                "title": banner.get("title"),
                "banner": banner.get("data"),
            }
            services.append(
                {key: value for key, value in service.items() if value is not None}
            )

            self._collect_cves(banner.get("vulns"), cves)

        self._collect_cves(body.get("vulns"), cves)

        os_name = body.get("os")
        if os_name is None:
            os_name = next(
                (
                    banner.get("os")
                    for banner in banners
                    if isinstance(banner, dict) and banner.get("os")
                ),
                None,
            )

        hostnames = body.get("hostnames") or []
        if not isinstance(hostnames, list):
            hostnames = []

        return ShodanResult(
            ip=ip,
            open_ports=sorted(open_ports),
            services=services,
            cves=sorted(cves),
            os=os_name,
            hostnames=[host for host in hostnames if isinstance(host, str)],
        )

    def _collect_cves(self, vulns: Any, cves: set[str]) -> None:
        """Collect CVE identifiers from Shodan's list or dict vulns shape."""
        if isinstance(vulns, dict):
            for cve in vulns:
                if isinstance(cve, str):
                    cves.add(cve)
        elif isinstance(vulns, list):
            for cve in vulns:
                if isinstance(cve, str):
                    cves.add(cve)

    # ------------------------------------------------------------------ #
    # Main execute
    # ------------------------------------------------------------------ #

    async def execute(self, target: str) -> AgentResult:
        """Query Shodan for open ports, banners, and CVEs.

        Args:
            target: IP address to investigate.

        Returns:
            AgentResult wrapping a :class:`ShodanResult`.
        """
        if not online_enrichment_enabled():
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                data=ShodanResult(ip=target),
                error=(
                    "Online enrichment is disabled. Set "
                    "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true to enable external lookups."
                ),
            )

        log.info("shodan_start", target=target)

        results = await asyncio.gather(
            self._shodan_lookup(target),
            return_exceptions=True,
        )

        shodan_res = results[0]
        errors: list[str] = []

        if isinstance(shodan_res, ShodanResult):
            shodan = shodan_res
        else:
            shodan = ShodanResult(ip=target)
            errors.append(f"Shodan: {shodan_res}")

        status = AgentStatus.FAILED if errors else AgentStatus.SUCCESS

        log.info(
            "shodan_complete",
            target=target,
            status=status.value,
            errors=len(errors),
        )

        return AgentResult(
            agent_name=self.name,
            status=status,
            data=shodan,
            error="; ".join(errors) if errors else None,
        )
