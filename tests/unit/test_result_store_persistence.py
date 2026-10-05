"""Tests for ResultStore SQLite persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.controller.result_store import ResultStore
from soc_copilot.phase4.controller.schemas import (
    AlertSummary,
    AnalysisResult,
    LogSummary,
    PipelineStats,
)


def _make_result(batch_id: str, seconds: int = 0) -> AnalysisResult:
    ts = datetime(2026, 1, 1, 12, 0, 0) + timedelta(seconds=seconds)
    return AnalysisResult(
        batch_id=batch_id,
        timestamp=ts,
        alerts=[
            AlertSummary(
                alert_id=f"alert-{batch_id}",
                priority="P1-High",
                classification="BruteForce",
                confidence=0.91,
                anomaly_score=0.77,
                risk_score=0.85,
                source_ip="1.2.3.4",
                destination_ip="10.0.0.1",
                timestamp=ts,
                reasoning="repeated failed logins",
                suggested_action="block IP",
            )
        ],
        logs=[
            LogSummary(
                log_id=f"log-{batch_id}",
                timestamp=ts,
                classification="BruteForce",
                confidence=0.91,
                risk_level="HIGH",
                source_ip="1.2.3.4",
                destination_ip="10.0.0.1",
                raw_log="Failed password for admin",
                is_alert=True,
            )
        ],
        stats=PipelineStats(
            total_records=5,
            processed_records=4,
            alerts_generated=1,
            risk_distribution={"HIGH": 1},
            classification_distribution={"BruteForce": 1},
            processing_time=0.42,
        ),
        raw_count=5,
    )


def test_round_trip_persists_analysis_result(tmp_path: Path) -> None:
    db = tmp_path / "results.db"
    store = ResultStore(db_path=db)
    store.add(_make_result("batch-1"))

    reopened = ResultStore(db_path=db)

    assert reopened.count() == 1
    assert reopened.get_latest(1) == [_make_result("batch-1")]


def test_retention_prunes_to_max_results(tmp_path: Path) -> None:
    db = tmp_path / "results.db"
    store = ResultStore(max_results=3, db_path=db)
    for i in range(5):
        store.add(_make_result(f"batch-{i}", seconds=i))

    reopened = ResultStore(max_results=3, db_path=db)

    assert [r.batch_id for r in reopened.get_all()] == [
        "batch-2",
        "batch-3",
        "batch-4",
    ]
    with sqlite3.connect(db) as conn:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM analysis_results"
        ).fetchone()
    assert count == 3


def test_clear_removes_persisted_rows(tmp_path: Path) -> None:
    db = tmp_path / "results.db"
    store = ResultStore(db_path=db)
    store.add(_make_result("batch-1"))
    store.clear()

    reopened = ResultStore(db_path=db)

    assert reopened.count() == 0
    assert reopened.get_all() == []


def test_default_in_memory_creates_no_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    store = ResultStore()
    store.add(_make_result("batch-1"))

    assert store.count() == 1
    assert list(tmp_path.iterdir()) == []


def test_corrupt_row_is_skipped_on_load(tmp_path: Path) -> None:
    db = tmp_path / "results.db"
    store = ResultStore(db_path=db)
    store.add(_make_result("good-batch"))

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO analysis_results (batch_id, created_at, payload) "
            "VALUES (?, ?, ?)",
            ("bad-batch", "9999-01-01T00:00:00", "not-json{{"),
        )

    reopened = ResultStore(db_path=db)

    assert reopened.count() == 1
    assert reopened.get_latest(1)[0].batch_id == "good-batch"


def test_app_controller_persists_result_store(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    controller = AppController(models_dir="unused", results_db=db)
    controller.result_store.add(_make_result("batch-x"))

    reopened = ResultStore(db_path=db)

    assert reopened.get_by_id("batch-x") is not None
