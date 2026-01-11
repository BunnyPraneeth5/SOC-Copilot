"""Audit Logging - Append-Only Audit Trail"""

import sqlite3
from datetime import datetime
from typing import Optional, List
import uuid


class AuditEvent:
    """Audit event record"""
    
    def __init__(self, event_id: str, timestamp: datetime, actor: str,
                 action: str, reason: str):
        self.event_id = event_id
        self.timestamp = timestamp
        self.actor = actor
        self.action = action
        self.reason = reason
    
    def to_dict(self) -> dict:
        """Export as dictionary"""
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "reason": self.reason
        }


class AuditLogger:
    """Append-only audit logging system"""
    
    MAX_EVENTS_PER_ROTATION = 10000
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize audit log database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Append-only audit log (no DELETE or UPDATE allowed)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL
            )
        """)
        
        # Rotation tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_rotation (
                rotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rotated_at TEXT NOT NULL,
                event_count INTEGER NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def log_event(self, actor: str, action: str, reason: str) -> AuditEvent:
        """Log audit event (append-only)"""
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            actor=actor,
            action=action,
            reason=reason
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO audit_log (event_id, timestamp, actor, action, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (event.event_id, event.timestamp.isoformat(), 
              event.actor, event.action, event.reason))
        
        conn.commit()
        conn.close()
        
        # Check if rotation needed
        self._check_rotation()
        
        return event
    
    def get_events(self, limit: Optional[int] = 100, 
                   actor: Optional[str] = None,
                   action: Optional[str] = None) -> List[AuditEvent]:
        """Retrieve audit events (read-only)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT event_id, timestamp, actor, action, reason FROM audit_log"
        params = []
        conditions = []
        
        if actor:
            conditions.append("actor = ?")
            params.append(actor)
        
        if action:
            conditions.append("action = ?")
            params.append(action)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [
            AuditEvent(
                event_id=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                actor=row[2],
                action=row[3],
                reason=row[4]
            )
            for row in rows
        ]
    
    def get_event_count(self) -> int:
        """Get total event count"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        count = cursor.fetchone()[0]
        
        conn.close()
        return count
    
    def _check_rotation(self):
        """Check if log rotation is needed (basic policy)"""
        count = self.get_event_count()
        
        if count >= self.MAX_EVENTS_PER_ROTATION:
            self._rotate_logs()
    
    def _rotate_logs(self):
        """Rotate audit logs (archive old events)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Count events before rotation
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        event_count = cursor.fetchone()[0]
        
        # Record rotation (metadata only, actual archival not implemented)
        cursor.execute("""
            INSERT INTO audit_rotation (rotated_at, event_count)
            VALUES (?, ?)
        """, (datetime.utcnow().isoformat(), event_count))
        
        conn.commit()
        conn.close()
    
    def get_rotation_history(self) -> List[dict]:
        """Get log rotation history"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT rotation_id, rotated_at, event_count
            FROM audit_rotation
            ORDER BY rotated_at DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "rotation_id": row[0],
                "rotated_at": row[1],
                "event_count": row[2]
            }
            for row in rows
        ]
