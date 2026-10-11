"""Result retention keeps alerts: alert-free results are evicted first.

Live system-log ingestion stores a small, usually alert-free batch every
few seconds. With oldest-first eviction the store (1000 results) dropped
uploaded files' alerts and their triage status after ~80 minutes.
"""

import sqlite3
from datetime import datetime, timedelta

from soc_copilot.phase4.controller.result_store import ResultStore
from soc_copilot.phase4.controller.schemas import AlertSummary, AnalysisResult

T0 = datetime(2026, 10, 12, 9, 0, 0)


def _alert(alert_id):
    return AlertSummary(
        alert_id=alert_id, priority="P1-High", classification="BruteForce",
        confidence=0.9, anomaly_score=0.7, risk_score=0.7, source_ip="45.67.89.101",
        destination_ip=None, timestamp=T0, reasoning="r", suggested_action="a",
    )


def _result(batch_id, minutes, alerts=()):
    return AnalysisResult(batch_id=batch_id, timestamp=T0 + timedelta(minutes=minutes),
                          alerts=[_alert(a) for a in alerts])


def _ids(store):
    return [r.batch_id for r in store.get_all()]


class TestMemory:
    def test_alert_result_outlives_alert_free_ones(self):
        store = ResultStore(max_results=3)
        store.add(_result("upload", 0, ["ML-1"]))
        for i in range(5):
            store.add(_result(f"sys-{i}", i + 1))
        assert _ids(store) == ["upload", "sys-3", "sys-4"]  # order kept

    def test_all_alerts_oldest_goes(self):
        store = ResultStore(max_results=2)
        for i in range(3):
            store.add(_result(f"b{i}", i, [f"ML-{i}"]))
        assert _ids(store) == ["b1", "b2"]

    def test_triage_kept_with_its_alert(self):
        store = ResultStore(max_results=2)
        store.add(_result("upload", 0, ["ML-1"]))
        store.set_triage("ML-1", "In progress")
        for i in range(10):
            store.add(_result(f"sys-{i}", i + 1))
        assert store.get_triage("ML-1")["status"] == "In progress"

    def test_live_ingestion_scenario(self):
        """One upload with alerts, then ~3 hours of 5-second system batches."""
        store = ResultStore(max_results=1000)
        store.add(_result("upload", 0, ["ML-A", "ML-B"]))
        for i in range(2000):
            store.add(_result(f"sys-{i}", i))
        assert store.count() == 1000
        assert store.get_by_id("upload") is not None
        assert store.get_latest(1)[0].batch_id == "sys-1999"


class TestDatabase:
    def test_db_prune_keeps_alert_results(self, tmp_path):
        db = tmp_path / "results.db"
        store = ResultStore(max_results=3, db_path=db)
        store.add(_result("upload", 0, ["ML-1"]))
        store.set_triage("ML-1", "Resolved")
        for i in range(5):
            store.add(_result(f"sys-{i}", i + 1))

        reopened = ResultStore(max_results=3, db_path=db)
        assert _ids(reopened) == ["upload", "sys-3", "sys-4"]
        assert reopened.get_triage("ML-1")["status"] == "Resolved"
        with sqlite3.connect(db) as conn:
            assert conn.execute("SELECT COUNT(*) FROM analysis_results").fetchone()[0] == 3

    def test_db_all_alerts_oldest_goes(self, tmp_path):
        db = tmp_path / "results.db"
        store = ResultStore(max_results=2, db_path=db)
        for i in range(3):
            store.add(_result(f"b{i}", i, [f"ML-{i}"]))
        assert _ids(ResultStore(max_results=2, db_path=db)) == ["b1", "b2"]

    def test_memory_and_db_agree(self, tmp_path):
        db = tmp_path / "results.db"
        store = ResultStore(max_results=4, db_path=db)
        plan = [("a", ["ML-1"]), ("b", []), ("c", ["ML-2"]), ("d", []), ("e", []), ("f", ["ML-3"])]
        for i, (bid, alerts) in enumerate(plan):
            store.add(_result(bid, i, alerts))
        assert _ids(store) == _ids(ResultStore(max_results=4, db_path=db))
        assert _ids(store) == ["a", "c", "e", "f"]
