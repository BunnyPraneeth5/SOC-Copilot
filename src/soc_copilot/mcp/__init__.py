"""MCP — Multi-agent Cyber-investigation Pipeline.

This package implements the agentic investigation layer for SOC Copilot.
When an analyst clicks an IP in the alert table, the orchestrator runs
four agents in parallel to produce a structured ThreatReport.

Agents:
    ReconAgent       — WHOIS, reverse DNS, ASN, geo-IP
    ReputationAgent  — AbuseIPDB + VirusTotal
    ShodanAgent      — open ports, banners, CVEs
    ReportAgent      — LLM-powered threat analysis (Claude)

Orchestrator:
    MCPOrchestrator  — parallel execution, caching, Qt signal emission
"""

from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    AsnInfo,
    AbuseIPDBResult,
    DnsInfo,
    GeoInfo,
    ReconResult,
    ReputationResult,
    ShodanResult,
    ThreatReport,
    ThreatSeverity,
    VirusTotalResult,
    WhoisInfo,
)
from soc_copilot.mcp.exceptions import (
    AgentLookupError,
    AgentTimeoutError,
    APIKeyMissingError,
    MCPError,
)
from soc_copilot.mcp.base_agent import BaseAgent
from soc_copilot.mcp.recon_agent import ReconAgent
from soc_copilot.mcp.reputation_agent import ReputationAgent
from soc_copilot.mcp.shodan_agent import ShodanAgent
from soc_copilot.mcp.report_agent import ReportAgent
from soc_copilot.mcp.orchestrator import MCPOrchestrator

__all__ = [
    # Models
    "AgentResult",
    "AgentStatus",
    "AsnInfo",
    "AbuseIPDBResult",
    "DnsInfo",
    "GeoInfo",
    "ReconResult",
    "ReputationResult",
    "ShodanResult",
    "ThreatReport",
    "ThreatSeverity",
    "VirusTotalResult",
    "WhoisInfo",
    # Exceptions
    "AgentLookupError",
    "AgentTimeoutError",
    "APIKeyMissingError",
    "MCPError",
    # Agents
    "BaseAgent",
    "ReconAgent",
    "ReputationAgent",
    "ShodanAgent",
    "ReportAgent",
    # Orchestrator
    "MCPOrchestrator",
]
