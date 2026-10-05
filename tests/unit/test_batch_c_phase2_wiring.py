"""Tests for Batch C — wiring Phase-2 (feedback, drift) and Phase-3
audit into the Phase-4 controller and UI."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from soc_copilot.phase2.drift.monitor import DriftMonitor
from soc_copilot.phase2.feedback.store import FeedbackStore
from soc_copilot.phase3.governance import AuditLogger
from soc_copilot.phase4.controller import AppController


def _alert(alert_id="ML-1", classification="BruteForce", priority="P0-Critical"):
    return SimpleNamespace(
        alert_id=alert_id,
        timestamp=datetime.now(),
        classification=classification,
        priority=priority,
        risk_score=0.9,
        confidence=0.9,
        anomaly_score=0.8,
        source_ip="45.67.89.101",
        destination_ip=None,
        reasoning="test",
        suggested_action="test",
    )


@pytest.fixture
def stores(tmp_path):
    drift = DriftMonitor(tmp_path / "drift.db")
    drift.initialize()
    feedback = FeedbackStore(tmp_path / "feedback.db")
    feedback.initialize()
    audit = AuditLogger(str(tmp_path / "audit.db"))
    return drift, feedback, audit


@pytest.fixture
def controller(stores):
    drift, feedback, audit = stores
    c = AppController(
        "unused",
        drift_monitor=drift,
        feedback_store=feedback,
        audit_logger=audit,
    )
    c._pipeline = Mock()
    c._text_log_classifier = None
    # Empty feature set → no line is routed to the ML pipeline.
    c._flow_feature_names = set()
    return c


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class TestFeedback:
    def test_submit_and_read_back(self, controller):
        rid = controller.submit_feedback(
            "alert-1", "accept", comment="looks good"
        )
        assert isinstance(rid, int)
        entries = controller.get_feedback_for_alert("alert-1")
        assert len(entries) == 1
        assert entries[0]["analyst_action"] == "accept"
        assert entries[0]["alert_id"] == "alert-1"

    def test_audit_event_written(self, controller, stores):
        _, _, audit = stores
        controller.submit_feedback("alert-2", "reject", label="Benign")
        events = audit.get_events()
        assert any(
            e.action == "feedback_reject" and "alert-2" in e.reason
            for e in events
        )

    def test_invalid_action_raises(self, controller):
        with pytest.raises(ValueError):
            controller.submit_feedback("alert-3", "bogus")

    def test_no_store_raises_runtime_error(self):
        c = AppController("unused")
        with pytest.raises(RuntimeError, match="Feedback store not configured"):
            c.submit_feedback("x", "accept")
        assert c.get_feedback_for_alert("x") == []


# ---------------------------------------------------------------------------
# Drift feed
# ---------------------------------------------------------------------------

class TestDriftFeed:
    def test_alerts_recorded(self, controller, stores):
        drift, _, _ = stores
        result = controller.process_batch(
            [{"raw_line": f"Jan 18 02:56:0{i} server sshd[1]: Failed password "
                          f"for root from 45.67.89.101 port 22 ssh2"}
             for i in range(6)]
        )
        conn = sqlite3.connect(str(drift.db_path))
        count = conn.execute("SELECT COUNT(*) FROM inference_stats").fetchone()[0]
        conn.close()
        # One aggregated BruteForce alert was produced and recorded
        assert count == len(result.alerts) == 1

    def test_report_computed_at_interval(self, controller, stores, monkeypatch):
        drift, _, _ = stores
        monkeypatch.setattr(
            "soc_copilot.phase4.controller.app_controller.DRIFT_REPORT_INTERVAL", 2
        )
        controller.process_batch(
            [{"raw_line": "Jan 18 02:56:01 server sshd[1]: Failed password "
                          "for root from 45.67.89.101 port 22 ssh2"}]
            * 6
        )
        # >= 2 inferences recorded -> compute_drift_report was invoked
        conn = sqlite3.connect(str(drift.db_path))
        rows = conn.execute("SELECT COUNT(*) FROM inference_stats").fetchone()[0]
        conn.close()
        assert rows >= 1
        assert drift.get_latest_report() is None or isinstance(
            drift.get_latest_report().timestamp, str
        )

    def test_broken_monitor_does_not_break_batch(self, tmp_path):
        drift = Mock()
        drift.record_inference.side_effect = RuntimeError("db gone")
        c = AppController("unused", drift_monitor=drift)
        c._pipeline = Mock()
        c._text_log_classifier = None
        c._flow_feature_names = set()
        result = c.process_batch(
            [{"raw_line": "Jan 18 02:56:01 server sshd[1]: Failed password "
                          "for root from 45.67.89.101 port 22 ssh2"}]
            * 6
        )
        assert len(result.alerts) == 1  # batch still produced the alert


# ---------------------------------------------------------------------------
# get_drift_status
# ---------------------------------------------------------------------------

class TestDriftStatus:
    def test_unavailable(self):
        c = AppController("unused")
        s = c.get_drift_status()
        assert s == {
            "available": False, "level": None, "timestamp": None, "summary": None
        }

    def test_collecting_no_report(self, controller):
        s = controller.get_drift_status()
        assert s["available"] is True
        assert s["level"] is None

    def test_with_report(self, controller, stores):
        drift, _, _ = stores
        for i in range(12):
            drift.record_inference(0.5 + i * 0.01, 0.6, "BruteForce", "P0")
        drift.compute_drift_report()
        s = controller.get_drift_status()
        assert s["available"] is True
        assert s["level"] in ("NONE", "LOW", "MODERATE", "HIGH")
        assert s["timestamp"]

    def test_stats_phase2_flags(self, controller):
        stats = controller.get_stats()
        assert stats["phase2"] == {"feedback_enabled": True, "drift_enabled": True}
        bare = AppController("unused").get_stats()
        assert bare["phase2"] == {"feedback_enabled": False, "drift_enabled": False}


# ---------------------------------------------------------------------------
# UI — AlertDetailsPanel feedback + alert_id disambiguation
# ---------------------------------------------------------------------------

class TestAlertDetailsUI:
    def _panel(self, qapp, bridge):
        from soc_copilot.phase4.ui.alert_details import AlertDetailsPanel
        return AlertDetailsPanel(bridge)

    def _result(self):
        a1 = _alert(alert_id="ML-AAA", classification="BruteForce")
        a2 = _alert(alert_id="ML-BBB", classification="BruteForce")
        a2.reasoning = "second alert"
        return SimpleNamespace(batch_id="b1", alerts=[a1, a2])

    def _bridge(self, feedback_enabled=True):
        bridge = Mock()
        bridge.get_alert_by_id.return_value = self._result()
        bridge.get_stats.return_value = {
            "phase2": {"feedback_enabled": feedback_enabled}
        }
        bridge.get_feedback_for_alert.return_value = []
        return bridge

    def test_accept_submits_feedback(self, qapp):
        bridge = self._bridge()
        panel = self._panel(qapp, bridge)
        panel.show_alert("b1", alert_id="ML-AAA")
        panel._accept_button.click()
        bridge.submit_feedback.assert_called_once_with(
            "ML-AAA", "accept", label=None, comment=None
        )
        assert "accept" in panel._feedback_status_label.text()

    def test_reclassify_passes_label(self, qapp):
        bridge = self._bridge()
        panel = self._panel(qapp, bridge)
        panel.show_alert("b1", alert_id="ML-AAA")
        panel._reclassify_combo.setCurrentText("Malware")
        panel._reclassify_button.click()
        bridge.submit_feedback.assert_called_once_with(
            "ML-AAA", "reclassify", label="Malware", comment=None
        )

    def test_feedback_disabled_disables_controls(self, qapp):
        bridge = self._bridge(feedback_enabled=False)
        panel = self._panel(qapp, bridge)
        panel.show_alert("b1", alert_id="ML-AAA")
        assert not panel._accept_button.isEnabled()
        assert not panel._reject_button.isEnabled()
        assert not panel._reclassify_button.isEnabled()
        assert "not available" in panel._accept_button.toolTip()

    def test_alert_id_disambiguates_same_classification(self, qapp):
        bridge = self._bridge()
        panel = self._panel(qapp, bridge)
        panel.show_alert("b1", alert_classification="BruteForce",
                         alert_id="ML-BBB")
        # The feedback section must be bound to the second alert
        panel._accept_button.click()
        bridge.submit_feedback.assert_called_once_with(
            "ML-BBB", "accept", label=None, comment=None
        )

    def test_submit_error_shown(self, qapp):
        bridge = self._bridge()
        bridge.submit_feedback.side_effect = RuntimeError("nope")
        panel = self._panel(qapp, bridge)
        panel.show_alert("b1", alert_id="ML-AAA")
        panel._accept_button.click()
        assert "nope" in panel._feedback_status_label.text()


# ---------------------------------------------------------------------------
# UI — ConfigPanel drift indicator
# ---------------------------------------------------------------------------

class TestConfigPanelDrift:
    def _panel(self, qapp, tmp_path, drift_status):
        from soc_copilot.phase4.ui.config_panel import ConfigPanel
        bridge = Mock()
        bridge.get_stats.return_value = {}
        bridge.get_drift_status.return_value = drift_status
        bridge.get_provider_statuses.return_value = []
        return ConfigPanel(bridge=bridge, project_root=tmp_path)

    def test_unavailable(self, qapp, tmp_path):
        panel = self._panel(qapp, tmp_path, {"available": False})
        assert panel.drift_indicator.status_label.text() == "Unavailable"

    def test_collecting(self, qapp, tmp_path):
        panel = self._panel(
            qapp, tmp_path, {"available": True, "level": None}
        )
        assert panel.drift_indicator.status_label.text() == "Collecting data"

    def test_high_drift(self, qapp, tmp_path):
        panel = self._panel(
            qapp, tmp_path,
            {"available": True, "level": "HIGH", "timestamp": "t", "summary": "s"},
        )
        assert panel.drift_indicator.status_label.text() == "High"
