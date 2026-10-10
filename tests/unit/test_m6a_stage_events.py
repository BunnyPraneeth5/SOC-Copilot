"""Tests for Milestone 6a: pipeline stage events (controller + pipeline hook)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from soc_copilot.core.base import ParsedRecord
from soc_copilot.phase4.controller import app_controller as app_controller_module
from soc_copilot.phase4.controller import schemas as schemas_module
from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.controller.schemas import (
    AlertSummary,
    FLOW_ML_STAGES,
    PIPELINE_STAGES,
    StageEvent,
)
from soc_copilot.pipeline import AnalysisStats, SOCCopilot


SSHD_FAIL = (
    "Jan 18 02:56:{sec:02d} server sshd[123]: Failed password for root "
    "from 45.67.89.101 port 22 ssh2"
)


def _batch(n=3):
    return [{"raw_line": SSHD_FAIL.format(sec=i)} for i in range(n)]


@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._pipeline = Mock()
    c._text_log_classifier = None
    c._flow_feature_names = set()  # text lines never route to the ML pipeline
    return c


@pytest.fixture()
def events(controller):
    received: list[StageEvent] = []
    controller.add_stage_listener(received.append)
    return received


def _pairs(events):
    return [(e.stage, e.status) for e in events]


def _final(events):
    """Last status per stage."""
    return {e.stage: e.status for e in events}


def _text_alert():
    return AlertSummary(
        alert_id="RULE-BF-test",
        priority="P1-High",
        classification="BruteForce",
        confidence=0.9,
        anomaly_score=0.0,
        risk_score=0.8,
        source_ip="45.67.89.101",
        destination_ip=None,
        timestamp=datetime.now(),
        reasoning="test",
        suggested_action="test",
    )


def _reporting_pipeline(fail_in=None):
    """Mock pipeline whose analyze_file reports ML stages like SOCCopilot."""
    pipeline = Mock()

    def analyze_file(path, on_stage=None):
        for stage in FLOW_ML_STAGES:
            on_stage(stage, "active", "")
            if stage == fail_in:
                raise RuntimeError("boom")
            on_stage(stage, "done", f"{stage} ok")
        stats = AnalysisStats()
        stats.total_records = 3
        return [], [], stats

    pipeline.analyze_file.side_effect = analyze_file
    return pipeline


# ---------------------------------------------------------------------------
# Controller stage events
# ---------------------------------------------------------------------------

class TestControllerStageEvents:
    def test_text_only_batch_skips_flow_lane(self, controller, events):
        result = controller.process_batch(_batch())

        assert result is not None
        assert {e.batch_id for e in events} == {result.batch_id}
        assert _pairs(events) == [
            ("ingest", "active"), ("ingest", "done"),
            ("text_detect", "active"), ("text_detect", "done"),
            ("bf_correlate", "active"), ("bf_correlate", "done"),
            ("flow_route", "active"), ("flow_route", "done"),
            ("preprocess", "skipped"),
            ("features", "skipped"),
            ("detect", "skipped"),
            ("alerts", "active"), ("alerts", "done"),
            ("store", "active"), ("store", "done"),
        ]
        assert controller._pipeline.analyze_file.call_count == 0

    def test_every_stage_is_reported_in_order(self, controller, events):
        controller.process_batch(_batch())
        first_seen = list(dict.fromkeys(e.stage for e in events))
        assert first_seen == list(PIPELINE_STAGES)

    def test_details_and_data(self, controller, events):
        result = controller.process_batch(_batch(3))
        done = {e.stage: e for e in events if e.status == "done"}

        assert done["ingest"].data == {"records": 3}
        assert done["text_detect"].detail.startswith("rules:")
        assert done["flow_route"].data == {"routed": 0, "other": 3}
        store = done["store"].data
        assert store["records"] == 3
        assert store["alerts"] == len(result.alerts)
        assert store["seconds"] >= 0

    def test_flow_batch_relays_pipeline_stages(self, controller, events):
        controller._flow_feature_names = None  # route every record
        controller._pipeline = _reporting_pipeline()

        controller.process_batch(_batch())

        ml = [(e.stage, e.status, e.detail) for e in events
              if e.stage in FLOW_ML_STAGES]
        assert ml == [
            ("preprocess", "active", ""), ("preprocess", "done", "preprocess ok"),
            ("features", "active", ""), ("features", "done", "features ok"),
            ("detect", "active", ""), ("detect", "done", "detect ok"),
        ]
        kwargs = controller._pipeline.analyze_file.call_args.kwargs
        assert callable(kwargs["on_stage"])

    def test_silent_pipeline_stages_marked_done(self, controller, events):
        """A pipeline that never calls on_stage still completes the graph."""
        controller._flow_feature_names = None
        stats = Mock()
        stats.total_records = 3
        stats.processed_records = 3
        stats.risk_distribution = {}
        stats.classification_distribution = {}
        controller._pipeline.analyze_file.return_value = ([], [], stats)

        controller.process_batch(_batch())

        final = _final(events)
        assert all(final[s] == "done" for s in FLOW_ML_STAGES)

    def test_nothing_parsed_marks_ml_skipped(self, controller, events):
        controller._flow_feature_names = None
        controller._pipeline.analyze_file.return_value = ([], [], AnalysisStats())

        controller.process_batch(_batch())

        final = _final(events)
        assert all(final[s] == "skipped" for s in FLOW_ML_STAGES)

    def test_ml_failure_fails_stage_and_batch_continues(self, controller, events):
        controller._flow_feature_names = None
        controller._pipeline = _reporting_pipeline(fail_in="features")
        controller._text_log_ml_detect = lambda _lines: [_text_alert()]

        result = controller.process_batch(_batch())

        final = _final(events)
        assert final["preprocess"] == "done"
        assert final["features"] == "failed"
        assert final["detect"] == "skipped"
        failed = [e for e in events if e.status == "failed"]
        assert failed[0].detail == "boom"
        # text/rule alerts are kept and stored, as before 6a
        assert result is not None
        assert final["store"] == "done"

    def test_ml_failure_without_text_alerts_skips_alerts_and_store(
        self, controller, events
    ):
        controller._flow_feature_names = None
        controller._pipeline = _reporting_pipeline(fail_in="detect")

        assert controller.process_batch(_batch()) is None

        final = _final(events)
        assert final["detect"] == "failed"
        assert final["alerts"] == "skipped"
        assert final["store"] == "skipped"
        assert "active" not in {final[s] for s in PIPELINE_STAGES}

    def test_ml_failure_before_any_report_fails_first_stage(self, controller, events):
        controller._flow_feature_names = None
        controller._pipeline.analyze_file.side_effect = RuntimeError("nope")

        controller.process_batch(_batch())

        final = _final(events)
        assert final["preprocess"] == "failed"
        assert final["features"] == "skipped"
        assert final["detect"] == "skipped"

    def test_kill_switch_blocks_ingest(self, tmp_path):
        c = AppController(str(tmp_path / "models"), killswitch_check=lambda: True)
        c._pipeline = Mock()
        received = []
        c.add_stage_listener(received.append)

        assert c.process_batch(_batch()) is None
        assert _pairs(received) == [("ingest", "blocked")]
        assert received[0].detail == "Kill switch active"

    def test_no_raw_lines_skips_ingest_only(self, controller, events):
        assert controller.process_batch([{"source": "x"}]) is None
        assert _pairs(events) == [("ingest", "active"), ("ingest", "skipped")]

    def test_empty_batch_under_kill_switch_is_silent(self, tmp_path):
        c = AppController(str(tmp_path / "models"), killswitch_check=lambda: True)
        received = []
        c.add_stage_listener(received.append)
        c.process_batch([])
        assert received == []

    def test_failing_listener_does_not_break_batch(self, controller, events):
        def bad(_event):
            raise RuntimeError("listener bug")

        controller.add_stage_listener(bad)
        result = controller.process_batch(_batch())

        assert result is not None
        assert _final(events)["store"] == "done"

    def test_remove_stage_listener(self, controller, events):
        controller.remove_stage_listener(events.append)
        controller.remove_stage_listener(events.append)  # no-op when absent
        controller.process_batch(_batch())
        assert events == []

    def test_batch_id_matches_stored_result(self, controller, events):
        result = controller.process_batch(_batch())
        assert controller.result_store.get_by_id(result.batch_id) is not None
        assert events[-1].batch_id == result.batch_id

    def test_events_are_immutable(self, controller, events):
        controller.process_batch(_batch())
        with pytest.raises(Exception):
            events[0].status = "done"


class TestControllerHasNoQtDependency:
    @pytest.mark.parametrize("module", [app_controller_module, schemas_module])
    def test_no_qt_import(self, module):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "PyQt" not in source


# ---------------------------------------------------------------------------
# SOCCopilot on_stage hook
# ---------------------------------------------------------------------------

def _stub_copilot(results=None):
    copilot = object.__new__(SOCCopilot)
    copilot._loaded = True
    copilot._feature_order = ["a", "b"]
    copilot._preprocessing = Mock()
    copilot._preprocessing.fit_transform.side_effect = lambda recs: pd.DataFrame(recs)
    copilot._features = Mock()
    copilot._features.transform.side_effect = lambda df: df
    copilot._analysis = Mock()
    copilot._analysis.analyze.return_value = results
    return copilot


def _records(n=2):
    return [
        ParsedRecord(timestamp="2026-01-01T00:00:00", raw={"a": i, "b": i})
        for i in range(n)
    ]


class TestPipelineStageHook:
    def test_reports_stages_in_order(self):
        calls = []
        _stub_copilot().analyze_records(
            _records(), on_stage=lambda *a: calls.append(a)
        )
        assert [(s, st) for s, st, _ in calls] == [
            ("preprocess", "active"), ("preprocess", "done"),
            ("features", "active"), ("features", "done"),
            ("detect", "active"), ("detect", "done"),
        ]
        details = {s: d for s, st, d in calls if st == "done"}
        assert details["preprocess"] == "2 of 2 records kept"
        assert details["features"] == "2 features"
        assert details["detect"] == "0 results, 0 alerts"

    def test_default_has_no_hook(self):
        results, alerts = _stub_copilot().analyze_records(_records())
        assert results == [] and alerts == []

    def test_empty_records_report_nothing(self):
        calls = []
        _stub_copilot().analyze_records([], on_stage=lambda *a: calls.append(a))
        assert calls == []

    def test_failing_hook_does_not_break_analysis(self):
        def bad(*_args):
            raise RuntimeError("hook bug")

        results, alerts = _stub_copilot().analyze_records(_records(), on_stage=bad)
        assert results == [] and alerts == []

    def test_analyze_file_passes_hook_through(self, tmp_path, monkeypatch):
        log = tmp_path / "x.jsonl"
        log.write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr(
            "soc_copilot.pipeline.parse_log_file", lambda _p: _records(1)
        )
        calls = []
        _stub_copilot().analyze_file(log, on_stage=lambda *a: calls.append(a))
        assert calls[0][:2] == ("preprocess", "active")
        assert calls[-1][:2] == ("detect", "done")
