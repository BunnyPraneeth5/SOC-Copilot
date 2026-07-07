"""Tests for ReportAgent LLM report generation.

All LLM calls are mocked through an injected adapter so tests never hit a
real provider API.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

import soc_copilot.mcp.report_agent as report_agent_module
from soc_copilot.mcp.models import (
    AbuseIPDBResult,
    AgentResult,
    AgentStatus,
    AsnInfo,
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
from soc_copilot.mcp.report_agent import REPORT_SYSTEM_PROMPT, ReportAgent


TARGET_IP = "198.51.100.42"


class MockReportAdapter:
    """Small async adapter used to avoid real LLM calls in tests."""

    provider_name = "mock_provider"
    model = "mock-model"

    def __init__(
        self,
        response: str | None = None,
        exc: Exception | None = None,
    ) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self.exc is not None:
            raise self.exc
        return self.response or ""


@pytest.fixture
def enable_online(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", "true")


@pytest.fixture
def recon_result() -> AgentResult:
    return AgentResult(
        agent_name="ReconAgent",
        status=AgentStatus.SUCCESS,
        data=ReconResult(
            ip=TARGET_IP,
            whois=WhoisInfo(org="Example Hosting", country="US"),
            dns=DnsInfo(hostname="host.example.test"),
            asn=AsnInfo(asn="64500", asn_name="EXAMPLE-NET"),
            geo=GeoInfo(country="United States", isp="Example ISP"),
        ),
    )


@pytest.fixture
def reputation_result() -> AgentResult:
    return AgentResult(
        agent_name="ReputationAgent",
        status=AgentStatus.SUCCESS,
        data=ReputationResult(
            ip=TARGET_IP,
            abuseipdb=AbuseIPDBResult(
                confidence_score=82,
                total_reports=41,
                usage_type="Data Center",
            ),
            virustotal=VirusTotalResult(
                malicious=3,
                suspicious=1,
                harmless=60,
                undetected=10,
                detection_ratio=0.0541,
            ),
        ),
    )


@pytest.fixture
def shodan_result() -> AgentResult:
    return AgentResult(
        agent_name="ShodanAgent",
        status=AgentStatus.SUCCESS,
        data=ShodanResult(
            ip=TARGET_IP,
            open_ports=[22, 443],
            services=[{"port": 22, "transport": "tcp", "product": "OpenSSH"}],
            cves=["CVE-2023-38408"],
            os="Linux",
            hostnames=["host.example.test"],
        ),
    )


def _valid_llm_json(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "severity": "HIGH",
        "summary": "The target has malicious reputation and exposed SSH.",
        "recommendations": [
            "Review recent traffic involving the target.",
            "Prioritize containment if internal communication is observed.",
        ],
        "limitations": [],
        "evidence": {
            "recon": [{"field": "asn.asn", "value": "64500"}],
            "reputation": [
                {"field": "abuseipdb.confidence_score", "value": "82"},
                {"field": "virustotal.malicious", "value": "3"},
            ],
            "shodan": [
                {"field": "open_ports", "value": "22"},
                {"field": "cves", "value": "CVE-2023-38408"},
            ],
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


def _missing_required_llm_json() -> str:
    payload = json.loads(_valid_llm_json())
    del payload["recommendations"]
    return json.dumps(payload)


def _agent(
    adapter: MockReportAdapter,
    recon: AgentResult,
    reputation: AgentResult,
    shodan: AgentResult,
) -> ReportAgent:
    return ReportAgent(
        timeout=5.0,
        recon=recon,
        reputation=reputation,
        shodan=shodan,
        llm_adapter=adapter,
    )


@pytest.mark.asyncio
async def test_execute_success_returns_threat_report(
    enable_online: None,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    adapter = MockReportAdapter(_valid_llm_json())
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.SUCCESS
    assert result.error is None
    assert isinstance(result.data, ThreatReport)
    assert result.data.target == TARGET_IP
    assert result.data.severity == ThreatSeverity.HIGH
    assert result.data.summary == "The target has malicious reputation and exposed SSH."
    assert result.data.llm_model == "mock-model"
    assert result.data.recon == recon_result.data
    assert len(adapter.calls) == 1
    assert adapter.calls[0][0] == REPORT_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_execute_malformed_json_gracefully_fails(
    enable_online: None,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    adapter = MockReportAdapter("not-json-at-all")
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "JSON" in result.error


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _missing_required_llm_json(),
        _valid_llm_json(extra_field="not allowed"),
    ],
)
async def test_execute_schema_validation_failure_gracefully_fails(
    response: str,
    enable_online: None,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    adapter = MockReportAdapter(response)
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "schema validation failed" in result.error


@pytest.mark.asyncio
async def test_execute_unsupported_evidence_gracefully_fails(
    enable_online: None,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    response = _valid_llm_json(
        evidence={
            "recon": [],
            "reputation": [],
            "shodan": [{"field": "cves", "value": "CVE-2099-0001"}],
        }
    )
    adapter = MockReportAdapter(response)
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "Unsupported shodan evidence" in result.error


@pytest.mark.asyncio
async def test_execute_agent_name_mismatch_gracefully_fails(
    enable_online: None,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    recon_result.agent_name = "WrongAgent"
    adapter = MockReportAdapter(_valid_llm_json())
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "Expected ReconAgent, got WrongAgent" in result.error
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_execute_online_enrichment_disabled_gracefully_fails(
    monkeypatch: pytest.MonkeyPatch,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    monkeypatch.delenv("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", raising=False)
    adapter = MockReportAdapter(_valid_llm_json())
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "Online enrichment is disabled" in result.error
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_execute_unexpected_exception_gracefully_fails_and_logs(
    enable_online: None,
    monkeypatch: pytest.MonkeyPatch,
    recon_result: AgentResult,
    reputation_result: AgentResult,
    shodan_result: AgentResult,
) -> None:
    mock_log = MagicMock()
    monkeypatch.setattr(report_agent_module, "log", mock_log)
    adapter = MockReportAdapter(exc=RuntimeError("adapter exploded"))
    agent = _agent(adapter, recon_result, reputation_result, shodan_result)

    result = await agent.execute(TARGET_IP)

    assert result.status == AgentStatus.FAILED
    assert result.data is None
    assert "adapter exploded" in result.error
    mock_log.error.assert_called_once()
    assert mock_log.error.call_args.kwargs["exc_info"] is True
