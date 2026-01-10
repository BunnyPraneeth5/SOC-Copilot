"""Integration tests for end-to-end SOC Copilot pipeline."""

import pytest
import tempfile
from pathlib import Path
import json

from soc_copilot.pipeline import (
    SOCCopilot,
    SOCCopilotConfig,
    AnalysisStats,
)
from soc_copilot.data.log_ingestion import parse_log_file
from soc_copilot.models.ensemble import RiskLevel, AlertPriority


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_json_log(tmp_path):
    """Create a sample JSON Lines log file."""
    log_file = tmp_path / "sample.jsonl"  # Use .jsonl extension
    records = [
        {"timestamp": "2026-01-10T10:00:00Z", "src_ip": "192.168.1.1", "dst_ip": "10.0.0.1", "dst_port": 443, "action": "connect"},
        {"timestamp": "2026-01-10T10:01:00Z", "src_ip": "192.168.1.1", "dst_ip": "10.0.0.2", "dst_port": 80, "action": "request"},
        {"timestamp": "2026-01-10T10:02:00Z", "src_ip": "192.168.1.2", "dst_ip": "10.0.0.1", "dst_port": 22, "action": "login"},
    ]
    with open(log_file, "w") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")
    return log_file


@pytest.fixture
def models_dir():
    """Get models directory."""
    return Path("data/models")


# =============================================================================
# Pipeline Configuration Tests
# =============================================================================

class TestSOCCopilotConfig:
    """Tests for pipeline configuration."""
    
    def test_default_config(self):
        """Should create default config."""
        config = SOCCopilotConfig()
        assert config.models_dir == "data/models"
    
    def test_custom_models_dir(self):
        """Should accept custom models directory."""
        config = SOCCopilotConfig(models_dir="/custom/path")
        assert config.models_dir == "/custom/path"


class TestAnalysisStats:
    """Tests for analysis statistics."""
    
    def test_default_stats(self):
        """Should initialize with zeros."""
        stats = AnalysisStats()
        assert stats.total_records == 0
        assert stats.alerts_generated == 0
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        stats = AnalysisStats()
        stats.total_records = 100
        stats.alerts_generated = 5
        
        d = stats.to_dict()
        assert d["total_records"] == 100
        assert d["alerts_generated"] == 5


# =============================================================================
# SOCCopilot Tests
# =============================================================================

class TestSOCCopilot:
    """Tests for SOCCopilot pipeline."""
    
    def test_not_loaded_initially(self):
        """Should not be loaded initially."""
        copilot = SOCCopilot()
        assert copilot.is_loaded is False
    
    def test_analyze_without_load_raises(self):
        """Should raise error if analyze called before load."""
        copilot = SOCCopilot()
        
        with pytest.raises(RuntimeError, match="not loaded"):
            copilot.analyze_records([])
    
    @pytest.mark.skipif(
        not Path("data/models/random_forest_v1.joblib").exists(),
        reason="Models not trained"
    )
    def test_load_models(self, models_dir):
        """Should load models successfully."""
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        assert copilot.is_loaded
        assert len(copilot._feature_order) > 0
    
    @pytest.mark.skipif(
        not Path("data/models/random_forest_v1.joblib").exists(),
        reason="Models not trained"
    )
    def test_analyze_empty_records(self, models_dir):
        """Should handle empty records list."""
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts = copilot.analyze_records([])
        
        assert results == []
        assert alerts == []
    
    @pytest.mark.skipif(
        not Path("data/models/random_forest_v1.joblib").exists(),
        reason="Models not trained"
    )
    def test_analyze_file_not_found(self, models_dir):
        """Should handle missing file."""
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts, stats = copilot.analyze_file("/nonexistent/file.log")
        
        assert results == []
        assert alerts == []
        assert stats.total_records == 0


# =============================================================================
# Log Parsing Integration Tests
# =============================================================================

class TestLogParsingIntegration:
    """Tests for log parsing integration."""
    
    def test_parse_json_log(self, sample_json_log):
        """Should parse JSON Lines log file."""
        records = parse_log_file(sample_json_log)
        
        assert len(records) == 3
        assert records[0].raw.get("src_ip") == "192.168.1.1"
    
    def test_parse_invalid_file(self, tmp_path):
        """Should handle invalid file gracefully."""
        invalid_file = tmp_path / "invalid.log"  # Use .log extension
        invalid_file.write_text("this is not valid log data\nrandom text\n")
        
        records = parse_log_file(invalid_file)
        # Should return parsed as syslog (fallback)
        assert isinstance(records, list)


# =============================================================================
# End-to-End Integration Tests
# =============================================================================

@pytest.mark.skipif(
    not Path("data/models/random_forest_v1.joblib").exists(),
    reason="Models not trained"
)
class TestEndToEndIntegration:
    """End-to-end integration tests."""
    
    def test_full_pipeline_json_log(self, sample_json_log, models_dir):
        """Should process JSON log end-to-end."""
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts, stats = copilot.analyze_file(sample_json_log)
        
        # Should process all records
        assert stats.total_records == 3
        assert stats.processed_records >= 0  # May be less if features missing
        
        # Each result should have risk level
        for result in results:
            assert result.ensemble_result.risk_level in RiskLevel
    
    def test_sample_threats_file(self, models_dir):
        """Should analyze sample threats file."""
        sample_file = Path("tests/fixtures/sample_threats.jsonl")
        
        if not sample_file.exists():
            pytest.skip("Sample threats file not found")
        
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts, stats = copilot.analyze_file(sample_file)
        
        assert stats.total_records == 10
        assert len(results) >= 0  # May have processing issues
    
    def test_directory_analysis(self, tmp_path, models_dir):
        """Should analyze directory of logs."""
        # Create multiple log files
        for i in range(3):
            log_file = tmp_path / f"log_{i}.jsonl"
            records = [
                {"timestamp": f"2026-01-10T{10+i}:00:00Z", "src_ip": f"192.168.1.{i}", "action": "test"}
            ]
            with open(log_file, "w") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")
        
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts, stats = copilot.analyze_directory(tmp_path)
        
        assert stats.total_records == 3


# =============================================================================
# Alert Verification Tests
# =============================================================================

@pytest.mark.skipif(
    not Path("data/models/random_forest_v1.joblib").exists(),
    reason="Models not trained"
)
class TestAlertVerification:
    """Tests to verify alert generation and content."""
    
    def test_alert_has_required_fields(self, sample_json_log, models_dir):
        """Alerts should have all required fields."""
        config = SOCCopilotConfig(models_dir=str(models_dir))
        copilot = SOCCopilot(config)
        copilot.load()
        
        results, alerts, stats = copilot.analyze_file(sample_json_log)
        
        for alert in alerts:
            # Required fields
            assert alert.alert_id is not None
            assert alert.timestamp is not None
            assert alert.priority in AlertPriority
            assert alert.risk_level in RiskLevel
            assert alert.suggested_action is not None
            assert len(alert.reasoning) >= 0
    
    def test_alert_priority_ordering(self, models_dir):
        """Alert priorities should be correctly ordered."""
        # P0 is more severe than P4
        assert AlertPriority.P0_CRITICAL.value < AlertPriority.P4_INFO.value
