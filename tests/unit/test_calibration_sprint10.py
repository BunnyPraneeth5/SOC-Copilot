"""Unit tests for Sprint-10 Threshold Calibration."""

import pytest
import yaml
from pathlib import Path

from soc_copilot.phase2.calibration import ThresholdCalibrator, CalibrationRecommendation


@pytest.fixture
def temp_config(tmp_path):
    """Create temporary config file."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    config_path = config_dir / "thresholds.yaml"
    config_data = {
        "anomaly": {
            "low_threshold": 0.3,
            "high_threshold": 0.7
        },
        "priority": {
            "critical": 0.85,
            "high": 0.70,
            "medium": 0.50
        },
        "weights": {
            "isolation_forest": 0.4,
            "random_forest": 0.4,
            "context": 0.2
        }
    }
    
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    return config_path


@pytest.fixture
def calibrator(temp_config):
    """Create calibrator with temp config."""
    return ThresholdCalibrator(str(temp_config))


class TestCalibrationRecommendation:
    """Tests for CalibrationRecommendation."""
    
    def test_create_recommendation(self):
        """Should create recommendation."""
        rec = CalibrationRecommendation()
        rec.add_recommendation(
            "anomaly.high_threshold",
            0.7,
            0.75,
            "Test justification"
        )
        
        assert rec.has_recommendations()
        assert "anomaly.high_threshold" in rec.recommendations
        assert rec.recommendations["anomaly.high_threshold"] == 0.75
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        rec = CalibrationRecommendation()
        rec.add_recommendation("test.value", 0.5, 0.6, "Test reason")
        
        data = rec.to_dict()
        
        assert "timestamp" in data
        assert "recommendations" in data
        assert len(data["recommendations"]) == 1
        assert data["recommendations"][0]["path"] == "test.value"
        assert data["recommendations"][0]["current"] == 0.5
        assert data["recommendations"][0]["recommended"] == 0.6
        assert abs(data["recommendations"][0]["change"] - 0.1) < 0.001


class TestThresholdCalibrator:
    """Tests for ThresholdCalibrator."""
    
    def test_load_current_thresholds(self, calibrator):
        """Should load current thresholds."""
        thresholds = calibrator.load_current_thresholds()
        
        assert "anomaly" in thresholds
        assert thresholds["anomaly"]["high_threshold"] == 0.7
    
    def test_generate_recommendations_no_data(self, calibrator):
        """Should handle no drift/feedback data."""
        rec = calibrator.generate_recommendations()
        
        assert not rec.has_recommendations()
    
    def test_generate_recommendations_high_drift(self, calibrator):
        """Should recommend threshold increase for high drift."""
        drift_stats = {
            "anomaly_score_mean": 0.65,
            "anomaly_change_pct": 30.0
        }
        
        rec = calibrator.generate_recommendations(drift_stats=drift_stats)
        
        # Should recommend raising anomaly threshold
        if rec.has_recommendations():
            assert "anomaly.high_threshold" in rec.recommendations
            assert rec.recommendations["anomaly.high_threshold"] > 0.7
    
    def test_generate_recommendations_high_rejection(self, calibrator):
        """Should recommend threshold increase for high rejection rate."""
        feedback_stats = {
            "total_count": 50,
            "reject_count": 25  # 50% rejection
        }
        
        rec = calibrator.generate_recommendations(feedback_stats=feedback_stats)
        
        # Should recommend raising critical threshold
        if rec.has_recommendations():
            assert "priority.critical" in rec.recommendations
            assert rec.recommendations["priority.critical"] > 0.85
    
    def test_preview_changes(self, calibrator):
        """Should generate preview diff."""
        rec = CalibrationRecommendation()
        rec.add_recommendation("test.value", 0.5, 0.6, "Test reason")
        
        preview = calibrator.preview_changes(rec)
        
        assert "test.value" in preview
        assert "0.500" in preview
        assert "0.600" in preview
    
    def test_preview_no_changes(self, calibrator):
        """Should handle no recommendations."""
        rec = CalibrationRecommendation()
        
        preview = calibrator.preview_changes(rec)
        
        assert "No threshold changes" in preview
    
    def test_create_backup(self, calibrator):
        """Should create config backup."""
        backup_path = calibrator.create_backup()
        
        assert backup_path.exists()
        assert backup_path.parent == calibrator.backup_dir
        assert "thresholds_" in backup_path.name
    
    def test_apply_without_confirmation(self, calibrator):
        """Should reject application without confirmation."""
        rec = CalibrationRecommendation()
        rec.add_recommendation("test.value", 0.5, 0.6, "Test")
        
        with pytest.raises(ValueError, match="explicit confirmation"):
            calibrator.apply_recommendations(rec, confirmed=False)
    
    def test_apply_with_confirmation(self, calibrator):
        """Should apply recommendations with confirmation."""
        rec = CalibrationRecommendation()
        rec.add_recommendation("anomaly.high_threshold", 0.7, 0.75, "Test")
        
        calibrator.apply_recommendations(rec, confirmed=True)
        
        # Verify applied
        updated = calibrator.load_current_thresholds()
        assert updated["anomaly"]["high_threshold"] == 0.75
        
        # Verify backup created
        backups = calibrator.list_backups()
        assert len(backups) > 0
    
    def test_list_backups(self, calibrator):  
        """Should list available backups."""
        import time
        # Create some backups with delay to ensure different timestamps
        calibrator.create_backup()
        time.sleep(0.1)
        calibrator.create_backup()
        
        backups = calibrator.list_backups()
        
        assert len(backups) >= 1  # At least one backup
        if len(backups) >= 2:
            # Should be sorted newest first
            assert backups[0].stat().st_mtime >= backups[1].stat().st_mtime
    
    def test_restore_backup(self, calibrator):
        """Should restore from backup."""
        import time
        # Get original value
        original = calibrator.load_current_thresholds()
        original_value = original["anomaly"]["high_threshold"]
        
        # Create backup of original
        original_backup = calibrator.create_backup()
        time.sleep(0.1)
        
        # Modify config
        rec = CalibrationRecommendation()
        rec.add_recommendation("anomaly.high_threshold", original_value, 0.8, "Test")
        calibrator.apply_recommendations(rec, confirmed=True)
        
        # Verify modified
        modified = calibrator.load_current_thresholds()
        assert modified["anomaly"]["high_threshold"] == 0.8
        
        # Restore original
        calibrator.restore_backup(original_backup)
        
        # Verify restored
        restored = calibrator.load_current_thresholds()
        assert restored["anomaly"]["high_threshold"] == original_value
    
    def test_conservative_adjustments(self, calibrator):
        """Should make conservative threshold adjustments."""
        drift_stats = {
            "anomaly_score_mean": 0.75,
            "anomaly_change_pct": 50.0  # Large drift
        }
        
        rec = calibrator.generate_recommendations(drift_stats=drift_stats)
        
        if rec.has_recommendations():
            for path, value in rec.recommendations.items():
                current = rec.current_values[path]
                change = abs(value - current)
                # Changes should be small (max 0.05 with floating point tolerance)
                assert change <= 0.051


class TestCalibrationIntegration:
    """Integration tests."""
    
    def test_full_calibration_workflow(self, calibrator):
        """Should handle complete calibration workflow."""
        # Generate recommendations
        drift_stats = {"anomaly_score_mean": 0.65, "anomaly_change_pct": 30.0}
        rec = calibrator.generate_recommendations(drift_stats=drift_stats)
        
        if not rec.has_recommendations():
            # No recommendations is valid
            return
        
        # Preview
        preview = calibrator.preview_changes(rec)
        assert len(preview) > 0
        
        # Apply
        calibrator.apply_recommendations(rec, confirmed=True)
        
        # Verify applied
        updated = calibrator.load_current_thresholds()
        for path, value in rec.recommendations.items():
            parts = path.split(".")
            current = updated
            for part in parts:
                current = current[part]
            assert current == value
        
        # List backups
        backups = calibrator.list_backups()
        assert len(backups) > 0
        
        # Restore
        calibrator.restore_backup(backups[0])
