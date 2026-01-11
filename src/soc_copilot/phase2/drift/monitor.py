"""Phase-2 Sprint-9: Drift Monitoring (Statistical, Reporting-Only).

Tracks changes in model outputs and feature distributions over time.
Does NOT affect detection, scoring, thresholds, or alerts.
"""

import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class DriftLevel(str, Enum):
    """Drift severity level."""
    NONE = "NONE"
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class DriftReport:
    """Drift monitoring report."""
    
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.window_size = 0
        self.baseline_size = 0
        
        # Output drift metrics
        self.anomaly_score_mean = 0.0
        self.anomaly_score_std = 0.0
        self.risk_score_mean = 0.0
        self.risk_score_std = 0.0
        self.class_distribution = {}
        self.priority_distribution = {}
        
        # Drift flags
        self.anomaly_drift = DriftLevel.NONE
        self.risk_drift = DriftLevel.NONE
        self.class_drift = DriftLevel.NONE
        
        # Comparison metrics
        self.anomaly_change_pct = 0.0
        self.risk_change_pct = 0.0
        
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "window_size": self.window_size,
            "baseline_size": self.baseline_size,
            "metrics": {
                "anomaly_score_mean": self.anomaly_score_mean,
                "anomaly_score_std": self.anomaly_score_std,
                "risk_score_mean": self.risk_score_mean,
                "risk_score_std": self.risk_score_std,
                "class_distribution": self.class_distribution,
                "priority_distribution": self.priority_distribution,
            },
            "drift": {
                "anomaly": self.anomaly_drift.value,
                "risk": self.risk_drift.value,
                "class": self.class_drift.value,
            },
            "changes": {
                "anomaly_change_pct": self.anomaly_change_pct,
                "risk_change_pct": self.risk_change_pct,
            }
        }


