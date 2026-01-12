"""Unit tests for dashboard empty states"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime

from soc_copilot.phase4.ui.dashboard import Dashboard


@pytest.fixture
def mock_bridge():
    """Create mock controller bridge"""
    bridge = Mock()
    bridge.get_latest_alerts = Mock(return_value=[])
    bridge.get_stats = Mock(return_value={
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0
    })
    return bridge


@pytest.fixture
def dashboard(qtbot, mock_bridge):
    """Create dashboard widget"""
    widget = Dashboard(mock_bridge)
    qtbot.addWidget(widget)
    return widget


def test_dashboard_shows_not_started_state(dashboard, mock_bridge):
    """Dashboard should show 'Not Started' when no sources configured"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0
    }
    
    dashboard.refresh()
    
    assert "Not Started" in dashboard.status_label.text()
    assert "No log sources configured" in dashboard.empty_state_label.text()


def test_dashboard_shows_active_state(dashboard, mock_bridge):
    """Dashboard should show 'Active' when ingestion running"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": True,
        "shutdown_flag": False,
        "sources_count": 1,
        "dropped_count": 0
    }
    
    dashboard.refresh()
    
    assert "Active" in dashboard.status_label.text()


def test_dashboard_shows_stopped_state(dashboard, mock_bridge):
    """Dashboard should show 'Stopped' when shutdown flag set"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": False,
        "shutdown_flag": True,
        "sources_count": 1,
        "dropped_count": 0
    }
    
    dashboard.refresh()
    
    assert "Stopped" in dashboard.status_label.text()
    assert "Ingestion stopped" in dashboard.empty_state_label.text()


def test_dashboard_shows_dropped_records(dashboard, mock_bridge):
    """Dashboard should show dropped record count"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": True,
        "shutdown_flag": False,
        "sources_count": 1,
        "dropped_count": 42
    }
    
    dashboard.refresh()
    
    assert "Dropped: 42" in dashboard.status_label.text()


def test_dashboard_shows_pipeline_inactive(dashboard, mock_bridge):
    """Dashboard should show pipeline inactive state"""
    mock_bridge.get_stats.return_value = {
        "pipeline_loaded": False,
        "results_stored": 0,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0
    }
    
    dashboard.refresh()
    
    assert "Inactive" in dashboard.status_label.text()
    assert "Pipeline inactive" in dashboard.empty_state_label.text()


def test_dashboard_handles_error_gracefully(dashboard, mock_bridge):
    """Dashboard should handle errors gracefully"""
    mock_bridge.get_latest_alerts.side_effect = Exception("Test error")
    
    dashboard.refresh()
    
    assert "Error" in dashboard.status_label.text()
    assert "Unable to load" in dashboard.empty_state_label.text()


def test_dashboard_get_ingestion_status_not_started(dashboard):
    """Get ingestion status should return 'Not Started'"""
    stats = {"running": False, "shutdown_flag": False, "sources_count": 0}
    status = dashboard._get_ingestion_status(stats)
    assert status == "Not Started"


def test_dashboard_get_ingestion_status_active(dashboard):
    """Get ingestion status should return 'Active'"""
    stats = {"running": True, "shutdown_flag": False, "sources_count": 1}
    status = dashboard._get_ingestion_status(stats)
    assert status == "Active"


def test_dashboard_get_ingestion_status_stopped(dashboard):
    """Get ingestion status should return 'Stopped'"""
    stats = {"running": False, "shutdown_flag": True, "sources_count": 1}
    status = dashboard._get_ingestion_status(stats)
    assert status == "Stopped"


def test_dashboard_get_ingestion_status_configured(dashboard):
    """Get ingestion status should return 'Configured'"""
    stats = {"running": False, "shutdown_flag": False, "sources_count": 1}
    status = dashboard._get_ingestion_status(stats)
    assert status == "Configured"
