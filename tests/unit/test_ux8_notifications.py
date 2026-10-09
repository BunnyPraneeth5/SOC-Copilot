"""Tests for UX-8: tray notifications for new P0/P1 alerts with mute."""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from soc_copilot.phase4.ui.notifications import AlertNotifier
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "notify.ini"), QSettings.Format.IniFormat)


class FakeBridge(QObject):
    resultsUpdated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.results = []

    def get_all_results(self):
        return list(self.results)

    def add(self, batch_id, *alerts):
        self.results.append(SimpleNamespace(batch_id=batch_id, alerts=list(alerts)))


def _alert(alert_id, priority, classification="Malware", ip="10.0.0.5"):
    return SimpleNamespace(alert_id=alert_id, priority=priority,
                           classification=classification, source_ip=ip)


@pytest.fixture()
def bridge(qapp):
    b = FakeBridge()
    yield b
    destroy(b)


@pytest.fixture()
def notifier(qapp, bridge, settings):
    n = AlertNotifier(bridge, settings=settings)
    n.shown = []
    n._show = lambda title, body, icon: n.shown.append((title, body, icon))
    yield n
    destroy(n)


class TestDetection:
    def test_existing_alerts_are_not_announced(self, qapp, bridge, settings):
        bridge.add("b1", _alert("a1", "P0-Critical"))
        n = AlertNotifier(bridge, settings=settings)
        n._show = lambda *a: pytest.fail("startup alerts announced")
        assert n.check_new_alerts() == []
        destroy(n)

    def test_new_p0_and_p1_announced_once(self, notifier, bridge):
        bridge.add("b1", _alert("a1", "P0-Critical"), _alert("a2", "P1-High"))
        assert len(notifier.check_new_alerts()) == 2
        assert len(notifier.shown) == 1  # one combined balloon
        assert notifier.check_new_alerts() == []
        assert len(notifier.shown) == 1

    def test_lower_priorities_ignored(self, notifier, bridge):
        bridge.add("b1", _alert("a1", "P2-Medium"), _alert("a2", "P4-Info"))
        assert notifier.check_new_alerts() == []
        assert notifier.shown == []

    def test_same_type_alerts_in_one_batch_counted_separately(self, notifier, bridge):
        bridge.add("b1", _alert(None, "P1-High"), _alert(None, "P1-High"))
        assert len(notifier.check_new_alerts()) == 2

    def test_results_updated_signal_triggers_check(self, notifier, bridge):
        bridge.add("b1", _alert("a1", "P0-Critical"))
        bridge.resultsUpdated.emit()
        assert len(notifier.shown) == 1

    def test_bridge_error_is_silent(self, notifier, bridge):
        def boom():
            raise RuntimeError("store unavailable")
        bridge.get_all_results = boom
        assert notifier.check_new_alerts() == []


class TestMessages:
    def test_single_alert_message(self):
        title, body, icon = AlertNotifier.format_message([
            {"priority": "P1-High", "classification": "Brute Force",
             "source_ip": "1.2.3.4"},
        ])
        assert title == "P1-High: Brute Force"
        assert "1.2.3.4" in body
        assert icon == QSystemTrayIcon.MessageIcon.Warning

    def test_combined_message_lists_most_severe_first(self):
        alerts = [
            {"priority": "P1-High", "classification": f"C{i}", "source_ip": "x"}
            for i in range(4)
        ] + [{"priority": "P0-Critical", "classification": "Ransomware",
              "source_ip": "y"}]
        title, body, icon = AlertNotifier.format_message(alerts)
        assert title == "5 new high-priority alerts"
        assert body.splitlines()[0].startswith("P0-Critical: Ransomware")
        assert "and 2 more" in body
        assert icon == QSystemTrayIcon.MessageIcon.Critical


class TestPreferences:
    def test_mute_suppresses_but_marks_seen(self, notifier, bridge):
        notifier.set_muted(True)
        bridge.add("b1", _alert("a1", "P0-Critical"))
        assert notifier.check_new_alerts() == []
        notifier.set_muted(False)
        # Muted alerts are not replayed on unmute
        assert notifier.check_new_alerts() == []
        assert notifier.shown == []

    def test_priority_toggle(self, notifier, bridge):
        notifier.set_priority_enabled("P1-High", False)
        bridge.add("b1", _alert("a1", "P1-High"), _alert("a2", "P0-Critical"))
        fresh = notifier.check_new_alerts()
        assert [a["priority"] for a in fresh] == ["P0-Critical"]

    def test_unknown_priority_rejected(self, notifier):
        with pytest.raises(ValueError):
            notifier.set_priority_enabled("P3-Low", True)

    def test_preferences_persist(self, qapp, bridge, settings):
        n = AlertNotifier(bridge, settings=settings)
        n.set_muted(True)
        n.set_priority_enabled("P1-High", False)
        destroy(n)
        fresh = QSettings(settings.fileName(), QSettings.Format.IniFormat)
        n2 = AlertNotifier(bridge, settings=fresh)
        assert n2.muted is True
        assert n2.priority_enabled("P1-High") is False
        assert n2.priority_enabled("P0-Critical") is True
        destroy(n2)

    def test_tray_menu_mute_syncs(self, notifier):
        changes = []
        notifier.preferences_changed.connect(lambda: changes.append(1))
        notifier._mute_action.setChecked(True)
        assert notifier.muted is True
        assert changes == [1]
        notifier.set_muted(False)
        assert notifier._mute_action.isChecked() is False

    def test_balloon_click_requests_alerts(self, notifier):
        hits = []
        notifier.open_alerts_requested.connect(lambda: hits.append(1))
        notifier.tray.messageClicked.emit()
        assert hits == [1]


class TestMainWindowIntegration:
    @pytest.fixture()
    def window(self, qapp, tmp_path, settings):
        from unittest.mock import Mock
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        w.notifier._settings = settings  # keep the real registry untouched
        yield w
        destroy(w)

    def test_window_owns_notifier(self, window):
        assert isinstance(window.notifier, AlertNotifier)
        assert window.config_panel.notifier is window.notifier
        assert window.config_panel._notifications_group.isEnabled()

    def test_settings_checkbox_mutes(self, window):
        panel = window.config_panel
        panel.notify_enabled_check.setChecked(False)
        assert window.notifier.muted is True
        assert not panel.notify_priority_checks["P0-Critical"].isEnabled()
        panel.notify_enabled_check.setChecked(True)
        assert window.notifier.muted is False

    def test_tray_mute_updates_settings_checkbox(self, window):
        window.notifier._mute_action.setChecked(True)
        assert window.config_panel.notify_enabled_check.isChecked() is False
        window.notifier.set_muted(False)
        assert window.config_panel.notify_enabled_check.isChecked() is True

    def test_priority_checkbox(self, window):
        window.config_panel.notify_priority_checks["P1-High"].setChecked(False)
        assert window.notifier.priority_enabled("P1-High") is False

    def test_balloon_click_opens_alerts(self, window):
        window.notifier.open_alerts_requested.emit()
        assert window.page_stack.currentIndex() == 1
