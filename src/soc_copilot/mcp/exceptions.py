"""MCP-specific exceptions for the agentic investigation pipeline.

All MCP exceptions inherit from the project-wide SOCCopilotError so that
callers can catch either the narrow MCP type or the broad project type.
"""

from soc_copilot.core.base import SOCCopilotError


# =============================================================================
# MCP Exceptions
# =============================================================================

class MCPError(SOCCopilotError):
    """Base exception for all MCP agent errors."""

    pass


class AgentTimeoutError(MCPError):
    """An agent exceeded its configured deadline."""

    def __init__(self, agent_name: str, timeout: float) -> None:
        self.agent_name = agent_name
        self.timeout = timeout
        super().__init__(
            f"Agent '{agent_name}' timed out after {timeout:.1f}s"
        )


class AgentLookupError(MCPError):
    """An external lookup (HTTP, DNS, WHOIS, etc.) failed."""

    def __init__(self, agent_name: str, service: str, detail: str = "") -> None:
        self.agent_name = agent_name
        self.service = service
        self.detail = detail
        msg = f"Agent '{agent_name}' lookup failed for {service}"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class APIKeyMissingError(MCPError):
    """A required API key is not configured in the environment."""

    def __init__(self, key_name: str) -> None:
        self.key_name = key_name
        super().__init__(
            f"Required API key '{key_name}' is not set. "
            f"Add it to your .env file or environment variables."
        )
