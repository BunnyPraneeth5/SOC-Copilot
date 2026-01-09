"""Unit tests for preprocessing pipeline components."""

import pytest
from datetime import datetime

from soc_copilot.data.preprocessing.missing_values import (
    MissingValueHandler,
    MissingValueConfig,
    MissingValueStrategy,
    is_missing,
)
from soc_copilot.data.preprocessing.timestamp_normalizer import (
    TimestampNormalizer,
    TimestampConfig,
    parse_timestamp,
    to_iso8601,
)
from soc_copilot.data.preprocessing.field_standardizer import (
    FieldStandardizer,
    FieldStandardizerConfig,
    normalize_field_name,
)
from soc_copilot.data.preprocessing.categorical_encoder import (
    CategoricalEncoder,
    CategoricalEncoderConfig,
)
from soc_copilot.data.preprocessing.pipeline import (
    PreprocessingPipeline,
    PipelineConfig,
    PipelineStep,
)


# =============================================================================
# Missing Value Handler Tests
# =============================================================================

class TestIsMissing:
    """Tests for missing value detection."""
    
    def test_none_is_missing(self):
        assert is_missing(None, []) is True
    
    def test_empty_string_is_missing(self):
        assert is_missing("", [""]) is True
    
    def test_null_string_is_missing(self):
        assert is_missing("null", ["null"]) is True
    
    def test_na_is_missing(self):
        assert is_missing("N/A", ["N/A"]) is True
    
    def test_valid_value_not_missing(self):
        assert is_missing("value", [""]) is False
    
    def test_zero_not_missing(self):
        assert is_missing(0, [""]) is False


class TestMissingValueHandler:
    """Tests for missing value handling."""
    
    def test_drop_required_missing(self):
        """Should drop records missing required fields."""
        config = MissingValueConfig(required_fields=["id"])
        handler = MissingValueHandler(config)
        records = [
            {"id": "1", "value": 100},
            {"value": 200},  # Missing id
        ]
        result = handler.process(records)
        assert len(result) == 1
        assert result[0]["id"] == "1"
    
    def test_fill_default(self):
        """Should fill missing with default value."""
        from soc_copilot.data.preprocessing.missing_values import FieldMissingConfig
        config = MissingValueConfig(
            field_configs=[
                FieldMissingConfig(
                    field="status",
                    strategy=MissingValueStrategy.FILL_DEFAULT,
                    default_value="unknown",
                    required=False,
                )
            ]
        )
        handler = MissingValueHandler(config)
        records = [{"id": "1", "status": None}]
        result = handler.process(records)
        assert result[0]["status"] == "unknown"
    
    def test_fill_zero(self):
        """Should fill missing numerics with zero."""
        from soc_copilot.data.preprocessing.missing_values import FieldMissingConfig
        config = MissingValueConfig(
            default_strategy=MissingValueStrategy.FILL_ZERO,
        )
        handler = MissingValueHandler(config)
        handler.fit([{"count": 10}])
        records = [{"id": "1", "count": None}]
        result = handler.process(records)
        assert result[0]["count"] == 0
    
    def test_flag_missing(self):
        """Should add _missing flag for flagged fields."""
        from soc_copilot.data.preprocessing.missing_values import FieldMissingConfig
        config = MissingValueConfig(
            field_configs=[
                FieldMissingConfig(
                    field="optional",
                    strategy=MissingValueStrategy.FLAG_MISSING,
                    required=False,
                )
            ]
        )
        handler = MissingValueHandler(config)
        records = [{"id": "1", "optional": None}]
        result = handler.process(records)
        assert result[0].get("optional_missing") is True


# =============================================================================
# Timestamp Normalizer Tests
# =============================================================================

class TestParseTimestamp:
    """Tests for timestamp parsing."""
    
    def test_iso8601(self):
        """Should parse ISO 8601 format."""
        dt = parse_timestamp("2026-01-09T10:30:00Z")
        assert dt is not None
        assert dt.hour == 10
    
    def test_iso8601_with_millis(self):
        """Should parse ISO 8601 with milliseconds."""
        dt = parse_timestamp("2026-01-09T10:30:00.123Z")
        assert dt is not None
    
    def test_epoch_seconds(self):
        """Should parse Unix epoch seconds."""
        dt = parse_timestamp("1767982200")  # 2026-01-09
        assert dt is not None
    
    def test_epoch_millis(self):
        """Should parse Unix epoch milliseconds."""
        dt = parse_timestamp("1767982200000")
        assert dt is not None
    
    def test_syslog_format(self):
        """Should parse syslog timestamp."""
        dt = parse_timestamp("Jan  9 10:30:00")
        assert dt is not None
        assert dt.month == 1
        assert dt.day == 9


class TestToIso8601:
    """Tests for ISO 8601 output."""
    
    def test_naive_datetime(self):
        """Should handle naive datetime as UTC."""
        dt = datetime(2026, 1, 9, 10, 30, 0)
        result = to_iso8601(dt)
        assert result == "2026-01-09T10:30:00.000Z"
    
    def test_output_format(self):
        """Should output with Z suffix."""
        dt = datetime(2026, 1, 9, 10, 30, 0)
        result = to_iso8601(dt)
        assert result.endswith("Z")


