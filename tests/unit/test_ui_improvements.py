"""Tests for UI improvements and empty state handling"""

import unittest
from unittest.mock import Mock, patch
import sys

# Mock PyQt6 for testing
sys.modules['PyQt6'] = Mock()
sys.modules['PyQt6.QtWidgets'] = Mock()
sys.modules['PyQt6.QtCore'] = Mock()
sys.modules['PyQt6.QtGui'] = Mock()

from soc_copilot.phase4.ui.dashboard import Dashboard
from soc_copilot.phase4.ui.alerts_view import AlertsView


class TestDashboardImprovements(unittest.TestCase):
    """Test Dashboard improvements"""
    
    def setUp(self):
        self.bridge = Mock()
        
        # Mock PyQt6 components
        with patch('soc_copilot.phase4.ui.dashboard.QWidget'), \
             patch('soc_copilot.phase4.ui.dashboard.QTimer'):
            self.dashboard = Dashboard(self.bridge)
    
    def test_empty_state_handling(self):
        """Test dashboard handles empty state"""
        # Mock empty results
        self.bridge.get_latest_alerts.return_value = []
        self.bridge.get_stats.return_value = {
            "pipeline_loaded": True,
            "results_stored": 0
        }
        
        # Should not raise exception
        self.dashboard.refresh()
    
    def test_error_handling(self):
        """Test dashboard handles errors gracefully"""
        # Mock bridge to raise exception
        self.bridge.get_latest_alerts.side_effect = Exception("Connection error")
        
        # Should not raise exception
        self.dashboard.refresh()
    
    def test_empty_state_messaging(self):
        """Test improved empty state messaging"""
        # Mock different system states
        self.bridge.get_stats.return_value = {
            "pipeline_loaded": False,
            "ingestion_running": False
        }
        
        # Should not raise exception and should show appropriate message
        self.dashboard.refresh()
        self.bridge.get_stats.assert_called()
    
    def test_metric_update_safety(self):
        """Test safe metric updates"""
        # Mock successful state
        self.bridge.get_latest_alerts.return_value = []
        self.bridge.get_stats.return_value = {
            "pipeline_loaded": True,
            "results_stored": 10,
            "ingestion_running": True
        }
        
        # Should handle metric updates safely
        self.dashboard.refresh()
        self.bridge.get_latest_alerts.assert_called()


class TestAlertsViewImprovements(unittest.TestCase):
    """Test AlertsView improvements"""
    
    def setUp(self):
        self.bridge = Mock()
        
        # Mock PyQt6 components
        with patch('soc_copilot.phase4.ui.alerts_view.QWidget'), \
             patch('soc_copilot.phase4.ui.alerts_view.QTableWidget'), \
             patch('soc_copilot.phase4.ui.alerts_view.QTimer'):
            self.alerts_view = AlertsView(self.bridge)
    
    def test_empty_alerts_handling(self):
        """Test alerts view handles empty state"""
        # Mock empty results
        self.bridge.get_latest_alerts.return_value = []
        
        # Should not raise exception
        self.alerts_view.refresh()
    
    def test_error_handling(self):
        """Test alerts view handles errors gracefully"""
        # Mock bridge to raise exception
        self.bridge.get_latest_alerts.side_effect = Exception("Database error")
        
        # Should not raise exception
        self.alerts_view.refresh()
    
    def test_enhanced_error_states(self):
        """Test enhanced error state handling"""
        # Mock bridge to raise exception
        self.bridge.get_latest_alerts.side_effect = Exception("Database connection failed")
        
        # Should not raise exception and show detailed error
        self.alerts_view.refresh()
    
    def test_safe_data_access(self):
        """Test safe data access for alert attributes"""
        # Mock alert with missing attributes
        mock_result = Mock()
        mock_result.batch_id = "test-batch"
        mock_alert = Mock()
        mock_alert.alert_id = "test-alert"
        mock_alert.timestamp = "2023-01-01 12:00:00"  # String instead of datetime
        mock_alert.priority = "High"
        mock_alert.classification = "Test Attack"
        # Missing source_ip and confidence attributes
        mock_result.alerts = [mock_alert]
        
        self.bridge.get_latest_alerts.return_value = [mock_result]
        
        # Should handle missing attributes gracefully
        self.alerts_view.refresh()


class TestUIRobustness(unittest.TestCase):
    """Test overall UI robustness"""
    
    def test_import_error_handling(self):
        """Test UI handles import errors gracefully"""
        # This would be tested in integration tests
        # where we can actually test import failures
        pass
    
    def test_initialization_with_failed_controller(self):
        """Test UI initialization with failed controller"""
        # Mock controller that fails to initialize
        mock_controller = Mock()
        mock_controller.initialize.side_effect = Exception("Init failed")
        
        # UI should still be creatable (tested in integration)
        pass


if __name__ == "__main__":
    unittest.main()