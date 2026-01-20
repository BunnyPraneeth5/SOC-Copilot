"""
Event deduplication for benign event suppression.

This module prevents repeated evaluation and logging of benign (P4-Info)
events by using stable fingerprinting and a cooldown window.

Design goals:
- Do NOT affect alert-worthy events (P1–P3)
- Reduce CPU usage and log spam
- Preserve SOC auditability
- Safe for long-running processes
"""

import hashlib
import time
from typing import Dict, Optional


class EventDeduplicator:
    """
    Deduplicates benign events using fingerprinting and cooldown logic.

    Only suppresses repeated benign events (e.g., P4-Info).
    Alert-worthy events must always pass through immediately.
    """

    def __init__(self, cooldown_seconds: float = 60.0):
        """
        Args:
            cooldown_seconds: Minimum time time between processing
                              identical benign events.
        """
        self.cooldown_seconds = cooldown_seconds
        self._seen: Dict[str, float] = {}  # fingerprint -> last_seen_timestamp

    def should_process(self, fingerprint: str) -> bool:
        """
        Determine whether an event should be processed.

        Returns:
            True  -> Event should be processed
            False -> Event is suppressed due to cooldown
        """
        now = time.time()
        last_seen = self._seen.get(fingerprint)

        if last_seen is None:
            # First time seeing this event
            self._seen[fingerprint] = now
            return True

        if (now - last_seen) >= self.cooldown_seconds:
            # Cooldown expired
            self._seen[fingerprint] = now
            return True

        # Suppress duplicate benign event
        return False

    def fingerprint_event(
        self,
        classification: str,
        anomaly_score: float,
        source_ip: Optional[str] = None,
    ) -> str:
        """
        Generate a stable fingerprint for an event.

        Fingerprint intentionally ignores volatile fields
        (timestamps, IDs) to prevent fingerprint explosion.

        Args:
            classification: Model classification (Benign/Malicious/etc)
            anomaly_score: Model anomaly score
            source_ip: Optional source IP

        Returns:
            Short SHA256-based fingerprint
        """
        # Bucket anomaly score to reduce noise
        score_bucket = int(anomaly_score * 10) / 10  # e.g. 0.08 → 0.0, 0.85 → 0.8

        parts = [
            classification,
            f"{score_bucket:.1f}",
            source_ip or "unknown",
        ]

        fingerprint_str = "|".join(parts)
        return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]

    def cleanup_old_entries(self, max_age_seconds: float = 3600.0) -> None:
        """
        Remove old fingerprints to prevent memory growth.

        Args:
            max_age_seconds: Maximum age for stored fingerprints
        """
        now = time.time()
        self._seen = {
            fp: ts
            for fp, ts in self._seen.items()
            if (now - ts) < max_age_seconds
        }
