"""Micro-batch buffer for real-time log ingestion"""

from collections import deque
from threading import Lock
from typing import List, Optional
from datetime import datetime


class MicroBatchBuffer:
    """Thread-safe buffer for micro-batching log records"""
    
    def __init__(self, batch_interval: float = 5.0, max_size: int = 10000):
        self.batch_interval = batch_interval
        self.max_size = max_size
        self._buffer = deque(maxlen=max_size)
        self._lock = Lock()
        self._last_flush = datetime.now()
        self._dropped_count = 0
        self._overflow_warnings = 0
    
    def add(self, record: dict) -> bool:
        """Add record to buffer. Returns False if buffer is full."""
        with self._lock:
            if len(self._buffer) >= self.max_size:
                self._dropped_count += 1
                self._overflow_warnings += 1
                return False
            self._buffer.append(record)
            return True
    
    def should_flush(self) -> bool:
        """Check if buffer should be flushed based on time interval"""
        elapsed = (datetime.now() - self._last_flush).total_seconds()
        return elapsed >= self.batch_interval or len(self._buffer) >= self.max_size
    
    def flush(self) -> List[dict]:
        """Flush buffer and return all records"""
        with self._lock:
            records = list(self._buffer)
            self._buffer.clear()
            self._last_flush = datetime.now()
            return records
    
    def size(self) -> int:
        """Get current buffer size"""
        with self._lock:
            return len(self._buffer)
    
    def get_stats(self) -> dict:
        """Get buffer statistics"""
        with self._lock:
            return {
                "size": len(self._buffer),
                "max_size": self.max_size,
                "dropped_count": self._dropped_count,
                "overflow_warnings": self._overflow_warnings
            }
    
    def clear(self):
        """Clear buffer"""
        with self._lock:
            self._buffer.clear()
            self._last_flush = datetime.now()
