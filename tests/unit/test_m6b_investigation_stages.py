"""Milestone 6b step 2: MCPOrchestrator reports investigation progress.

on_stage(stage, status, detail) for lookup, recon, reputation, shodan and
report; the data agents run in parallel and report as each one finishes.
No network: agents, cache and provider status are doubles.
"""

from __future__ import annotations

import asyncio

import pytest

from soc_copilot.mcp.exceptions import AgentLookupError
from soc_copilot.mcp.models import AgentResult, AgentStatus, ThreatReport, ThreatSeverity
from soc_copilot.mcp.orchestrator import INVESTIGATION_STAGES, MCPOrchestrator
from soc_copilot.mcp.provider_registry import ProviderState, ProviderStatus

_PROVIDERS = (
    ("whois", "WHOIS (RDAP)", "ReconAgent"),
    ("geoip", "GeoIP (ipwho.is)", "ReconAgent"),
    ("abuseipdb", "AbuseIPDB", "ReputationAgent"),
    ("virustotal", "VirusTotal", "ReputationAgent"),
    ("shodan", "Shodan", "ShodanAgent"),
    ("report_llm", "Report LLM", "ReportAgent"),
)


def _statuses(missing=()):
    return [
        ProviderStatus(key, name, agent,
                       ProviderState.MISSING_KEY if key in missing else ProviderState.CONFIGURED,
                       detail="no API key" if key in missing else "")
        for key, name, agent in _PROVIDERS
    ]


@pytest.fixture()
def online(monkeypatch):
    monkeypatch.setattr("soc_copilot.mcp.orchestrator.online_enrichment_enabled", lambda: True)
    monkeypatch.setattr("soc_copilot.mcp.orchestrator.get_provider_statuses", _statuses)


class Cache:
    def __init__(self, report=None):
        self.report = report

    def get_report(self, target):
        return self.report

    def set_report(self, target, report):
        pass


class Agent:
    """Finishes when released, so tests control the finishing order."""

    def __init__(self, name, status=AgentStatus.SUCCESS, error=None, raise_exc=None):
        self.name, self.status, self.error, self.raise_exc = name, status, error, raise_exc
        self.release = asyncio.Event()

    async def safe_execute(self, target):
        await self.release.wait()
        if self.raise_exc:
            raise self.raise_exc
        return AgentResult(agent_name=self.name, status=self.status, error=self.error)


def _report(target="example.com"):
    return ThreatReport(target=target, severity=ThreatSeverity.HIGH, summary="test")


def _orchestrator(cache=None, report_result=None, **agents):
    o = MCPOrchestrator(cache=cache or Cache())
    o._recon = agents.get("recon") or Agent("ReconAgent")
    o._reputation = agents.get("reputation") or Agent("ReputationAgent")
    o._shodan = agents.get("shodan") or Agent("ShodanAgent")
    for agent in (o._recon, o._reputation, o._shodan):
        agent.release.set()
    result = report_result or AgentResult(
        agent_name="ReportAgent", status=AgentStatus.SUCCESS, data=_report()
    )

    class ReportAgent:
        async def safe_execute(self, target):
            return result

    o._build_report_agent = lambda *a: ReportAgent()
    return o


def _run(o, target="example.com"):
    """Events are reported even when the investigation itself fails
    (no report and no agent data raises AgentLookupError, shown as an
    error in the drawer)."""
    events = []
    try:
        report = asyncio.run(o.investigate(target, on_stage=lambda *e: events.append(e)))
    except AgentLookupError:
        report = None
    return report, events


def _final(events):
    return {stage: status for stage, status, _ in events}


def _details(events):
    return {stage: detail for stage, status, detail in events if status != "active"}


class TestEarlyExits:
    def test_cache_hit(self, online):
        _, events = _run(_orchestrator(cache=Cache(_report())))
        assert events[0] == ("lookup", "active", "")
        assert _final(events) == {"lookup": "done", "recon": "skipped", "reputation": "skipped",
                                  "shodan": "skipped", "report": "skipped"}
        assert _details(events)["lookup"].startswith("Cached report")

    def test_internal_address(self, online):
        _, events = _run(_orchestrator(), target="192.168.1.22")
        assert _final(events)["recon"] == "skipped"
        assert "Internal address" in _details(events)["lookup"]

    def test_enrichment_off(self, monkeypatch):
        monkeypatch.setattr("soc_copilot.mcp.orchestrator.online_enrichment_enabled", lambda: False)
        _, events = _run(_orchestrator())
        assert "Online enrichment off" in _details(events)["lookup"]
        assert all(_final(events)[s] == "skipped" for s in INVESTIGATION_STAGES[1:])


