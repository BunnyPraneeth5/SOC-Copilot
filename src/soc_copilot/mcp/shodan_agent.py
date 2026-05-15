"""ShodanAgent — Open ports, service banners, and known CVEs.

Queries the Shodan API for host intelligence including open ports,
running services, operating system detection, and associated CVEs.

.. note::
    This is a scaffold — full implementation is pending.
"""

from __future__ import annotations

from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.models import AgentResult, AgentStatus, ShodanResult
from soc_copilot.security.network import online_enrichment_enabled


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

    async def execute(self, target: str) -> AgentResult:
        """Query Shodan for open ports, banners, and CVEs.

        Args:
            target: IP address to investigate.

        Returns:
            AgentResult wrapping a :class:`ShodanResult`.

        Todo:
            - Validate SHODAN_API_KEY from env
            - GET ``https://api.shodan.io/shodan/host/{ip}``
            - Parse ports, services, vulns
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
        raise NotImplementedError("ShodanAgent is not yet implemented")
