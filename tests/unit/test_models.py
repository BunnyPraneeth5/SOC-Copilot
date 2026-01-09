"""Unit tests for ML models training and inference."""

import pytest
import numpy as np
import tempfile
from pathlib import Path

from soc_copilot.models.training.data_loader import (
    TrainingDataLoader,
    DataLoaderConfig,
    SOC_LABELS,
    DEFAULT_LABEL_MAPPINGS,
)
from soc_copilot.models.inference.engine import (
    ModelInference,
    InferenceConfig,
    InferenceResult,
    compute_risk_level,
)


# =============================================================================
# Training Data Loader Tests
# =============================================================================

class TestLabelMappings:
    """Tests for label mapping."""
    
    def test_soc_labels_defined(self):
        """Should have all SOC taxonomy labels."""
        assert "Benign" in SOC_LABELS
        assert "DDoS" in SOC_LABELS
        assert "BruteForce" in SOC_LABELS
        assert "Malware" in SOC_LABELS
        assert "Exfiltration" in SOC_LABELS
    
    def test_default_mappings_cover_common(self):
        """Should map common attack types."""
        assert DEFAULT_LABEL_MAPPINGS.get("BENIGN") == "Benign"
        assert DEFAULT_LABEL_MAPPINGS.get("DDoS") == "DDoS"
        assert DEFAULT_LABEL_MAPPINGS.get("DoS Slowloris") == "DDoS"
        assert DEFAULT_LABEL_MAPPINGS.get("SSH-Patator") == "BruteForce"


class TestTrainingDataLoader:
    """Tests for training data loader."""
    
    @pytest.fixture
    def loader(self):
        return TrainingDataLoader()
    
    def test_list_datasets_empty(self, loader, tmp_path):
        """Should handle empty datasets directory."""
        config = DataLoaderConfig(datasets_dir=str(tmp_path))
        loader = TrainingDataLoader(config)
        datasets = loader.list_datasets()
        assert datasets == []
    
    def test_prepare_features_basic(self, loader):
        """Should prepare feature matrix from DataFrame."""
        import pandas as pd
        
        df = pd.DataFrame({
            "feature1": [1.0, 2.0, 3.0],
            "feature2": [4.0, 5.0, 6.0],
            "label": ["Benign", "DDoS", "Benign"],
        })
        
        X, y, features = loader.prepare_features(df)
        
        assert X.shape == (3, 2)
        assert len(y) == 3
        assert len(features) == 2
    
    def test_get_benign_only(self, loader):
        """Should filter to benign only."""
        import pandas as pd
        
        df = pd.DataFrame({
            "feature1": [1.0, 2.0, 3.0, 4.0],
            "label": ["Benign", "DDoS", "Benign", "Malware"],
        })
        
        benign_df = loader.get_benign_only(df)
        
        assert len(benign_df) == 2
        assert (benign_df["label"] == "Benign").all()


# =============================================================================
# Risk Level Computation Tests
# =============================================================================

class TestRiskLevel:
    """Tests for risk level computation."""
    
    def test_critical_risk(self):
        """High anomaly + malicious + high confidence = Critical."""
        level = compute_risk_level(0.9, "Malware", 0.9)
        assert level == "Critical"
    
    def test_high_risk_anomaly(self):
        """High anomaly score = High risk."""
        level = compute_risk_level(0.8, "Benign", 0.5)
        assert level == "High"
    
    def test_high_risk_class(self):
        """Malicious class = High risk."""
        level = compute_risk_level(0.3, "Exfiltration", 0.8)
        assert level == "High"
    
    def test_medium_risk(self):
        """Moderate signals = Medium risk."""
        level = compute_risk_level(0.6, "DDoS", 0.4)
        assert level == "Medium"
    
    def test_low_risk(self):
        """Normal traffic = Low risk."""
        level = compute_risk_level(0.2, "Benign", 0.9)
        assert level == "Low"


# =============================================================================
# Inference Result Tests
# =============================================================================

class TestInferenceResult:
    """Tests for inference result model."""
    
    def test_default_result(self):
        """Should create default result."""
        result = InferenceResult()
        assert result.anomaly_score == 0.0
        assert result.is_anomaly is False
        assert result.predicted_class == "Unknown"
        assert result.risk_level == "Low"
    
    def test_custom_result(self):
        """Should create custom result."""
        result = InferenceResult(
            anomaly_score=0.8,
            is_anomaly=True,
            predicted_class="DDoS",
            confidence=0.9,
            risk_level="High",
        )
        assert result.anomaly_score == 0.8
        assert result.predicted_class == "DDoS"


# =============================================================================
# Model Inference Tests
# =============================================================================

