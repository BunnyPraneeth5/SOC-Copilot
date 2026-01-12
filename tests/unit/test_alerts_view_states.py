"""Unit tests for alerts view empty states"""

import pytest
from unittest.mock import Mock
from datetime import datetime

from soc_copilot.phase4.ui.alerts_view import AlertsView


@pytest.fixture
def mock_bridge():
    """Create mock controller bridge"""
    bridge = Mock()
    bridge.get_latest_alerts = Mock(return_value=[])
    bridge.get_stats = Mock(return_value={
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0
    })
    return bridge


@pytest.fixture
def alerts_view(qtbot, mock_bridge):
    """Create alerts view widget"""
    widget = AlertsView(mock_bridge)
    qtbot.addWidget(widget)
    return widget


def test_alerts_view_shows_not_started_empty_state(alerts_view, mock_bridge):
    """Alerts view should show 'Not Started' empty state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0
    }
    
    alerts_view.refresh()
    
    assert "No log sources configured" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()
    assert not alerts_view.table.isVisible()


def test_alerts_view_shows_active_empty_state(alerts_view, mock_bridge):
    """Alerts view should show 'Active' empty state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": True,
        "shutdown_flag": False,
        "sources_count": 1
    }
    
    alerts_view.refresh()
    
    assert "Monitoring active" in alerts_view.empty_label.text()
    assert "No alerts yet" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()


def test_alerts_view_shows_stopped_empty_state(alerts_view, mock_bridge):
    """Alerts view should show 'Stopped' empty state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": True,
        "sources_count": 1
    }
    
    alerts_view.refresh()
    
    assert "Ingestion stopped" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()


def test_alerts_view_shows_pipeline_inactive(alerts_view, mock_bridge):
    """Alerts view should show pipeline inactive state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": False,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0
    }
    
    alerts_view.refresh()
    
    assert "Pipeline not active" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()


def test_alerts_view_hides_empty_state_with_alerts(alerts_view, mock_bridge):
    """Alerts view should hide empty state when alerts present"""
    # Create mock alert
    mock_alert = Mock()
    mock_alert.alert_id = "alert-1"
    mock_alert.timestamp = datetime.now()
    mock_alert.priority = "High"
    mock_alert.classification = "Port Scan"
    mock_alert.source_ip = "192.168.1.1"
    mock_alert.confidence = 0.95
    
    mock_result = Mock()
    mock_result.batch_id = "batch-1"
    mock_result.alerts = [mock_alert]
    
    mock_bridge.get_latest_alerts.return_value = [mock_result]
    
    alerts_view.refresh()
    
    assert not alerts_view.empty_label.isVisible()
    assert alerts_view.table.isVisible()
    assert alerts_view.table.rowCount() == 1


def test_alerts_view_handles_error_gracefully(alerts_view, mock_bridge):
    """Alerts view should handle errors gracefully"""
    mock_bridge.get_latest_alerts.side_effect = Exception("Test error")
    
    alerts_view.refresh()
    
    assert "Error loading alerts" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()
    assert not alerts_view.table.isVisible()


def test_alerts_view_safe_refresh_with_empty_results(alerts_view, mock_bridge):
    """Alerts view should safely refresh with empty results"""
    mock_bridge.get_latest_alerts.return_value = []
    
    # Should not raise exception
    alerts_view.refresh()
    
    assert alerts_view.table.rowCount() == 0
    assert alerts_view.empty_label.isVisible()


def test_alerts_view_configured_state(alerts_view, mock_bridge):
    """Alerts view should show configured state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 1
    }
    
    alerts_view.refresh()
    
    assert "No alerts detected" in alerts_view.empty_label.text()
    assert alerts_view.empty_label.isVisible()
