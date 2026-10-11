"""Milestone 6b step 4: investigation steps graph in the report drawer."""

from datetime import datetime, timedelta

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from soc_copilot.mcp.models import ThreatReport, ThreatSeverity
from soc_copilot.phase4.controller.schemas import StageEvent
from soc_copilot.phase4.ui.investigation_graph import (
    INVESTIGATION_GRAPH,
    KEY_COLLAPSED,
    InvestigationGraphPanel,
    summarize,
)
from soc_copilot.phase4.ui.pipeline_graph import (
    STATUS_TEXT,
    STATUS_TOKEN,
    TIMEOUT,
    aggregate_status,
)
from soc_copilot.phase4.ui.report_drawer import ReportDrawer
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy

T0 = datetime(2026, 10, 12, 21, 14, 0)
TARGET = "185.220.101.45"


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(qapp, tmp_path):
    s = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    ThemeManager.instance().load_preferences(s)
    return s


def ev(stage, status, detail="", t=0.0, run="r1"):
    return StageEvent(batch_id=run, stage=stage, status=status, detail=detail,
                      timestamp=T0 + timedelta(seconds=t))


def full_run(run="r1"):
    return [ev("lookup", "active", run=run),
            ev("lookup", "done", "External target: enrichment on", 0.1, run),
            *[ev(s, "active", t=0.1, run=run) for s in ("recon", "reputation", "shodan")],
            *[ev(s, "done", t=1.0 + i, run=run) for i, s in enumerate(("recon", "reputation", "shodan"))],
            ev("report", "active", t=3.0, run=run), ev("report", "done", t=12.5, run=run)]


def _report(target=TARGET):
    return ThreatReport(target=target, severity=ThreatSeverity.HIGH, summary="s",
                        generated_at=T0)


class TestTimedOutStatus:
    def test_text_and_colour(self):
        assert STATUS_TEXT[TIMEOUT] == "Timed out"
        assert STATUS_TOKEN[TIMEOUT] == "warning"

    def test_group_aggregate(self):
        assert aggregate_status(["done", "timeout", "skipped"]) == "timeout"
        assert aggregate_status(["timeout", "failed"]) == "failed"


class TestGraphSpec:
    def test_stages_match_orchestrator(self):
        from soc_copilot.mcp.orchestrator import INVESTIGATION_STAGES
        assert tuple(s.key for s in INVESTIGATION_GRAPH.stages) == INVESTIGATION_STAGES

    def test_agents_run_in_parallel_into_report(self):
        edges = set(INVESTIGATION_GRAPH.edges)
        for agent in ("recon", "reputation", "shodan"):
            assert ("lookup", agent) in edges and (agent, "report") in edges


class TestSummary:
    def _statuses(self, **kw):
        base = dict.fromkeys(("lookup", "recon", "reputation", "shodan", "report"), "idle")
        base.update(kw)
        return base

    def test_waiting(self):
        assert summarize(self._statuses()) == "Waiting for the first step"

    def test_running_lists_active_steps(self):
        s = self._statuses(lookup="done", recon="done", reputation="active", shodan="active")
        assert summarize(s) == "Running · Reputation, Shodan"

    def test_early_exit_uses_lookup_reason(self):
        s = self._statuses(lookup="done", recon="skipped", reputation="skipped",
                           shodan="skipped", report="skipped")
        assert summarize(s, "Online enrichment off: local-only report") == \
            "Online enrichment off: local-only report"

    def test_finished_with_problems(self):
        s = self._statuses(lookup="done", recon="done", reputation="skipped",
                           shodan="timeout", report="done")
        assert summarize(s, seconds=22.94) == "Finished in 22.9 s · 1 timed out · 1 skipped"

    def test_report_timed_out(self):
        s = self._statuses(lookup="done", recon="done", reputation="failed",
                           shodan="done", report="timeout")
        assert summarize(s, seconds=33.1) == "Report timed out in 33.1 s · 1 failed"


