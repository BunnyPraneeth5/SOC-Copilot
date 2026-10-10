"""Tests for Milestone 6a step 4: Pipeline card on the dashboard."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.controller.schemas import PIPELINE_STAGES, StageEvent
from soc_copilot.phase4.ui import pipeline_card as card_mod
from soc_copilot.phase4.ui import pipeline_graph as graph_mod
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
from soc_copilot.phase4.ui.dashboard_v2 import Dashboard
from soc_copilot.phase4.ui.pipeline_card import (
    FULL,
    KEY_ML_COLLAPSED,
    KEY_VIEW,
    STEP_MS,
    STRIP,
    PipelineCard,
)
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(qapp, tmp_path):
    s = QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)
    ThemeManager.instance().load_preferences(s)
    return s


@pytest.fixture()
def card(settings):
    widget = PipelineCard(settings)
    widget.resize(1200, 240)
    widget.show()  # resize events reach shown widgets only
    yield widget
    destroy(widget)


@pytest.fixture()
def motion(monkeypatch):
    """Force motion on (offscreen normally disables it)."""
    monkeypatch.setattr(card_mod, "motion_enabled", lambda *_: True)
    monkeypatch.setattr(graph_mod, "motion_enabled", lambda *_: True)


def ev(stage, status, detail="", data=None, batch="b1"):
    return StageEvent(
        batch_id=batch, stage=stage, status=status, detail=detail,
        data=data or {}, timestamp=datetime(2026, 10, 10, 12, 4, 31),
    )


def run(batch="b1", records=1240, alerts=3, seconds=0.84):
    events = [ev(s, "done", batch=batch) for s in PIPELINE_STAGES[:-1]]
    events.append(ev("store", "done", batch=batch, data={
        "records": records, "alerts": alerts, "seconds": seconds}))
    return events


class TestView:
    def test_defaults_to_automatic_full(self, card):
        assert card.view_preference == "auto"
        assert card.view == FULL
        assert not card.graph.isHidden() and card.strip.isHidden()

    def test_auto_view_follows_dashboard(self, card):
        card.set_auto_view(STRIP)
        assert card.view == STRIP
        assert card.graph.isHidden() and not card.strip.isHidden()
        card.set_auto_view(FULL)
        assert card.view == FULL

    def test_user_choice_is_saved_and_wins(self, card, settings):
        card._on_toggle_clicked()
        assert card.view == STRIP
        assert settings.value(KEY_VIEW) == STRIP
        card.set_auto_view(FULL)  # dashboard resize no longer overrides
        assert card.view == STRIP

    def test_saved_choice_restored(self, settings):
        settings.setValue(KEY_VIEW, STRIP)
        widget = PipelineCard(settings)
        assert widget.view == STRIP
        widget.set_auto_view(FULL)
        assert widget.view == STRIP
        destroy(widget)

    def test_toggle_button_describes_action(self, card):
        assert card.toggle_btn.accessibleName() == "Show compact view"
        card._on_toggle_clicked()
        assert card.toggle_btn.accessibleName() == "Show pipeline graph"

    def test_graph_has_no_minimum_height(self, card):
        """The graph must never stop the window from shrinking."""
        assert card.graph.minimumHeight() == 0
        assert card.graph.maximumHeight() <= card_mod.GRAPH_MAX_H


class TestMlGroupPreference:
    def test_narrow_card_collapses_automatically(self, card, settings):
        card.resize(700, 200)
        assert card.graph.ml_collapsed
        card.resize(1200, 240)
        assert not card.graph.ml_collapsed
        assert settings.value(KEY_ML_COLLAPSED) is None  # not a user choice

    def test_user_toggle_saved_and_wins(self, card, settings):
        card.graph.group_frame._on_click()  # user collapses
        assert settings.value(KEY_ML_COLLAPSED) in (True, "true")
        card.resize(1300, 240)
        assert card.graph.ml_collapsed

    def test_saved_preference_restored(self, settings):
        settings.setValue(KEY_ML_COLLAPSED, True)
        widget = PipelineCard(settings)
        widget.resize(1300, 240)
        widget.show()
        assert widget.graph.ml_collapsed
        destroy(widget)


class TestSummary:
    def test_waiting(self, card):
        assert card.summary_label.text() == "Waiting for logs"

    def test_running(self, card):
        card.on_stage_event(ev("ingest", "done"))
        card.on_stage_event(ev("text_detect", "active"))
        assert card.summary_label.text() == "Running · Text ML"

    def test_between_stages_names_next(self, card):
        card.on_stage_event(ev("ingest", "done"))
        assert card.summary_label.text() == "Running · Text ML"

    def test_last_run(self, card):
        for e in run():
            card.on_stage_event(e)
        assert card.summary_label.text() == (
            "Last run 12:04:31 · 1,240 logs · 3 alerts · 0.8 s"
        )

    def test_single_alert_wording(self, card):
        for e in run(alerts=1):
            card.on_stage_event(e)
        assert "· 1 alert ·" in card.summary_label.text()

    def test_blocked(self, card):
        card.on_stage_event(ev("ingest", "blocked", "Kill switch active"))
        assert card.summary_label.text() == "Blocked · kill switch is on"

    def test_batch_dropped(self, card):
        card.on_stage_event(ev("detect", "failed", "boom"))
        card.on_stage_event(ev("alerts", "skipped"))
        card.on_stage_event(ev("store", "skipped"))
        assert card.summary_label.text() == (
            "Last run 12:04:31 · ML step failed, batch dropped"
        )

    def test_failed_but_stored(self, card):
        events = run()
        events[6] = ev("detect", "failed", "boom")
        for e in events:
            card.on_stage_event(e)
        assert card.summary_label.text().endswith("· ML step failed")

    def test_new_run_forgets_previous_totals(self, card):
        for e in run(batch="b1"):
            card.on_stage_event(e)
        card.on_stage_event(ev("ingest", "active", batch="b2"))
        assert card.summary_label.text() == "Running · Ingest"

    def test_strip_mirrors_graph(self, card):
        card.on_stage_event(ev("ingest", "done"))
        card.on_stage_event(ev("preprocess", "skipped"))
        assert card.strip.status("ingest") == "done"
        assert card.strip.status("preprocess") == "skipped"
        assert "Ingest: Done" in card.strip.toolTip()


class TestPlayback:
    def test_reduce_motion_applies_instantly(self, card):
        for e in run():
            card.on_stage_event(e)
        assert card.pending_events == 0
        assert card.graph.status("store") == "done"
        assert not card.graph.is_fading()

    def test_events_get_minimum_time_on_screen(self, card, motion):
        events = run()
        for e in events:
            card.on_stage_event(e)
        assert card.graph.status("ingest") == "done"  # first one at once
        assert card.graph.status("store") == "idle"
        assert card.pending_events == len(events) - 1
        for _ in range(100):
            if card.pending_events == 0:
                break
            QTest.qWait(STEP_MS)
        QTest.qWait(STEP_MS * 2)
        assert card.graph.status("store") == "done"

    def test_newer_run_drops_old_backlog(self, card, motion):
        for e in run(batch="b1"):
            card.on_stage_event(e)
        card.on_stage_event(ev("ingest", "active", batch="b2"))
        assert card.pending_events == 1
        assert all(e.batch_id == "b2" for e in card._queue)

    def test_switching_motion_off_flushes_queue(self, card, motion, monkeypatch):
        for e in run():
            card.on_stage_event(e)
        monkeypatch.setattr(card_mod, "motion_enabled", lambda *_: False)
        card.on_stage_event(ev("ingest", "active", batch="b2"))
        assert card.pending_events == 0
        assert card.graph.batch_id == "b2"

    def test_nodes_fade_when_motion_on(self, card, motion):
        card.on_stage_event(ev("ingest", "active"))
        assert card.graph.nodes["ingest"].fading

    def test_destroy_with_pending_playback_is_safe(self, settings, motion):
        widget = PipelineCard(settings)
        for e in run():
            widget.on_stage_event(e)
        destroy(widget)
        QTest.qWait(STEP_MS * 3)


class TestDashboard:
    @pytest.fixture()
    def dashboard(self, settings, tmp_path):
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        controller._text_log_classifier = None
        controller._flow_feature_names = set()
        bridge = ControllerBridge(controller)
        page = Dashboard(bridge)
        page.show()  # resize events reach shown widgets only
        yield page, controller
        destroy(page, bridge)

    def test_card_sits_between_metrics_and_alerts(self, dashboard):
        page, _ = dashboard
        lay = page.layout()
        order = [lay.itemAt(i).widget() for i in range(lay.count())]
        i = order.index(page.pipeline_card)
        assert order[i - 1] is page.metrics_row
        assert order[i + 1] is page.alerts_timeline

    def test_batch_updates_card(self, dashboard):
        page, controller = dashboard
        controller.process_batch([{"raw_line": "Jan 18 02:56:01 host sshd[1]: test"}])
        assert page.pipeline_card.graph.status("store") == "done"
        assert page.pipeline_card.summary_label.text().startswith("Last run")

    def test_tall_page_shows_graph_short_page_shows_strip(self, dashboard):
        page, _ = dashboard
        page.resize(1250, 900)
        assert page.pipeline_card.view == FULL
        page.resize(1250, 560)
        assert page.pipeline_card.view == STRIP

    def test_full_view_keeps_five_alert_rows(self, dashboard):
        page, _ = dashboard
        page.resize(1250, 900)
        QApplication.processEvents()
        assert page.pipeline_card.view == FULL
        table = page.alerts_timeline.table
        rows_visible = (table.height() - table.horizontalHeader().height()) // 36
        assert rows_visible >= Dashboard.MIN_ALERT_ROWS
