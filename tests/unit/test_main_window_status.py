"""Unit tests for main window status bar"""

import pytest
from unittest.mock import Mock

from soc_copilot.phase4.ui.main_window import MainWindow


@pytest.fixture
def mock_controller():
    """Create mock controller"""
    controller = Mock()
    controller.get_results = Mock(return_value=[])
    controller.get_result_by_id = Mock(return_value=None)
    controller.get_stats = Mock(return_value={
        "pipeline_loaded": True,
        "results_stored": 0,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0
    })
    controller.result_store = Mock()
    controller.result_store.count = Mock(return_value=0)
    return controller


@pytest.fixture
def main_window(qtbot, mock_controller):
    """Create main window"""
    window = MainWindow(mock_controller)
    qtbot.addWidget(window)
    return window


def test_status_bar_shows_not_started(main_window, mock_controller):
    """Status bar should show 'Not Started' state"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Not Started" in status_text


def test_status_bar_shows_active(main_window, mock_controller):
    """Status bar should show 'Active' state"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": True,
        "shutdown_flag": False,
        "sources_count": 1,
        "dropped_count": 0
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Active" in status_text


def test_status_bar_shows_stopped(main_window, mock_controller):
    """Status bar should show 'Stopped' state"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": True,
        "sources_count": 1,
        "dropped_count": 0
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Stopped" in status_text


def test_status_bar_shows_dropped_records(main_window, mock_controller):
    """Status bar should show dropped record count"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": True,
        "shutdown_flag": False,
        "sources_count": 1,
        "dropped_count": 25
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Dropped: 25" in status_text


def test_status_bar_shows_permission_warning(main_window, mock_controller):
    """Status bar should show permission warning"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0,
        "permission_check": {
            "has_permission": False,
            "error_message": "No admin rights"
        }
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Permissions: Limited" in status_text


def test_status_bar_handles_error_gracefully(main_window, mock_controller):
    """Status bar should handle errors gracefully"""
    mock_controller.get_stats.side_effect = Exception("Test error")
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "unavailable" in status_text


def test_status_bar_shows_configured_state(main_window, mock_controller):
    """Status bar should show 'Configured' state"""
    mock_controller.get_stats.return_value = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 1,
        "dropped_count": 0
    }
    
    main_window._update_status_bar()
    
    status_text = main_window.status_bar.currentMessage()
    assert "Configured" in status_text
