"""Thread-safe result storage (read-only access) with optional SQLite persistence."""

import dataclasses
import json
import sqlite3
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import List, Optional

from soc_copilot.core.logging import get_logger
from .schemas import (
    AlertSummary,
    AnalysisResult,
    LogSummary,
    PipelineStats,
)

logger = get_logger(__name__)


def _serialize_result(result: AnalysisResult) -> str:
    """Serialize an AnalysisResult to a JSON payload string."""
    return json.dumps(
        dataclasses.asdict(result),
        default=lambda value: (
            value.isoformat() if isinstance(value, datetime) else str(value)
        ),
    )


def _deserialize_result(payload: str) -> AnalysisResult:
    """Deserialize a JSON payload back into an AnalysisResult."""
    data = json.loads(payload)
    return AnalysisResult(
        batch_id=data["batch_id"],
        timestamp=datetime.fromisoformat(data["timestamp"]),
        alerts=[
            AlertSummary(
                alert_id=alert["alert_id"],
                priority=alert["priority"],
                classification=alert["classification"],
                confidence=alert["confidence"],
                anomaly_score=alert["anomaly_score"],
                risk_score=alert["risk_score"],
                source_ip=alert["source_ip"],
                destination_ip=alert["destination_ip"],
                timestamp=datetime.fromisoformat(alert["timestamp"]),
                reasoning=alert["reasoning"],
                suggested_action=alert["suggested_action"],
            )
            for alert in data["alerts"]
        ],
        logs=[
            LogSummary(
                log_id=log["log_id"],
                timestamp=datetime.fromisoformat(log["timestamp"]),
                classification=log["classification"],
                confidence=log["confidence"],
                risk_level=log["risk_level"],
                source_ip=log["source_ip"],
                destination_ip=log["destination_ip"],
                raw_log=log["raw_log"],
                is_alert=log["is_alert"],
            )
            for log in data.get("logs", [])
        ],
        stats=(
            PipelineStats(**data["stats"])
            if data.get("stats")
            else PipelineStats(
                total_records=0,
                processed_records=0,
                alerts_generated=0,
                risk_distribution={},
                classification_distribution={},
                processing_time=0.0,
            )
        ),
        raw_count=data.get("raw_count", 0),
    )


class ResultStore:
    """Thread-safe storage for analysis results.

    With ``db_path=None`` the store is purely in-memory. When a database
    path is given, results are persisted to SQLite so they survive
    restarts; any database failure is logged and the store keeps working
    in memory.
    """

    def __init__(self, max_results: int = 1000, db_path=None):
        self.max_results = max_results
        self._results = deque(maxlen=max_results)
        self._lock = Lock()
        self._db_path = Path(db_path) if db_path is not None else None
        if self._db_path is not None:
            self._init_db()
            self._load_from_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self):
        """Create the storage table and index."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS analysis_results (
                        batch_id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_analysis_results_created_at
                    ON analysis_results (created_at)
                    """
                )
        except (sqlite3.Error, OSError) as exc:
            logger.warning("result_store_db_init_failed", error=str(exc))

    def _load_from_db(self):
        """Load the newest max_results rows into the deque (oldest to newest)."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT payload FROM analysis_results
                    ORDER BY created_at DESC, batch_id DESC
                    LIMIT ?
                    """,
                    (self.max_results,),
                ).fetchall()
        except (sqlite3.Error, OSError) as exc:
            logger.warning("result_store_db_load_failed", error=str(exc))
            return

        for (payload,) in reversed(rows):
            try:
                self._results.append(_deserialize_result(payload))
            except Exception as exc:  # noqa: BLE001 - skip corrupt rows
                logger.warning("result_store_row_skipped", error=str(exc))

    def _persist_add(self, result: AnalysisResult):
        """Insert the row and prune anything beyond max_results."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO analysis_results
                        (batch_id, created_at, payload)
                    VALUES (?, ?, ?)
                    """,
                    (
                        result.batch_id,
                        result.timestamp.isoformat(),
                        _serialize_result(result),
                    ),
                )
                conn.execute(
                    """
                    DELETE FROM analysis_results
                    WHERE batch_id NOT IN (
                        SELECT batch_id FROM analysis_results
                        ORDER BY created_at DESC, batch_id DESC
                        LIMIT ?
                    )
                    """,
                    (self.max_results,),
                )
        except (sqlite3.Error, OSError) as exc:
            logger.warning("result_store_db_add_failed", error=str(exc))

    def _persist_clear(self):
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM analysis_results")
        except (sqlite3.Error, OSError) as exc:
            logger.warning("result_store_db_clear_failed", error=str(exc))

    def add(self, result: AnalysisResult):
        """Add analysis result"""
        with self._lock:
            self._results.append(result)
            if self._db_path is not None:
                self._persist_add(result)

    def get_latest(self, limit: int = 10) -> List[AnalysisResult]:
        """Get latest N results"""
        with self._lock:
            return list(self._results)[-limit:]

    def get_all(self) -> List[AnalysisResult]:
        """Get all stored results"""
        with self._lock:
            return list(self._results)

    def get_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get result by batch ID"""
        with self._lock:
            for result in reversed(self._results):
                if result.batch_id == batch_id:
                    return result
            return None

    def count(self) -> int:
        """Get total result count"""
        with self._lock:
            return len(self._results)

    def clear(self):
        """Clear all results"""
        with self._lock:
            self._results.clear()
            if self._db_path is not None:
                self._persist_clear()
