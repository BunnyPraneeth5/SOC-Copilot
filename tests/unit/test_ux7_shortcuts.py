"""Tests for UX-7: keyboard shortcuts + IP context menus."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QMenu, QTableWidgetItem,
)

from soc_copilot.phase4.ui.alerts_view import AlertsView
from soc_copilot.phase4.ui.main_window import MainWindow
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])




def _alert(i=1, ip="45.67.89.10", dip="10.0.0.99"):
    return SimpleNamespace(
        alert_id=f"ML-{i:04d}", priority="P0-Critical",
        classification="DDoS", timestamp=datetime(2026, 7, 10, 14, 30, i),
        source_ip=ip, destination_ip=dip, confidence=0.9,
        anomaly_score=0.8, risk_score=0.85, reasoning="r",
        suggested_action="block",
    )


def _bridge(alerts):
    bridge = Mock()
    bridge.get_all_results.return_value = [
        SimpleNamespace(batch_id="b1", alerts=alerts)
    ]
    bridge.get_latest_alerts.return_value = [
        SimpleNamespace(batch_id="b1", alerts=alerts)
    ]
    bridge.get_triage_map.return_value = {}
    bridge.get_alert_status.side_effect = lambda a: "New"
    bridge.is_investigation_in_flight.return_value = False
    bridge.get_stats.return_value = {"pipeline_loaded": True}
    bridge.get_logs.return_value = []
    bridge.get_latest_logs.return_value = []
    bridge.get_feedback_for_alert.return_value = []
    bridge.get_result_by_id.return_value = None
    return bridge


def _trigger_shortcut(window, key_str):
    """Fire the window QShortcut bound to `key_str`.

    QTest.keyClick→QShortcutMap is flaky/crashing under the offscreen
    platform once many windows have been created in a session, so tests
    verify the shortcut exists with the right key and emit its `activated`
    signal directly (which exercises the real binding + slot).
    """
    from PyQt6.QtGui import QKeySequence, QShortcut
    for sc in window.findChildren(QShortcut):
        if sc.key() == QKeySequence(key_str):
            assert sc.context() == Qt.ShortcutContext.WindowShortcut
            sc.activated.emit()
            return True
    raise AssertionError(f"no QShortcut bound to {key_str}")


class TestWindowShortcuts:
    def _window(self, qapp):
        bridge = _bridge([_alert(i) for i in range(3)])
        w = MainWindow(bridge)
        return w, bridge

    def test_ctrl2_goes_to_alerts(self, qapp):
        w, _ = self._window(qapp)
        assert _trigger_shortcut(w, "Ctrl+2")
        assert w.page_stack.currentIndex() == 1
        destroy(w)

    def test_ctrlf_focuses_search(self, qapp):
        w, _ = self._window(qapp)
        w.show()
        QTest.qWaitForWindowExposed(w)
        w.activateWindow()
        assert _trigger_shortcut(w, "Ctrl+F")
        assert w.page_stack.currentIndex() == 1
        assert QApplication.focusWidget() is w.alerts_view.search_box
        destroy(w)

    def test_slash_in_editor_types_normally(self, qapp):
        w, _ = self._window(qapp)
        w.show()
        w._on_nav_changed(1)
        w.alerts_view.search_box.setFocus()
        QTest.keyClick(w.alerts_view.search_box, Qt.Key.Key_Slash)
        assert w.alerts_view.search_box.text() == "/"
        destroy(w)

    def test_slash_opens_search_when_not_typing(self, qapp):
        w, _ = self._window(qapp)
        w.show()
        QTest.keyClick(w, Qt.Key.Key_Slash)
        assert w.page_stack.currentIndex() == 1
        destroy(w)

    def test_f5_requests_refresh(self, qapp):
        w, _ = self._window(qapp)
        fired = []
        w.bridge.resultsUpdated.connect(lambda: fired.append(1))
        assert _trigger_shortcut(w, "F5")
        assert fired == [1]  # bridge.request_refresh() emits immediately
        destroy(w)

    def test_escape_closes_drawer_then_backs_out(self, qapp):
        w, _ = self._window(qapp)
        w.show()
        w.report_drawer.show_loading("1.2.3.4")
        assert _trigger_shortcut(w, "Escape")
        assert not w.report_drawer.isVisible()
        w.page_stack.setCurrentIndex(2)
        assert _trigger_shortcut(w, "Escape")
        assert w.page_stack.currentIndex() == 1
        destroy(w)

    def test_f1_opens_help(self, qapp, monkeypatch):
        w, _ = self._window(qapp)
        opened = []
        monkeypatch.setattr(QDialog, "exec",
                            lambda self_: opened.append(self_) or 0)
        assert _trigger_shortcut(w, "F1")
        assert len(opened) == 1
        assert opened[0].windowTitle() == "Keyboard Shortcuts"
        destroy(opened[0])
        destroy(w)


class TestTableShortcuts:
    def _view(self, qapp, n=3):
        bridge = _bridge([_alert(i) for i in range(n)])
        return AlertsView(bridge), bridge

    def _click(self, view, key):
        QTest.keyClick(view.table, key)

    def test_jk_move_selection(self, qapp):
        view, _ = self._view(qapp)
        view.table.setCurrentCell(0, 0)
        self._click(view, Qt.Key.Key_J)
        assert view.table.currentRow() == 1
        self._click(view, Qt.Key.Key_K)
        assert view.table.currentRow() == 0
        destroy(view)

    def test_i_investigates(self, qapp):
        view, bridge = self._view(qapp)
        view.table.setCurrentCell(0, 0)
        self._click(view, Qt.Key.Key_I)
        bridge.investigate_target.assert_called_once_with("45.67.89.10")
        destroy(view)

    def test_a_and_r_feedback(self, qapp):
        view, bridge = self._view(qapp)
        view.table.setCurrentCell(0, 0)
        self._click(view, Qt.Key.Key_A)
        bridge.submit_feedback.assert_called_with("ML-0002", "accept")
        self._click(view, Qt.Key.Key_R)
        bridge.submit_feedback.assert_called_with("ML-0002", "reject")
        destroy(view)

    def test_status_keys(self, qapp):
        view, bridge = self._view(qapp)
        view.table.setCurrentCell(0, 0)
        self._click(view, Qt.Key.Key_3)
        bridge.set_alert_status.assert_called_with("ML-0002", "Resolved")
        self._click(view, Qt.Key.Key_1)
        bridge.set_alert_status.assert_called_with("ML-0002", "New")
        destroy(view)

    def test_enter_opens_details(self, qapp):
        view, _ = self._view(qapp)
        view.table.setCurrentCell(1, 0)
        emitted = []
        view.alert_selected.connect(lambda b, a: emitted.append(a))
        self._click(view, Qt.Key.Key_Return)
        assert emitted == ["ML-0001"]
        destroy(view)

    def test_feedback_error_does_not_crash(self, qapp):
        view, bridge = self._view(qapp)
        bridge.submit_feedback.side_effect = RuntimeError("no store")
        view.table.setCurrentCell(0, 0)
        self._click(view, Qt.Key.Key_A)
        destroy(view)


class TestContextMenu:
    def _menu_actions(self, menu):
        texts = []
        for a in menu.actions():
            texts.append(a.text())
            if a.menu():
                texts.extend(s.text() for s in a.menu().actions())
        return texts

    def test_ip_submenus_and_items(self, qapp):
        view, _ = TestTableShortcuts._view(self, qapp)
        view.refresh()
        menu = view._build_row_context_menu(0)
        texts = self._menu_actions(menu)
        for expected in ("45.67.89.10", "10.0.0.99", "Set status",
                         "Investigate", "Copy IP",
                         "Filter alerts by this IP", "Show logs for this IP",
                         "Copy alert ID", "Open details", "Resolved"):
            assert expected in texts, expected
        destroy(menu)
        destroy(view)

    def test_copy_ip(self, qapp):
        view, _ = TestTableShortcuts._view(self, qapp)
        view.refresh()
        menu = view._build_row_context_menu(0)
        submenu = menu.actions()[0].menu()  # source IP
        for a in submenu.actions():
            if a.text() == "Copy IP":
                a.trigger()
        assert QApplication.clipboard().text() == "45.67.89.10"
        destroy(menu)
        destroy(view)

    def test_filter_by_ip_sets_search(self, qapp):
        view, _ = TestTableShortcuts._view(self, qapp)
        view.refresh()
        menu = view._build_row_context_menu(0)
        submenu = menu.actions()[0].menu()
        for a in submenu.actions():
            if a.text() == "Filter alerts by this IP":
                a.trigger()
        assert view.search_box.text() == "45.67.89.10"
        assert view.table.rowCount() == 1
        destroy(menu)
        destroy(view)

    def test_show_logs_signal(self, qapp):
        view, _ = TestTableShortcuts._view(self, qapp)
        view.refresh()
        got = []
        view.show_logs_requested.connect(got.append)
        menu = view._build_row_context_menu(0)
        submenu = menu.actions()[0].menu()
        for a in submenu.actions():
            if a.text() == "Show logs for this IP":
                a.trigger()
        assert got == ["45.67.89.10"]
        destroy(menu)
        destroy(view)

    def test_dest_ip_investigate(self, qapp):
        view, bridge = TestTableShortcuts._view(self, qapp)
        view.refresh()
        menu = view._build_row_context_menu(0)
        dest_menu = menu.actions()[1].menu()  # destination IP submenu
        for a in dest_menu.actions():
            if a.text() == "Investigate":
                a.trigger()
        bridge.investigate_target.assert_called_with("10.0.0.99")
        destroy(menu)
        destroy(view)


class TestDetailsIpMenu:
    def test_signals_emitted(self, qapp):
        bridge = _bridge([_alert()])
        result = bridge.get_all_results.return_value[0]
        bridge.get_result_by_id.return_value = result
        from soc_copilot.phase4.ui.alert_details import AlertDetailsPanel
        panel = AlertDetailsPanel(bridge)
        panel.show_alert("b1", alert_id="ML-0001")

        got = {"inv": [], "flt": [], "logs": []}
        panel.investigate_requested.connect(got["inv"].append)
        panel.filter_alerts_requested.connect(got["flt"].append)
        panel.show_logs_requested.connect(got["logs"].append)

        # Trigger the menu builder directly at a point
        captured = []
        orig_exec = QMenu.exec
        try:
            QMenu.exec = lambda self_, *a: captured.append(self_) or 0
            panel._show_ip_menu("45.67.89.10", panel.rect().center())
        finally:
            QMenu.exec = orig_exec
        menu = captured[0]
        labels = [a.text() for a in menu.actions()]
        assert labels[:4] == [
            "Investigate", "Copy IP",
            "Filter alerts by this IP", "Show logs for this IP",
        ]
        menu.actions()[0].trigger()
        menu.actions()[2].trigger()
        menu.actions()[3].trigger()
        assert got["inv"] == ["45.67.89.10"]
        assert got["flt"] == ["45.67.89.10"]
        assert got["logs"] == ["45.67.89.10"]
        destroy(menu)
        destroy(panel)

    def test_mainwindow_wires_signals(self, qapp):
        bridge = _bridge([_alert()])
        w = MainWindow(bridge)
        # details signals reach the same handlers as the table menu
        w.details_panel.show_logs_requested.emit("8.8.8.8")
        assert w.page_stack.currentIndex() == 4
        assert w.all_logs_view.search_box.text() == "8.8.8.8"
        w.details_panel.filter_alerts_requested.emit("9.9.9.9")
        assert w.page_stack.currentIndex() == 1
        assert w.alerts_view.search_box.text() == "9.9.9.9"
        destroy(w)
