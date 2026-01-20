"""
Unified analysis pipeline for SOC Copilot.

Integrates feature extraction, model inference, and ensemble scoring
into a single pipeline for analyzing log records.
"""

from typing import Any
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
)
from soc_copilot.models.ensemble.deduplication import EventDeduplicator
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
        benign_cooldown: float = 60.0,
    ):
        self.models_dir = models_dir
        self.inference_config = inference_config or InferenceConfig(
            models_dir=models_dir
        )
        self.ensemble_config = ensemble_config or EnsembleConfig()
        self.include_mitre = include_mitre
        self.benign_cooldown = benign_cooldown


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
        """Convert result to dictionary."""
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
    1. Model inference (Isolation Forest + Random Forest)
    2. Ensemble scoring
    3. Alert generation
    """

    def __init__(self, config: AnalysisPipelineConfig | None = None):
        self.config = config or AnalysisPipelineConfig()

        self._inference = ModelInference(self.config.inference_config)
        self._ensemble = EnsembleCoordinator(self.config.ensemble_config)
        self._alert_generator = AlertGenerator(self.config.include_mitre)
        self._deduplicator = EventDeduplicator(self.config.benign_cooldown)

        self._loaded = False
        self._analysis_count = 0

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def feature_order(self) -> list[str]:
        return self._inference.feature_order

    def load(self) -> None:
        """Load ML models."""
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
    ) -> AnalysisResult | None:
        """
        Analyze a single log record.

        Returns:
            AnalysisResult or None if benign event was deduplicated
        """
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")

        context = source_context or {}

        # Periodic deduplication cleanup
        self._analysis_count += 1
        if self._analysis_count % 1000 == 0:
            self._deduplicator.cleanup_old_entries()

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

        # Step 2.5: Benign event deduplication (CRITICAL FIX)
        alert: Alert | None = None

        if ensemble_result.requires_alert:
            # Always process alert-worthy events
            alert = self._alert_generator.generate(ensemble_result, context)

        else:
            # Apply cooldown to benign / non-alert events
            fingerprint = self._deduplicator.fingerprint_event(
                classification=classification,
                anomaly_score=anomaly_score,
                source_ip=context.get("src_ip"),
            )

            if not self._deduplicator.should_process(fingerprint):
                # Terminal state: suppress duplicate benign event
                return None

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
        """Analyze batch of records."""
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")

        contexts = contexts or [{}] * len(X)
        results: list[AnalysisResult] = []

        for i in range(len(X)):
            result = self.analyze(
                X[i],
                contexts[i] if i < len(contexts) else {},
            )
            if result is not None:
                results.append(result)

        alerts = [r for r in results if r.requires_alert]

        logger.info(
            "batch_analysis_complete",
            total=len(results),
            alerts_generated=len(alerts),
        )

        return results

    def get_statistics(self, results: list[AnalysisResult]) -> dict[str, Any]:
        """Generate statistics from results."""
        if not results:
            return {}

        anomaly_scores = [r.ensemble_result.anomaly_score for r in results]
        risk_scores = [r.ensemble_result.combined_risk_score for r in results]

        from collections import Counter

        classifications = Counter(
            r.ensemble_result.classification for r in results
        )
        risk_levels = Counter(
            r.ensemble_result.risk_level.value for r in results
        )

        return {
            "total_records": len(results),
            "alerts_generated": sum(1 for r in results if r.requires_alert),
            "anomaly_score_mean": float(np.mean(anomaly_scores)),
            "anomaly_score_std": float(np.std(anomaly_scores)),
            "risk_score_mean": float(np.mean(risk_scores)),
            "risk_score_std": float(np.std(risk_scores)),
            "classification_distribution": dict(classifications),
            "risk_level_distribution": dict(risk_levels),
        }


def create_analysis_pipeline(models_dir: str = "data/models") -> AnalysisPipeline:
    """Factory helper to create and load pipeline."""
    config = AnalysisPipelineConfig(models_dir=models_dir)
    pipeline = AnalysisPipeline(config)
    pipeline.load()
    return pipeline
