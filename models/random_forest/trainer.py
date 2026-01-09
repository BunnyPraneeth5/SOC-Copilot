"""Random Forest trainer for multi-class attack classification.

Trains on labeled data to classify network traffic into SOC categories.
"""

import json
from pathlib import Path
from datetime import datetime

import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class RandomForestConfig(BaseModel):
    """Configuration for Random Forest training."""
    
    # Random Forest hyperparameters
    n_estimators: int = 100
    max_depth: int | None = None
    min_samples_split: int = 2
    min_samples_leaf: int = 1
    max_features: str = "sqrt"
    
    # Class imbalance handling
    class_weight: str | dict | None = "balanced"
    
    # Random seed for reproducibility
    random_state: int = 42
    
    # Output paths
    model_output_dir: str = "data/models"
    model_name: str = "random_forest_v1"


class RandomForestTrainer:
    """Trains Random Forest for multi-class attack classification.
    
    Classes (SOC taxonomy):
    - Benign
    - DDoS
    - BruteForce
    - Malware
    - Exfiltration
    
    Features:
    - Handles class imbalance with configurable weights
    - Outputs class probabilities
    - Saves model with label encoder for consistent inference
    """
    
    def __init__(self, config: RandomForestConfig | None = None):
        """Initialize trainer.
        
        Args:
            config: Training configuration
        """
        self.config = config or RandomForestConfig()
        
        self.model: RandomForestClassifier | None = None
        self.scaler: StandardScaler | None = None
        self.label_encoder: LabelEncoder | None = None
        self.feature_names: list[str] = []
        self.classes: list[str] = []
        
        self._training_stats: dict = {}
    
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        feature_names: list[str],
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> dict:
        """Train the Random Forest classifier.
        
        Args:
            X_train: Training feature matrix
            y_train: Training labels (string labels)
            feature_names: Names of features in order
            X_val: Optional validation features
            y_val: Optional validation labels
            
        Returns:
            Dict with training metrics
        """
        logger.info(
            "random_forest_training_start",
            train_samples=X_train.shape[0],
            features=X_train.shape[1],
        )
        
        self.feature_names = feature_names
        
        # Encode labels
        self.label_encoder = LabelEncoder()
        y_train_encoded = self.label_encoder.fit_transform(y_train)
        self.classes = list(self.label_encoder.classes_)
        
        # Log class distribution
        unique, counts = np.unique(y_train, return_counts=True)
        class_dist = dict(zip(unique, counts))
        logger.info("class_distribution", distribution=class_dist)
        
        # Standardize features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_train_scaled = np.nan_to_num(X_train_scaled, nan=0.0, posinf=0.0, neginf=0.0)
        
        # Train Random Forest
        self.model = RandomForestClassifier(
            n_estimators=self.config.n_estimators,
            max_depth=self.config.max_depth,
            min_samples_split=self.config.min_samples_split,
            min_samples_leaf=self.config.min_samples_leaf,
            max_features=self.config.max_features,
            class_weight=self.config.class_weight,
            random_state=self.config.random_state,
            n_jobs=-1,
        )
        
        self.model.fit(X_train_scaled, y_train_encoded)
        
        # Training metrics
        train_pred = self.model.predict(X_train_scaled)
        train_accuracy = accuracy_score(y_train_encoded, train_pred)
        
        self._training_stats = {
            "train_samples": X_train.shape[0],
            "features": X_train.shape[1],
            "n_classes": len(self.classes),
            "classes": self.classes,
            "n_estimators": self.config.n_estimators,
            "train_accuracy": float(train_accuracy),
            "class_distribution": class_dist,
            "trained_at": datetime.now().isoformat(),
        }
        
        # Validation metrics if provided
        if X_val is not None and y_val is not None:
            val_metrics = self.evaluate(X_val, y_val)
            self._training_stats["val_accuracy"] = val_metrics["accuracy"]
            self._training_stats["val_samples"] = len(y_val)
        
        logger.info(
            "random_forest_training_complete",
            train_accuracy=train_accuracy,
            classes=len(self.classes),
        )
        
        return self._training_stats
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels.
        
        Args:
            X: Feature matrix
            
        Returns:
            String class labels
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained")
        
        X_scaled = self.scaler.transform(X)
        X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
        
        y_encoded = self.model.predict(X_scaled)
        return self.label_encoder.inverse_transform(y_encoded)
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities.
        
        Args:
            X: Feature matrix
            
        Returns:
            Probability matrix (samples x classes)
        """
        if self.model is None or self.scaler is None:
            raise RuntimeError("Model not trained")
        
        X_scaled = self.scaler.transform(X)
        X_scaled = np.nan_to_num(X_scaled, nan=0.0, posinf=0.0, neginf=0.0)
        
        return self.model.predict_proba(X_scaled)
    
    def evaluate(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Evaluate model on test data.
        
        Args:
            X: Test feature matrix
            y: True labels (string labels)
            
        Returns:
            Dict with evaluation metrics
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        y_pred = self.predict(X)
        y_encoded = self.label_encoder.transform(y)
        y_pred_encoded = self.label_encoder.transform(y_pred)
        
        accuracy = accuracy_score(y_encoded, y_pred_encoded)
        cm = confusion_matrix(y_encoded, y_pred_encoded)
        report = classification_report(y, y_pred, output_dict=True, zero_division=0)
        
        return {
            "accuracy": float(accuracy),
            "confusion_matrix": cm.tolist(),
            "classification_report": report,
        }
    
    def get_feature_importance(self) -> dict[str, float]:
        """Get feature importance scores.
        
        Returns:
            Dict of feature_name -> importance
        """
        if self.model is None:
            raise RuntimeError("Model not trained")
        
        importances = self.model.feature_importances_
        return dict(zip(self.feature_names, importances))
    
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
            "label_encoder": self.label_encoder,
            "config": self.config.model_dump(),
            "training_stats": self._training_stats,
            "classes": self.classes,
        }, model_path)
        
        # Save feature order
        feature_path = output_dir / "feature_order.json"
        with open(feature_path, "w") as f:
            json.dump({
                "feature_names": self.feature_names,
                "feature_count": len(self.feature_names),
                "model": self.config.model_name,
            }, f, indent=2)
        
        # Save label map
        label_path = output_dir / "label_map.json"
        with open(label_path, "w") as f:
            json.dump({
                "classes": self.classes,
                "class_to_index": {c: i for i, c in enumerate(self.classes)},
            }, f, indent=2)
        
        paths = {
            "model": str(model_path),
            "features": str(feature_path),
            "labels": str(label_path),
        }
        
        logger.info("random_forest_saved", **paths)
        
        return paths
    
    def get_training_stats(self) -> dict:
        """Get training statistics.
        
        Returns:
            Dict with training stats
        """
        return self._training_stats.copy()


def load_random_forest(model_path: str | Path) -> RandomForestTrainer:
    """Load a trained Random Forest model.
    
    Args:
        model_path: Path to .joblib model file
        
    Returns:
        Loaded RandomForestTrainer
    """
    model_path = Path(model_path)
    
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    data = joblib.load(model_path)
    
    config = RandomForestConfig(**data["config"])
    trainer = RandomForestTrainer(config)
    trainer.model = data["model"]
    trainer.scaler = data["scaler"]
    trainer.label_encoder = data["label_encoder"]
    trainer.classes = data.get("classes", [])
    trainer._training_stats = data.get("training_stats", {})
    
    # Load feature order if available
    feature_path = model_path.parent / "feature_order.json"
    if feature_path.exists():
        with open(feature_path) as f:
            feature_data = json.load(f)
            trainer.feature_names = feature_data.get("feature_names", [])
    
    logger.info(
        "random_forest_loaded",
        path=str(model_path),
        features=len(trainer.feature_names),
        classes=len(trainer.classes),
    )
    
    return trainer
