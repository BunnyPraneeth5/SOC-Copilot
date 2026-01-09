"""Unified analysis pipeline for SOC Copilot.

Integrates feature extraction, model inference, and ensemble scoring
into a single pipeline for analyzing log records.
"""

from typing import Any
import pandas as pd
import numpy as np

from soc_copilot.models.inference.engine import (
    ModelInference,
    InferenceConfig,
)
from soc_copilot.models.ensemble.coordinator import (
    EnsembleCoordinator,
    EnsembleConfig,
    EnsembleResult,
)
from soc_copilot.models.ensemble.alert_generator import (
    AlertGenerator,
    Alert,
    format_alert_summary,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class AnalysisPipelineConfig:
    """Configuration for analysis pipeline."""
    
    def __init__(
        self,
        models_dir: str = "data/models",
        inference_config: InferenceConfig | None = None,
        ensemble_config: EnsembleConfig | None = None,
        include_mitre: bool = True,
    ):
        self.models_dir = models_dir
        self.inference_config = inference_config or InferenceConfig(models_dir=models_dir)
        self.ensemble_config = ensemble_config or EnsembleConfig()
        self.include_mitre = include_mitre


class AnalysisResult:
    """Result from full analysis pipeline."""
    
    def __init__(
        self,
        ensemble_result: EnsembleResult,
        alert: Alert | None,
        source_context: dict[str, Any],
    ):
        self.ensemble_result = ensemble_result
        self.alert = alert
        self.source_context = source_context
    
    @property
    def risk_level(self) -> str:
        return self.ensemble_result.risk_level.value
    
    @property
    def requires_alert(self) -> bool:
        return self.ensemble_result.requires_alert
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "anomaly_score": self.ensemble_result.anomaly_score,
            "classification": self.ensemble_result.classification,
            "confidence": self.ensemble_result.class_confidence,
            "risk_score": self.ensemble_result.combined_risk_score,
            "risk_level": self.ensemble_result.risk_level.value,
            "priority": self.ensemble_result.alert_priority.value,
            "threat_category": self.ensemble_result.threat_category.value,
            "reasoning": self.ensemble_result.reasoning,
            "suggested_action": self.ensemble_result.suggested_action,
            "requires_alert": self.ensemble_result.requires_alert,
            "alert_id": self.alert.alert_id if self.alert else None,
        }


class AnalysisPipeline:
    """Full analysis pipeline for SOC Copilot.
    
    Combines:
    1. Model inference (IF + RF)
    2. Ensemble scoring
    3. Alert generation
    
    Usage:
        pipeline = AnalysisPipeline()
        pipeline.load()
        result = pipeline.analyze(features)
    """
    
    def __init__(self, config: AnalysisPipelineConfig | None = None):
        """Initialize pipeline.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or AnalysisPipelineConfig()
        
        self._inference = ModelInference(self.config.inference_config)
        self._ensemble = EnsembleCoordinator(self.config.ensemble_config)
        self._alert_generator = AlertGenerator(self.config.include_mitre)
        
        self._loaded = False
    
    @property
    def is_loaded(self) -> bool:
        """Whether models are loaded."""
        return self._loaded
    
    @property
    def feature_order(self) -> list[str]:
        """Get expected feature order."""
        return self._inference.feature_order
    
    def load(self) -> None:
        """Load models from disk."""
        self._inference.load_models()
        self._loaded = True
        
        logger.info(
            "analysis_pipeline_loaded",
            features=len(self.feature_order),
        )
    
    def analyze(
        self,
        features: dict[str, float] | np.ndarray,
        source_context: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        """Analyze a single record.
        
        Args:
            features: Feature values (dict or array)
            source_context: Optional source metadata (IPs, ports)
            
        Returns:
            AnalysisResult with full assessment
        """
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")
        
        context = source_context or {}
        
        # Step 1: Model inference
        anomaly_score = self._inference.score_anomaly(features)
        classification, class_probs = self._inference.classify(features)
        confidence = max(class_probs.values()) if class_probs else 0.0
        
        # Step 2: Ensemble scoring
        ensemble_result = self._ensemble.score(
            anomaly_score=anomaly_score,
            classification=classification,
            class_confidence=confidence,
            class_probabilities=class_probs,
        )
        
        # Step 3: Alert generation
        alert = self._alert_generator.generate(ensemble_result, context)
        
        return AnalysisResult(
            ensemble_result=ensemble_result,
            alert=alert,
            source_context=context,
        )
    
    def analyze_batch(
        self,
        X: np.ndarray,
        contexts: list[dict[str, Any]] | None = None,
    ) -> list[AnalysisResult]:
        """Analyze a batch of records.
        
        Args:
            X: Feature matrix (samples x features)
            contexts: Optional list of source contexts
            
        Returns:
            List of AnalysisResults
        """
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")
        
        contexts = contexts or [{}] * len(X)
        results = []
        
        for i in range(len(X)):
            result = self.analyze(X[i], contexts[i] if i < len(contexts) else {})
            results.append(result)
        
        # Log summary
        alerts = [r for r in results if r.requires_alert]
        
        logger.info(
            "batch_analysis_complete",
            total=len(results),
            alerts_generated=len(alerts),
        )
        
        return results
    
    def get_statistics(self, results: list[AnalysisResult]) -> dict[str, Any]:
        """Get statistics from analysis results.
        
        Args:
            results: List of AnalysisResults
            
        Returns:
            Statistics dictionary
        """
        if not results:
            return {}
        
        anomaly_scores = [r.ensemble_result.anomaly_score for r in results]
        risk_scores = [r.ensemble_result.combined_risk_score for r in results]
        
        from collections import Counter
        classifications = Counter(r.ensemble_result.classification for r in results)
        risk_levels = Counter(r.ensemble_result.risk_level.value for r in results)
        
        return {
            "total_records": len(results),
            "alerts_generated": sum(1 for r in results if r.requires_alert),
            "anomaly_score_mean": np.mean(anomaly_scores),
            "anomaly_score_std": np.std(anomaly_scores),
            "risk_score_mean": np.mean(risk_scores),
            "risk_score_std": np.std(risk_scores),
            "classification_distribution": dict(classifications),
            "risk_level_distribution": dict(risk_levels),
        }


def create_analysis_pipeline(models_dir: str = "data/models") -> AnalysisPipeline:
    """Create and load analysis pipeline.
    
    Args:
        models_dir: Path to models directory
        
    Returns:
        Loaded AnalysisPipeline
    """
    config = AnalysisPipelineConfig(models_dir=models_dir)
    pipeline = AnalysisPipeline(config)
    pipeline.load()
    return pipeline
