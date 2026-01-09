"""Inference module for trained ML models.

Provides a unified interface for loading and running inference
with trained models. Completely separate from training code.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import joblib
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class InferenceConfig(BaseModel):
    """Configuration for model inference."""
    
    # Model paths
    models_dir: str = "data/models"
    isolation_forest_name: str = "isolation_forest_v1"
    random_forest_name: str = "random_forest_v1"
    
    # Anomaly detection threshold
    anomaly_threshold: float = 0.5
    
    # Classification confidence threshold
    confidence_threshold: float = 0.7


class InferenceResult(BaseModel):
    """Result from inference pipeline."""
    
    # Anomaly detection
    anomaly_score: float = 0.0
    is_anomaly: bool = False
    
    # Classification
    predicted_class: str = "Unknown"
    class_probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    
    # Combined risk assessment
    risk_level: str = "Low"  # Low, Medium, High, Critical
    
    # Metadata
    model_versions: dict[str, str] = Field(default_factory=dict)


def compute_risk_level(
    anomaly_score: float,
    predicted_class: str,
    confidence: float,
) -> str:
    """Compute overall risk level.
    
    Args:
        anomaly_score: Normalized anomaly score [0, 1]
        predicted_class: Predicted attack class
        confidence: Classification confidence
        
    Returns:
        Risk level: Low, Medium, High, or Critical
    """
    # High anomaly + malicious class = Critical
    if anomaly_score > 0.8 and predicted_class != "Benign" and confidence > 0.7:
        return "Critical"
    
    # High anomaly or clear malicious class
    if anomaly_score > 0.7 or (predicted_class in ["Malware", "Exfiltration"] and confidence > 0.5):
        return "High"
    
    # Moderate signals
    if anomaly_score > 0.5 or (predicted_class != "Benign" and confidence > 0.5):
        return "Medium"
    
    return "Low"


class ModelInference:
    """Unified inference interface for SOC Copilot models.
    
    Loads trained models and provides inference methods.
    Ensures feature order consistency with training.
    
    This module is completely separate from training code.
    It only loads persisted models and runs inference.
    """
    
    def __init__(self, config: InferenceConfig | None = None):
        """Initialize inference engine.
        
        Args:
            config: Inference configuration
        """
        self.config = config or InferenceConfig()
        
        self._isolation_forest = None
        self._random_forest = None
        self._feature_order: list[str] = []
        self._label_classes: list[str] = []
        
        self._loaded = False
    
    @property
    def is_loaded(self) -> bool:
        """Whether models are loaded."""
        return self._loaded
    
    @property
    def feature_order(self) -> list[str]:
        """Get expected feature order."""
        return self._feature_order.copy()
    
    @property
    def classes(self) -> list[str]:
        """Get classification classes."""
        return self._label_classes.copy()
    
    def load_models(self) -> None:
        """Load all trained models from disk."""
        models_dir = Path(self.config.models_dir)
        
        if not models_dir.exists():
            raise FileNotFoundError(f"Models directory not found: {models_dir}")
        
        # Load feature order first
        feature_path = models_dir / "feature_order.json"
        if feature_path.exists():
            with open(feature_path) as f:
                feature_data = json.load(f)
                self._feature_order = feature_data.get("feature_names", [])
        
        # Load label map
        label_path = models_dir / "label_map.json"
        if label_path.exists():
            with open(label_path) as f:
                label_data = json.load(f)
                self._label_classes = label_data.get("classes", [])
        
        # Load Isolation Forest
        if_path = models_dir / f"{self.config.isolation_forest_name}.joblib"
        if if_path.exists():
            self._isolation_forest = joblib.load(if_path)
            logger.info("isolation_forest_loaded", path=str(if_path))
        else:
            logger.warning("isolation_forest_not_found", path=str(if_path))
        
        # Load Random Forest
        rf_path = models_dir / f"{self.config.random_forest_name}.joblib"
        if rf_path.exists():
            self._random_forest = joblib.load(rf_path)
            logger.info("random_forest_loaded", path=str(rf_path))
        else:
            logger.warning("random_forest_not_found", path=str(rf_path))
        
        self._loaded = True
        
        logger.info(
            "models_loaded",
            isolation_forest=self._isolation_forest is not None,
            random_forest=self._random_forest is not None,
            feature_count=len(self._feature_order),
        )
    
    def _prepare_features(self, features: dict[str, float] | np.ndarray) -> np.ndarray:
        """Prepare feature vector in correct order.
        
        Args:
            features: Either a dict of feature_name -> value or pre-ordered array
            
        Returns:
            Feature array in correct order
        """
        if isinstance(features, np.ndarray):
            return features.reshape(1, -1) if features.ndim == 1 else features
        
        # Convert dict to array in correct order
        if not self._feature_order:
            raise RuntimeError("Feature order not loaded")
        
        vector = np.zeros(len(self._feature_order))
        for i, name in enumerate(self._feature_order):
            vector[i] = features.get(name, 0.0)
        
        return vector.reshape(1, -1)
    
    def score_anomaly(self, features: dict[str, float] | np.ndarray) -> float:
        """Compute anomaly score for a single sample.
        
        Args:
            features: Feature values (dict or array)
            
        Returns:
            Normalized anomaly score [0, 1]
        """
        if self._isolation_forest is None:
            logger.warning("isolation_forest_not_loaded")
            return 0.0
        
        X = self._prepare_features(features)
        
        # Apply stored scaler
        scaler = self._isolation_forest.get("scaler")
        if scaler:
            X = scaler.transform(X)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Get decision function score
        model = self._isolation_forest.get("model")
        if model is None:
            return 0.0
        
        raw_score = model.decision_function(X)[0]
        
        # Normalize to [0, 1] where higher = more anomalous
        normalized = 1 / (1 + np.exp(raw_score))
        
        return float(normalized)
    
    def classify(
        self,
        features: dict[str, float] | np.ndarray,
    ) -> tuple[str, dict[str, float]]:
        """Classify a single sample.
        
        Args:
            features: Feature values (dict or array)
            
        Returns:
            Tuple of (predicted_class, class_probabilities)
        """
        if self._random_forest is None:
            logger.warning("random_forest_not_loaded")
            return "Unknown", {}
        
        X = self._prepare_features(features)
        
        # Apply stored scaler
        scaler = self._random_forest.get("scaler")
        if scaler:
            X = scaler.transform(X)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        model = self._random_forest.get("model")
        label_encoder = self._random_forest.get("label_encoder")
        
        if model is None or label_encoder is None:
            return "Unknown", {}
        
        # Get prediction and probabilities
        pred_encoded = model.predict(X)[0]
        probas = model.predict_proba(X)[0]
        
        predicted_class = label_encoder.inverse_transform([pred_encoded])[0]
        classes = label_encoder.classes_
        
        class_probs = {str(c): float(p) for c, p in zip(classes, probas)}
        
        return predicted_class, class_probs
    
    def infer(self, features: dict[str, float] | np.ndarray) -> InferenceResult:
        """Run full inference pipeline on a sample.
        
        Args:
            features: Feature values (dict or array)
            
        Returns:
            InferenceResult with all predictions
        """
        if not self._loaded:
            raise RuntimeError("Models not loaded. Call load_models() first.")
        
        # Anomaly detection
        anomaly_score = self.score_anomaly(features)
        is_anomaly = anomaly_score >= self.config.anomaly_threshold
        
        # Classification
        predicted_class, class_probs = self.classify(features)
        confidence = max(class_probs.values()) if class_probs else 0.0
        
        # Risk assessment
        risk_level = compute_risk_level(anomaly_score, predicted_class, confidence)
        
        return InferenceResult(
            anomaly_score=anomaly_score,
            is_anomaly=is_anomaly,
            predicted_class=predicted_class,
            class_probabilities=class_probs,
            confidence=confidence,
            risk_level=risk_level,
            model_versions={
                "isolation_forest": self.config.isolation_forest_name,
                "random_forest": self.config.random_forest_name,
            },
        )
    
    def infer_batch(
        self,
        X: np.ndarray,
    ) -> list[InferenceResult]:
        """Run inference on a batch of samples.
        
        Args:
            X: Feature matrix (samples x features)
            
        Returns:
            List of InferenceResults
        """
        if not self._loaded:
            raise RuntimeError("Models not loaded. Call load_models() first.")
        
        results = []
        for i in range(X.shape[0]):
            result = self.infer(X[i])
            results.append(result)
        
        return results


def create_inference_engine(models_dir: str = "data/models") -> ModelInference:
    """Create and load inference engine.
    
    Args:
        models_dir: Path to models directory
        
    Returns:
        Loaded ModelInference instance
    """
    config = InferenceConfig(models_dir=models_dir)
    engine = ModelInference(config)
    engine.load_models()
    return engine
