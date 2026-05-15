"""MCPOrchestrator — Parallel agent execution and result aggregation.

Runs ReconAgent, ReputationAgent, and ShodanAgent concurrently via
``asyncio.gather``, then feeds their results into the ReportAgent for
final threat analysis.  Results are cached with ``diskcache`` (6-hour TTL).

.. note::
    This is a scaffold — full implementation is pending.
"""

from __future__ import annotations

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.models import AgentResult, ThreatReport
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
    ) -> None:
        self._recon = ReconAgent(timeout=agent_timeout)
        self._reputation = ReputationAgent(timeout=agent_timeout)
        self._shodan = ShodanAgent(timeout=agent_timeout)
        self._report = ReportAgent(timeout=30.0)
        self._cache_dir = cache_dir

    async def investigate(self, target: str) -> ThreatReport:
        """Run the full investigation pipeline for a target.

        Steps:
            1. Check diskcache for ``"ip:<target>"``; return early on hit.
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
            - Integrate diskcache with key format ``"ip:<target>"``
            - Parallel gather of agents 1–3
            - Feed results into ReportAgent
            - Emit Qt signals back to UI thread
        """
        raise NotImplementedError("MCPOrchestrator is not yet implemented")
