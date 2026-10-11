"""Milestone 6b step 6: replay recent runs on the dashboard Pipeline card."""

from datetime import datetime, timedelta

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.schemas import PIPELINE_STAGES, StageEvent
from soc_copilot.phase4.ui.pipeline_card import MAX_RUNS, STEP_MS, PipelineCard
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy

T0 = datetime(2026, 10, 12, 21, 9, 43)


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def card(qapp, tmp_path):
    s = QSettings(str(tmp_path / "p.ini"), QSettings.Format.IniFormat)
    ThemeManager.instance().load_preferences(s)
    widget = PipelineCard(s)
    widget.resize(1200, 240)
    widget.show()
    yield widget
    destroy(widget)


def run(batch, records=1240, alerts=3, t0=T0):
    events = [StageEvent(batch_id=batch, stage=s, status="done", timestamp=t0 + timedelta(seconds=i))
              for i, s in enumerate(PIPELINE_STAGES[:-1])]
    events.append(StageEvent(batch_id=batch, stage="store", status="done",
                             data={"records": records, "alerts": alerts, "seconds": 0.8},
                             timestamp=t0 + timedelta(seconds=9)))
    return events


def feed(card, events):
    for e in events:
        card.on_stage_event(e)  # offscreen: applied at once


def drain(card):
    for _ in range(200):
        if card.pending_events == 0:
            break
        QTest.qWait(STEP_MS)


class TestRecording:
    def test_runs_recorded_newest_first(self, card):
        feed(card, run("b1"))
        feed(card, run("b2", records=10, alerts=1, t0=T0 + timedelta(minutes=5)))
        runs = card.recent_runs()
        assert [r["id"] for r in runs] == ["b2", "b1"]
        assert len(runs[1]["events"]) == len(PIPELINE_STAGES)

    def test_keeps_last_twenty(self, card):
        for i in range(MAX_RUNS + 5):
            feed(card, run(f"b{i}"))
        runs = card.recent_runs()
        assert len(runs) == MAX_RUNS and runs[0]["id"] == f"b{MAX_RUNS + 4}"

    def test_labels(self, card):
        feed(card, run("b1"))
        assert card.run_label(card.recent_runs()[0]) == "21:09:43 · 1,240 logs · 3 alerts"
        blocked = {"id": "k", "events": [StageEvent(batch_id="k", stage="ingest", status="blocked", timestamp=T0)]}
        assert card.run_label(blocked) == "21:09:43 · blocked by kill switch"
        partial = {"id": "p", "events": run("p")[:3]}
        assert card.run_label(partial).endswith("incomplete")


class TestReplay:
    def test_replays_step_by_step_even_without_motion(self, card):
        feed(card, run("b1"))
        assert card.replay(0)
        # offscreen = no motion, yet the replay still steps
        assert card.graph.status("ingest") == "done"
        assert card.graph.status("store") == "idle"
        assert card.pending_events == len(PIPELINE_STAGES) - 1
        assert card.summary_label.text().startswith("Replay · ")
        drain(card)
        QTest.qWait(STEP_MS * 2)
        assert card.graph.status("store") == "done"
        assert card.summary_label.text() == "Replay · Last run 21:09:52 · 1,240 logs · 3 alerts · 0.8 s"
        assert not card.graph.is_fading()

    def test_replay_restarts_graph_each_time(self, card):
        feed(card, run("b1"))
        card.replay(0)
        first = card.graph.batch_id
        card.replay(0)
        assert card.graph.batch_id != first
        assert card.graph.status("store") == "idle"

    def test_older_run(self, card):
        feed(card, run("b1", records=5))
        feed(card, run("b2", records=9))
        card.replay(1)
        drain(card)
        QTest.qWait(STEP_MS * 2)
        assert "5 logs" in card.summary_label.text()

    def test_live_run_takes_over(self, card):
        feed(card, run("b1"))
        card.replay(0)
        assert card.pending_events > 0
        card.on_stage_event(StageEvent(batch_id="live", stage="ingest", status="active"))
        assert card.pending_events == 0
        assert card.graph.batch_id == "live"
        assert not card.summary_label.text().startswith("Replay")

    def test_replay_is_not_recorded(self, card):
        feed(card, run("b1"))
        card.replay(0)
        drain(card)
        assert [r["id"] for r in card.recent_runs()] == ["b1"]

    def test_nothing_to_replay(self, card):
        assert card.replay(0) is False
        assert card.replay(5) is False


class TestMenu:
    def test_empty_menu(self, card):
        actions = card.build_replay_menu().actions()
        assert len(actions) == 1 and not actions[0].isEnabled()

    def test_menu_lists_runs_and_replays(self, card):
        feed(card, run("b1", records=5))
        feed(card, run("b2", records=9))
        actions = card.build_replay_menu().actions()
        assert [a.text() for a in actions] == [
            "Replay last run · 21:09:43 · 9 logs · 3 alerts",
            "21:09:43 · 5 logs · 3 alerts",
        ]
        actions[1].trigger()
        assert card.is_replay(card.graph.batch_id)
        assert card.graph.batch_id.startswith("b1")

    def test_button_opens_menu_without_blocking(self, card):
        feed(card, run("b1"))
        card.replay_btn.click()  # popup(), not exec(): returns at once
        assert card._replay_menu is not None
        card._replay_menu.close()

    def test_button_has_accessible_name(self, card):
        assert card.replay_btn.accessibleName() == "Replay a recent run"
