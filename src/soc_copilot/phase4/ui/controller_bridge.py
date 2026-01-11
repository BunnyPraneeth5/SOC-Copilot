"""Read-only bridge between UI and AppController"""

from typing import List, Optional
from ..controller import AppController, AnalysisResult


class ControllerBridge:
    """Read-only adapter for UI to access AppController"""
    
    def __init__(self, controller: AppController):
        self._controller = controller
    
    def get_latest_alerts(self, limit: int = 50) -> List[AnalysisResult]:
        """Get latest analysis results (read-only)"""
        return self._controller.get_results(limit=limit)
    
    def get_alert_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get specific result by ID (read-only)"""
        return self._controller.get_result_by_id(batch_id)
    
    def get_stats(self) -> dict:
        """Get controller statistics (read-only)"""
        return self._controller.get_stats()
    
    def get_total_alert_count(self) -> int:
        """Get total stored alert count"""
        return self._controller.result_store.count()
