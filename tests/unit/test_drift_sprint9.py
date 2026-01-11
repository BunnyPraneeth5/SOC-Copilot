"""Unit tests for Sprint-9 Drift Monitoring."""

import pytest
import json
from pathlib import Path

from soc_copilot.phase2.drift import DriftMonitor, DriftReport, DriftLevel


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary database path."""
    return tmp_path / "drift.db"


@pytest.fixture
def monitor(temp_db):
    """Create initialized drift monitor."""
    monitor = DriftMonitor(temp_db)
    monitor.initialize()
    yield monitor
    monitor.close()


class TestDriftMonitor:
    """Tests for DriftMonitor."""
    
    def test_initialize_creates_db(self, temp_db):
        """Should create database file."""
        monitor = DriftMonitor(temp_db)
        monitor.initialize()
        
        assert temp_db.exists()
        monitor.close()
    
    def test_record_inference(self, monitor):
        """Should record inference output."""
        monitor.record_inference(
            anomaly_score=0.75,
            risk_score=0.82,
            predicted_class="BruteForce",
            priority="P1-High"
        )
        
        # Verify recorded
        conn = monitor._get_connection()
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM inference_stats")
        assert cursor.fetchone()["cnt"] == 1
    
    def test_compute_drift_report_insufficient_data(self, monitor):
        """Should handle insufficient data gracefully."""
        # Add only 5 records
        for i in range(5):
            monitor.record_inference(0.5, 0.6, "Benign", "P4-Info")
        
        report = monitor.compute_drift_report()
        
        assert report.window_size < 10
        assert report.baseline_size == 0
    
    def test_compute_drift_report_with_data(self, monitor):
        """Should compute drift report with sufficient data."""
        # Add baseline (100 records)
        for i in range(100):
            monitor.record_inference(0.3, 0.4, "Benign", "P4-Info")
        
        # Add current window (100 records with higher scores)
        for i in range(100):
            monitor.record_inference(0.6, 0.7, "BruteForce", "P2-Medium")
        
        report = monitor.compute_drift_report(window_size=100, baseline_size=100)
        
        assert report.window_size == 100
        assert report.baseline_size == 100
        assert report.anomaly_score_mean > 0.5
        assert report.risk_score_mean > 0.6
        assert "BruteForce" in report.class_distribution
    
    def test_drift_classification(self, monitor):
        """Should classify drift levels correctly."""
        # Add stable baseline
        for i in range(100):
            monitor.record_inference(0.3, 0.4, "Benign", "P4-Info")
        
        # Add drifted window (100% increase)
        for i in range(100):
            monitor.record_inference(0.6, 0.8, "Malware", "P1-High")
        
        report = monitor.compute_drift_report(window_size=100, baseline_size=100)
        
        # Should detect HIGH drift (>50% change)
        assert report.anomaly_drift in [DriftLevel.MODERATE, DriftLevel.HIGH]
        assert report.risk_drift in [DriftLevel.MODERATE, DriftLevel.HIGH]
    
    def test_get_latest_report(self, monitor):
        """Should retrieve latest drift report."""
        # Add data and compute report
        for i in range(50):
            monitor.record_inference(0.5, 0.6, "Benign", "P4-Info")
        
        report1 = monitor.compute_drift_report(window_size=50, baseline_size=0)
        
        # Get latest
        latest = monitor.get_latest_report()
        
        assert latest is not None
        assert latest.timestamp == report1.timestamp
    
    def test_get_report_history(self, monitor):
        """Should retrieve report history."""
        # Add data
        for i in range(50):
            monitor.record_inference(0.5, 0.6, "Benign", "P4-Info")
        
        # Compute multiple reports
        monitor.compute_drift_report(window_size=20, baseline_size=0)
        monitor.compute_drift_report(window_size=30, baseline_size=0)
        
        history = monitor.get_report_history(limit=10)
        
        assert len(history) == 2
        assert "timestamp" in history[0]
        assert "metrics" in history[0]
    
    def test_class_distribution(self, monitor):
        """Should track class distribution."""
        for i in range(50):
            monitor.record_inference(0.5, 0.6, "Benign", "P4-Info")
        for i in range(30):
            monitor.record_inference(0.7, 0.8, "BruteForce", "P2-Medium")
        for i in range(20):
            monitor.record_inference(0.8, 0.9, "Malware", "P1-High")
        
        report = monitor.compute_drift_report(window_size=100, baseline_size=0)
        
        assert report.class_distribution["Benign"] == 50
        assert report.class_distribution["BruteForce"] == 30
        assert report.class_distribution["Malware"] == 20
    
    def test_priority_distribution(self, monitor):
        """Should track priority distribution."""
        for i in range(60):
            monitor.record_inference(0.5, 0.6, "Benign", "P4-Info")
        for i in range(40):
            monitor.record_inference(0.7, 0.8, "BruteForce", "P2-Medium")
        
        report = monitor.compute_drift_report(window_size=100, baseline_size=0)
        
        assert report.priority_distribution["P4-Info"] == 60
        assert report.priority_distribution["P2-Medium"] == 40
    
    def test_drift_level_thresholds(self, monitor):
        """Should use conservative drift thresholds."""
        # Test NONE (<10%)
        assert monitor._classify_drift(5.0) == DriftLevel.NONE
        
        # Test LOW (10-25%)
        assert monitor._classify_drift(15.0) == DriftLevel.LOW
        
        # Test MODERATE (25-50%)
        assert monitor._classify_drift(35.0) == DriftLevel.MODERATE
        
        # Test HIGH (>50%)
        assert monitor._classify_drift(60.0) == DriftLevel.HIGH
    
    def test_report_to_dict(self):
        """Should convert report to dictionary."""
        report = DriftReport()
        report.window_size = 100
        report.anomaly_score_mean = 0.5
        report.anomaly_drift = DriftLevel.LOW
        
        data = report.to_dict()
        
        assert data["window_size"] == 100
        assert data["metrics"]["anomaly_score_mean"] == 0.5
        assert data["drift"]["anomaly"] == "LOW"


class TestDriftMonitorIntegration:
    """Integration tests."""
    
    def test_full_workflow(self, monitor):
        """Should handle complete drift monitoring workflow."""
        # Simulate baseline period
        for i in range(100):
            monitor.record_inference(
                anomaly_score=0.3 + (i % 10) * 0.01,
                risk_score=0.4 + (i % 10) * 0.01,
                predicted_class="Benign",
                priority="P4-Info"
            )
        
        # Simulate drift period
        for i in range(100):
            monitor.record_inference(
                anomaly_score=0.6 + (i % 10) * 0.01,
                risk_score=0.7 + (i % 10) * 0.01,
                predicted_class="BruteForce",
                priority="P2-Medium"
            )
        
        # Compute report
        report = monitor.compute_drift_report(window_size=100, baseline_size=100)
        
        # Verify metrics
        assert report.window_size == 100
        assert report.baseline_size == 100
        assert report.anomaly_score_mean > 0.5
        assert report.anomaly_drift != DriftLevel.NONE
        
        # Verify history
        history = monitor.get_report_history()
        assert len(history) >= 1
        
        # Verify latest
        latest = monitor.get_latest_report()
        assert latest.timestamp == report.timestamp
    
    def test_default_db_path(self, tmp_path, monkeypatch):
        """Should use default path data/drift/drift.db."""
        monkeypatch.chdir(tmp_path)
        
        monitor = DriftMonitor()
        monitor.initialize()
        
        assert monitor.db_path == Path("data/drift/drift.db")
        assert monitor.db_path.parent.exists()
        
        monitor.close()