class TestPanel:
    @pytest.fixture()
    def panel(self, settings):
        widget = InvestigationGraphPanel(settings)
        widget.resize(420, 200)
        widget.show()
        yield widget
        destroy(widget)

    def test_events_drive_graph_and_summary(self, panel):
        for e in full_run():
            panel.apply_event(e)
        assert panel.graph.status("report") == "done"
        assert panel.summary_label.text() == "Finished in 12.5 s"
        assert len(panel.events) == len(full_run())

    def test_new_run_replaces_old_one(self, panel):
        for e in full_run("r1"):
            panel.apply_event(e)
        panel.apply_event(ev("lookup", "active", run="r2"))
        assert panel.events == [ev("lookup", "active", run="r2")]
        assert panel.graph.status("report") == "idle"

    def test_start_clears(self, panel):
        for e in full_run():
            panel.apply_event(e)
        panel.start()
        assert panel.events == [] and panel.graph.batch_id is None

    def test_collapse_saved(self, panel, settings):
        panel._on_toggle()
        assert panel.collapsed and panel.graph.isHidden()
        assert settings.value(KEY_COLLAPSED) in (True, "true")
        again = InvestigationGraphPanel(settings)
        assert again.collapsed
        destroy(again)

    def test_show_events_is_instant(self, panel, monkeypatch):
        from soc_copilot.phase4.ui import pipeline_graph
        monkeypatch.setattr(pipeline_graph, "motion_enabled", lambda *_: True)
        panel.show_events(full_run())
        assert not panel.graph.is_fading()


class TestDrawer:
    @pytest.fixture()
    def drawer(self, settings):
        widget = ReportDrawer()
        widget.resize(440, 800)
        yield widget
        destroy(widget)

    def test_hidden_until_first_investigation(self, drawer):
        assert drawer.steps_panel.isHidden()
        drawer.show_loading(TARGET)
        assert not drawer.steps_panel.isHidden()

    def test_events_for_current_target_shown(self, drawer):
        drawer.show_loading(TARGET)
        assert not drawer._loading_bar.isHidden()
        drawer.on_investigation_stage(TARGET, ev("lookup", "active"))
        assert drawer.steps_panel.graph.status("lookup") == "active"
        assert drawer._loading_bar.isHidden()  # the graph shows progress now

    def test_target_compared_case_insensitively(self, drawer):
        drawer.show_loading("Example.COM")
        drawer.on_investigation_stage("example.com", ev("lookup", "active"))
        assert drawer.steps_panel.graph.status("lookup") == "active"

    def test_other_targets_ignored(self, drawer):
        drawer.show_loading(TARGET)
        drawer.on_investigation_stage("10.0.0.9", ev("lookup", "active"))
        assert drawer.steps_panel.graph.status("lookup") == "idle"

    def test_report_keeps_graph_and_history_keeps_events(self, drawer):
        drawer.show_loading(TARGET)
        for e in full_run():
            drawer.on_investigation_stage(TARGET, e)
        drawer.show_report(_report())
        assert not drawer.steps_panel.isHidden()
        assert drawer._history[0][2] == full_run()

    def test_history_restores_that_runs_graph(self, drawer):
        drawer.show_loading(TARGET)
        for e in full_run("r1"):
            drawer.on_investigation_stage(TARGET, e)
        drawer.show_report(_report())
        drawer.show_loading("example.com")
        drawer.on_investigation_stage("example.com", ev("lookup", "done", "Cached report", run="r2"))
        drawer.show_report(_report("example.com"))
        assert drawer.steps_panel.graph.batch_id == "r2"
        drawer._on_history_select(1)  # the first investigation
        assert drawer.steps_panel.graph.batch_id == "r1"
        assert drawer.steps_panel.graph.status("report") == "done"

    def test_report_without_steps_hides_panel(self, drawer):
        drawer.show_loading(TARGET)  # orchestrator reported no steps
        drawer.show_report(_report())
        assert drawer.steps_panel.isHidden()
        assert drawer._history[0][2] == []

    def test_error_keeps_graph(self, drawer):
        drawer.show_loading(TARGET)
        drawer.on_investigation_stage(TARGET, ev("report", "timeout", "Timed out after 30.0s"))
        drawer.show_error(TARGET, "no data")
        assert not drawer.steps_panel.isHidden()
        assert drawer.steps_panel.graph.status("report") == "timeout"


def test_main_window_wires_bridge_to_drawer(qapp, settings, tmp_path):
    from unittest.mock import Mock
    from soc_copilot.phase4.controller.app_controller import AppController
    from soc_copilot.phase4.ui.main_window import MainWindow

    controller = AppController(str(tmp_path / "models"))
    controller._pipeline = Mock()
    window = MainWindow(controller)
    window.report_drawer.show_loading(TARGET)
    window.bridge.investigationStageUpdated.emit(TARGET, ev("lookup", "active"))
    assert window.report_drawer.steps_panel.graph.status("lookup") == "active"
    destroy(window)
