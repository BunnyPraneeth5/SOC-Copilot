"""MCPOrchestrator — Parallel agent execution and result aggregation.

Runs ReconAgent, ReputationAgent, and ShodanAgent concurrently via
``asyncio.gather``, then feeds their results into the ReportAgent for
final threat analysis.  Results are cached with ``diskcache`` (6-hour TTL).

.. note::
    This is a scaffold — full implementation is pending.
"""

from __future__ import annotations

import asyncio

from soc_copilot.mcp.cache import MCPCache
from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import AgentResult, AgentStatus, ThreatReport, ThreatSeverity
from soc_copilot.security.network import is_external_ip
from soc_copilot.mcp.recon_agent import ReconAgent
from soc_copilot.mcp.reputation_agent import ReputationAgent
from soc_copilot.mcp.shodan_agent import ShodanAgent
from soc_copilot.mcp.report_agent import ReportAgent


class MCPOrchestrator:
    """Orchestrates the four-agent MCP investigation pipeline.

    Usage::

        orchestrator = MCPOrchestrator()
        report = await orchestrator.investigate("8.8.8.8")

    Attributes:
        cache_ttl: Seconds to keep cached results (default 21 600 = 6 h).
    """

    cache_ttl: int = 21_600  # 6 hours

    def __init__(
        self,
        agent_timeout: float = 10.0,
        cache_dir: str = ".cache/mcp",
        cache: MCPCache | None = None,
    ) -> None:
        self._recon = ReconAgent(timeout=agent_timeout)
        self._reputation = ReputationAgent(timeout=agent_timeout)
        self._shodan = ShodanAgent(timeout=agent_timeout)
        self._cache_dir = cache_dir
        self._cache = cache or MCPCache(
            cache_dir,
            default_ttl=self.cache_ttl,
        )

    async def _run_data_agents(self, target: str) -> tuple[
        AgentResult,
        AgentResult,
        AgentResult,
    ]:
        """Run Recon, Reputation, and Shodan concurrently."""
        agent_names = ("ReconAgent", "ReputationAgent", "ShodanAgent")
        results = await asyncio.gather(
            self._recon.safe_execute(target),
            self._reputation.safe_execute(target),
            self._shodan.safe_execute(target),
            return_exceptions=True,
        )

        normalized: list[AgentResult] = []
        for agent_name, result in zip(agent_names, results, strict=True):
            if isinstance(result, AgentResult):
                normalized.append(result)
            else:
                normalized.append(
                    AgentResult(
                        agent_name=agent_name,
                        status=AgentStatus.FAILED,
                        error=str(result),
                    )
                )

        return normalized[0], normalized[1], normalized[2]

    def _build_report_agent(
        self,
        recon: AgentResult,
        reputation: AgentResult,
        shodan: AgentResult,
    ) -> ReportAgent:
        """Create a fresh ReportAgent for one investigation."""
        return ReportAgent(
            timeout=30.0,
            recon=recon,
            reputation=reputation,
            shodan=shodan,
        )

    def _build_internal_target_report(self, target: str) -> ThreatReport:
        """Build a lightweight templated report for private/internal IPs, bypassing enrichment and the LLM."""
        return ThreatReport(
            target=target,
            severity=ThreatSeverity.LOW,
            summary=(
                f"{target} is a private/internal address. External threat "
                "intelligence enrichment (Recon, Reputation, Shodan) does not "
                "apply to internal network ranges, so this report was "
                "generated without external lookups or an LLM call."
            ),
            recommendations=[
                "Verify this host's identity and purpose within internal network documentation.",
                "Cross-reference with internal asset inventory or CMDB if unrecognized.",
            ],
            recon=None,
            reputation=None,
            shodan=None,
            llm_model=None,
        )

    async def investigate(self, target: str) -> ThreatReport:
        """Run the full investigation pipeline for a target.

        Steps:
            1. Check diskcache for ``"target:<normalized>"``; return early on hit.
            2. Run Recon + Reputation + Shodan in parallel via
               ``asyncio.gather`` with ``return_exceptions=True``.
            3. Feed results into ReportAgent.
            4. Cache the ThreatReport.
            5. Return the report.

        Args:
            target: IP address or domain to investigate.

        Returns:
            A fully-populated :class:`ThreatReport`.

        Todo:
            - Integrate diskcache with key format ``"target:<normalized>"``
            - Parallel gather of agents 1–3
            - Feed results into ReportAgent
            - Emit Qt signals back to UI thread
        """
        # diskcache is synchronous. For this desktop app milestone the cache
        # access is small enough to perform directly on the event loop.
        cached_report = self._cache.get_report(target)
        if cached_report is not None:
            return cached_report

        if not is_external_ip(target):
            report = self._build_internal_target_report(target)
            self._cache.set_report(target, report)
            return report

        # TODO: Concurrent cache misses for the same target deliberately run
        # duplicate investigations in this milestone instead of sharing one
        # in-flight task. Add per-target dedupe only if upstream API load
        # becomes a real product issue.
        recon, reputation, shodan = await self._run_data_agents(target)
        report_agent = self._build_report_agent(recon, reputation, shodan)
        report_result = await report_agent.safe_execute(target)

        if (
            report_result.status == AgentStatus.SUCCESS
            and isinstance(report_result.data, ThreatReport)
        ):
            self._cache.set_report(target, report_result.data)
            return report_result.data

        raise AgentLookupError(
            "MCPOrchestrator",
            "ReportAgent",
            report_result.error or "ReportAgent did not produce a ThreatReport",
        )
