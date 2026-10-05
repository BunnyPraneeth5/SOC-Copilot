"""MCPOrchestrator — Parallel agent execution and result aggregation.

Runs ReconAgent, ReputationAgent, and ShodanAgent concurrently via
``asyncio.gather``, then feeds their results into the ReportAgent for
final threat analysis.  Results are cached with ``diskcache`` (6-hour TTL).
Private/internal IP targets get a local templated report without any
external lookups.  When online enrichment is disabled, external targets
get a local-only UNKNOWN-severity report instead of failing; when the
ReportAgent fails but at least one data agent returned data, a partial
UNKNOWN-severity report is built from whatever data was collected.
"""

from __future__ import annotations

import asyncio

from soc_copilot.mcp.cache import MCPCache
from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    ReconResult,
    ReputationResult,
    ShodanResult,
    ThreatReport,
    ThreatSeverity,
)
from soc_copilot.security.network import is_internal_ip, online_enrichment_enabled
from soc_copilot.mcp.provider_registry import (
    ProviderStatus,
    get_provider_statuses,
)
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

    async def _run_data_agents(
        self,
        target: str,
        statuses: list[ProviderStatus],
    ) -> tuple[
        AgentResult,
        AgentResult,
        AgentResult,
    ]:
        """Run Recon, Reputation, and Shodan concurrently.

        Agents whose providers are all unusable (missing keys, disabled)
        are skipped and get a FAILED result without calling safe_execute.
        """
        usable = {s.key for s in statuses if s.usable}
        detail = {s.key: s for s in statuses}

        def _skip_error(keys: tuple[str, ...]) -> str:
            parts = [
                detail[k].detail or detail[k].state.value
                for k in keys
                if k in detail
            ]
            return "Skipped: " + "; ".join(parts)

        agent_names = ("ReconAgent", "ReputationAgent", "ShodanAgent")
        agents = (self._recon, self._reputation, self._shodan)
        run_flags = (
            True,  # ReconAgent always runs (whois/geoip need no key)
            "abuseipdb" in usable or "virustotal" in usable,
            "shodan" in usable,
        )
        skip_errors = (
            "",
            _skip_error(("abuseipdb", "virustotal")),
            _skip_error(("shodan",)),
        )

        async def _run_or_skip(agent, agent_name, run, skip_error) -> AgentResult:
            if run:
                return await agent.safe_execute(target)
            return AgentResult(
                agent_name=agent_name,
                status=AgentStatus.FAILED,
                error=skip_error or "Skipped: provider not usable",
            )

        results = await asyncio.gather(
            *(
                _run_or_skip(agent, name, run, skip_error)
                for agent, name, run, skip_error in zip(
                    agents, agent_names, run_flags, skip_errors, strict=True
                )
            ),
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

    def _build_local_only_report(self, target: str) -> ThreatReport:
        """Build a local-only report for external targets when online enrichment is disabled."""
        return ThreatReport(
            target=target,
            severity=ThreatSeverity.UNKNOWN,
            summary=(
                "Online threat-intelligence enrichment is disabled "
                "(SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT is not set to true), "
                f"so no external lookups were made and {target} was not "
                "assessed against Recon, Reputation, or Shodan sources."
            ),
            recommendations=[
                "Enable online enrichment (SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT=true) "
                "to run Recon, Reputation and Shodan lookups.",
                "Correlate this target with local alerts and logs.",
            ],
            recon=None,
            reputation=None,
            shodan=None,
            llm_model=None,
        )

    def _build_partial_report(
        self,
        target: str,
        recon: AgentResult,
        reputation: AgentResult,
        shodan: AgentResult,
        error: str,
    ) -> ThreatReport:
        """Build an UNKNOWN-severity report from whatever agent data exists."""
        results = {
            "ReconAgent": recon,
            "ReputationAgent": reputation,
            "ShodanAgent": shodan,
        }
        returned = [
            name
            for name, result in results.items()
            if isinstance(
                result.data, (ReconResult, ReputationResult, ShodanResult)
            )
        ]
        failed = [name for name in results if name not in returned]
        summary_parts = [
            f"AI threat report could not be generated: {error}.",
        ]
        if returned:
            summary_parts.append(
                "Agents that returned data: " + ", ".join(returned) + "."
            )
        if failed:
            failed_details = ", ".join(
                f"{name}: {results[name].error or 'no data'}"
                for name in failed
            )
            summary_parts.append(
                "Agents that failed or returned no data: "
                + failed_details
                + "."
            )
        return ThreatReport(
            target=target,
            severity=ThreatSeverity.UNKNOWN,
            summary=" ".join(summary_parts),
            recommendations=[
                "Retry the investigation once the LLM provider is reachable "
                "or re-configured.",
                "Review the partial agent data attached to this report and "
                "correlate it with local alerts and logs.",
            ],
            recon=recon.data if isinstance(recon.data, ReconResult) else None,
            reputation=(
                reputation.data
                if isinstance(reputation.data, ReputationResult)
                else None
            ),
            shodan=shodan.data if isinstance(shodan.data, ShodanResult) else None,
            llm_model=None,
        )

    async def investigate(self, target: str) -> ThreatReport:
        """Run the full investigation pipeline for a target.

        Steps:
            1. Check diskcache for ``"target:<normalized>"``; return early on hit.
            2. Private/internal IPs get a local templated LOW report (cached).
            3. If online enrichment is disabled, return an uncached
               local-only UNKNOWN report without running any agents.
            4. Run Recon + Reputation + Shodan in parallel via
               ``asyncio.gather`` with ``return_exceptions=True``.
            5. Feed results into ReportAgent.
            6. Cache and return the ThreatReport; if the ReportAgent failed
               but at least one data agent returned data, return an uncached
               partial UNKNOWN report instead of raising.

        Args:
            target: IP address or domain to investigate.

        Returns:
            A fully-populated :class:`ThreatReport`.
        """
        # diskcache is synchronous. For this desktop app milestone the cache
        # access is small enough to perform directly on the event loop.
        cached_report = self._cache.get_report(target)
        if cached_report is not None:
            return cached_report

        if is_internal_ip(target):
            report = self._build_internal_target_report(target)
            self._cache.set_report(target, report)
            return report

        if not online_enrichment_enabled():
            return self._build_local_only_report(target)

        # Local provider statuses (no probing) drive agent dispatch.
        statuses = get_provider_statuses()
        usable = {s.key for s in statuses if s.usable}

        # TODO: Concurrent cache misses for the same target deliberately run
        # duplicate investigations in this milestone instead of sharing one
        # in-flight task. Add per-target dedupe only if upstream API load
        # becomes a real product issue.
        recon, reputation, shodan = await self._run_data_agents(target, statuses)

        if "report_llm" in usable:
            report_agent = self._build_report_agent(recon, reputation, shodan)
            report_result = await report_agent.safe_execute(target)

            if (
                report_result.status == AgentStatus.SUCCESS
                and isinstance(report_result.data, ThreatReport)
            ):
                self._cache.set_report(target, report_result.data)
                return report_result.data

            report_error = (
                report_result.error or "ReportAgent did not produce a ThreatReport"
            )
        else:
            llm_status = next(
                (s for s in statuses if s.key == "report_llm"), None
            )
            report_error = (
                "Skipped: "
                + (llm_status.detail or llm_status.state.value)
                if llm_status is not None
                else "Skipped: report LLM provider not usable"
            )

        data_types = (ReconResult, ReputationResult, ShodanResult)
        if any(
            isinstance(result.data, data_types)
            for result in (recon, reputation, shodan)
        ):
            return self._build_partial_report(
                target,
                recon,
                reputation,
                shodan,
                report_error,
            )

        raise AgentLookupError(
            "MCPOrchestrator",
            "ReportAgent",
            report_error,
        )
