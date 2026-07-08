"""Tests for the MCP orchestrator."""

from __future__ import annotations

import asyncio

import pytest

from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import (
    AgentResult,
    AgentStatus,
    ThreatReport,
    ThreatSeverity,
)
from soc_copilot.mcp.orchestrator import MCPOrchestrator


class FakeCache:
    """Tiny cache double for orchestrator cache-path tests."""

    def __init__(
        self,
        report: ThreatReport | None = None,
        *,
        write_exc: Exception | None = None,
    ) -> None:
        self.report = report
        self.write_exc = write_exc
        self.requested_targets: list[str] = []
        self.writes: list[tuple[str, ThreatReport]] = []

    def get_report(self, target: str) -> ThreatReport | None:
        self.requested_targets.append(target)
        return self.report

    def set_report(self, target: str, report: ThreatReport) -> None:
        if self.write_exc is not None:
            raise self.write_exc
        self.writes.append((target, report))


class FakeAgent:
    """Agent double that records safe_execute calls."""

    def __init__(
        self,
        agent_name: str,
        *,
        delay: float = 0.0,
        raise_exc: Exception | None = None,
        status: AgentStatus = AgentStatus.SUCCESS,
        error: str | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.delay = delay
        self.raise_exc = raise_exc
        self.status = status
        self.error = error
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.targets: list[str] = []

    async def safe_execute(self, target: str) -> AgentResult:
        self.targets.append(target)
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        await self.release.wait()
        if self.raise_exc is not None:
            raise self.raise_exc
        return AgentResult(
            agent_name=self.agent_name,
            status=self.status,
            error=self.error,
        )


class FakeReportAgent:
    """ReportAgent double that records safe_execute calls."""

    def __init__(self, result: AgentResult) -> None:
        self.result = result
        self.targets: list[str] = []

    async def safe_execute(self, target: str) -> AgentResult:
        self.targets.append(target)
        return self.result


def _report() -> ThreatReport:
    return ThreatReport(
        target="example.com",
        severity=ThreatSeverity.LOW,
        summary="Cached report.",
    )


@pytest.mark.asyncio
async def test_investigate_returns_cached_report_on_hit() -> None:
    report = _report()
    cache = FakeCache(report)
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report_agent_built = False

    def _build_report_agent(*args) -> FakeReportAgent:
        nonlocal report_agent_built
        report_agent_built = True
        return FakeReportAgent(
            AgentResult(agent_name="ReportAgent", status=AgentStatus.SUCCESS)
        )

    orchestrator._build_report_agent = _build_report_agent

    result = await orchestrator.investigate(" Example.COM ")

    assert result is report
    assert cache.requested_targets == [" Example.COM "]
    assert [agent.targets for agent in agents] == [[], [], []]
    assert report_agent_built is False


@pytest.mark.asyncio
async def test_investigate_cache_miss_returns_report_agent_threat_report() -> None:
    cache = FakeCache()
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report = _report()
    report_agent = FakeReportAgent(
        AgentResult(
            agent_name="ReportAgent",
            status=AgentStatus.SUCCESS,
            data=report,
        )
    )
    report_inputs: list[tuple[AgentResult, AgentResult, AgentResult]] = []

    async def _release_agents() -> None:
        await asyncio.gather(*(agent.started.wait() for agent in agents))
        for agent in agents:
            agent.release.set()

    def _build_report_agent(
        recon: AgentResult,
        reputation: AgentResult,
        shodan: AgentResult,
    ) -> FakeReportAgent:
        report_inputs.append((recon, reputation, shodan))
        return report_agent

    orchestrator._build_report_agent = _build_report_agent
    releaser = asyncio.create_task(_release_agents())

    result = await orchestrator.investigate("example.com")

    await releaser
    assert result is report
    assert cache.requested_targets == ["example.com"]
    assert cache.writes == [("example.com", report)]
    assert [agent.targets for agent in agents] == [
        ["example.com"],
        ["example.com"],
        ["example.com"],
    ]
    assert len(report_inputs) == 1
    assert [agent_result.agent_name for agent_result in report_inputs[0]] == [
        "ReconAgent",
        "ReputationAgent",
        "ShodanAgent",
    ]
    assert report_agent.targets == ["example.com"]


@pytest.mark.asyncio
async def test_investigate_report_agent_failure_raises_controlled_error() -> None:
    cache = FakeCache()
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report_agent = FakeReportAgent(
        AgentResult(
            agent_name="ReportAgent",
            status=AgentStatus.FAILED,
            error="LLM unavailable",
        )
    )

    async def _release_agents() -> None:
        await asyncio.gather(*(agent.started.wait() for agent in agents))
        for agent in agents:
            agent.release.set()

    orchestrator._build_report_agent = lambda *args: report_agent
    releaser = asyncio.create_task(_release_agents())

    with pytest.raises(AgentLookupError, match="LLM unavailable"):
        await orchestrator.investigate("example.com")

    await releaser
    assert report_agent.targets == ["example.com"]
    assert cache.writes == []


@pytest.mark.asyncio
async def test_investigate_agent_timeout_still_reaches_report_agent() -> None:
    cache = FakeCache()
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent(
            "ReconAgent",
            status=AgentStatus.TIMEOUT,
            error="Timed out after 1.0s",
        ),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report = _report()
    report_agent = FakeReportAgent(
        AgentResult(
            agent_name="ReportAgent",
            status=AgentStatus.SUCCESS,
            data=report,
        )
    )
    report_inputs: list[tuple[AgentResult, AgentResult, AgentResult]] = []

    async def _release_agents() -> None:
        await asyncio.gather(*(agent.started.wait() for agent in agents))
        for agent in agents:
            agent.release.set()

    def _build_report_agent(
        recon: AgentResult,
        reputation: AgentResult,
        shodan: AgentResult,
    ) -> FakeReportAgent:
        report_inputs.append((recon, reputation, shodan))
        return report_agent

    orchestrator._build_report_agent = _build_report_agent
    releaser = asyncio.create_task(_release_agents())

    result = await orchestrator.investigate("example.com")

    await releaser
    assert result is report
    assert report_inputs[0][0].status == AgentStatus.TIMEOUT
    assert report_inputs[0][0].error == "Timed out after 1.0s"
    assert cache.writes == [("example.com", report)]


@pytest.mark.asyncio
async def test_investigate_cache_write_failure_is_not_hidden() -> None:
    cache = FakeCache(write_exc=RuntimeError("cache locked"))
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report_agent = FakeReportAgent(
        AgentResult(
            agent_name="ReportAgent",
            status=AgentStatus.SUCCESS,
            data=_report(),
        )
    )

    async def _release_agents() -> None:
        await asyncio.gather(*(agent.started.wait() for agent in agents))
        for agent in agents:
            agent.release.set()

    orchestrator._build_report_agent = lambda *args: report_agent
    releaser = asyncio.create_task(_release_agents())

    with pytest.raises(RuntimeError, match="cache locked"):
        await orchestrator.investigate("example.com")

    await releaser
    assert cache.writes == []


@pytest.mark.asyncio
async def test_concurrent_same_target_calls_both_run_full_pipeline() -> None:
    cache = FakeCache()
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent"),
        FakeAgent("ShodanAgent"),
    ]
    for agent in agents:
        agent.release.set()
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]
    report_agents: list[FakeReportAgent] = []

    def _build_report_agent(*args) -> FakeReportAgent:
        report_agent = FakeReportAgent(
            AgentResult(
                agent_name="ReportAgent",
                status=AgentStatus.SUCCESS,
                data=_report(),
            )
        )
        report_agents.append(report_agent)
        return report_agent

    orchestrator._build_report_agent = _build_report_agent

    first, second = await asyncio.gather(
        orchestrator.investigate("example.com"),
        orchestrator.investigate("example.com"),
    )

    assert first == _report()
    assert second == _report()
    assert cache.requested_targets == ["example.com", "example.com"]
    assert [agent.targets for agent in agents] == [
        ["example.com", "example.com"],
        ["example.com", "example.com"],
        ["example.com", "example.com"],
    ]
    assert len(report_agents) == 2
    assert len(cache.writes) == 2


@pytest.mark.asyncio
async def test_run_data_agents_normalizes_unexpected_gather_exceptions() -> None:
    cache = FakeCache()
    orchestrator = MCPOrchestrator(cache=cache)
    agents = [
        FakeAgent("ReconAgent"),
        FakeAgent("ReputationAgent", raise_exc=RuntimeError("boom")),
        FakeAgent("ShodanAgent"),
    ]
    orchestrator._recon = agents[0]
    orchestrator._reputation = agents[1]
    orchestrator._shodan = agents[2]

    async def _release_agents() -> None:
        await asyncio.gather(*(agent.started.wait() for agent in agents))
        for agent in agents:
            agent.release.set()

    releaser = asyncio.create_task(_release_agents())
    recon, reputation, shodan = await orchestrator._run_data_agents("example.com")
    await releaser

    assert recon.status == AgentStatus.SUCCESS
    assert reputation == AgentResult(
        agent_name="ReputationAgent",
        status=AgentStatus.FAILED,
        error="boom",
    )
    assert shodan.status == AgentStatus.SUCCESS
