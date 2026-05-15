"""Pydantic data models for the MCP agentic investigation pipeline.

Defines structured outputs for each agent and the final ThreatReport
that the orchestrator returns to the UI layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class ThreatSeverity(str, Enum):
    """Severity rating assigned by the ReportAgent."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AgentStatus(str, Enum):
    """Execution status of an individual agent run."""

    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


# =============================================================================
# ReconAgent models
# =============================================================================

class WhoisInfo(BaseModel):
    """WHOIS registration data for an IP address."""

    registrar: str | None = None
    org: str | None = None
    country: str | None = None
    creation_date: str | None = None
    updated_date: str | None = None
    description: str | None = None


class DnsInfo(BaseModel):
    """Reverse DNS and record data."""

    hostname: str | None = None
    aliases: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)


class AsnInfo(BaseModel):
    """Autonomous System Number data."""

    asn: str | None = None
    asn_name: str | None = None
    asn_cidr: str | None = None
    asn_country: str | None = None


class GeoInfo(BaseModel):
    """Geographic location data for an IP address."""

    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    isp: str | None = None
    org: str | None = None


class ReconResult(BaseModel):
    """Aggregated output of the ReconAgent."""

    ip: str
    whois: WhoisInfo = Field(default_factory=WhoisInfo)
    dns: DnsInfo = Field(default_factory=DnsInfo)
    asn: AsnInfo = Field(default_factory=AsnInfo)
    geo: GeoInfo = Field(default_factory=GeoInfo)


# =============================================================================
# ReputationAgent models
# =============================================================================

class AbuseIPDBResult(BaseModel):
    """AbuseIPDB check result for an IP address."""

    confidence_score: int = 0
    total_reports: int = 0
    usage_type: str | None = None
    isp: str | None = None
    is_whitelisted: bool | None = None
    domain: str | None = None


class VirusTotalResult(BaseModel):
    """VirusTotal analysis result for an IP address."""

    malicious: int = 0
    suspicious: int = 0
    harmless: int = 0
    undetected: int = 0
    detection_ratio: float = 0.0


class ReputationResult(BaseModel):
    """Aggregated output of the ReputationAgent."""

    ip: str
    abuseipdb: AbuseIPDBResult = Field(default_factory=AbuseIPDBResult)
    virustotal: VirusTotalResult = Field(default_factory=VirusTotalResult)


# =============================================================================
# ShodanAgent models
# =============================================================================

class ShodanResult(BaseModel):
    """Aggregated output of the ShodanAgent."""

    ip: str
    open_ports: list[int] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    cves: list[str] = Field(default_factory=list)
    os: str | None = None
    hostnames: list[str] = Field(default_factory=list)


# =============================================================================
# ReportAgent models
# =============================================================================

class ThreatReport(BaseModel):
    """Final threat intelligence report produced by the ReportAgent.

    Aggregates results from Recon, Reputation, and Shodan agents and
    includes an LLM-generated analysis with severity rating.
    """

    target: str
    severity: ThreatSeverity = ThreatSeverity.LOW
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)
    recon: ReconResult | None = None
    reputation: ReputationResult | None = None
    shodan: ShodanResult | None = None
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    llm_model: str | None = None


# =============================================================================
# Generic agent wrapper
# =============================================================================

class AgentResult(BaseModel):
    """Generic wrapper returned by every agent's safe_execute() method.

    Carries the status, typed data payload, and an optional error message
    so the orchestrator can handle partial failures gracefully.
    """

    agent_name: str
    status: AgentStatus
    data: ReconResult | ReputationResult | ShodanResult | ThreatReport | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0
