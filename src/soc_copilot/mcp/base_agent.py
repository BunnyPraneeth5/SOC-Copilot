"""Abstract base class for all MCP investigation agents.

Every agent inherits from BaseAgent and implements the async execute()
method.  The safe_execute() wrapper adds timeout enforcement and
automatic error-to-AgentResult conversion so the orchestrator never
has to deal with raw exceptions.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod

import structlog

from soc_copilot.mcp.exceptions import AgentTimeoutError
from soc_copilot.mcp.models import AgentResult, AgentStatus


log = structlog.get_logger(__name__)


class BaseAgent(ABC):
    """Abstract base for every MCP agent.

    Attributes:
        name:    Human-readable agent identifier (e.g. ``"ReconAgent"``).
        timeout: Per-agent deadline in seconds (default 10 s).
    """

    name: str = "BaseAgent"
    timeout: float = 10.0

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    @abstractmethod
    async def execute(self, target: str) -> AgentResult:
        """Run the agent's investigation logic.

        Args:
            target: IP address or domain to investigate.

        Returns:
            AgentResult with status, data payload, and optional error.
        """
        ...

    async def safe_execute(self, target: str) -> AgentResult:
        """Execute with timeout and blanket error handling.

        This is the method the orchestrator should call.  It wraps
        :meth:`execute` so that:

        * A timeout yields ``AgentStatus.TIMEOUT``.
        * Any other exception yields ``AgentStatus.FAILED``.

        Returns:
            AgentResult — always, never raises.
        """
        start = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.execute(target), timeout=self.timeout
            )
            result.elapsed_seconds = time.monotonic() - start
            return result

        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start
            log.warning(
                "agent_timeout",
                agent=self.name,
                target=target,
                timeout=self.timeout,
            )
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.TIMEOUT,
                error=f"Timed out after {self.timeout:.1f}s",
                elapsed_seconds=elapsed,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - start
            log.error(
                "agent_failed",
                agent=self.name,
                target=target,
                error=str(exc),
                exc_info=True,
            )
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(exc),
                elapsed_seconds=elapsed,
            )
