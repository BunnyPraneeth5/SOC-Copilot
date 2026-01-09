"""Unit tests for feature engineering components."""

import pytest
import pandas as pd
import numpy as np

from soc_copilot.data.feature_engineering.base import (
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
)


# =============================================================================
# Base Utilities Tests
# =============================================================================

class TestEntropy:
    """Tests for entropy calculation."""
    
    def test_uniform_distribution(self):
        """Uniform distribution has max entropy."""
        probs = np.array([0.25, 0.25, 0.25, 0.25])
        ent = entropy(probs)
        assert np.isclose(ent, 2.0)  # log2(4) = 2
    
    def test_single_value(self):
        """Single value has zero entropy."""
        probs = np.array([1.0])
        ent = entropy(probs)
        assert ent == 0.0
    
    def test_skewed_distribution(self):
        """Skewed distribution has lower entropy."""
        uniform = entropy(np.array([0.5, 0.5]))
        skewed = entropy(np.array([0.9, 0.1]))
        assert skewed < uniform


class TestSafeDivide:
    """Tests for safe division."""
    
    def test_normal_division(self):
        """Normal division works correctly."""
        result = safe_divide(np.array([10, 20]), np.array([2, 4]))
        assert np.allclose(result, [5, 5])
    
    def test_divide_by_zero(self):
        """Division by zero returns default."""
        result = safe_divide(np.array([10, 20]), np.array([0, 4]), default=0)
        assert result[0] == 0
        assert result[1] == 5


# =============================================================================
# Statistical Features Tests
# =============================================================================

class TestStatisticalFeatureExtractor:
    """Tests for statistical feature extraction."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "src_ip": ["192.168.1.1", "192.168.1.1", "192.168.1.2", "192.168.1.2"],
            "dst_ip": ["10.0.0.1", "10.0.0.2", "10.0.0.1", "10.0.0.1"],
            "dst_port": [80, 443, 22, 22],
            "bytes_total": [1000, 2000, 500, 1500],
        })
    
    def test_fit_transform(self, sample_df):
        """Should extract statistical features."""
        config = StatisticalFeatureConfig(
            entity_field="src_ip",
            numeric_fields=["bytes_total"],
            categorical_fields=["dst_ip", "dst_port"],
        )
        extractor = StatisticalFeatureExtractor(config)
        result = extractor.fit_transform(sample_df)
        
        assert "stat_record_count" in result.columns
        assert "stat_bytes_total_mean" in result.columns
        assert "stat_dst_ip_entropy" in result.columns
    
    def test_feature_definitions(self):
        """Should provide feature definitions."""
        extractor = StatisticalFeatureExtractor()
        definitions = extractor.feature_definitions
        assert len(definitions) > 0
        assert all(isinstance(d, FeatureDefinition) for d in definitions)
    
    def test_per_entity_aggregation(self, sample_df):
        """Should compute stats per entity."""
        config = StatisticalFeatureConfig(
            entity_field="src_ip",
            numeric_fields=["bytes_total"],
        )
        extractor = StatisticalFeatureExtractor(config)
        result = extractor.fit_transform(sample_df)
        
        # Entity 1 has 2 records
        entity1_rows = result[result["src_ip"] == "192.168.1.1"]
        assert entity1_rows["stat_record_count"].iloc[0] == 2


# =============================================================================
# Temporal Features Tests
# =============================================================================

class TestTemporalFeatureExtractor:
    """Tests for temporal feature extraction."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "src_ip": ["192.168.1.1", "192.168.1.1", "192.168.1.1"],
            "timestamp_normalized": [
                "2026-01-09T10:00:00.000Z",
                "2026-01-09T10:05:00.000Z",
                "2026-01-09T14:00:00.000Z",
            ],
        })
    
    def test_fit_transform(self, sample_df):
        """Should extract temporal features."""
        extractor = TemporalFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        assert "time_hour_sin" in result.columns
        assert "time_is_weekend" in result.columns
        assert "time_delta_global_seconds" in result.columns
    
    def test_cyclical_encoding(self, sample_df):
        """Should use cyclical encoding for hour/day."""
        config = TemporalFeatureConfig(use_cyclical=True)
        extractor = TemporalFeatureExtractor(config)
        result = extractor.fit_transform(sample_df)
        
        # Sin and cos should be between -1 and 1
        assert result["time_hour_sin"].between(-1, 1).all()
        assert result["time_hour_cos"].between(-1, 1).all()
    
    def test_business_hours(self, sample_df):
        """Should detect business hours correctly."""
        extractor = TemporalFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        # All samples are on Friday during business hours (9am-5pm)
        # Note: Jan 9, 2026 is a Friday
        assert (result["time_is_business_hours"] == 1).all()


# =============================================================================
# Behavioral Features Tests
# =============================================================================

