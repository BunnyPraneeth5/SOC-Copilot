"""Feature engineering module for SOC Copilot."""

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
    entropy,
    safe_divide,
)
from soc_copilot.data.feature_engineering.statistical_features import (
    StatisticalFeatureExtractor,
    StatisticalFeatureConfig,
)
from soc_copilot.data.feature_engineering.temporal_features import (
    TemporalFeatureExtractor,
    TemporalFeatureConfig,
)
from soc_copilot.data.feature_engineering.behavioral_features import (
    BehavioralFeatureExtractor,
    BehavioralFeatureConfig,
)
from soc_copilot.data.feature_engineering.network_features import (
    NetworkFeatureExtractor,
    NetworkFeatureConfig,
)
from soc_copilot.data.feature_engineering.pipeline import (
    FeatureEngineeringPipeline,
    FeaturePipelineConfig,
    create_default_pipeline,
)

__all__ = [
    # Base
    "BaseFeatureExtractor",
    "FeatureDefinition",
    "FeatureType",
    "entropy",
    "safe_divide",
    # Statistical
    "StatisticalFeatureExtractor",
    "StatisticalFeatureConfig",
    # Temporal
    "TemporalFeatureExtractor",
    "TemporalFeatureConfig",
    # Behavioral
    "BehavioralFeatureExtractor",
    "BehavioralFeatureConfig",
    # Network
    "NetworkFeatureExtractor",
    "NetworkFeatureConfig",
    # Pipeline
    "FeatureEngineeringPipeline",
    "FeaturePipelineConfig",
    "create_default_pipeline",
]