class DriftMonitor:
    """Statistical drift monitoring (reporting-only)."""
    
    def __init__(self, db_path: str | Path = "data/drift/drift.db"):
        """Initialize drift monitor.
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
    
    def _get_connection(self):
        """Get or create database connection."""
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def initialize(self):
        """Initialize database schema."""
        conn = self._get_connection()
        
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS inference_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                anomaly_score REAL,
                risk_score REAL,
                predicted_class TEXT,
                priority TEXT
            );
            
            CREATE TABLE IF NOT EXISTS drift_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                report_json TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_inference_timestamp ON inference_stats(timestamp);
        """)
        
        conn.commit()
        logger.info("drift_monitor_initialized", db_path=str(self.db_path))
    
    def record_inference(self, anomaly_score: float, risk_score: float, 
                        predicted_class: str, priority: str):
        """Record inference output for drift tracking.
        
        Args:
            anomaly_score: Isolation Forest anomaly score
            risk_score: Combined risk score
            predicted_class: Predicted threat class
            priority: Alert priority
        """
        conn = self._get_connection()
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        conn.execute(
            "INSERT INTO inference_stats (timestamp, anomaly_score, risk_score, predicted_class, priority) VALUES (?, ?, ?, ?, ?)",
            (timestamp, anomaly_score, risk_score, predicted_class, priority)
        )
        conn.commit()
    
    def compute_drift_report(self, window_size: int = 100, baseline_size: int = 100):
        """Compute drift report comparing current window to baseline.
        
        Args:
            window_size: Number of recent inferences to analyze
            baseline_size: Number of baseline inferences to compare against
            
        Returns:
            DriftReport object
        """
        conn = self._get_connection()
        report = DriftReport()
        
        # Get current window
        cursor = conn.execute(
            "SELECT * FROM inference_stats ORDER BY timestamp DESC LIMIT ?",
            (window_size,)
        )
        current = list(cursor.fetchall())
        
        if len(current) < 10:
            logger.warning("insufficient_data_for_drift", count=len(current))
            return report
        
        report.window_size = len(current)
        
        # Get baseline (skip current window)
        cursor = conn.execute(
            "SELECT * FROM inference_stats ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (baseline_size, window_size)
        )
        baseline = list(cursor.fetchall())
        
        if len(baseline) < 10:
            logger.warning("insufficient_baseline_for_drift", count=len(baseline))
            # Compute current stats only
            self._compute_window_stats(current, report)
            self._save_report(report)  # Save even without baseline
            return report
        
        report.baseline_size = len(baseline)
        
        # Compute current window stats
        self._compute_window_stats(current, report)
        
        # Compute baseline stats
        baseline_anomaly_mean = sum(r["anomaly_score"] for r in baseline if r["anomaly_score"]) / len(baseline)
        baseline_risk_mean = sum(r["risk_score"] for r in baseline if r["risk_score"]) / len(baseline)
        
        # Compute drift
        if baseline_anomaly_mean > 0:
            report.anomaly_change_pct = ((report.anomaly_score_mean - baseline_anomaly_mean) / baseline_anomaly_mean) * 100
            report.anomaly_drift = self._classify_drift(abs(report.anomaly_change_pct))
        
        if baseline_risk_mean > 0:
            report.risk_change_pct = ((report.risk_score_mean - baseline_risk_mean) / baseline_risk_mean) * 100
            report.risk_drift = self._classify_drift(abs(report.risk_change_pct))
        
        # Class distribution drift
        baseline_classes = {}
        for r in baseline:
            cls = r["predicted_class"] or "Unknown"
            baseline_classes[cls] = baseline_classes.get(cls, 0) + 1
        
        class_drift_score = self._compute_distribution_drift(report.class_distribution, baseline_classes)
        report.class_drift = self._classify_drift(class_drift_score * 100)
        
        # Save report
        self._save_report(report)
        
        return report
    
    def _compute_window_stats(self, window, report: DriftReport):
        """Compute statistics for a window."""
        anomaly_scores = [r["anomaly_score"] for r in window if r["anomaly_score"] is not None]
        risk_scores = [r["risk_score"] for r in window if r["risk_score"] is not None]
        
        if anomaly_scores:
            report.anomaly_score_mean = sum(anomaly_scores) / len(anomaly_scores)
            if len(anomaly_scores) > 1:
                mean = report.anomaly_score_mean
                variance = sum((x - mean) ** 2 for x in anomaly_scores) / (len(anomaly_scores) - 1)
                report.anomaly_score_std = variance ** 0.5
        
        if risk_scores:
            report.risk_score_mean = sum(risk_scores) / len(risk_scores)
            if len(risk_scores) > 1:
                mean = report.risk_score_mean
                variance = sum((x - mean) ** 2 for x in risk_scores) / (len(risk_scores) - 1)
                report.risk_score_std = variance ** 0.5
        
        # Class distribution
        for r in window:
            cls = r["predicted_class"] or "Unknown"
            report.class_distribution[cls] = report.class_distribution.get(cls, 0) + 1
        
        # Priority distribution
        for r in window:
            pri = r["priority"] or "Unknown"
            report.priority_distribution[pri] = report.priority_distribution.get(pri, 0) + 1
    
    def _classify_drift(self, change_pct: float) -> DriftLevel:
        """Classify drift level based on percentage change.
        
        Conservative thresholds to avoid false alarms.
        """
        if change_pct < 10:
            return DriftLevel.NONE
        elif change_pct < 25:
            return DriftLevel.LOW
        elif change_pct < 50:
            return DriftLevel.MODERATE
        else:
            return DriftLevel.HIGH
    
    def _compute_distribution_drift(self, current: dict, baseline: dict) -> float:
        """Compute distribution drift using simple difference metric."""
        all_keys = set(current.keys()) | set(baseline.keys())
        if not all_keys:
            return 0.0
        
        current_total = sum(current.values()) or 1
        baseline_total = sum(baseline.values()) or 1
        
        diff = 0.0
        for key in all_keys:
            curr_pct = current.get(key, 0) / current_total
            base_pct = baseline.get(key, 0) / baseline_total
            diff += abs(curr_pct - base_pct)
        
        return diff / 2  # Normalize to [0, 1]
    
    def _save_report(self, report: DriftReport):
        """Save drift report to database."""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO drift_reports (timestamp, report_json) VALUES (?, ?)",
            (report.timestamp, json.dumps(report.to_dict()))
        )
        conn.commit()
    
    def get_latest_report(self) -> DriftReport | None:
        """Get most recent drift report."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT report_json FROM drift_reports ORDER BY timestamp DESC LIMIT 1"
        )
        row = cursor.fetchone()
        
        if not row:
            return None
        
        data = json.loads(row["report_json"])
        report = DriftReport()
        report.timestamp = data["timestamp"]
        report.window_size = data["window_size"]
        report.baseline_size = data["baseline_size"]
        report.anomaly_score_mean = data["metrics"]["anomaly_score_mean"]
        report.anomaly_score_std = data["metrics"]["anomaly_score_std"]
        report.risk_score_mean = data["metrics"]["risk_score_mean"]
        report.risk_score_std = data["metrics"]["risk_score_std"]
        report.class_distribution = data["metrics"]["class_distribution"]
        report.priority_distribution = data["metrics"]["priority_distribution"]
        report.anomaly_drift = DriftLevel(data["drift"]["anomaly"])
        report.risk_drift = DriftLevel(data["drift"]["risk"])
        report.class_drift = DriftLevel(data["drift"]["class"])
        report.anomaly_change_pct = data["changes"]["anomaly_change_pct"]
        report.risk_change_pct = data["changes"]["risk_change_pct"]
        
        return report
    
    def get_report_history(self, limit: int = 10) -> list[dict]:
        """Get historical drift reports.
        
        Args:
            limit: Maximum number of reports to return
            
        Returns:
            List of report dictionaries
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT report_json FROM drift_reports ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        
        return [json.loads(row["report_json"]) for row in cursor.fetchall()]
    
    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
