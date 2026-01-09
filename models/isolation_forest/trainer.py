"""Isolation Forest trainer for anomaly detection.

Trains on benign-only data to learn normal behavior patterns.
Outputs normalized anomaly scores in range [0, 1].
"""

import json
from pathlib import Path
from datetime import datetime

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from pydantic import BaseModel

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class IsolationForestConfig(BaseModel):
    """Configuration for Isolation Forest training."""
    
    # Isolation Forest hyperparameters
    n_estimators: int = 100
    max_samples: str | int = "auto"
    contamination: float = 0.01  # Expected anomaly rate
    max_features: float = 1.0
    bootstrap: bool = False
    
    # Random seed for reproducibility
    random_state: int = 42
    
    # Output paths
    model_output_dir: str = "data/models"
    model_name: str = "isolation_forest_v1"


class IsolationForestTrainer:
    """Trains Isolation Forest for unsupervised anomaly detection.
    
    Training approach:
    - Uses only benign/normal data
    - Learns distribution of normal behavior
    - Anomalies are points far from learned distribution
    
    Output:
    - Normalized anomaly score [0, 1] where higher = more anomalous
    - Model persisted with feature order for inference consistency
    """
    
    def __init__(self, config: IsolationForestConfig | None = None):
        """Initialize trainer.
        
        Args:
            config: Training configuration
        """
        self.config = config or IsolationForestConfig()
        
        self.model: IsolationForest | None = None
        self.scaler: StandardScaler | None = None
        self.feature_names: list[str] = []
        
        self._training_stats: dict = {}
    
    def train(
        self,
        X: np.ndarray,
        feature_names: list[str],
    ) -> None:
        """Train the Isolation Forest model.
        
        Args:
            X: Feature matrix (benign samples only)
            feature_names: Names of features in order
        """
        logger.info(
            "isolation_forest_training_start",
            samples=X.shape[0],
            features=X.shape[1],
        )
        
        self.feature_names = feature_names
        
        # Standardize features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Handle any remaining NaN/Inf
        X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Train Isolation Forest
        self.model = IsolationForest(
            n_estimators=self.config.n_estimators,
            max_samples=self.config.max_samples,
            contamination=self.config.contamination,
            max_features=self.config.max_features,
            bootstrap=self.config.bootstrap,
            random_state=self.config.random_state,
            n_jobs=-1,
        )
        
        self.model.fit(X_scaled)
        
        # Compute training statistics
        train_scores = self.model.decision_function(X_scaled)
        train_predictions = self.model.predict(X_scaled)
        
        self._training_stats = {
            "samples_trained": X.shape[0],
            "features": X.shape[1],
            "n_estimators": self.config.n_estimators,
            "contamination": self.config.contamination,
            "train_score_mean": float(np.mean(train_scores)),
            "train_score_std": float(np.std(train_scores)),
            "train_inliers": int((train_predictions == 1).sum()),
            "train_outliers": int((train_predictions == -1).sum()),
            "trained_at": datetime.now().isoformat(),
        }
        
        logger.info(
            "isolation_forest_training_complete",
            **self._training_stats,
        )
    
    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute normalized anomaly scores.
        
        Args:
            X: Feature matrix
            
        Returns:
            Anomaly scores in range [0, 1] where higher = more anomalous
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained")
        
        X_scaled = self.scaler.transform(X)
        X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
        
        # decision_function returns negative scores for anomalies
        # More negative = more anomalous
        raw_scores = self.model.decision_function(X_scaled)
        
        # Normalize to [0, 1] where higher = more anomalous
        # Using sigmoid-like transformation centered on 0
        normalized = 1 / (1 + np.exp(raw_scores))
        
        return normalized
    
    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predict anomaly labels.
        
        Args:
            X: Feature matrix
            threshold: Score threshold for anomaly classification
            
        Returns:
            Binary predictions (1 = anomaly, 0 = normal)
        """
        scores = self.score(X)
        return (scores >= threshold).astype(int)
    
    def save(self, output_dir: str | Path | None = None) -> dict[str, str]:
        """Save trained model and metadata.
        
        Args:
            output_dir: Output directory (uses config default if None)
            
        Returns:
            Dict with paths to saved files
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        output_dir = Path(output_dir or self.config.model_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save model
        model_path = output_dir / f"{self.config.model_name}.joblib"
        joblib.dump({
            "model": self.model,
            "scaler": self.scaler,
            "config": self.config.model_dump(),
            "training_stats": self._training_stats,
        }, model_path)
        
        # Save feature order
        feature_path = output_dir / "feature_order.json"
        with open(feature_path, "w") as f:
            json.dump({
                "feature_names": self.feature_names,
                "feature_count": len(self.feature_names),
                "model": self.config.model_name,
            }, f, indent=2)
        
        paths = {
            "model": str(model_path),
            "features": str(feature_path),
        }
        
        logger.info("isolation_forest_saved", **paths)
        
        return paths
    
    def get_training_stats(self) -> dict:
        """Get training statistics.
        
        Returns:
            Dict with training stats
        """
        return self._training_stats.copy()


def load_isolation_forest(model_path: str | Path) -> IsolationForestTrainer:
    """Load a trained Isolation Forest model.
    
    Args:
        model_path: Path to .joblib model file
        
    Returns:
        Loaded IsolationForestTrainer
    """
    model_path = Path(model_path)
    
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    data = joblib.load(model_path)
    
    config = IsolationForestConfig(**data["config"])
    trainer = IsolationForestTrainer(config)
    trainer.model = data["model"]
    trainer.scaler = data["scaler"]
    trainer._training_stats = data.get("training_stats", {})
    
    # Load feature order if available
    feature_path = model_path.parent / "feature_order.json"
    if feature_path.exists():
        with open(feature_path) as f:
            feature_data = json.load(f)
            trainer.feature_names = feature_data.get("feature_names", [])
    
    logger.info(
        "isolation_forest_loaded",
        path=str(model_path),
        features=len(trainer.feature_names),
    )
    
    return trainer
