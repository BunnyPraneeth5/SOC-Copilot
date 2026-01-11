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
    stats: PipelineStats
    raw_count: int
