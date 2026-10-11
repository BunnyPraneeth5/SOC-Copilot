"""Milestone 6b step 3: investigation progress reaches the UI thread.

InvestigationWorker wraps each orchestrator progress update in a StageEvent
with a per-run id; ControllerBridge relays it as investigationStageUpdated.
"""

import threading
from unittest.mock import Mock

import pytest
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.mcp.models import ThreatReport, ThreatSeverity
from soc_copilot.phase4.controller.schemas import StageEvent
from soc_copilot.phase4.ui.controller_bridge import (
    ControllerBridge,
    InvestigationSignals,
    InvestigationWorker,
)
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _report(target):
    return ThreatReport(target=target, severity=ThreatSeverity.LOW, summary="ok")


class FakeOrchestrator:
    """Reports the five stages like MCPOrchestrator, no network."""

    async def investigate(self, target, on_stage=None):
        for stage in ("lookup", "recon", "reputation", "shodan", "report"):
            on_stage(stage, "active", "")
            on_stage(stage, "done", f"{stage} ok")
        return _report(target)


class OldOrchestrator:
    """An orchestrator without the progress hook."""

    async def investigate(self, target):
        return _report(target)


def _run_worker(factory, target="example.com"):
    signals = InvestigationSignals()
    stages, reports = [], []
    signals.stageUpdated.connect(lambda t, e: stages.append((t, e)))
    signals.reportReady.connect(lambda t, r, err: reports.append((t, r, err)))
    worker = InvestigationWorker(target, signals, orchestrator_factory=factory)
    worker.run()  # synchronous, current thread
    return worker, stages, reports


class TestWorker:
    def test_progress_wrapped_in_stage_events(self, qapp):
        worker, stages, reports = _run_worker(FakeOrchestrator)
        assert len(stages) == 10
        assert all(t == "example.com" and isinstance(e, StageEvent) for t, e in stages)
        assert {e.batch_id for _, e in stages} == {worker.investigation_id}
        assert (stages[1][1].stage, stages[1][1].status, stages[1][1].detail) == (
            "lookup", "done", "lookup ok")
        assert reports[0][1].target == "example.com" and reports[0][2] is None

    def test_each_run_has_its_own_id(self, qapp):
        first, _, _ = _run_worker(FakeOrchestrator)
        second, _, _ = _run_worker(FakeOrchestrator)
        assert first.investigation_id != second.investigation_id

    def test_orchestrator_without_hook_still_works(self, qapp):
        _, stages, reports = _run_worker(OldOrchestrator)
        assert stages == []
        assert reports[0][1].target == "example.com"


class TestBridgeRelay:
    def test_events_reach_ui_thread_before_report(self, qapp):
        bridge = ControllerBridge(Mock(spec=object), orchestrator_factory=FakeOrchestrator)
        order, threads = [], set()

        def on_stage(target, event):
            threads.add(threading.current_thread())
            order.append(("stage", event.stage, event.status))

        bridge.investigationStageUpdated.connect(on_stage)
        bridge.reportReady.connect(lambda t, r, e: order.append(("report", t)))

        assert bridge.investigate_target("Example.com")
        for _ in range(100):
            if order and order[-1][0] == "report":
                break
            QTest.qWait(20)

        assert order[-1] == ("report", "example.com")
        stage_events = [o for o in order if o[0] == "stage"]
        assert len(stage_events) == 10
        assert stage_events[0] == ("stage", "lookup", "active")
        assert threads == {threading.main_thread()}
        assert not bridge.is_investigation_in_flight("example.com")
        destroy(bridge)