class TestBehavioralFeatureExtractor:
    """Tests for behavioral feature extraction."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "src_ip": ["192.168.1.1", "192.168.1.1", "192.168.1.1"],
            "timestamp_normalized": [
                "2026-01-09T10:00:00.000Z",
                "2026-01-09T10:05:00.000Z",
                "2026-01-09T12:00:00.000Z",  # Gap > session timeout
            ],
            "action": ["login", "file_access", "login"],
            "dst_ip": ["10.0.0.1", "10.0.0.1", "10.0.0.2"],
            "bytes_total": [100, 200, 150],
        })
    
    def test_fit_transform(self, sample_df):
        """Should extract behavioral features."""
        extractor = BehavioralFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        assert "behav_session_id" in result.columns
        assert "behav_is_new_action" in result.columns
        assert "behav_deviation_score" in result.columns
    
    def test_session_detection(self, sample_df):
        """Should detect session boundaries."""
        config = BehavioralFeatureConfig(session_timeout=1800)  # 30 min
        extractor = BehavioralFeatureExtractor(config)
        result = extractor.fit_transform(sample_df)
        
        # Third event should be in new session (2h gap)
        assert result["behav_session_id"].iloc[2] > result["behav_session_id"].iloc[0]
    
    def test_new_destination_detection(self, sample_df):
        """Should detect new destinations."""
        extractor = BehavioralFeatureExtractor()
        # Fit on first two records
        extractor.fit(sample_df.iloc[:2])
        result = extractor.transform(sample_df)
        
        # Third record has new destination
        assert result["behav_is_new_destination"].iloc[2] == 1


# =============================================================================
# Network Features Tests
# =============================================================================

class TestNetworkFeatureExtractor:
    """Tests for network feature extraction."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "src_ip": ["192.168.1.1", "192.168.1.1", "192.168.1.2"],
            "dst_ip": ["10.0.0.1", "10.0.0.2", "10.0.0.1"],
            "dst_port": [80, 443, 22],
            "protocol": ["TCP", "TCP", "TCP"],
            "bytes_total": [1000, 2000, 500],
        })
    
    def test_fit_transform(self, sample_df):
        """Should extract network features."""
        extractor = NetworkFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        assert "net_dst_port_is_system" in result.columns
        assert "net_unique_dst_ips" in result.columns
        assert "net_is_scanner_like" in result.columns
    
    def test_port_classification(self, sample_df):
        """Should classify ports correctly."""
        extractor = NetworkFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        # Port 80, 443, 22 are all system ports
        assert (result["net_dst_port_is_system"] == 1).all()
        # Port 80, 443, 22 are all common security ports
        assert (result["net_dst_port_is_common"] == 1).all()
    
    def test_fanout_ratio(self, sample_df):
        """Should compute fanout ratio correctly."""
        extractor = NetworkFeatureExtractor()
        result = extractor.fit_transform(sample_df)
        
        # Entity 192.168.1.1 has 2 connections to 2 unique destinations
        entity1_rows = result[result["src_ip"] == "192.168.1.1"]
        assert entity1_rows["net_fanout_ratio"].iloc[0] == 1.0


# =============================================================================
# Pipeline Tests
# =============================================================================

class TestFeatureEngineeringPipeline:
    """Tests for feature engineering pipeline."""
    
    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            "src_ip": ["192.168.1.1", "192.168.1.1", "192.168.1.2"],
            "dst_ip": ["10.0.0.1", "10.0.0.2", "10.0.0.1"],
            "dst_port": [80, 443, 22],
            "protocol": ["TCP", "TCP", "TCP"],
            "bytes_total": [1000, 2000, 500],
            "timestamp_normalized": [
                "2026-01-09T10:00:00.000Z",
                "2026-01-09T10:05:00.000Z",
                "2026-01-09T10:10:00.000Z",
            ],
            "action": ["login", "file_access", "login"],
        })
    
    def test_default_pipeline(self, sample_df):
        """Should create and run default pipeline."""
        pipeline = FeatureEngineeringPipeline()
        result = pipeline.fit_transform(sample_df)
        
        # Should have features from all extractors
        assert any("stat_" in c for c in result.columns)
        assert any("time_" in c for c in result.columns)
        assert any("behav_" in c for c in result.columns)
        assert any("net_" in c for c in result.columns)
    
    def test_disabled_extractor(self, sample_df):
        """Should skip disabled extractors."""
        config = FeaturePipelineConfig(enable_behavioral=False)
        pipeline = FeatureEngineeringPipeline(config)
        result = pipeline.fit_transform(sample_df)
        
        # Should not have behavioral features
        assert not any("behav_" in c for c in result.columns)
        # Should still have other features
        assert any("stat_" in c for c in result.columns)
    
    def test_feature_definitions(self, sample_df):
        """Should provide combined feature definitions."""
        pipeline = FeatureEngineeringPipeline()
        pipeline.fit(sample_df)
        
        definitions = pipeline.feature_definitions
        assert len(definitions) > 0
        
        # Should have features from all types
        types = set(d.feature_type for d in definitions)
        assert FeatureType.STATISTICAL in types
        assert FeatureType.TEMPORAL in types
    
    def test_output_is_numeric(self, sample_df):
        """All features should be numeric."""
        pipeline = FeatureEngineeringPipeline()
        result = pipeline.fit_transform(sample_df)
        
        for feat_name in pipeline.feature_names:
            if feat_name in result.columns:
                assert np.issubdtype(result[feat_name].dtype, np.number), \
                    f"Feature {feat_name} is not numeric"
