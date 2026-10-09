"""Tests for Clear logs: confirmation dialog, audited bridge action, views."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.controller.schemas import (
    AlertSummary, AnalysisResult, LogSummary,
)
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _result(batch="b1", n_logs=3, n_alerts=2):
    now = datetime(2026, 10, 9, 12, 0, 0)
    alerts = [
        AlertSummary(alert_id=f"{batch}-a{i}", priority="P1-High",
                     classification="Brute Force", confidence=0.9,
                     anomaly_score=0.5, risk_score=0.7, source_ip=f"10.0.0.{i}",
                     destination_ip="10.0.0.1", timestamp=now,
                     reasoning="r", suggested_action="s")
        for i in range(n_alerts)
    ]
    logs = [
        LogSummary(log_id=f"{batch}-l{i}", timestamp=now, classification="Benign",
                   confidence=0.8, risk_level="low", source_ip=f"10.0.0.{i}",
                   destination_ip="10.0.0.1", raw_log=f"line {i}", is_alert=False)
        for i in range(n_logs)
    ]
    return AnalysisResult(batch_id=batch, timestamp=now, alerts=alerts, logs=logs)


@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._pipeline = Mock()
    c.audit_logger = Mock()
    c.result_store.add(_result("b1"))
    c.result_store.add(_result("b2", n_logs=1, n_alerts=1))
    return c


class TestControllerAndBridge:
    def test_clear_results_counts_and_audits(self, controller):
        removed = controller.clear_results(actor="analyst-ui")
        assert removed == {"logs": 4, "alerts": 3}
        assert controller.result_store.get_all() == []
        controller.audit_logger.log_event.assert_called_once_with(
            actor="analyst-ui", action="results_cleared", reason="logs=4 alerts=3",
        )

    def test_bridge_requires_confirmation(self, qapp, controller):
        bridge = ControllerBridge(controller)
        with pytest.raises(PermissionError):
            bridge.clear_logs()
        assert len(controller.result_store.get_all()) == 2
        assert bridge.clear_logs(confirmed=True) == {"logs": 4, "alerts": 3}
        assert controller.result_store.get_all() == []
        destroy(bridge)


class TestAllLogsView:
    @pytest.fixture()
    def view(self, qapp, controller):
        from soc_copilot.phase4.ui.all_logs_view import AllLogsView
        bridge = ControllerBridge(controller)
        v = AllLogsView(bridge)
        yield v
        destroy(v)
        destroy(bridge)

    def test_cancel_keeps_logs(self, view, controller, monkeypatch):
        monkeypatch.setattr(view, "_confirm_clear", lambda logs, alerts: False)
        view._on_clear_logs()
        assert len(controller.result_store.get_all()) == 2
        assert view.table.rowCount() == 4

    def test_confirm_clears_everything(self, view, controller, monkeypatch):
        asked = []
        monkeypatch.setattr(
            view, "_confirm_clear",
            lambda logs, alerts: asked.append((logs, alerts)) or True,
        )
        view._on_clear_logs()
        assert asked == [(4, 3)]
        assert controller.result_store.get_all() == []
        assert view.table.rowCount() == 0
        assert not view.clear_btn.isEnabled()

    def test_nothing_to_clear_skips_dialog(self, view, controller, monkeypatch):
        controller.result_store.clear()
        view.refresh()
        monkeypatch.setattr(
            view, "_confirm_clear",
            lambda *a: pytest.fail("dialog shown with nothing to clear"),
        )
        view._on_clear_logs()

    def test_dialog_defaults_to_cancel_and_states_impact(self, view, monkeypatch):
        seen = {}

        def fake_exec(box):
            seen["default"] = box.defaultButton().text()
            seen["text"] = box.text()
            seen["info"] = box.informativeText()
            return 0  # closed without choosing "Clear logs"

        monkeypatch.setattr(QMessageBox, "exec", fake_exec)
        assert view._confirm_clear(4, 3) is False
        assert seen["default"] == "Cancel"
        assert "4 log entries" in seen["text"] and "3 alerts" in seen["text"]
        assert "will not be shown again" in seen["info"]
        assert "cannot be undone" in seen["info"]


class TestOtherViewsAfterClear:
    def test_alerts_view_drops_cleared_rows(self, qapp, controller):
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        bridge = ControllerBridge(controller)
        view = AlertsView(bridge)
        view.refresh()
        assert view.table.rowCount() == 3
        bridge.clear_logs(confirmed=True)
        view._incremental_refresh()
        assert view.table.rowCount() == 0
        assert view._alert_cache == {}
        destroy(view)
        destroy(bridge)
