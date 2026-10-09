"""Main window status: shown once, in the header chips.

These cases used to check the bottom status bar's periodic summary; that
duplicate was removed, so the same states are checked on the Ingestion /
Pipeline header chips (text + tooltip details).
"""

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


def _chip(window, name):
    window.system_status_bar.refresh()
    return window.system_status_bar.chip_bar.chips[name]


def _stats(**overrides):
    stats = {
        "pipeline_loaded": True,
        "running": False,
        "shutdown_flag": False,
        "sources_count": 0,
        "dropped_count": 0,
    }
    stats.update(overrides)
    return stats


def test_ingestion_not_started(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats()
    assert _chip(main_window, "ingestion").text() == "Ingestion: Not Started"


def test_ingestion_active(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats(running=True, sources_count=1)
    assert _chip(main_window, "ingestion").text() == "Ingestion: Active (1)"


def test_ingestion_stopped(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats(shutdown_flag=True, sources_count=1)
    assert _chip(main_window, "ingestion").text() == "Ingestion: Stopped"


def test_dropped_records_in_details(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats(
        running=True, sources_count=1, dropped_count=25
    )
    chip = _chip(main_window, "ingestion")
    assert "Dropped: 25" in chip.toolTip()
    assert chip.tone == "warn"


def test_permission_warning_in_details(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats(
        permission_check={"has_permission": False, "error_message": "No admin rights"}
    )
    assert "Permissions: Limited" in _chip(main_window, "ingestion").toolTip()


def test_status_error_handled_gracefully(main_window, mock_controller):
    mock_controller.get_stats.side_effect = Exception("Test error")
    chip = _chip(main_window, "pipeline")
    assert chip.text() == "Pipeline: Error"
    assert "unavailable" in chip.toolTip()


def test_ingestion_configured(main_window, mock_controller):
    mock_controller.get_stats.return_value = _stats(sources_count=1)
    assert _chip(main_window, "ingestion").text() == "Ingestion: Configured (1)"


def test_bottom_bar_carries_no_status_summary(main_window, mock_controller):
    main_window._update_status_widgets()
    assert main_window.status_bar.currentMessage() == ""
