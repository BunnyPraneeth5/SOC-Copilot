"""ReconAgent — WHOIS, reverse DNS, ASN lookup, and geo-IP.

Performs passive reconnaissance on an IP address using:
- ipwhois for WHOIS + ASN data (run in executor — blocking library)
- socket.gethostbyaddr for reverse DNS (run in executor)
- httpx async GET to ip-api.com for geo-IP (free, no key required)

All four lookups run concurrently.  Individual failures produce partial
results rather than aborting the whole agent.
"""

from __future__ import annotations

import asyncio
import socket
from typing import Any

import httpx
import structlog
from ipwhois import IPWhois

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    AsnInfo,
    DnsInfo,
    GeoInfo,
    ReconResult,
    WhoisInfo,
)
from soc_copilot.security.network import online_enrichment_enabled


log = structlog.get_logger(__name__)

_GEOIP_URL = "https://ipwho.is/{ip}?fields=success,message,country,country_code,region,city,latitude,longitude,connection"


class ReconAgent(BaseAgent):
    """Passive IP reconnaissance agent.

    Runs WHOIS, reverse-DNS, ASN, and geo-IP lookups concurrently and
    assembles a :class:`ReconResult`.
    """

    name: str = "ReconAgent"
    timeout: float = 10.0

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Individual lookups
    # ------------------------------------------------------------------ #

    async def _whois_lookup(self, ip: str) -> WhoisInfo:
        """WHOIS lookup via ipwhois (blocking, run in executor)."""
        loop = asyncio.get_running_loop()

        def _blocking() -> dict[str, Any]:
            obj = IPWhois(ip)
            return obj.lookup_rdap(depth=1)

        try:
            data = await loop.run_in_executor(None, _blocking)
            network = data.get("network", {}) or {}
            return WhoisInfo(
                registrar=network.get("name"),
                org=network.get("name"),
                country=network.get("country"),
                description=network.get("remarks", [{}])[0].get("description")
                if network.get("remarks")
                else None,
            )
        except Exception as exc:
            log.warning("whois_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(self.name, "WHOIS", str(exc)) from exc

    async def _reverse_dns(self, ip: str) -> DnsInfo:
        """Reverse DNS lookup via socket (blocking, run in executor)."""
        loop = asyncio.get_running_loop()

        def _blocking() -> tuple[str, list[str], list[str]]:
            return socket.gethostbyaddr(ip)

        try:
            hostname, aliases, addresses = await loop.run_in_executor(
                None, _blocking
            )
            return DnsInfo(
                hostname=hostname,
                aliases=list(aliases),
                addresses=list(addresses),
            )
        except socket.herror as exc:
            log.warning("reverse_dns_failed", ip=ip, error=str(exc))
            raise AgentLookupError(self.name, "ReverseDNS", str(exc)) from exc

    async def _asn_lookup(self, ip: str) -> AsnInfo:
        """ASN lookup via ipwhois RDAP (blocking, run in executor)."""
        loop = asyncio.get_running_loop()

        def _blocking() -> dict[str, Any]:
            obj = IPWhois(ip)
            return obj.lookup_rdap(depth=0)

        try:
            data = await loop.run_in_executor(None, _blocking)
            return AsnInfo(
                asn=data.get("asn"),
                asn_name=data.get("asn_description"),
                asn_cidr=data.get("asn_cidr"),
                asn_country=data.get("asn_country_code"),
            )
        except Exception as exc:
            log.warning("asn_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(self.name, "ASN", str(exc)) from exc

    async def _geoip_lookup(self, ip: str) -> GeoInfo:
        """Geo-IP lookup via ip-api.com (async httpx)."""
        url = _GEOIP_URL.format(ip=ip)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

            if data.get("success") is False or data.get("status") == "fail":
                raise AgentLookupError(
                    self.name, "GeoIP", data.get("message", "unknown error")
                )

            connection = data.get("connection", {}) or {}
            return GeoInfo(
                country=data.get("country"),
                country_code=data.get("country_code") or data.get("countryCode"),
                region=data.get("region") or data.get("regionName"),
                city=data.get("city"),
                latitude=data.get("latitude") or data.get("lat"),
                longitude=data.get("longitude") or data.get("lon"),
                isp=connection.get("isp") or data.get("isp"),
                org=connection.get("org") or data.get("org"),
            )
        except httpx.HTTPStatusError as exc:
            log.warning("geoip_http_error", ip=ip, status=exc.response.status_code)
            raise AgentLookupError(
                self.name, "GeoIP", f"HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("geoip_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(self.name, "GeoIP", str(exc)) from exc

    # ------------------------------------------------------------------ #
    # Main execute
    # ------------------------------------------------------------------ #

    async def execute(self, target: str) -> AgentResult:
        """Run all four recon lookups concurrently.

        Individual failures are captured as partial results — the agent
        returns ``AgentStatus.PARTIAL`` instead of ``FAILED`` when at
        least one lookup succeeds.
        """
        if not online_enrichment_enabled():
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                data=ReconResult(ip=target),
                error=(
                    "Online enrichment is disabled. Set "
                    "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true to enable external lookups."
                ),
            )

        log.info("recon_start", target=target)

        results = await asyncio.gather(
            self._whois_lookup(target),
            self._reverse_dns(target),
            self._asn_lookup(target),
            self._geoip_lookup(target),
            return_exceptions=True,
        )

        whois_res, dns_res, asn_res, geo_res = results

        # Determine partial vs full success vs full failure
        errors: list[str] = []
        whois = whois_res if isinstance(whois_res, WhoisInfo) else WhoisInfo()
        if isinstance(whois_res, Exception):
            errors.append(f"WHOIS: {whois_res}")

        dns = dns_res if isinstance(dns_res, DnsInfo) else DnsInfo()
        if isinstance(dns_res, Exception):
            errors.append(f"DNS: {dns_res}")

        asn = asn_res if isinstance(asn_res, AsnInfo) else AsnInfo()
        if isinstance(asn_res, Exception):
            errors.append(f"ASN: {asn_res}")

        geo = geo_res if isinstance(geo_res, GeoInfo) else GeoInfo()
        if isinstance(geo_res, Exception):
            errors.append(f"GeoIP: {geo_res}")

        recon = ReconResult(ip=target, whois=whois, dns=dns, asn=asn, geo=geo)

        if len(errors) == 4:
            status = AgentStatus.FAILED
        elif errors:
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        log.info(
            "recon_complete",
            target=target,
            status=status.value,
            errors=len(errors),
        )

        return AgentResult(
            agent_name=self.name,
            status=status,
            data=recon,
            error="; ".join(errors) if errors else None,
        )
