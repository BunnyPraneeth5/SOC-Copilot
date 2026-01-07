"""Pydantic configuration schemas for SOC Copilot.

Provides type-safe configuration loading and validation for all YAML config files.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Thresholds Configuration
# =============================================================================

class AnomalyThresholds(BaseModel):
    """Isolation Forest anomaly score thresholds."""
    
    low_threshold: float = Field(0.3, ge=0.0, le=1.0)
    high_threshold: float = Field(0.7, ge=0.0, le=1.0)
    
    @field_validator("high_threshold")
    @classmethod
    def high_greater_than_low(cls, v: float, info) -> float:
        if "low_threshold" in info.data and v <= info.data["low_threshold"]:
            raise ValueError("high_threshold must be greater than low_threshold")
        return v


class Weights(BaseModel):
    """Priority calculation weights (must sum to 1.0)."""
    
    isolation_forest: float = Field(0.4, ge=0.0, le=1.0)
    random_forest: float = Field(0.4, ge=0.0, le=1.0)
    context: float = Field(0.2, ge=0.0, le=1.0)
    
    @field_validator("context")
    @classmethod
    def weights_sum_to_one(cls, v: float, info) -> float:
        total = (
            info.data.get("isolation_forest", 0.4) +
            info.data.get("random_forest", 0.4) +
            v
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")
        return v


class ClassificationThresholds(BaseModel):
    """Random Forest classification confidence thresholds."""
    
    min_confidence: float = Field(0.7, ge=0.0, le=1.0)
    unknown_threshold: float = Field(0.3, ge=0.0, le=1.0)


class PriorityThresholds(BaseModel):
    """Alert priority thresholds based on final score."""
    
    critical: float = Field(0.85, ge=0.0, le=1.0)
    high: float = Field(0.70, ge=0.0, le=1.0)
    medium: float = Field(0.50, ge=0.0, le=1.0)
    low: float = Field(0.30, ge=0.0, le=1.0)


class DeduplicationSettings(BaseModel):
    """Alert deduplication settings."""
    
    window_seconds: int = Field(300, ge=1)
    group_by: list[str] = Field(default_factory=lambda: ["src_ip", "dst_ip", "attack_class"])


class ConservativeMode(BaseModel):
    """Conservative mode settings for reducing alert fatigue."""
    
    enabled: bool = True
    min_signals: int = Field(2, ge=1)
    never_suppress_high_anomaly: bool = True


class ThresholdsConfig(BaseModel):
    """Complete thresholds configuration."""
    
    anomaly: AnomalyThresholds = Field(default_factory=AnomalyThresholds)
    weights: Weights = Field(default_factory=Weights)
    classification: ClassificationThresholds = Field(default_factory=ClassificationThresholds)
    priority: PriorityThresholds = Field(default_factory=PriorityThresholds)
    deduplication: DeduplicationSettings = Field(default_factory=DeduplicationSettings)
    conservative_mode: ConservativeMode = Field(default_factory=ConservativeMode)


# =============================================================================
# Feature Configuration
# =============================================================================

class FeatureDefinition(BaseModel):
    """Single feature definition."""
    
    name: str
    description: str
    aggregation: str | None = None
    field: str | None = None
    type: str | None = None
    component: str | None = None
    threshold: int | None = None
    window: int | None = None
    baseline_window: int | None = None
    lookback: int | None = None
    business_start: int | None = None
    business_end: int | None = None
    entity_field: str | None = None


class FeatureCategory(BaseModel):
    """Category of features (statistical, temporal, etc.)."""
    
    enabled: bool = True
    features: list[FeatureDefinition] = Field(default_factory=list)


class FeatureSettings(BaseModel):
    """Global feature settings."""
    
    default_window: int = Field(300, ge=1)
    entity_types: list[str] = Field(
        default_factory=lambda: ["user", "src_ip", "dst_ip", "host"]
    )


class FeaturesConfig(BaseModel):
    """Complete features configuration."""
    
    settings: FeatureSettings = Field(default_factory=FeatureSettings)
    statistical: FeatureCategory = Field(default_factory=FeatureCategory)
    temporal: FeatureCategory = Field(default_factory=FeatureCategory)
    behavioral: FeatureCategory = Field(default_factory=FeatureCategory)
    network: FeatureCategory = Field(default_factory=FeatureCategory)


# =============================================================================
# Model Configuration
# =============================================================================

class IFTrainingSettings(BaseModel):
    """Isolation Forest training settings."""
    
    min_samples: int = Field(1000, ge=1)
    baseline_days: int = Field(7, ge=1)
    retrain_trigger: int = Field(10000, ge=1)


class IFInferenceSettings(BaseModel):
    """Isolation Forest inference settings."""
    
    batch_size: int = Field(1000, ge=1)


class IsolationForestConfig(BaseModel):
    """Isolation Forest model configuration."""
    
    n_estimators: int = Field(100, ge=1)
    max_samples: str | int = "auto"
    contamination: float = Field(0.1, ge=0.0, le=0.5)
    max_features: float = Field(1.0, ge=0.0, le=1.0)
    bootstrap: bool = False
    random_state: int = 42
    training: IFTrainingSettings = Field(default_factory=IFTrainingSettings)
    inference: IFInferenceSettings = Field(default_factory=IFInferenceSettings)
    model_path: str = "data/models/isolation_forest"
    version_format: str = "if_v{version}_{timestamp}.joblib"


class RFTrainingSettings(BaseModel):
    """Random Forest training settings."""
    
    min_samples_per_class: int = Field(100, ge=1)
    test_split: float = Field(0.2, ge=0.0, le=0.5)
    cross_validation_folds: int = Field(5, ge=2)


class RFInferenceSettings(BaseModel):
    """Random Forest inference settings."""
    
    batch_size: int = Field(1000, ge=1)
    return_probabilities: bool = True


class RandomForestConfig(BaseModel):
    """Random Forest model configuration."""
    
    n_estimators: int = Field(100, ge=1)
    max_depth: int | None = Field(20, ge=1)
    min_samples_split: int = Field(5, ge=2)
    min_samples_leaf: int = Field(2, ge=1)
    max_features: str = "sqrt"
    class_weight: str = "balanced"
    random_state: int = 42
    n_jobs: int = -1
    classes: list[str] = Field(
        default_factory=lambda: [
            "Benign", "DDoS", "BruteForce", "Malware",
            "Exfiltration", "Reconnaissance", "Injection"
        ]
    )
    training: RFTrainingSettings = Field(default_factory=RFTrainingSettings)
    inference: RFInferenceSettings = Field(default_factory=RFInferenceSettings)
    model_path: str = "data/models/random_forest"
    version_format: str = "rf_v{version}_{timestamp}.joblib"


class EnsembleFusion(BaseModel):
    """Ensemble decision fusion parameters."""
    
    if_weight: float = Field(0.4, ge=0.0, le=1.0)
    rf_weight: float = Field(0.4, ge=0.0, le=1.0)
    context_weight: float = Field(0.2, ge=0.0, le=1.0)


class EnsembleConfig(BaseModel):
    """Ensemble controller configuration."""
    
    load_on_startup: bool = True
    fallback_to_default: bool = True
    parallel_inference: bool = True
    timeout_seconds: int = Field(30, ge=1)
    fusion: EnsembleFusion = Field(default_factory=EnsembleFusion)


class AutoencoderConfig(BaseModel):
    """Autoencoder configuration (Phase-2 placeholder)."""
    
    enabled: bool = False


class ModelConfig(BaseModel):
    """Complete model configuration."""
    
    isolation_forest: IsolationForestConfig = Field(default_factory=IsolationForestConfig)
    random_forest: RandomForestConfig = Field(default_factory=RandomForestConfig)
    ensemble: EnsembleConfig = Field(default_factory=EnsembleConfig)
    autoencoder: AutoencoderConfig = Field(default_factory=AutoencoderConfig)


# =============================================================================
# Configuration Loader
# =============================================================================

class ConfigLoader:
    """Loads and validates configuration files."""
    
    def __init__(self, config_dir: Path | str = "config"):
        self.config_dir = Path(config_dir)
    
    def _load_yaml(self, filename: str) -> dict:
        """Load a YAML file from the config directory."""
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath, "r") as f:
            return yaml.safe_load(f) or {}
    
    def load_thresholds(self) -> ThresholdsConfig:
        """Load and validate thresholds configuration."""
        data = self._load_yaml("thresholds.yaml")
        return ThresholdsConfig(**data)
    
    def load_features(self) -> FeaturesConfig:
        """Load and validate features configuration."""
        data = self._load_yaml("features.yaml")
        return FeaturesConfig(**data)
    
    def load_models(self) -> ModelConfig:
        """Load and validate model configuration."""
        data = self._load_yaml("model_config.yaml")
        return ModelConfig(**data)
    
    def load_all(self) -> tuple[ThresholdsConfig, FeaturesConfig, ModelConfig]:
        """Load all configuration files."""
        return (
            self.load_thresholds(),
            self.load_features(),
            self.load_models(),
        )
