"""ReportAgent — LLM-powered threat analysis and severity rating.

Aggregates outputs from ReconAgent, ReputationAgent, and ShodanAgent,
then calls the Anthropic Claude API to generate a structured
ThreatReport with severity classification.

.. note::
    This is a scaffold — full implementation is pending.
"""

from __future__ import annotations

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    ReconResult,
    ReputationResult,
    ShodanResult,
    ThreatReport,
)


# The exact system prompt specified in docs/Agent.md
REPORT_SYSTEM_PROMPT = (
    "You are a senior SOC analyst. Given the following threat intelligence "
    "data about an IP address, produce a structured threat assessment. "
    "Rate severity as CRITICAL, HIGH, MEDIUM, or LOW. "
    "Provide a concise summary and actionable recommendations."
)


class ReportAgent(BaseAgent):
    """LLM-powered threat report generator.

    Consumes outputs from the three data-gathering agents and calls
    Anthropic ``claude-sonnet-4-20250514`` to produce a final
    :class:`ThreatReport`.

    Attributes:
        name:    ``"ReportAgent"``
        timeout: Per-agent deadline in seconds (default 30 s — LLM calls
                 are slower than network lookups).
    """

    name: str = "ReportAgent"
    timeout: float = 30.0

    def __init__(
        self,
        timeout: float = 30.0,
        recon: ReconResult | None = None,
        reputation: ReputationResult | None = None,
        shodan: ShodanResult | None = None,
    ) -> None:
        self.timeout = timeout
        self._recon = recon
        self._reputation = reputation
        self._shodan = shodan

    async def execute(self, target: str) -> AgentResult:
        """Generate a ThreatReport via the Claude API.

        Args:
            target: IP address or domain under investigation.

        Returns:
            AgentResult wrapping a :class:`ThreatReport`.

        Todo:
            - Build user prompt from recon/reputation/shodan data
            - Call Anthropic claude-sonnet-4-20250514 with REPORT_SYSTEM_PROMPT
            - Parse structured response into ThreatReport
            - Handle API errors gracefully
        """
        raise NotImplementedError("ReportAgent is not yet implemented")