class TestModelInference:
    """Tests for model inference engine."""
    
    def test_not_loaded_initially(self):
        """Should not be loaded initially."""
        engine = ModelInference()
        assert engine.is_loaded is False
    
    def test_load_missing_models(self, tmp_path):
        """Should handle missing model directory."""
        config = InferenceConfig(models_dir=str(tmp_path / "nonexistent"))
        engine = ModelInference(config)
        
        with pytest.raises(FileNotFoundError):
            engine.load_models()
    
    def test_inference_not_loaded_error(self):
        """Should raise error if inference called before loading."""
        engine = ModelInference()
        
        with pytest.raises(RuntimeError, match="not loaded"):
            engine.infer({"feature": 1.0})
    
    def test_feature_order_empty_initial(self):
        """Should have empty feature order initially."""
        engine = ModelInference()
        assert engine.feature_order == []


# =============================================================================
# Integration Tests (Mocked)
# =============================================================================

class TestIsolationForestTrainer:
    """Tests for Isolation Forest trainer (imports from models dir)."""
    
    def test_can_import(self):
        """Should be able to import trainer module."""
        import sys
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root / "models" / "isolation_forest"))
        
        from trainer import IsolationForestTrainer, IsolationForestConfig
        
        config = IsolationForestConfig()
        trainer = IsolationForestTrainer(config)
        
        assert trainer.model is None
        assert trainer.feature_names == []
    
    def test_train_and_score(self):
        """Should train and score samples."""
        import sys
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root / "models" / "isolation_forest"))
        
        from trainer import IsolationForestTrainer, IsolationForestConfig
        
        # Create synthetic benign data
        np.random.seed(42)
        X_train = np.random.randn(100, 5)  # Normal distribution
        feature_names = [f"feature_{i}" for i in range(5)]
        
        config = IsolationForestConfig(n_estimators=10)
        trainer = IsolationForestTrainer(config)
        trainer.train(X_train, feature_names)
        
        # Test scoring
        X_normal = np.random.randn(10, 5)  # Normal samples
        X_anomaly = np.random.randn(10, 5) * 5 + 10  # Anomalous samples
        
        normal_scores = trainer.score(X_normal)
        anomaly_scores = trainer.score(X_anomaly)
        
        # Anomaly scores should be higher on average
        assert np.mean(anomaly_scores) > np.mean(normal_scores)


class TestRandomForestTrainer:
    """Tests for Random Forest trainer."""
    
    @pytest.fixture
    def rf_trainer_module(self):
        """Import random forest trainer module."""
        import importlib.util
        from pathlib import Path
        
        project_root = Path(__file__).parent.parent.parent
        spec = importlib.util.spec_from_file_location(
            "rf_trainer",
            project_root / "models" / "random_forest" / "trainer.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    
    def test_can_import(self, rf_trainer_module):
        """Should be able to import trainer module."""
        config = rf_trainer_module.RandomForestConfig()
        trainer = rf_trainer_module.RandomForestTrainer(config)
        
        assert trainer.model is None
        assert trainer.classes == []
    
    def test_train_and_predict(self, rf_trainer_module):
        """Should train and predict classes."""
        # Create synthetic labeled data
        np.random.seed(42)
        X_train = np.vstack([
            np.random.randn(50, 5),          # Benign
            np.random.randn(50, 5) + 3,      # DDoS
        ])
        y_train = np.array(["Benign"] * 50 + ["DDoS"] * 50)
        feature_names = [f"feature_{i}" for i in range(5)]
        
        config = rf_trainer_module.RandomForestConfig(n_estimators=10)
        trainer = rf_trainer_module.RandomForestTrainer(config)
        trainer.train(X_train, y_train, feature_names)
        
        # Test prediction
        X_test = np.vstack([
            np.random.randn(10, 5),          # Should be Benign
            np.random.randn(10, 5) + 3,      # Should be DDoS
        ])
        
        predictions = trainer.predict(X_test)
        
        # Should have some correct predictions
        assert "Benign" in predictions
        assert "DDoS" in predictions
    
    def test_train_accuracy(self, rf_trainer_module):
        """Should achieve reasonable accuracy."""
        # Create well-separated data
        np.random.seed(42)
        X_train = np.vstack([
            np.random.randn(100, 5),          # Benign
            np.random.randn(100, 5) + 5,      # DDoS (well separated)
        ])
        y_train = np.array(["Benign"] * 100 + ["DDoS"] * 100)
        feature_names = [f"feature_{i}" for i in range(5)]
        
        config = rf_trainer_module.RandomForestConfig(n_estimators=50)
        trainer = rf_trainer_module.RandomForestTrainer(config)
        stats = trainer.train(X_train, y_train, feature_names)
        
        # Should achieve high training accuracy
        assert stats["train_accuracy"] > 0.9

