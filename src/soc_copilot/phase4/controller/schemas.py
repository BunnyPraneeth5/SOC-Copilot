"""Typed schemas for analysis results (view models only)"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class AlertSummary:
    """Alert summary view model"""
    alert_id: str
    priority: str
    classification: str
    confidence: float
    anomaly_score: float
    risk_score: float
    source_ip: Optional[str]
    destination_ip: Optional[str]
    timestamp: datetime
    reasoning: str
    suggested_action: str


@dataclass
class LogSummary:
    """Summary of any processed log (benign or alert)"""
    log_id: str
    timestamp: datetime
    classification: str
    confidence: float
    risk_level: str
    source_ip: Optional[str]
    destination_ip: Optional[str]
    raw_log: str
    is_alert: bool


@dataclass
class PipelineStats:
    """Pipeline statistics view model"""
    total_records: int
    processed_records: int
    alerts_generated: int
    risk_distribution: Dict[str, int]
    classification_distribution: Dict[str, int]
    processing_time: float


@dataclass
class AnalysisResult:
    """Complete analysis result view model"""
    batch_id: str
    timestamp: datetime
    alerts: List[AlertSummary]
    logs: List[LogSummary] = field(default_factory=list)
    stats: PipelineStats = field(default_factory=lambda: PipelineStats(
        total_records=0,
        processed_records=0,
        alerts_generated=0,
        risk_distribution={},
        classification_distribution={},
        processing_time=0.0,
    ))
    raw_count: int = 0
