"""Tests for UX-10: alerts cache key, Action column, banner height, dead code."""

import importlib.util
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QHeaderView

from soc_copilot.phase4.ui.alerts_view import AlertsView
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _alert(alert_id, second, classification="Brute Force", ip="10.0.0.7"):
    return SimpleNamespace(
        alert_id=alert_id, priority="P1-High", classification=classification,
        timestamp=datetime(2026, 7, 10, 14, 30, second), source_ip=ip,
        destination_ip="10.0.0.1", confidence=0.9, anomaly_score=0.5,
        risk_score=0.7, reasoning="r", suggested_action="s",
    )


def _bridge(results):
    bridge = Mock()
    bridge.get_all_results.return_value = results
    bridge.get_triage_map.return_value = {}
    bridge.is_investigation_in_flight.return_value = False
    return bridge


class TestAlertCacheKey:
    def test_same_type_alerts_in_one_batch_all_shown(self, qapp):
        results = [SimpleNamespace(batch_id="b1", alerts=[
            _alert("ML-1", 1, ip="10.0.0.7"), _alert("ML-2", 2, ip="10.0.0.8"),
        ])]
        view = AlertsView(_bridge(results))
        view.refresh()
        assert view.table.rowCount() == 2
        ips = {view.table.item(r, view.SOURCE_IP_COLUMN).text() for r in range(2)}
        assert ips == {"10.0.0.7", "10.0.0.8"}
        destroy(view)

    def test_alerts_without_ids_keyed_by_position(self, qapp):
        results = [SimpleNamespace(batch_id="b1", alerts=[
            _alert(None, 1), _alert(None, 2),
        ])]
        view = AlertsView(_bridge(results))
        view.refresh()
        assert view.table.rowCount() == 2
        destroy(view)

    def test_incremental_refresh_adds_without_duplicates(self, qapp):
        results = [SimpleNamespace(batch_id="b1", alerts=[_alert("ML-1", 1)])]
        bridge = _bridge(results)
        view = AlertsView(bridge)
        view.refresh()
        results.append(SimpleNamespace(batch_id="b2", alerts=[
            _alert("ML-2", 2), _alert("ML-3", 3),
        ]))
        view._incremental_refresh()
        view._incremental_refresh()
        assert len(view._alert_cache) == 3
        assert view.table.rowCount() == 3
        destroy(view)


class TestActionColumn:
    def test_action_column_fixed_classification_stretches(self, qapp):
        view = AlertsView(_bridge([]))
        header = view.table.horizontalHeader()
        assert (header.sectionResizeMode(view.ACTION_COLUMN)
                == QHeaderView.ResizeMode.Fixed)
        assert (header.sectionResizeMode(view.CLASSIFICATION_COLUMN)
                == QHeaderView.ResizeMode.Stretch)
        view.resize(1800, 600)
        view.show()
        QApplication.processEvents()
        assert view.table.columnWidth(view.ACTION_COLUMN) == 130
        destroy(view)


class TestPermissionBanner:
    def test_banner_does_not_absorb_spare_height(self, qapp, tmp_path, monkeypatch):
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
        from soc_copilot.phase4.ui.main_window import MainWindow
        monkeypatch.setattr(
            ControllerBridge, "get_permission_status",
            lambda self: {"has_permission": False},
        )
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        w.resize(1500, 950)
        w.show()
        w._on_nav_changed(1)  # short page: plenty of spare height
        QApplication.processEvents()
        banner = w.permission_banner
        assert banner.height() <= banner.sizeHint().height() + 2
        assert banner.height() < 100
        destroy(w)


class TestDeadCodeRemoved:
    def test_legacy_dashboard_module_gone(self):
        assert importlib.util.find_spec("soc_copilot.phase4.ui.dashboard") is None

    def test_package_exports_current_dashboard(self):
        from soc_copilot.phase4 import ui
        from soc_copilot.phase4.ui.dashboard_v2 import Dashboard
        assert ui.Dashboard is Dashboard
