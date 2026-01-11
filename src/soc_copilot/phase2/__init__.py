"""Phase-2 modules for SOC Copilot.

Phase-2 adds intelligence and adaptability while preserving Phase-1 stability:
- Feedback Store: Analyst verdict persistence
- Drift Monitoring: Model performance tracking
- Calibration: Environment-specific tuning
- Explainability: Enhanced reasoning
- Autoencoder: Advisory anomaly signal
"""

from soc_copilot.phase2.feedback import (
    FeedbackStore,
    FeedbackStats,
)
from soc_copilot.phase2.drift import (
    DriftMonitor,
    DriftReport,
    DriftLevel,
)
from soc_copilot.phase2.calibration import (
    ThresholdCalibrator,
    CalibrationRecommendation,
)
from soc_copilot.phase2.explainability import (
    AlertExplainer,
    ExplainedAlert,
    AlertExplanation,
)

__all__ = [
    "FeedbackStore",
    "FeedbackStats",
    "DriftMonitor",
    "DriftReport",
    "DriftLevel",
    "ThresholdCalibrator",
    "CalibrationRecommendation",
    "AlertExplainer",
    "ExplainedAlert",
    "AlertExplanation",
]
