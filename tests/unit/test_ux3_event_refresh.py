"""Tests for UX-3: event-driven refresh replacing polling timers."""

import threading
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge


SSHD_FAIL = (
    "Jan 18 02:56:{sec:02d} server sshd[123]: Failed password for root "
    "from 45.67.89.101 port 22 ssh2"
)


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._pipeline = Mock()
    c._text_log_classifier = None
    c._flow_feature_names = set()  # no text line routes to the ML pipeline
    return c


def _batch(n=3):
    return [
        {"raw_line": SSHD_FAIL.format(sec=i), "source": "test"}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Controller listener plumbing
# ---------------------------------------------------------------------------

class TestControllerListeners:
    def test_listener_called_per_stored_result(self, controller):
        calls = []
        controller.add_result_listener(calls.append)
        controller.process_batch(_batch())
        assert len(calls) == 1
        assert calls[0] is not None  # the AnalysisResult

    def test_no_notify_when_nothing_stored(self, controller):
        calls = []
        controller.add_result_listener(calls.append)
        controller.process_batch([])  # no raw lines -> returns None
        assert calls == []

    def test_listener_exception_does_not_break_batch(self, controller):
        def boom(_result):
            raise RuntimeError("listener exploded")

        good = []
        controller.add_result_listener(boom)
        controller.add_result_listener(good.append)
        result = controller.process_batch(_batch())
        assert result is not None
        assert len(good) == 1

    def test_clear_results_notifies_none(self, controller):
        calls = []
        controller.add_result_listener(calls.append)
        controller.process_batch(_batch())
        controller.clear_results()
        assert calls[-1] is None

    def test_remove_result_listener(self, controller):
        calls = []
        controller.add_result_listener(calls.append)
        controller.remove_result_listener(calls.append)
        controller.process_batch(_batch())
        assert calls == []


# ---------------------------------------------------------------------------
# Bridge debounce + request_refresh
# ---------------------------------------------------------------------------

class TestBridgeDebounce:
    def test_burst_coalesces_to_one_emit(self, qapp, controller):
        bridge = ControllerBridge(controller)
        received = []
        bridge.resultsUpdated.connect(lambda: received.append(1))

        def worker():
            for _ in range(5):
                # invoke the registered listener from a worker thread
                for cb in controller._result_listeners:
                    cb(object())

        t = threading.Thread(target=worker)
        t.start()
        t.join()
        # poll until delivered (queued slot + 250 ms throttle under load)
        for _ in range(50):
            if received:
                break
            QTest.qWait(50)
        QTest.qWait(300)  # let any extra fires land
        assert received == [1]
        bridge.deleteLater()

    def test_no_emit_without_activity(self, qapp, controller):
        bridge = ControllerBridge(controller)
        received = []
        bridge.resultsUpdated.connect(lambda: received.append(1))
        QTest.qWait(400)
        assert received == []
        bridge.deleteLater()

    def test_request_refresh_emits_immediately(self, qapp, controller):
        bridge = ControllerBridge(controller)
        received = []
        bridge.resultsUpdated.connect(lambda: received.append(1))
        bridge.request_refresh()
        assert received == [1]  # synchronous — no event loop wait needed
        bridge.deleteLater()

    def test_process_batch_triggers_signal(self, qapp, controller):
        bridge = ControllerBridge(controller)
        received = []
        bridge.resultsUpdated.connect(lambda: received.append(1))
        controller.process_batch(_batch())
        QTest.qWait(500)
        assert received
        bridge.deleteLater()

    def test_mock_controller_without_listener_api(self, qapp):
        """Mocked controllers lacking add_result_listener must not break."""
        bridge = ControllerBridge(Mock(spec=object))
        bridge.deleteLater()


# ---------------------------------------------------------------------------
# Views: no polling timers, refresh via signal, dirty-on-show
# ---------------------------------------------------------------------------

def _active_poll_timers(widget):
    return [
        t for t in widget.findChildren(QTimer)
        if t.isActive() and not t.isSingleShot()
    ]


class TestViewsEventDriven:
    def test_alerts_view_no_poll_timer(self, qapp, controller):
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        bridge = ControllerBridge(controller)
        view = AlertsView(bridge)
        assert _active_poll_timers(view) == []
        view.deleteLater()
        bridge.deleteLater()

    def test_all_logs_view_no_poll_timer(self, qapp, controller):
        from soc_copilot.phase4.ui.all_logs_view import AllLogsView
        bridge = ControllerBridge(controller)
        view = AllLogsView(bridge)
        assert _active_poll_timers(view) == []
        view.deleteLater()
        bridge.deleteLater()

    def test_dashboard_no_poll_timer(self, qapp, controller):
        from soc_copilot.phase4.ui.dashboard_v2 import Dashboard
        bridge = ControllerBridge(controller)
        dash = Dashboard(bridge)
        assert _active_poll_timers(dash) == []
        dash.deleteLater()
        bridge.deleteLater()

    def test_hidden_view_defers_then_refreshes_on_show(self, qapp, controller):
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        bridge = ControllerBridge(controller)
        view = AlertsView(bridge)
        view._incremental_refresh = Mock()
        view.refresh = Mock()
        view._on_results_updated()  # hidden -> dirty
        view._incremental_refresh.assert_not_called()
        assert view._dirty is True
        view.show()  # showEvent should refresh
        assert view._dirty is False
        view.refresh.assert_called_once()
        view.deleteLater()
        bridge.deleteLater()

    def test_mainwindow_single_status_timer(self, qapp, tmp_path):
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        # exactly one periodic timer driving status (created parentless,
        # so findChildren() can't see it — check the attribute directly)
        timer = w.status_timer
        assert isinstance(timer, QTimer)
        assert timer.isActive() and timer.interval() == 5000
        # child status widgets no longer own polling timers
        assert getattr(w.sidebar, "poll_timer", None) is None
        assert getattr(w.system_status_bar, "poll_timer", None) is None
        w.deleteLater()

    def test_nav_switch_refreshes_target_page(self, qapp, tmp_path):
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        w.dashboard.refresh = Mock()
        w._on_nav_changed(0)
        w.dashboard.refresh.assert_called()
        w.deleteLater()
