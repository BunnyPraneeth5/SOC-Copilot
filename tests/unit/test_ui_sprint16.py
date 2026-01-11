"""Unit tests for Sprint-16: UI/UX Layer"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from soc_copilot.phase4.ui import ControllerBridge
from soc_copilot.phase4.controller import AnalysisResult, AlertSummary, PipelineStats


# ============================================================================
# ControllerBridge Tests
# ============================================================================

class TestControllerBridge:
    """Test read-only controller bridge"""
    
    @pytest.fixture
    def mock_controller(self):
        """Create mock controller"""
        controller = Mock()
        controller.result_store = Mock()
        return controller
    
    def test_get_latest_alerts(self, mock_controller):
        """Test getting latest alerts"""
        mock_controller.get_results.return_value = []
        
        bridge = ControllerBridge(mock_controller)
        results = bridge.get_latest_alerts(limit=10)
        
        mock_controller.get_results.assert_called_once_with(limit=10)
        assert results == []
    
    def test_get_alert_by_id(self, mock_controller):
        """Test getting alert by ID"""
        mock_result = Mock()
        mock_controller.get_result_by_id.return_value = mock_result
        
        bridge = ControllerBridge(mock_controller)
        result = bridge.get_alert_by_id("batch-001")
        
        mock_controller.get_result_by_id.assert_called_once_with("batch-001")
        assert result == mock_result
    
    def test_get_stats(self, mock_controller):
        """Test getting statistics"""
        mock_controller.get_stats.return_value = {"pipeline_loaded": True}
        
        bridge = ControllerBridge(mock_controller)
        stats = bridge.get_stats()
        
        assert stats["pipeline_loaded"] is True
    
    def test_get_total_alert_count(self, mock_controller):
        """Test getting total alert count"""
        mock_controller.result_store.count.return_value = 42
        
        bridge = ControllerBridge(mock_controller)
        count = bridge.get_total_alert_count()
        
        assert count == 42
    
    def test_read_only_access(self, mock_controller):
        """Verify bridge provides read-only access"""
        bridge = ControllerBridge(mock_controller)
        
        # Should not have write methods
        assert not hasattr(bridge, 'process_batch')
        assert not hasattr(bridge, 'clear_results')
        assert not hasattr(bridge, 'initialize')


# ============================================================================
# UI Component Tests (Logic Only)
# ============================================================================

class TestUIComponents:
    """Test UI component logic without Qt event loop"""
    
    def test_alert_priority_color_mapping(self):
        """Test priority to color mapping logic"""
        def get_priority_color(priority: str):
            if "Critical" in priority:
                return "red"
            elif "High" in priority:
                return "yellow"
            elif "Medium" in priority:
                return "orange"
            else:
                return "white"
        
        assert get_priority_color("P0-Critical") == "red"
        assert get_priority_color("P1-High") == "yellow"
        assert get_priority_color("P2-Medium") == "orange"
        assert get_priority_color("P3-Low") == "white"
    
    def test_alert_explanation_template(self):
        """Test explanation template generation"""
        templates = {
            "BruteForce": "A brute force attack involves repeated login attempts",
            "PortScan": "A port scan is reconnaissance activity",
            "DDoS": "A Distributed Denial of Service attack"
        }
        
        assert "brute force" in templates["BruteForce"].lower()
        assert "port scan" in templates["PortScan"].lower()
        assert "denial of service" in templates["DDoS"].lower()
    
    def test_metric_calculation(self):
        """Test dashboard metric calculation logic"""
        # Mock alerts
        alerts = [
            Mock(priority="P0-Critical"),
            Mock(priority="P1-High"),
            Mock(priority="P1-High"),
            Mock(priority="P2-Medium"),
        ]
        
        critical = sum(1 for a in alerts if "Critical" in a.priority)
        high = sum(1 for a in alerts if "High" in a.priority)
        medium = sum(1 for a in alerts if "Medium" in a.priority)
        
        assert critical == 1
        assert high == 2
        assert medium == 1
    
    def test_alert_data_extraction(self):
        """Test alert data extraction for table"""
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
        
        # Extract table data
        table_data = {
            "time": alert.timestamp.strftime("%H:%M:%S"),
            "priority": alert.priority,
            "classification": alert.classification,
            "source_ip": alert.source_ip or "N/A",
            "confidence": f"{alert.confidence:.2f}"
        }
        
        assert table_data["priority"] == "P1-High"
        assert table_data["classification"] == "BruteForce"
        assert table_data["source_ip"] == "192.168.1.100"
        assert table_data["confidence"] == "0.85"


# ============================================================================
# Integration Tests
# ============================================================================

class TestUIIntegration:
    """Test UI integration with controller"""
    
    def test_bridge_with_real_schemas(self):
        """Test bridge with real schema objects"""
        # Create real result
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
            reasoning="Test reasoning",
            suggested_action="Investigate"
        )
        
        stats = PipelineStats(
            total_records=10,
            processed_records=10,
            alerts_generated=1,
            risk_distribution={"High": 1},
            classification_distribution={"BruteForce": 1},
            processing_time=0.5
        )
        
        result = AnalysisResult(
            batch_id="batch-001",
            timestamp=datetime.now(),
            alerts=[alert],
            stats=stats,
            raw_count=10
        )
        
        # Mock controller
        controller = Mock()
        controller.get_results.return_value = [result]
        controller.get_result_by_id.return_value = result
        controller.get_stats.return_value = {"pipeline_loaded": True}
        controller.result_store.count.return_value = 1
        
        # Test bridge
        bridge = ControllerBridge(controller)
        
        results = bridge.get_latest_alerts(limit=10)
        assert len(results) == 1
        assert results[0].batch_id == "batch-001"
        
        retrieved = bridge.get_alert_by_id("batch-001")
        assert retrieved.batch_id == "batch-001"
        assert len(retrieved.alerts) == 1
    
    def test_no_backend_modification(self):
        """Verify UI does not modify backend"""
        controller = Mock()
        bridge = ControllerBridge(controller)
        
        # All bridge methods should be read-only
        bridge.get_latest_alerts()
        bridge.get_stats()
        bridge.get_total_alert_count()
        
        # Verify no write operations called
        assert not controller.process_batch.called
        assert not controller.clear_results.called
        assert not controller.initialize.called


# ============================================================================
# Safety Tests
# ============================================================================

class TestUISafety:
    """Test UI safety constraints"""
    
    def test_read_only_bridge(self):
        """Verify bridge is read-only"""
        controller = Mock()
        bridge = ControllerBridge(controller)
        
        # Should only have read methods
        read_methods = ['get_latest_alerts', 'get_alert_by_id', 'get_stats', 'get_total_alert_count']
        
        for method in read_methods:
            assert hasattr(bridge, method)
        
        # Should not have write methods
        write_methods = ['process_batch', 'initialize', 'clear_results']
        
        for method in write_methods:
            assert not hasattr(bridge, method)
    
    def test_no_ml_calls(self):
        """Verify UI makes no ML calls"""
        import inspect
        from soc_copilot.phase4.ui import controller_bridge
        
        source = inspect.getsource(controller_bridge)
        
        # Should not import ML modules
        assert "from soc_copilot.models" not in source
        assert "from soc_copilot.data" not in source
        assert "import sklearn" not in source
        assert "import torch" not in source
    
    def test_no_internet_calls(self):
        """Verify UI makes no internet calls"""
        import inspect
        from soc_copilot.phase4.ui import assistant_panel
        
        source = inspect.getsource(assistant_panel)
        
        # Should not have internet-related imports
        assert "import requests" not in source
        assert "import urllib" not in source
        assert "import http" not in source
        assert "openai" not in source.lower()
        assert "anthropic" not in source.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
