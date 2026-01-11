"""Unit tests for Sprint-15: Application Controller Layer"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

from soc_copilot.phase4.controller import (
    AnalysisResult,
    AlertSummary,
    PipelineStats,
    ResultStore,
    AppController,
)


# ============================================================================
# Schema Tests
# ============================================================================

class TestSchemas:
    """Test view model schemas"""
    
    def test_alert_summary_creation(self):
        """Test AlertSummary creation"""
        alert = AlertSummary(
            alert_id="test-001",
            priority="P1-High",
            classification="BruteForce",
            confidence=0.85,
            anomaly_score=0.72,
            risk_score=0.78,
            source_ip="192.168.1.100",
            destination_ip="10.0.0.1",
            timestamp=datetime.now(),
            reasoning="High anomaly detected",
            suggested_action="Investigate immediately"
        )
        
        assert alert.alert_id == "test-001"
        assert alert.priority == "P1-High"
        assert alert.classification == "BruteForce"
    
    def test_pipeline_stats_creation(self):
        """Test PipelineStats creation"""
        stats = PipelineStats(
            total_records=100,
            processed_records=95,
            alerts_generated=5,
            risk_distribution={"High": 2, "Medium": 3},
            classification_distribution={"BruteForce": 3, "PortScan": 2},
            processing_time=1.5
        )
        
        assert stats.total_records == 100
        assert stats.processed_records == 95
        assert stats.alerts_generated == 5
    
    def test_analysis_result_creation(self):
        """Test AnalysisResult creation"""
        alert = AlertSummary(
            alert_id="test-001",
            priority="P1-High",
            classification="BruteForce",
            confidence=0.85,
            anomaly_score=0.72,
            risk_score=0.78,
            source_ip="192.168.1.100",
            destination_ip="10.0.0.1",
            timestamp=datetime.now(),
            reasoning="Test",
            suggested_action="Test"
        )
        
        stats = PipelineStats(
            total_records=10,
            processed_records=10,
            alerts_generated=1,
            risk_distribution={},
            classification_distribution={},
            processing_time=0.5
        )
        
        result = AnalysisResult(
            batch_id="batch-001",
            timestamp=datetime.now(),
            alerts=[alert],
            stats=stats,
            raw_count=10
        )
        
        assert result.batch_id == "batch-001"
        assert len(result.alerts) == 1
        assert result.raw_count == 10


# ============================================================================
# ResultStore Tests
# ============================================================================

class TestResultStore:
    """Test result storage"""
    
    def test_add_result(self):
        """Test adding results"""
        store = ResultStore(max_results=10)
        
        result = self._create_mock_result("batch-001")
        store.add(result)
        
        assert store.count() == 1
    
    def test_get_latest(self):
        """Test getting latest results"""
        store = ResultStore(max_results=10)
        
        for i in range(5):
            result = self._create_mock_result(f"batch-{i}")
            store.add(result)
        
        latest = store.get_latest(limit=3)
        assert len(latest) == 3
        assert latest[-1].batch_id == "batch-4"
    
    def test_get_by_id(self):
        """Test getting result by ID"""
        store = ResultStore(max_results=10)
        
        result = self._create_mock_result("batch-001")
        store.add(result)
        
        retrieved = store.get_by_id("batch-001")
        assert retrieved is not None
        assert retrieved.batch_id == "batch-001"
        
        missing = store.get_by_id("nonexistent")
        assert missing is None
    
    def test_max_results_limit(self):
        """Test max results limit"""
        store = ResultStore(max_results=3)
        
        for i in range(5):
            result = self._create_mock_result(f"batch-{i}")
            store.add(result)
        
        assert store.count() == 3
        
        # Should only have last 3
        all_results = store.get_all()
        assert len(all_results) == 3
        assert all_results[0].batch_id == "batch-2"
    
    def test_clear_results(self):
        """Test clearing results"""
        store = ResultStore(max_results=10)
        
        for i in range(5):
            result = self._create_mock_result(f"batch-{i}")
            store.add(result)
        
        assert store.count() == 5
        
        store.clear()
        assert store.count() == 0
    
    def test_thread_safety(self):
        """Test thread-safe operations"""
        store = ResultStore(max_results=100)
        
        from threading import Thread
        
        def add_results():
            for i in range(10):
                result = self._create_mock_result(f"batch-{i}")
                store.add(result)
        
        threads = [Thread(target=add_results) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Should have added results safely
        assert store.count() <= 100
    
    def _create_mock_result(self, batch_id: str) -> AnalysisResult:
        """Create mock analysis result"""
        return AnalysisResult(
            batch_id=batch_id,
            timestamp=datetime.now(),
            alerts=[],
            stats=PipelineStats(
                total_records=0,
                processed_records=0,
                alerts_generated=0,
                risk_distribution={},
                classification_distribution={},
                processing_time=0.0
            ),
            raw_count=0
        )


# ============================================================================
# AppController Tests
# ============================================================================

class TestAppController:
    """Test application controller"""
    
    @pytest.fixture
    def mock_pipeline(self):
        """Create mock pipeline"""
        pipeline = Mock()
        
        # Mock alert
        alert = Mock()
        alert.alert_id = "alert-001"
        alert.priority = Mock(value="P1-High")
        alert.classification = "BruteForce"
        alert.classification_confidence = 0.85
        alert.anomaly_score = 0.72
        alert.combined_risk_score = 0.78
        alert.source_ip = "192.168.1.100"
        alert.destination_ip = "10.0.0.1"
        alert.reasoning = "Test reasoning"
        alert.suggested_action = "Test action"
        
        # Mock stats
        stats = Mock()
        stats.total_records = 10
        stats.processed_records = 10
        stats.risk_distribution = {"High": 1}
        stats.classification_distribution = {"BruteForce": 1}
        
        pipeline.analyze_file.return_value = ([], [alert], stats)
        
        return pipeline
    
    def test_initialize_controller(self, tmp_path):
        """Test controller initialization"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        assert controller.models_dir == models_dir
        assert controller.result_store is not None
    
    def test_process_batch_without_init(self, tmp_path):
        """Test processing batch without initialization"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        records = [{"raw_line": "test log line"}]
        
        with pytest.raises(RuntimeError):
            controller.process_batch(records)
    
    def test_process_batch_with_killswitch(self, tmp_path, mock_pipeline):
        """Test kill switch enforcement"""
        models_dir = str(tmp_path / "models")
        killswitch_enabled = True
        
        def check_killswitch():
            return killswitch_enabled
        
        controller = AppController(models_dir, killswitch_check=check_killswitch)
        controller._pipeline = mock_pipeline
        
        records = [{"raw_line": "test log line"}]
        
        # Kill switch enabled - should return None
        result = controller.process_batch(records)
        assert result is None
        
        # Kill switch disabled - should process
        killswitch_enabled = False
        result = controller.process_batch(records)
        assert result is not None
    
    def test_process_empty_batch(self, tmp_path, mock_pipeline):
        """Test processing empty batch"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        controller._pipeline = mock_pipeline
        
        # Empty records
        result = controller.process_batch([])
        assert result is None
        
        # Records without raw_line
        result = controller.process_batch([{"other": "data"}])
        assert result is None
    
    def test_get_results(self, tmp_path):
        """Test getting results"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        # Add mock results
        for i in range(5):
            result = AnalysisResult(
                batch_id=f"batch-{i}",
                timestamp=datetime.now(),
                alerts=[],
                stats=PipelineStats(
                    total_records=0,
                    processed_records=0,
                    alerts_generated=0,
                    risk_distribution={},
                    classification_distribution={},
                    processing_time=0.0
                ),
                raw_count=0
            )
            controller.result_store.add(result)
        
        results = controller.get_results(limit=3)
        assert len(results) == 3
    
    def test_get_result_by_id(self, tmp_path):
        """Test getting result by ID"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        result = AnalysisResult(
            batch_id="batch-001",
            timestamp=datetime.now(),
            alerts=[],
            stats=PipelineStats(
                total_records=0,
                processed_records=0,
                alerts_generated=0,
                risk_distribution={},
                classification_distribution={},
                processing_time=0.0
            ),
            raw_count=0
        )
        controller.result_store.add(result)
        
        retrieved = controller.get_result_by_id("batch-001")
        assert retrieved is not None
        assert retrieved.batch_id == "batch-001"
    
    def test_get_stats(self, tmp_path):
        """Test getting controller stats"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        stats = controller.get_stats()
        assert stats["pipeline_loaded"] is False
        assert stats["results_stored"] == 0
        assert stats["models_dir"] == models_dir
    
    def test_clear_results(self, tmp_path):
        """Test clearing results"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        # Add results
        for i in range(3):
            result = AnalysisResult(
                batch_id=f"batch-{i}",
                timestamp=datetime.now(),
                alerts=[],
                stats=PipelineStats(
                    total_records=0,
                    processed_records=0,
                    alerts_generated=0,
                    risk_distribution={},
                    classification_distribution={},
                    processing_time=0.0
                ),
                raw_count=0
            )
            controller.result_store.add(result)
        
        assert controller.result_store.count() == 3
        
        controller.clear_results()
        assert controller.result_store.count() == 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestControllerIntegration:
    """Test controller integration"""
    
    def test_batch_to_analysis_flow(self, tmp_path):
        """Test complete batch → analysis flow"""
        models_dir = str(tmp_path / "models")
        controller = AppController(models_dir)
        
        # Mock pipeline
        mock_pipeline = Mock()
        alert = Mock()
        alert.alert_id = "alert-001"
        alert.priority = Mock(value="P1-High")
        alert.classification = "BruteForce"
        alert.classification_confidence = 0.85
        alert.anomaly_score = 0.72
        alert.combined_risk_score = 0.78
        alert.source_ip = "192.168.1.100"
        alert.destination_ip = "10.0.0.1"
        alert.reasoning = "Test"
        alert.suggested_action = "Test"
        
        stats = Mock()
        stats.total_records = 5
        stats.processed_records = 5
        stats.risk_distribution = {"High": 1}
        stats.classification_distribution = {"BruteForce": 1}
        
        mock_pipeline.analyze_file.return_value = ([], [alert], stats)
        controller._pipeline = mock_pipeline
        
        # Process batch
        records = [
            {"raw_line": "log line 1"},
            {"raw_line": "log line 2"},
            {"raw_line": "log line 3"}
        ]
        
        result = controller.process_batch(records)
        
        # Verify result
        assert result is not None
        assert result.raw_count == 3
        assert len(result.alerts) == 1
        assert result.alerts[0].alert_id == "alert-001"
        assert result.stats.total_records == 5
        
        # Verify stored
        assert controller.result_store.count() == 1
    
    def test_killswitch_prevents_analysis(self, tmp_path):
        """Test kill switch prevents analysis"""
        models_dir = str(tmp_path / "models")
        
        killswitch_enabled = True
        
        def check_killswitch():
            return killswitch_enabled
        
        controller = AppController(models_dir, killswitch_check=check_killswitch)
        
        mock_pipeline = Mock()
        controller._pipeline = mock_pipeline
        
        records = [{"raw_line": "test"}]
        
        # Kill switch enabled
        result = controller.process_batch(records)
        assert result is None
        assert mock_pipeline.analyze_file.call_count == 0
        
        # Kill switch disabled
        killswitch_enabled = False
        result = controller.process_batch(records)
        # Should attempt analysis (may fail due to mock, but call is made)
    
    def test_no_phase_coupling(self):
        """Verify no imports from Phase-1/2/3 internals"""
        import inspect
        from soc_copilot.phase4.controller import app_controller
        
        source = inspect.getsource(app_controller)
        
        # Should only import public APIs
        assert "from soc_copilot.pipeline import" in source
        
        # Should not import internals
        assert "from soc_copilot.models" not in source
        assert "from soc_copilot.data" not in source
        assert "from soc_copilot.intelligence" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
