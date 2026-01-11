"""Kill Switch - Global Disable Flag for Phase-3"""

import sqlite3
from datetime import datetime
from typing import Optional


class KillSwitch:
    """Global kill switch for Phase-3 components"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize kill switch database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS killswitch_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled BOOLEAN NOT NULL DEFAULT 1,
                last_changed TEXT NOT NULL,
                changed_by TEXT NOT NULL,
                reason TEXT
            )
        """)
        
        # Initialize with enabled state (Phase-3 disabled by default)
        cursor.execute("""
            INSERT OR IGNORE INTO killswitch_state (id, enabled, last_changed, changed_by, reason)
            VALUES (1, 1, ?, 'system', 'Initial state - Phase-3 disabled')
        """, (datetime.utcnow().isoformat(),))
        
        conn.commit()
        conn.close()
    
    def is_enabled(self) -> bool:
        """Check if kill switch is enabled (Phase-3 disabled)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT enabled FROM killswitch_state WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        
        return bool(row[0]) if row else True
    
    def enable(self, actor: str, reason: str):
        """Enable kill switch (disable Phase-3) - CLI only"""
        self._set_state(True, actor, reason)
    
    def disable(self, actor: str, reason: str):
        """Disable kill switch (enable Phase-3) - CLI only"""
        self._set_state(False, actor, reason)
    
    def _set_state(self, enabled: bool, actor: str, reason: str):
        """Set kill switch state (persistent across restarts)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE killswitch_state
            SET enabled = ?, last_changed = ?, changed_by = ?, reason = ?
            WHERE id = 1
        """, (enabled, datetime.utcnow().isoformat(), actor, reason))
        
        conn.commit()
        conn.close()
    
    def get_state(self) -> dict:
        """Get current kill switch state with metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT enabled, last_changed, changed_by, reason
            FROM killswitch_state WHERE id = 1
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {
                "enabled": True,
                "phase3_status": "disabled",
                "last_changed": None,
                "changed_by": None,
                "reason": None
            }
        
        return {
            "enabled": bool(row[0]),
            "phase3_status": "disabled" if row[0] else "enabled",
            "last_changed": row[1],
            "changed_by": row[2],
            "reason": row[3]
        }
