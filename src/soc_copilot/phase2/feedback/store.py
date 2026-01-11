"""Phase-2 Sprint-8: Feedback Store (Read-Only).

Provides SQLite-based persistence for analyst feedback on alerts.
Feedback is OBSERVATIONAL ONLY - it does NOT alter models, thresholds, or scoring.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class FeedbackStats:
    """Statistics from feedback data."""
    
    def __init__(self):
        self.total_count = 0
        self.accept_count = 0
        self.reject_count = 0
        self.reclassify_count = 0
        self.by_label = {}


class FeedbackStore:
    """SQLite-based store for analyst feedback (Sprint-8).
    
    Stores analyst actions on alerts. Does NOT modify models or thresholds.
    """
    
    def __init__(self, db_path: str | Path = "data/feedback/feedback.db"):
        """Initialize feedback store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def initialize(self) -> None:
        """Initialize database schema per Sprint-8 spec."""
        conn = self._get_connection()
        
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_id TEXT NOT NULL,
                analyst_action TEXT NOT NULL CHECK(analyst_action IN ('accept', 'reject', 'reclassify')),
                analyst_label TEXT,
                comment TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_feedback_alert_id ON feedback(alert_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_action ON feedback(analyst_action);
        """)
        
        conn.commit()
        logger.info("feedback_store_initialized", db_path=str(self.db_path))
    
    def add_feedback(
        self,
        alert_id: str,
        analyst_action: str,
        analyst_label: str | None = None,
        comment: str | None = None,
    ) -> int:
        """Add feedback record.
        
        Args:
            alert_id: Alert ID
            analyst_action: One of: accept, reject, reclassify
            analyst_label: New label (required if reclassify)
            comment: Optional comment
            
        Returns:
            ID of inserted record
        """
        if analyst_action not in ("accept", "reject", "reclassify"):
            raise ValueError(f"Invalid action: {analyst_action}")
        
        conn = self._get_connection()
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        cursor = conn.execute(
            "INSERT INTO feedback (timestamp, alert_id, analyst_action, analyst_label, comment) VALUES (?, ?, ?, ?, ?)",
            (timestamp, alert_id, analyst_action, analyst_label, comment)
        )
        
        conn.commit()
        record_id = cursor.lastrowid
        logger.info("feedback_added", record_id=record_id, alert_id=alert_id, action=analyst_action)
        return record_id
    
    def get_feedback_by_alert(self, alert_id: str) -> list[dict]:
        """Get all feedback for a specific alert.
        
        Args:
            alert_id: Alert ID
            
        Returns:
            List of feedback records as dicts
        """
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM feedback WHERE alert_id = ? ORDER BY timestamp DESC",
            (alert_id,)
        )
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_feedback_stats(self) -> FeedbackStats:
        """Get feedback statistics.
        
        Returns:
            FeedbackStats object with counts
        """
        conn = self._get_connection()
        stats = FeedbackStats()
        
        # Action counts
        cursor = conn.execute("""
            SELECT analyst_action, COUNT(*) as cnt
            FROM feedback
            GROUP BY analyst_action
        """)
        
        for row in cursor.fetchall():
            action = row["analyst_action"]
            count = row["cnt"]
            stats.total_count += count
            if action == "accept":
                stats.accept_count = count
            elif action == "reject":
                stats.reject_count = count
            elif action == "reclassify":
                stats.reclassify_count = count
        
        # Label counts (for reclassify)
        cursor = conn.execute("""
            SELECT analyst_label, COUNT(*) as cnt
            FROM feedback
            WHERE analyst_action = 'reclassify' AND analyst_label IS NOT NULL
            GROUP BY analyst_label
        """)
        
        for row in cursor.fetchall():
            stats.by_label[row["analyst_label"]] = row["cnt"]
        
        return stats
    
    def close(self) -> None:
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
