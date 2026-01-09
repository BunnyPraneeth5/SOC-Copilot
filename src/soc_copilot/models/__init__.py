"""Models package for SOC Copilot."""

from soc_copilot.models.inference import (
    ModelInference,
    InferenceConfig,
    InferenceResult,
    create_inference_engine,
)
from soc_copilot.models.training import (
    TrainingDataLoader,
    DataLoaderConfig,
    SOC_LABELS,
)
from soc_copilot.models.ensemble import (
    EnsembleCoordinator,
    EnsembleConfig,
    EnsembleResult,
    RiskLevel,
    AlertPriority,
    ThreatCategory,
    AlertGenerator,
    Alert,
    AnalysisPipeline,
    create_analysis_pipeline,
    format_alert_summary,
)

__all__ = [
    # Inference
    "ModelInference",
    "InferenceConfig",
    "InferenceResult",
    "create_inference_engine",
    # Training
    "TrainingDataLoader",
    "DataLoaderConfig",
    "SOC_LABELS",
    # Ensemble
    "EnsembleCoordinator",
    "EnsembleConfig",
    "EnsembleResult",
    "RiskLevel",
    "AlertPriority",
    "ThreatCategory",
    "AlertGenerator",
    "Alert",
    "AnalysisPipeline",
    "create_analysis_pipeline",
    "format_alert_summary",
]
