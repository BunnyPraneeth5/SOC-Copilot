"""Tests for UX-5: alert triage status (New/In progress/Resolved/False positive)."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMenu

from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.phase4.controller.result_store import (
    ResultStore, TRIAGE_STATUSES,
)
from soc_copilot.phase4.controller.schemas import (
    AlertSummary, AnalysisResult, PipelineStats,
)
from soc_copilot.phase4.ui.alerts_view import AlertsView
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _result(batch_id="b1", alert_id="ML-0001"):
    return AnalysisResult(
        batch_id=batch_id,
        timestamp=datetime(2026, 7, 10, 14, 0, 0),
        alerts=[
            AlertSummary(
                alert_id=alert_id,
                priority="P0-Critical",
                classification="BruteForce",
                confidence=0.9,
                anomaly_score=0.8,
                risk_score=0.9,
                source_ip="45.67.89.101",
                destination_ip="10.0.0.1",
                timestamp=datetime(2026, 7, 10, 14, 0, 0),
                reasoning="r",
                suggested_action="a",
            )
        ],
        logs=[],
        stats=PipelineStats(
            total_records=1, processed_records=1, alerts_generated=1,
            risk_distribution={}, classification_distribution={},
            processing_time=0.0,
        ),
        raw_count=1,
    )


# ---------------------------------------------------------------------------
# ResultStore
# ---------------------------------------------------------------------------

class TestResultStoreTriage:
    def test_default_none(self):
        store = ResultStore()
        assert store.get_triage("x") is None
        assert store.get_triage_map() == {}

    def test_set_get_map(self):
        store = ResultStore()
        store.set_triage("a1", "Resolved", actor="me", note="done")
        entry = store.get_triage("a1")
        assert entry["status"] == "Resolved"
        assert entry["updated_by"] == "me"
        assert entry["note"] == "done"
        assert store.get_triage_map() == {"a1": "Resolved"}

    def test_invalid_status(self):
        store = ResultStore()
        with pytest.raises(ValueError):
            store.set_triage("a1", "Bogus")

    def test_persistence_round_trip(self, tmp_path):
        db = tmp_path / "r.db"
        s1 = ResultStore(db_path=db)
        s1.add(_result())
        s1.set_triage("ML-0001", "In progress")
        s2 = ResultStore(db_path=db)
        assert s2.get_triage("ML-0001")["status"] == "In progress"

    def test_orphan_triage_dropped_on_load(self, tmp_path):
        db = tmp_path / "r.db"
        s1 = ResultStore(db_path=db)
        s1.add(_result())
        s1.set_triage("ML-0001", "Resolved")
        s1.set_triage("ML-ORPHAN", "Resolved")  # no such alert stored
        s2 = ResultStore(db_path=db)
        assert s2.get_triage("ML-ORPHAN") is None
        assert s2.get_triage("ML-0001")["status"] == "Resolved"

    def test_triage_pruned_with_results(self, tmp_path):
        db = tmp_path / "r.db"
        store = ResultStore(max_results=1, db_path=db)
        store.add(_result("b1", "ML-AAA"))
        store.set_triage("ML-AAA", "Resolved")
        store.add(_result("b2", "ML-BBB"))  # evicts b1
        assert store.get_triage("ML-AAA") is None  # in-memory prune
        s2 = ResultStore(max_results=1, db_path=db)
        assert s2.get_triage("ML-AAA") is None     # db prune persisted
        assert s2.get_triage("ML-BBB") is None

    def test_clear_wipes_triage(self, tmp_path):
        db = tmp_path / "r.db"
        store = ResultStore(db_path=db)
        store.add(_result())
        store.set_triage("ML-0001", "Resolved")
        store.clear()
        assert store.get_triage("ML-0001") is None
        s2 = ResultStore(db_path=db)
        assert s2.get_triage_map() == {}


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._pipeline = Mock()
    c._text_log_classifier = None
    c._flow_feature_names = set()
    c.result_store.add(_result())
    return c


class TestControllerTriage:
    def test_set_get_and_audit(self, controller):
        audit = Mock()
        controller.audit_logger = audit
        calls = []
        controller.add_result_listener(calls.append)
        controller.set_alert_status("ML-0001", "In progress")
        assert controller.get_alert_status("ML-0001") == "In progress"
        audit.log_event.assert_called_once()
        assert audit.log_event.call_args.kwargs["action"] == "triage_in_progress"
        assert calls == [None]  # listeners notified (None = no new result)

    def test_invalid_status(self, controller):
        with pytest.raises(ValueError):
            controller.set_alert_status("ML-0001", "Nope")

    def _feedback(self, tmp_path):
        from soc_copilot.phase2.feedback.store import FeedbackStore
        store = FeedbackStore(str(tmp_path / "fb.db"))
        store.initialize()
        return store

    def test_reject_marks_false_positive(self, controller, tmp_path):
        controller.feedback_store = self._feedback(tmp_path)
        controller.submit_feedback("ML-0001", "reject")
        assert controller.get_alert_status("ML-0001") == "False positive"

    def test_accept_on_new_marks_in_progress(self, controller, tmp_path):
        controller.feedback_store = self._feedback(tmp_path)
        controller.submit_feedback("ML-0001", "accept")
        assert controller.get_alert_status("ML-0001") == "In progress"

    def test_accept_on_resolved_keeps_resolved(self, controller, tmp_path):
        controller.feedback_store = self._feedback(tmp_path)
        controller.set_alert_status("ML-0001", "Resolved")
        controller.submit_feedback("ML-0001", "accept")
        assert controller.get_alert_status("ML-0001") == "Resolved"

    def test_reclassify_no_status_change(self, controller, tmp_path):
        controller.feedback_store = self._feedback(tmp_path)
        controller.set_alert_status("ML-0001", "Resolved")
        controller.submit_feedback("ML-0001", "reclassify", label="DDoS")
        assert controller.get_alert_status("ML-0001") == "Resolved"


# ---------------------------------------------------------------------------
# AlertsView
# ---------------------------------------------------------------------------

def _view(qapp, tmp_path):
    controller = AppController(str(tmp_path / "models"))
    controller._pipeline = Mock()
    bridge = ControllerBridge(controller)
    return AlertsView(bridge), bridge, controller


class TestAlertsViewTriage:
    def test_status_column(self, qapp, tmp_path):
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result())
        ctrl.set_alert_status("ML-0001", "In progress")
        view.refresh()
        item = view.table.item(0, AlertsView.STATUS_COLUMN)
        assert item.text() == "In progress"
        destroy(view); destroy(bridge)

    def test_open_filter_hides_resolved(self, qapp, tmp_path):
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result("b1", "ML-AAA"))
        ctrl.result_store.add(_result("b2", "ML-BBB"))
        ctrl.set_alert_status("ML-BBB", "Resolved")
        view.refresh()
        view.status_filter.setCurrentText("Open")
        assert view.table.rowCount() == 1
        view.status_filter.setCurrentText("Resolved")
        assert view.table.rowCount() == 1
        assert (
            view.table.item(0, AlertsView.STATUS_COLUMN).text() == "Resolved"
        )
        destroy(view); destroy(bridge)

    def test_status_filter_combines_with_priority(self, qapp, tmp_path):
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result("b1", "ML-AAA"))
        ctrl.set_alert_status("ML-AAA", "Resolved")
        view.refresh()
        view.status_filter.setCurrentText("Resolved")
        view.priority_filter.setCurrentText("Critical")
        assert view.table.rowCount() == 1  # both match
        view.priority_filter.setCurrentText("Low")
        assert view.table.rowCount() == 0  # status matches, priority doesn't
        destroy(view); destroy(bridge)

    def test_open_counter(self, qapp, tmp_path):
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result("b1", "ML-AAA"))
        ctrl.result_store.add(_result("b2", "ML-BBB"))
        ctrl.set_alert_status("ML-BBB", "False positive")
        view.refresh()
        assert "Open: 1" in view.counter_label.text()
        destroy(view); destroy(bridge)

    def test_context_menu_sets_status(self, qapp, tmp_path):
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result())
        view.refresh()
        menu = view._build_row_context_menu(0)
        assert isinstance(menu, QMenu)
        submenu = next(
            a.menu() for a in menu.actions()
            if a.menu() and a.text() == "Set status"
        )
        labels = [a.text() for a in submenu.actions()]
        assert labels == list(TRIAGE_STATUSES)
        submenu.actions()[2].trigger()  # "Resolved"
        assert ctrl.get_alert_status("ML-0001") == "Resolved"
        assert view.table.item(0, AlertsView.STATUS_COLUMN).text() == "Resolved"
        destroy(menu)
        destroy(view); destroy(bridge)

    def test_one_action_button_per_row(self, qapp, tmp_path):
        """Rebuilds must not leak cell widgets (UX-5 regression)."""
        from PyQt6.QtWidgets import QPushButton
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result("b1", "ML-AAA"))
        ctrl.result_store.add(_result("b2", "ML-BBB"))
        view.refresh()
        view._set_row_status(0, "Resolved")  # triggers a rebuild path
        view.status_filter.setCurrentText("Open")
        view.status_filter.setCurrentText("All")

        # Leaked cell widgets stay children of the viewport — count all.
        # (Avoid show()/paint here; offscreen it adds nothing and, under
        # full-suite load, painted deleted widgets reproducibly crashed.)
        viewport_buttons = view.table.viewport().findChildren(QPushButton)
        assert len(viewport_buttons) == view.table.rowCount()
        for row in range(view.table.rowCount()):
            btn = view.table.cellWidget(row, AlertsView.ACTION_COLUMN)
            assert isinstance(btn, QPushButton)
            for col in range(view.table.columnCount()):
                if col == AlertsView.ACTION_COLUMN:
                    continue
                assert view.table.cellWidget(row, col) is None
        destroy(view); destroy(bridge)

    def test_columns_after_insert(self, qapp, tmp_path):
        """Double-click + row click still hit the right columns/ids."""
        view, bridge, ctrl = _view(qapp, tmp_path)
        ctrl.result_store.add(_result())
        view.refresh()
        row = 0
        # classification cell carries the real alert_id
        class_item = view.table.item(row, AlertsView.CLASSIFICATION_COLUMN)
        assert class_item.data(Qt.ItemDataRole.UserRole) == "ML-0001"
        # source ip for investigation
        src = view.table.item(row, AlertsView.SOURCE_IP_COLUMN)
        assert src.text() == "45.67.89.101"
        # row click emits alert_id
        emitted = []
        view.alert_selected.connect(lambda b, a: emitted.append(a))
        view._on_row_clicked(class_item)
        assert emitted == ["ML-0001"]
        destroy(view); destroy(bridge)


# ---------------------------------------------------------------------------
# AlertDetailsPanel
# ---------------------------------------------------------------------------

class TestDetailsPanelTriage:
    def _panel(self, qapp, tmp_path):
        ctrl = AppController(str(tmp_path / "models"))
        ctrl._pipeline = Mock()
        ctrl.result_store.add(_result())
        bridge = ControllerBridge(ctrl)
        from soc_copilot.phase4.ui.alert_details import AlertDetailsPanel
        return AlertDetailsPanel(bridge), bridge, ctrl

    def test_status_badge_and_combo(self, qapp, tmp_path):
        panel, bridge, ctrl = self._panel(qapp, tmp_path)
        panel.show_alert("b1", alert_id="ML-0001")
        assert panel._status_badge.text().strip() == "New"
        panel._status_combo.setCurrentText("Resolved")
        assert ctrl.get_alert_status("ML-0001") == "Resolved"
        assert panel._status_badge.text().strip() == "Resolved"
        destroy(panel); destroy(bridge)

    def test_feedback_reject_updates_badge(self, qapp, tmp_path):
        panel, bridge, ctrl = self._panel(qapp, tmp_path)
        from soc_copilot.phase2.feedback.store import FeedbackStore
        store = FeedbackStore(str(tmp_path / "fb.db"))
        store.initialize()
        ctrl.feedback_store = store
        panel.show_alert("b1", alert_id="ML-0001")
        panel._submit_feedback("ML-0001", "reject")
        assert panel._status_badge.text().strip() == "False positive"
        assert panel._status_combo.currentText() == "False positive"
        destroy(panel); destroy(bridge)
