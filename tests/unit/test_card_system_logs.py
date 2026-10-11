"""Pipeline card with live system-log ingestion (option C).

Uploads and system batches that raise alerts or fail are shown on the
graph and recorded for replay; routine system batches only update a quiet
"System logs: live" line.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.schemas import (
    PIPELINE_STAGES,
    SOURCE_SYSTEM_LOGS,
    SOURCE_UPLOAD,
    StageEvent,
)
from soc_copilot.phase4.ui.pipeline_card import STEP_MS, PipelineCard
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy

T0 = datetime(2026, 10, 12, 0, 49, 22)


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def card(qapp, tmp_path):
    s = QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat)
    ThemeManager.instance().load_preferences(s)
    widget = PipelineCard(s)
    widget.resize(1200, 260)
    widget.show()
    yield widget
    destroy(widget)


def batch(batch_id, source, label="", records=7, alerts=0, failed=None, t0=T0):
    origin = {"source": source, "source_label": label}
    events = [StageEvent(batch_id=batch_id, stage="ingest", status="active", data=origin, timestamp=t0),
              StageEvent(batch_id=batch_id, stage="ingest", status="done",
                         data={"records": records, **origin}, timestamp=t0)]
    for i, stage in enumerate(PIPELINE_STAGES[1:-2], 1):
        status = "failed" if stage == failed else "done"
        events.append(StageEvent(batch_id=batch_id, stage=stage, status=status, timestamp=t0))
    events.append(StageEvent(batch_id=batch_id, stage="alerts", status="done",
                             data={"alerts": alerts}, timestamp=t0))
    events.append(StageEvent(batch_id=batch_id, stage="store", status="done", timestamp=t0,
                             data={"records": records, "alerts": alerts, "seconds": 0.1}))
    return events


def feed(card, events):
    for e in events:
        card.on_stage_event(e)


class TestRoutineSystemBatches:
    def test_only_update_the_live_line(self, card):
        feed(card, batch("sys1", SOURCE_SYSTEM_LOGS))
        assert card.graph.batch_id is None  # graph untouched
        assert card.summary_label.text() == "Waiting for logs"
        assert not card.live_label.isHidden()
        assert card.live_status == "System logs: live · 7 events at 00:49:22 · no alerts"
        assert card.recent_runs() == []

    def test_upload_stays_on_the_graph(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "linux_auth.log", records=1240, alerts=3))
        for i in range(10):
            feed(card, batch(f"sys{i}", SOURCE_SYSTEM_LOGS, t0=T0 + timedelta(seconds=5 * i)))
        assert card.graph.batch_id == "up1"
        assert card.summary_label.text() == (
            "Last run 00:49:22 · linux_auth.log · 1,240 logs · 3 alerts · 0.1 s")
        assert [r["id"] for r in card.recent_runs()] == ["up1"]
        assert "00:50:07" in card.live_status  # latest system batch

    def test_routine_batch_does_not_interrupt_replay(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "a.log"))
        card.replay(0)
        pending = card.pending_events
        feed(card, batch("sys1", SOURCE_SYSTEM_LOGS))
        assert card.pending_events == pending and card.is_replay(card.graph.batch_id)

    def test_live_line_hidden_until_first_system_batch(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "a.log"))
        assert card.live_label.isHidden()

    def test_unfinished_batches_are_bounded(self, card):
        for i in range(20):  # e.g. an exception before the store stage
            card.on_stage_event(StageEvent(batch_id=f"x{i}", stage="ingest", status="active",
                                           data={"source": SOURCE_SYSTEM_LOGS}))
        assert len(card._pending_system) <= 5


class TestNotableSystemBatches:
    def test_alerting_batch_is_shown_and_recorded(self, card):
        feed(card, batch("sys1", SOURCE_SYSTEM_LOGS, "Windows event logs", alerts=2))
        assert card.graph.batch_id == "sys1"
        assert card.graph.status("store") == "done"
        assert "system logs" in card.summary_label.text()
        assert card.run_label(card.recent_runs()[0]) == "00:49:22 · system logs · 7 logs · 2 alerts"
        assert card.live_status.endswith("· 2 alerts")

    def test_failed_batch_is_shown(self, card):
        feed(card, batch("sys1", SOURCE_SYSTEM_LOGS, failed="detect"))
        assert card.graph.batch_id == "sys1"
        assert card.graph.status("detect") == "failed"
        assert card.live_status.endswith("analysis failed")

    def test_alerting_batch_takes_over_replay(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "a.log"))
        card.replay(0)
        feed(card, batch("sys1", SOURCE_SYSTEM_LOGS, alerts=1))
        assert card.graph.batch_id == "sys1" and card.pending_events == 0

    def test_kill_switch_block_is_notable(self, card):
        card.on_stage_event(StageEvent(batch_id="k", stage="ingest", status="blocked",
                                       data={"source": SOURCE_SYSTEM_LOGS}, timestamp=T0))
        assert card.graph.status("ingest") == "blocked"
        assert card.live_status.endswith("blocked by kill switch")


class TestUploads:
    def test_events_without_source_count_as_uploads(self, card):
        events = [StageEvent(batch_id="b", stage=s, status="done") for s in PIPELINE_STAGES]
        feed(card, events)
        assert card.graph.batch_id == "b" and len(card.recent_runs()) == 1

    def test_label_names_the_file(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "perimeter_firewall.csv", records=21, alerts=0))
        assert card.run_label(card.recent_runs()[0]) == "00:49:22 · perimeter_firewall.csv · 21 logs · 0 alerts"

    def test_replay_summary_keeps_file_name(self, card):
        feed(card, batch("up1", SOURCE_UPLOAD, "a.log"))
        card.replay(0)
        for _ in range(100):
            if card.pending_events == 0:
                break
            QTest.qWait(STEP_MS)
        QTest.qWait(STEP_MS * 2)
        assert card.summary_label.text().startswith("Replay · Last run 00:49:22 · a.log")


def test_live_line_does_not_make_the_card_taller(card):
    """It sits in the header, so the full graph still fits where it did."""
    before = card.full_height(1200)
    feed(card, batch("sys1", SOURCE_SYSTEM_LOGS))
    assert card.full_height(1200) == before


def test_long_live_text_is_elided(card):
    feed(card, batch("sys1", SOURCE_SYSTEM_LOGS, records=123456789, alerts=0))
    assert card.live_label.width() <= 300
    assert "123456789" in card.live_label.toolTip()  # full text in the tooltip


def test_controller_to_card_end_to_end(qapp, tmp_path, card):
    """Real controller + bridge: a system batch reaches only the live line."""
    from soc_copilot.phase4.controller.app_controller import AppController
    from soc_copilot.phase4.ui.controller_bridge import ControllerBridge

    controller = AppController(str(tmp_path / "models"))
    controller._pipeline = Mock()
    controller._text_log_classifier = None
    controller._flow_feature_names = set()
    bridge = ControllerBridge(controller)
    bridge.pipelineStageUpdated.connect(card.on_stage_event)

    controller.process_batch([{"raw_line": "Oct 12 00:49:22 host app: started"}],
                             source=SOURCE_SYSTEM_LOGS, source_label="Windows event logs")
    assert card.graph.batch_id is None
    assert card.live_status.startswith("System logs: live · 1 event at ")

    controller.process_batch([{"raw_line": "Oct 12 00:49:30 host app: ok"}],
                             source=SOURCE_UPLOAD, source_label="test.log")
    assert card.graph.status("store") == "done"
    assert "test.log" in card.summary_label.text()
    destroy(bridge)
