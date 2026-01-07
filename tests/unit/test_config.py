"""Unit tests for configuration loading and validation."""

import pytest
from pathlib import Path
from pydantic import ValidationError

from soc_copilot.core.config import (
    ThresholdsConfig,
    AnomalyThresholds,
    Weights,
    FeaturesConfig,
    ModelConfig,
    ConfigLoader,
)


class TestAnomalyThresholds:
    """Tests for AnomalyThresholds validation."""
    
    def test_valid_thresholds(self):
        """Valid thresholds should pass."""
        thresholds = AnomalyThresholds(low_threshold=0.3, high_threshold=0.7)
        assert thresholds.low_threshold == 0.3
        assert thresholds.high_threshold == 0.7
    
    def test_defaults(self):
        """Default values should be applied."""
        thresholds = AnomalyThresholds()
        assert thresholds.low_threshold == 0.3
        assert thresholds.high_threshold == 0.7
    
    def test_threshold_out_of_range(self):
        """Thresholds outside 0-1 should fail."""
        with pytest.raises(ValidationError):
            AnomalyThresholds(low_threshold=1.5)
    
    def test_high_must_exceed_low(self):
        """High threshold must be greater than low."""
        with pytest.raises(ValidationError):
            AnomalyThresholds(low_threshold=0.7, high_threshold=0.3)


class TestWeights:
    """Tests for priority calculation weights."""
    
    def test_valid_weights_sum_to_one(self):
        """Weights summing to 1.0 should pass."""
        weights = Weights(isolation_forest=0.4, random_forest=0.4, context=0.2)
        assert weights.isolation_forest == 0.4
        assert weights.random_forest == 0.4
        assert weights.context == 0.2
    
    def test_weights_must_sum_to_one(self):
        """Weights not summing to 1.0 should fail."""
        with pytest.raises(ValidationError):
            Weights(isolation_forest=0.5, random_forest=0.5, context=0.5)
    
    def test_defaults(self):
        """Default weights should sum to 1.0."""
        weights = Weights()
        total = weights.isolation_forest + weights.random_forest + weights.context
        assert abs(total - 1.0) < 0.001


class TestThresholdsConfig:
    """Tests for complete threshold configuration."""
    
    def test_load_defaults(self):
        """Complete config with defaults should work."""
        config = ThresholdsConfig()
        assert config.anomaly.low_threshold == 0.3
        assert config.weights.isolation_forest == 0.4
        assert config.conservative_mode.enabled is True
    
    def test_from_dict(self):
        """Loading from dict should work."""
        data = {
            "anomaly": {"low_threshold": 0.2, "high_threshold": 0.8},
            "weights": {"isolation_forest": 0.5, "random_forest": 0.3, "context": 0.2},
        }
        config = ThresholdsConfig(**data)
        assert config.anomaly.low_threshold == 0.2
        assert config.weights.isolation_forest == 0.5


class TestFeaturesConfig:
    """Tests for features configuration."""
    
    def test_load_defaults(self):
        """Features config with defaults should work."""
        config = FeaturesConfig()
        assert config.settings.default_window == 300
        assert "user" in config.settings.entity_types
    
    def test_feature_categories_default_enabled(self):
        """Feature categories should be enabled by default."""
        config = FeaturesConfig()
        assert config.statistical.enabled is True
        assert config.temporal.enabled is True


class TestModelConfig:
    """Tests for model configuration."""
    
    def test_load_defaults(self):
        """Model config with defaults should work."""
        config = ModelConfig()
        assert config.isolation_forest.n_estimators == 100
        assert config.random_forest.n_estimators == 100
        assert config.ensemble.parallel_inference is True
    
    def test_isolation_forest_parameters(self):
        """IF parameters should validate correctly."""
        config = ModelConfig()
        assert config.isolation_forest.contamination == 0.1
        assert config.isolation_forest.random_state == 42
    
    def test_random_forest_classes(self):
        """RF should have expected attack classes."""
        config = ModelConfig()
        assert "Benign" in config.random_forest.classes
        assert "DDoS" in config.random_forest.classes
        assert "Malware" in config.random_forest.classes
    
    def test_autoencoder_disabled_by_default(self):
        """Autoencoder should be disabled (Phase-2)."""
        config = ModelConfig()
        assert config.autoencoder.enabled is False


class TestConfigLoader:
    """Tests for ConfigLoader file loading."""
    
    def test_load_from_empty_dir(self, tmp_path):
        """Loading from empty dir should return defaults."""
        loader = ConfigLoader(tmp_path)
        config = loader.load_thresholds()
        assert config.anomaly.low_threshold == 0.3
    
    def test_load_thresholds_from_file(self, tmp_path):
        """Loading from YAML file should work."""
        yaml_content = """
anomaly:
  low_threshold: 0.25
  high_threshold: 0.75
weights:
  isolation_forest: 0.5
  random_forest: 0.3
  context: 0.2
"""
        (tmp_path / "thresholds.yaml").write_text(yaml_content)
        
        loader = ConfigLoader(tmp_path)
        config = loader.load_thresholds()
        
        assert config.anomaly.low_threshold == 0.25
        assert config.weights.isolation_forest == 0.5
    
    def test_load_all(self, tmp_path):
        """load_all should return all three configs."""
        loader = ConfigLoader(tmp_path)
        thresholds, features, models = loader.load_all()
        
        assert isinstance(thresholds, ThresholdsConfig)
        assert isinstance(features, FeaturesConfig)
        assert isinstance(models, ModelConfig)
