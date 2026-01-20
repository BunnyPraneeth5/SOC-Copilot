"""Application controller orchestrating ingestion → analysis → results"""

import time
import uuid
from datetime import datetime
from typing import Optional, Callable, List
from pathlib import Path

from soc_copilot.pipeline import create_soc_copilot
from .schemas import AnalysisResult, AlertSummary, PipelineStats
from .result_store import ResultStore


class AppController:
    """Main application controller for real-time analysis"""
    
    def __init__(self, models_dir: str, killswitch_check: Optional[Callable[[], bool]] = None):
        self.models_dir = models_dir
        self.killswitch_check = killswitch_check
        self.result_store = ResultStore(max_results=1000)
        self._pipeline = None
    
    def initialize(self):
        """Initialize analysis pipeline"""
        self._pipeline = create_soc_copilot(self.models_dir)
    
    def process_batch(self, records: List[dict]) -> Optional[AnalysisResult]:
        """Process batch of raw log records"""
        # Check kill switch
        if self.killswitch_check and self.killswitch_check():
            return None
        
        if not self._pipeline:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")
        
        # Extract raw lines
        raw_lines = [r.get("raw_line", "") for r in records if r.get("raw_line")]
        if not raw_lines:
            return None
        
        # Measure processing time
        start_time = time.time()
        
        # Analyze batch (using existing pipeline)
        try:
            results, alerts, stats = self._analyze_lines(raw_lines)
        except Exception:
            return None
        
        processing_time = time.time() - start_time
        
        # Convert to view models
        alert_summaries = self._convert_alerts(alerts)
        pipeline_stats = self._convert_stats(stats, processing_time)
        
        # Create result
        result = AnalysisResult(
            batch_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            alerts=alert_summaries,
            stats=pipeline_stats,
            raw_count=len(raw_lines)
        )
        
        # Store result
        self.result_store.add(result)
        
        return result
    
    def _analyze_lines(self, lines: List[str]):
        """Analyze lines using existing pipeline"""
        import tempfile
        import json
        
        # Create temp file in JSONL format for proper parsing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
            for line in lines:
                # Try to parse as JSON, otherwise wrap as raw log
                try:
                    # If it's already valid JSON, write as-is
                    json.loads(line)
                    f.write(line + '\n')
                except (json.JSONDecodeError, TypeError):
                    # Wrap non-JSON content as a raw log entry
                    log_entry = {
                        "timestamp": "2026-01-17T00:00:00Z",
                        "raw_log": line,
                        "src_ip": "0.0.0.0",
                        "dst_ip": "0.0.0.0",
                        "protocol": "TCP",
                        "action": "log_entry"
                    }
                    f.write(json.dumps(log_entry) + '\n')
            temp_path = f.name
        
        try:
            results, alerts, stats = self._pipeline.analyze_file(Path(temp_path))
            return results, alerts, stats
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def _convert_alerts(self, alerts) -> List[AlertSummary]:
        """Convert pipeline alerts to view models"""
        summaries = []
        for alert in alerts:
            summaries.append(AlertSummary(
                alert_id=alert.alert_id,
                priority=alert.priority.value,
                classification=alert.classification,
                confidence=alert.classification_confidence,
                anomaly_score=alert.anomaly_score,
                risk_score=alert.combined_risk_score,
                source_ip=alert.source_ip,
                destination_ip=alert.destination_ip,
                timestamp=datetime.now(),
                reasoning=alert.reasoning,
                suggested_action=alert.suggested_action
            ))
        return summaries
    
    def _convert_stats(self, stats, processing_time: float) -> PipelineStats:
        """Convert pipeline stats to view model"""
        return PipelineStats(
            total_records=stats.total_records,
            processed_records=stats.processed_records,
            alerts_generated=len(stats.risk_distribution),
            risk_distribution=dict(stats.risk_distribution),
            classification_distribution=dict(stats.classification_distribution),
            processing_time=processing_time
        )
    
    def get_results(self, limit: int = 10) -> List[AnalysisResult]:
        """Get latest analysis results"""
        return self.result_store.get_latest(limit)
    
    def get_result_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get specific result by ID"""
        return self.result_store.get_by_id(batch_id)
    
    def get_stats(self) -> dict:
        """Get controller statistics"""
        return {
            "pipeline_loaded": self._pipeline is not None,
            "results_stored": self.result_store.count(),
            "models_dir": self.models_dir
        }
    
    def clear_results(self):
        """Clear stored results"""
        self.result_store.clear()
