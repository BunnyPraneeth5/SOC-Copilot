"""Typed schemas for analysis results (view models only)"""

from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional
from datetime import datetime


# Pipeline stages reported to stage listeners (Milestone 6a), in run order.
# Text lane: text_detect, bf_correlate. Flow lane: flow_route, preprocess,
# features, detect. Both lanes merge into alerts → store.
PIPELINE_STAGES = (
    "ingest",
    "text_detect",
    "bf_correlate",
    "flow_route",
    "preprocess",
    "features",
    "detect",
    "alerts",
    "store",
)
FLOW_ML_STAGES = ("preprocess", "features", "detect")

# Where a batch came from (ingest stage event data["source"])
SOURCE_UPLOAD = "upload"
SOURCE_SYSTEM_LOGS = "system_logs"

STAGE_ACTIVE = "active"
STAGE_DONE = "done"
STAGE_SKIPPED = "skipped"
STAGE_FAILED = "failed"
STAGE_BLOCKED = "blocked"


@dataclass(frozen=True)
class StageEvent:
    """One stage transition of one batch (Milestone 6a live pipeline graph).

    ``detail`` is a short human-readable note (tooltip text); ``data``
    carries numbers for summaries, e.g. ``{"records": 120}``.
    """
    batch_id: str
    stage: str
    status: str
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


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