class TestFullRun:
    def test_every_stage_in_order(self, online):
        report, events = _run(_orchestrator())
        assert report.severity == ThreatSeverity.HIGH
        assert events[0] == ("lookup", "active", "")
        assert ("lookup", "done", "External target: enrichment on") in events
        assert list(dict.fromkeys(s for s, *_ in events)) == list(INVESTIGATION_STAGES)
        assert _final(events) == dict.fromkeys(INVESTIGATION_STAGES, "done")
        assert events[-1] == ("report", "done", "")

    def test_agents_start_together_and_finish_independently(self, online):
        recon, rep, shodan = Agent("ReconAgent"), Agent("ReputationAgent"), Agent("ShodanAgent")
        o = _orchestrator(recon=recon, reputation=rep, shodan=shodan)
        for a in (recon, rep, shodan):
            a.release.clear()
        events = []

        async def scenario():
            task = asyncio.create_task(o.investigate("example.com", on_stage=lambda *e: events.append(e)))
            for _ in range(5):
                await asyncio.sleep(0)
            started = [s for s, st, _ in events if st == "active"]
            for agent in (shodan, recon, rep):  # finish in this order
                agent.release.set()
                for _ in range(5):
                    await asyncio.sleep(0)
            await task
            return started

        started = asyncio.run(scenario())
        assert started == ["lookup", "recon", "reputation", "shodan"]
        done = [s for s, st, _ in events if st == "done" and s in ("recon", "reputation", "shodan")]
        assert done == ["shodan", "recon", "reputation"]


class TestAgentOutcomes:
    def test_unusable_providers_are_skipped(self, online, monkeypatch):
        monkeypatch.setattr("soc_copilot.mcp.orchestrator.get_provider_statuses",
                            lambda: _statuses(missing=("shodan", "report_llm")))
        _, events = _run(_orchestrator())
        final, details = _final(events), _details(events)
        assert final["shodan"] == "skipped" and "no API key" in details["shodan"]
        assert final["report"] == "skipped"
        assert ("shodan", "active", "") not in events

    def test_timeouts(self, online):
        o = _orchestrator(
            shodan=Agent("ShodanAgent", AgentStatus.TIMEOUT, "Timed out after 10.0s"),
            report_result=AgentResult(agent_name="ReportAgent", status=AgentStatus.TIMEOUT,
                                      error="Timed out after 30.0s"),
        )
        _, events = _run(o)
        assert _final(events)["shodan"] == "timeout"
        assert _details(events)["shodan"] == "Timed out after 10.0s"
        assert _final(events)["report"] == "timeout"

    def test_partial_and_failed_agents(self, online):
        o = _orchestrator(
            recon=Agent("ReconAgent", AgentStatus.PARTIAL, "GeoIP rate limited"),
            reputation=Agent("ReputationAgent", AgentStatus.FAILED, "HTTP 500"),
        )
        _, events = _run(o)
        assert _final(events)["recon"] == "done"
        assert _details(events)["recon"] == "Partial data: GeoIP rate limited"
        assert _final(events)["reputation"] == "failed"
        assert _details(events)["reputation"] == "HTTP 500"

    def test_agent_exception_reported_and_investigation_continues(self, online):
        o = _orchestrator(recon=Agent("ReconAgent", raise_exc=RuntimeError("boom")))
        report, events = _run(o)
        assert _final(events)["recon"] == "failed"
        assert _details(events)["recon"] == "boom"
        assert report is not None


def test_failing_hook_does_not_break_investigation(online):
    def bad(*_):
        raise RuntimeError("listener bug")

    report = asyncio.run(_orchestrator().investigate("example.com", on_stage=bad))
    assert report.severity == ThreatSeverity.HIGH


def test_default_has_no_hook(online):
    report = asyncio.run(_orchestrator().investigate("example.com"))
    assert report.severity == ThreatSeverity.HIGH
