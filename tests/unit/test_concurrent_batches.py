"""Uploads and live system-log ingestion analyse batches from two threads.

They used to run at the same time: shared controller state, interleaved
stage events, and "bad parameter or other API misuse" from the drift
monitor's shared SQLite connection (drift records lost).
"""

import threading
import time
from unittest.mock import Mock

import pytest

from soc_copilot.phase2.drift.monitor import DriftMonitor
from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.pipeline import AnalysisStats


def _batch(n=3):
    return [{"raw_line": f"line {i}"} for i in range(n)]


@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._text_log_classifier = None
    c._flow_feature_names = None  # route every line to the (slow) pipeline
    state = {"active": 0, "max": 0}
    lock = threading.Lock()

    def analyze_file(path, on_stage=None):
        with lock:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.05)  # long enough for the other thread to collide
        with lock:
            state["active"] -= 1
        stats = AnalysisStats()
        stats.total_records = 3
        return [], [], stats

    c._pipeline = Mock()
    c._pipeline.analyze_file.side_effect = analyze_file
    c._overlap = state
    return c


def _run_parallel(fn, n=4):
    errors = []

    def worker():
        try:
            fn()
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


def test_batches_never_overlap(controller):
    _run_parallel(lambda: controller.process_batch(_batch()))
    assert controller._pipeline.analyze_file.call_count == 4
    assert controller._overlap["max"] == 1


def test_stage_events_of_a_batch_stay_together(controller):
    events = []
    controller.add_stage_listener(events.append)
    _run_parallel(lambda: controller.process_batch(_batch()), n=3)
    order = [e.batch_id for e in events]
    # each batch's events form one contiguous block
    blocks = [b for i, b in enumerate(order) if i == 0 or order[i - 1] != b]
    assert len(blocks) == len(set(order)) == 3


def test_clear_waits_for_running_batch(controller):
    started = threading.Event()
    original = controller._pipeline.analyze_file.side_effect

    def slow(path, on_stage=None):
        started.set()
        return original(path, on_stage)

    controller._pipeline.analyze_file.side_effect = slow
    t = threading.Thread(target=lambda: controller.process_batch(_batch()))
    t.start()
    started.wait(2)
    controller.clear_results()  # blocks until the batch is stored
    t.join()
    assert controller.result_store.count() == 0


def test_drift_monitor_survives_concurrent_writers(tmp_path):
    monitor = DriftMonitor(tmp_path / "drift.db")
    monitor.initialize()

    def write():
        for i in range(50):
            monitor.record_inference(0.5, 0.4, "Benign", "P4-Info")
        monitor.get_latest_report()

    _run_parallel(write, n=6)
    conn = monitor._get_connection()
    assert conn.execute("SELECT COUNT(*) FROM inference_stats").fetchone()[0] == 300
    monitor.close()
