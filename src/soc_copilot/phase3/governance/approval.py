"""Approval Workflow - Manual Approval State Machine"""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import sqlite3


class ApprovalState(Enum):
    """Approval workflow states"""
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


@dataclass
class ApprovalRequest:
    """Manual approval request object"""
    request_id: str
    requester: str
    action: str
    reason: str
    state: ApprovalState
    requested_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Export as dictionary"""
        return {
            "request_id": self.request_id,
            "requester": self.requester,
            "action": self.action,
            "reason": self.reason,
            "state": self.state.value,
            "requested_at": self.requested_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer": self.reviewer,
            "review_notes": self.review_notes
        }


class ApprovalWorkflow:
    """Manages manual approval workflow"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize approval workflow database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_requests (
                request_id TEXT PRIMARY KEY,
                requester TEXT NOT NULL,
                action TEXT NOT NULL,
                reason TEXT NOT NULL,
                state TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewer TEXT,
                review_notes TEXT
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_request(self, request_id: str, requester: str, 
                      action: str, reason: str) -> ApprovalRequest:
        """Create new approval request (manual only)"""
        request = ApprovalRequest(
            request_id=request_id,
            requester=requester,
            action=action,
            reason=reason,
            state=ApprovalState.REQUESTED,
            requested_at=datetime.utcnow()
        )
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO approval_requests 
            (request_id, requester, action, reason, state, requested_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (request.request_id, request.requester, request.action, 
              request.reason, request.state.value, request.requested_at.isoformat()))
        
        conn.commit()
        conn.close()
        
        return request
    
    def approve_request(self, request_id: str, reviewer: str, 
                       notes: Optional[str] = None) -> ApprovalRequest:
        """Approve request (manual only, NO side effects)"""
        return self._transition_state(
            request_id, ApprovalState.APPROVED, reviewer, notes
        )
    
    def reject_request(self, request_id: str, reviewer: str,
                      notes: Optional[str] = None) -> ApprovalRequest:
        """Reject request (manual only)"""
        return self._transition_state(
            request_id, ApprovalState.REJECTED, reviewer, notes
        )
    
    def revoke_request(self, request_id: str, reviewer: str,
                      notes: Optional[str] = None) -> ApprovalRequest:
        """Revoke previously approved request (manual only)"""
        return self._transition_state(
            request_id, ApprovalState.REVOKED, reviewer, notes
        )
    
    def _transition_state(self, request_id: str, new_state: ApprovalState,
                         reviewer: str, notes: Optional[str]) -> ApprovalRequest:
        """Transition request to new state (NO automatic transitions)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        reviewed_at = datetime.utcnow()
        
        cursor.execute("""
            UPDATE approval_requests
            SET state = ?, reviewed_at = ?, reviewer = ?, review_notes = ?
            WHERE request_id = ?
        """, (new_state.value, reviewed_at.isoformat(), reviewer, notes, request_id))
        
        conn.commit()
        
        # Fetch updated request
        cursor.execute("""
            SELECT request_id, requester, action, reason, state, 
                   requested_at, reviewed_at, reviewer, review_notes
            FROM approval_requests WHERE request_id = ?
        """, (request_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            raise ValueError(f"Request {request_id} not found")
        
        return ApprovalRequest(
            request_id=row[0],
            requester=row[1],
            action=row[2],
            reason=row[3],
            state=ApprovalState(row[4]),
            requested_at=datetime.fromisoformat(row[5]),
            reviewed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            reviewer=row[7],
            review_notes=row[8]
        )
    
    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Retrieve approval request by ID"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT request_id, requester, action, reason, state,
                   requested_at, reviewed_at, reviewer, review_notes
            FROM approval_requests WHERE request_id = ?
        """, (request_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return ApprovalRequest(
            request_id=row[0],
            requester=row[1],
            action=row[2],
            reason=row[3],
            state=ApprovalState(row[4]),
            requested_at=datetime.fromisoformat(row[5]),
            reviewed_at=datetime.fromisoformat(row[6]) if row[6] else None,
            reviewer=row[7],
            review_notes=row[8]
        )
    
    def list_requests(self, state: Optional[ApprovalState] = None) -> list:
        """List all requests, optionally filtered by state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if state:
            cursor.execute("""
                SELECT request_id, requester, action, reason, state,
                       requested_at, reviewed_at, reviewer, review_notes
                FROM approval_requests WHERE state = ?
                ORDER BY requested_at DESC
            """, (state.value,))
        else:
            cursor.execute("""
                SELECT request_id, requester, action, reason, state,
                       requested_at, reviewed_at, reviewer, review_notes
                FROM approval_requests
                ORDER BY requested_at DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            ApprovalRequest(
                request_id=row[0],
                requester=row[1],
                action=row[2],
                reason=row[3],
                state=ApprovalState(row[4]),
                requested_at=datetime.fromisoformat(row[5]),
                reviewed_at=datetime.fromisoformat(row[6]) if row[6] else None,
                reviewer=row[7],
                review_notes=row[8]
            )
            for row in rows
        ]
