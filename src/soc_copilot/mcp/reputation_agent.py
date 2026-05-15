"""ReputationAgent — AbuseIPDB confidence score and VirusTotal detection ratio.

Queries two threat intelligence APIs concurrently:
- AbuseIPDB ``/api/v2/check`` for abuse confidence score and report count.
- VirusTotal ``/api/v3/ip_addresses/{ip}`` for detection statistics.

Both calls use async httpx.  API keys are read from environment variables
``ABUSEIPDB_API_KEY`` and ``VIRUSTOTAL_API_KEY``.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.exceptions import AgentLookupError, APIKeyMissingError
from soc_copilot.mcp.models import (
    AbuseIPDBResult,
    AgentResult,
    AgentStatus,
    ReputationResult,
    VirusTotalResult,
)
from soc_copilot.security.network import online_enrichment_enabled


log = structlog.get_logger(__name__)

_ABUSEIPDB_URL = "https://api.abuseipdb.com/api/v2/check"
_VIRUSTOTAL_URL = "https://www.virustotal.com/api/v3/ip_addresses/{ip}"


class ReputationAgent(BaseAgent):
    """IP reputation agent using AbuseIPDB and VirusTotal.

    Requires two environment variables:
    - ``ABUSEIPDB_API_KEY``
    - ``VIRUSTOTAL_API_KEY``

    Attributes:
        name:    ``"ReputationAgent"``
        timeout: Per-agent deadline in seconds (default 10 s).
    """

    name: str = "ReputationAgent"
    timeout: float = 10.0

    def __init__(self, timeout: float = 10.0) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------ #
    # Individual lookups
    # ------------------------------------------------------------------ #

    async def _abuseipdb_lookup(self, ip: str) -> AbuseIPDBResult:
        """Check an IP against the AbuseIPDB database.

        GET https://api.abuseipdb.com/api/v2/check
            params:  ipAddress={ip}, maxAgeInDays=90, verbose=True
            header:  Key={ABUSEIPDB_API_KEY}

        Returns:
            AbuseIPDBResult with confidence_score, total_reports,
            usage_type, and isp.

        Raises:
            APIKeyMissingError: If ``ABUSEIPDB_API_KEY`` is not set.
            AgentLookupError: On HTTP or API errors.
        """
        api_key = os.environ.get("ABUSEIPDB_API_KEY")
        if not api_key:
            raise APIKeyMissingError("ABUSEIPDB_API_KEY")

        headers = {
            "Key": api_key,
            "Accept": "application/json",
        }
        params = {
            "ipAddress": ip,
            "maxAgeInDays": "90",
            "verbose": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    _ABUSEIPDB_URL, headers=headers, params=params
                )
                resp.raise_for_status()
                body = resp.json()

            data = body.get("data", {})
            return AbuseIPDBResult(
                confidence_score=data.get("abuseConfidenceScore", 0),
                total_reports=data.get("totalReports", 0),
                usage_type=data.get("usageType"),
                isp=data.get("isp"),
                is_whitelisted=data.get("isWhitelisted"),
                domain=data.get("domain"),
            )

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            log.warning("abuseipdb_http_error", ip=ip, status=status)
            raise AgentLookupError(
                self.name, "AbuseIPDB", f"HTTP {status}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("abuseipdb_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(
                self.name, "AbuseIPDB", str(exc)
            ) from exc

    async def _virustotal_lookup(self, ip: str) -> VirusTotalResult:
        """Check an IP against the VirusTotal database.

        GET https://www.virustotal.com/api/v3/ip_addresses/{ip}
            header:  x-apikey={VIRUSTOTAL_API_KEY}

        Returns:
            VirusTotalResult with malicious, suspicious, harmless counts
            and a computed detection_ratio.

        Raises:
            APIKeyMissingError: If ``VIRUSTOTAL_API_KEY`` is not set.
            AgentLookupError: On HTTP or API errors.
        """
        api_key = os.environ.get("VIRUSTOTAL_API_KEY")
        if not api_key:
            raise APIKeyMissingError("VIRUSTOTAL_API_KEY")

        headers = {
            "x-apikey": api_key,
            "Accept": "application/json",
        }
        url = _VIRUSTOTAL_URL.format(ip=ip)

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                body = resp.json()

            stats = (
                body
                .get("data", {})
                .get("attributes", {})
                .get("last_analysis_stats", {})
            )

            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            harmless = stats.get("harmless", 0)
            undetected = stats.get("undetected", 0)

            total = malicious + suspicious + harmless + undetected
            detection_ratio = (
                (malicious + suspicious) / total if total > 0 else 0.0
            )

            return VirusTotalResult(
                malicious=malicious,
                suspicious=suspicious,
                harmless=harmless,
                undetected=undetected,
                detection_ratio=round(detection_ratio, 4),
            )

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            log.warning("virustotal_http_error", ip=ip, status=status)
            raise AgentLookupError(
                self.name, "VirusTotal", f"HTTP {status}"
            ) from exc
        except httpx.HTTPError as exc:
            log.warning("virustotal_lookup_failed", ip=ip, error=str(exc))
            raise AgentLookupError(
                self.name, "VirusTotal", str(exc)
            ) from exc

    # ------------------------------------------------------------------ #
    # Main execute
    # ------------------------------------------------------------------ #

    async def execute(self, target: str) -> AgentResult:
        """Run AbuseIPDB and VirusTotal lookups concurrently.

        Individual failures produce partial results — the agent returns
        ``AgentStatus.PARTIAL`` when one API fails but the other
        succeeds, and ``AgentStatus.FAILED`` only when both fail.

        Args:
            target: IP address to investigate.

        Returns:
            AgentResult wrapping a :class:`ReputationResult`.
        """
        if not online_enrichment_enabled():
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                data=ReputationResult(ip=target),
                error=(
                    "Online enrichment is disabled. Set "
                    "SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true to enable external lookups."
                ),
            )

        log.info("reputation_start", target=target)

        results = await asyncio.gather(
            self._abuseipdb_lookup(target),
            self._virustotal_lookup(target),
            return_exceptions=True,
        )

        abuse_res, vt_res = results

        errors: list[str] = []

        if isinstance(abuse_res, AbuseIPDBResult):
            abuseipdb = abuse_res
        else:
            abuseipdb = AbuseIPDBResult()
            errors.append(f"AbuseIPDB: {abuse_res}")

        if isinstance(vt_res, VirusTotalResult):
            virustotal = vt_res
        else:
            virustotal = VirusTotalResult()
            errors.append(f"VirusTotal: {vt_res}")

        reputation = ReputationResult(
            ip=target,
            abuseipdb=abuseipdb,
            virustotal=virustotal,
        )

        if len(errors) == 2:
            status = AgentStatus.FAILED
        elif errors:
            status = AgentStatus.PARTIAL
        else:
            status = AgentStatus.SUCCESS

        log.info(
            "reputation_complete",
            target=target,
            status=status.value,
            errors=len(errors),
        )

        return AgentResult(
            agent_name=self.name,
            status=status,
            data=reputation,
            error="; ".join(errors) if errors else None,
        )
