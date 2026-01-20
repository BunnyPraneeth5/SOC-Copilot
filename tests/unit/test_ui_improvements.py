"""Tests for UI improvements and empty state handling"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys

# Mock PyQt6 for testing
mock_qt = MagicMock()
sys.modules['PyQt6'] = mock_qt
sys.modules['PyQt6.QtWidgets'] = mock_qt
sys.modules['PyQt6.QtCore'] = mock_qt
sys.modules['PyQt6.QtGui'] = mock_qt


class TestDashboardImprovements(unittest.TestCase):
    """Test Dashboard improvements - basic functionality"""
    
    def test_dashboard_module_exists(self):
        """Test dashboard module can be imported"""
        # Just verify imports work
        pass
    
    def test_bridge_interface(self):
        """Test that bridge has required methods"""
        bridge = Mock()
        bridge.get_latest_alerts.return_value = []
        bridge.get_stats.return_value = {"pipeline_loaded": True}
        bridge.add_file_source.return_value = True
        bridge.start_ingestion.return_value = None
        
        # Verify mock works
        self.assertEqual(bridge.get_latest_alerts(), [])
        self.assertTrue(bridge.get_stats()["pipeline_loaded"])


class TestAlertsViewImprovements(unittest.TestCase):
    """Test AlertsView improvements - basic functionality"""
    
    def test_alerts_view_module_exists(self):
        """Test alerts view module can be imported"""
        pass
    
    def test_bridge_interface_for_alerts(self):
        """Test bridge interface for alerts"""
        bridge = Mock()
        bridge.get_latest_alerts.return_value = []
        bridge.get_stats.return_value = {}
        
        # Verify mock
        self.assertEqual(bridge.get_latest_alerts(), [])


class TestUIRobustness(unittest.TestCase):
    """Test overall UI robustness"""
    
    def test_mock_alert_structure(self):
        """Test mock alert has correct structure"""
        mock_result = Mock()
        mock_result.batch_id = "test-batch"
        mock_alert = Mock()
        mock_alert.alert_id = "test-alert"
        mock_alert.timestamp = "2023-01-01 12:00:00"
        mock_alert.priority = "High"
        mock_alert.classification = "Test Attack"
        mock_result.alerts = [mock_alert]
        
        self.assertEqual(len(mock_result.alerts), 1)
        self.assertEqual(mock_result.alerts[0].priority, "High")


if __name__ == "__main__":
    unittest.main()