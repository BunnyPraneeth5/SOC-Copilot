"""Thread-safe in-memory result storage (read-only access)"""

from collections import deque
from threading import Lock
from typing import List, Optional
from .schemas import AnalysisResult


class ResultStore:
    """Thread-safe in-memory storage for analysis results"""
    
    def __init__(self, max_results: int = 1000):
        self.max_results = max_results
        self._results = deque(maxlen=max_results)
        self._lock = Lock()
    
    def add(self, result: AnalysisResult):
        """Add analysis result"""
        with self._lock:
            self._results.append(result)
    
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