class TestTimestampNormalizer:
    """Tests for timestamp normalization."""
    
    def test_normalize_record(self):
        """Should normalize timestamp in record."""
        normalizer = TimestampNormalizer()
        records = [{"timestamp": "2026-01-09T10:30:00Z", "data": "test"}]
        result = normalizer.process(records)
        assert "timestamp_normalized" in result[0]
    
    def test_find_timestamp_field(self):
        """Should find common timestamp fields."""
        normalizer = TimestampNormalizer()
        record = {"@timestamp": "2026-01-09T10:00:00Z", "event": "test"}
        field = normalizer.find_timestamp_field(record)
        assert field == "@timestamp"


# =============================================================================
# Field Standardizer Tests
# =============================================================================

class TestNormalizeFieldName:
    """Tests for field name normalization."""
    
    def test_lowercase(self):
        assert normalize_field_name("SourceIP") == "sourceip"
    
    def test_special_chars(self):
        assert normalize_field_name("user.name") == "user_name"
        assert normalize_field_name("data[0]") == "data_0"
    
    def test_combined(self):
        assert normalize_field_name("User.Name[0]") == "user_name_0"


class TestFieldStandardizer:
    """Tests for field standardization."""
    
    def test_map_known_field(self):
        """Should map known fields to canonical names."""
        standardizer = FieldStandardizer()
        records = [{"source_ip": "192.168.1.1", "destination_ip": "10.0.0.1"}]
        result = standardizer.process(records)
        assert "src_ip" in result[0]
        assert "dst_ip" in result[0]
    
    def test_preserve_unmapped(self):
        """Should preserve unmapped fields."""
        standardizer = FieldStandardizer()
        records = [{"custom_field": "value"}]
        result = standardizer.process(records)
        assert "custom_field" in result[0]
    
    def test_drop_fields(self):
        """Should drop configured fields."""
        config = FieldStandardizerConfig(drop_fields=["debug"])
        standardizer = FieldStandardizer(config)
        records = [{"event": "test", "debug": "internal"}]
        result = standardizer.process(records)
        assert "debug" not in result[0]


# =============================================================================
# Categorical Encoder Tests
# =============================================================================

class TestCategoricalEncoder:
    """Tests for categorical encoding."""
    
    def test_fit_transform(self):
        """Should encode categorical fields."""
        config = CategoricalEncoderConfig(categorical_fields=["action"])
        encoder = CategoricalEncoder(config)
        records = [
            {"action": "login", "user": "alice"},
            {"action": "logout", "user": "bob"},
            {"action": "login", "user": "charlie"},
        ]
        result = encoder.fit_transform(records)
        assert "action_encoded" in result[0]
    
    def test_unknown_category(self):
        """Should handle unknown categories."""
        config = CategoricalEncoderConfig(categorical_fields=["action"])
        encoder = CategoricalEncoder(config)
        encoder.fit([{"action": "login"}])
        result = encoder.transform([{"action": "unknown_action"}])
        # Should get rare value (mapped from unknown)
        assert result[0]["action_encoded"] is not None
    
    def test_inverse_transform(self):
        """Should reverse encoding."""
        config = CategoricalEncoderConfig(categorical_fields=["action"])
        encoder = CategoricalEncoder(config)
        records = [{"action": "login"}]
        encoded = encoder.fit_transform(records)
        decoded = encoder.inverse_transform(encoded)
        assert decoded[0]["action"] == "login"


# =============================================================================
# Pipeline Tests
# =============================================================================

class TestPreprocessingPipeline:
    """Tests for the preprocessing pipeline."""
    
    def test_default_pipeline(self):
        """Should create and run default pipeline."""
        pipeline = PreprocessingPipeline()
        records = [
            {"timestamp": "2026-01-09T10:00:00Z", "source_ip": "192.168.1.1", "action": "login"},
            {"timestamp": "2026-01-09T10:01:00Z", "source_ip": "192.168.1.2", "action": "logout"},
        ]
        df = pipeline.fit_transform(records)
        assert len(df) == 2
        assert "timestamp_normalized" in df.columns
    
    def test_disabled_step(self):
        """Should skip disabled steps."""
        config = PipelineConfig(
            steps=[
                PipelineStep(name="timestamp_normalizer", enabled=False),
                PipelineStep(name="field_standardizer"),
            ],
            required_output_fields=[],  # Don't require timestamp when normalizer disabled
        )
        pipeline = PreprocessingPipeline(config)
        records = [{"timestamp": "2026-01-09T10:00:00Z", "source_ip": "192.168.1.1"}]
        result = pipeline.fit_transform(records)
        # Timestamp normalizer disabled, so no normalized timestamp
        # But field standardizer should work
        assert "src_ip" in result.columns
    
    def test_get_stats(self):
        """Should collect stats from all steps."""
        pipeline = PreprocessingPipeline()
        records = [{"timestamp": "2026-01-09T10:00:00Z", "src_ip": "192.168.1.1"}]
        pipeline.fit_transform(records)
        stats = pipeline.get_stats()
        assert "timestamp_normalizer" in stats
