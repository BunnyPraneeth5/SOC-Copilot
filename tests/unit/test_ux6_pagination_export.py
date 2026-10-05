"""Tests for UX-6: alerts pagination + CSV/JSON export."""

import csv
import io
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton

from soc_copilot.phase4.ui.alert_export import (
    EXPORT_FIELDS, alerts_to_csv, alerts_to_json,
)
from soc_copilot.phase4.ui.alerts_view import AlertsView


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _row(**over):
    row = {
        "timestamp": datetime(2026, 7, 10, 14, 0, 0),
        "priority": "P0-Critical", "status": "New",
        "classification": "DDoS", "source_ip": "1.2.3.4",
        "destination_ip": "10.0.0.1", "confidence": "0.90",
        "risk_score": 0.9, "anomaly_score": 0.8,
        "alert_id": "ML-1", "batch_id": "b1",
        "reasoning": "models agree", "suggested_action": "block",
    }
    row.update(over)
    return row


class TestAlertExport:
    def test_csv_header_and_rows(self):
        text = alerts_to_csv([_row(), _row()])
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0] == EXPORT_FIELDS
        assert len(rows) == 3
        assert rows[1][9] == "ML-1"  # alert_id column

    def test_csv_formula_injection_escaped(self):
        for payload in ("=cmd()", "+SUM(A1)", "-1", "@evil"):
            text = alerts_to_csv([_row(reasoning=payload)])
            rows = list(csv.reader(io.StringIO(text)))
            assert rows[1][11].startswith("'")

    def test_csv_special_chars_round_trip(self):
        messy = 'comma, "quote" and\nnewline'
        text = alerts_to_csv([_row(reasoning=messy)])
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[1][11] == messy

    def test_json_round_trip_iso_timestamps(self):
        text = alerts_to_json([_row()])
        data = json.loads(text)
        assert isinstance(data, list) and data[0]["alert_id"] == "ML-1"
        assert data[0]["timestamp"] == "2026-07-10T14:00:00"
        assert set(data[0]) == set(EXPORT_FIELDS)


# ---------------------------------------------------------------------------

def _view_250(qapp):
    """AlertsView over a fake bridge serving 250 alerts."""
    alerts = []
    for i in range(250):
        alerts.append(SimpleNamespace(
            alert_id=f"ML-{i:04d}",
            priority="P0-Critical" if i < 125 else "P2-Medium",
            classification=f"{'DDoS' if i % 2 else 'BruteForce'}-{i}",
            timestamp=datetime(2026, 7, 10) + timedelta(seconds=i),
            source_ip=f"10.0.{i // 256}.{i % 256}",
            destination_ip="10.0.0.1",
            confidence=0.9, risk_score=0.8, anomaly_score=0.7,
            reasoning="r", suggested_action="a",
        ))
    bridge = Mock()
    bridge.get_all_results.return_value = [
        SimpleNamespace(batch_id="b1", alerts=alerts)
    ]
    bridge.get_triage_map.return_value = {}
    bridge.get_alert_status.side_effect = lambda a: "New"
    bridge.is_investigation_in_flight.return_value = False
    view = AlertsView(bridge)
    return view, bridge


class TestPagination:
    def test_default_page_100(self, qapp):
        view, _ = _view_250(qapp)
        assert view.table.rowCount() == 100
        assert view.page_label.text() == "Page 1 of 3 · showing 1–100 of 250"
        assert not view.prev_btn.isEnabled() and view.next_btn.isEnabled()
        view.deleteLater()

    def test_next_and_last_page(self, qapp):
        view, _ = _view_250(qapp)
        view.next_btn.click()
        assert view.table.rowCount() == 100
        assert "101–200" in view.page_label.text()
        view.next_btn.click()
        assert view.table.rowCount() == 50
        assert "201–250" in view.page_label.text()
        assert not view.next_btn.isEnabled()
        view.prev_btn.click()
        assert "101–200" in view.page_label.text()
        view.deleteLater()

    def test_page_size_change(self, qapp):
        view, _ = _view_250(qapp)
        view.page_size_combo.setCurrentText("200")
        assert view.table.rowCount() == 200
        assert "Page 1 of 2" in view.page_label.text()
        view.deleteLater()

    def test_filter_resets_page_and_counters(self, qapp):
        view, _ = _view_250(qapp)
        view.next_btn.click()
        view.priority_filter.setCurrentText("Critical")  # 125 critical
        assert view._page == 0
        assert view.table.rowCount() == 100
        assert "Page 1 of 2" in view.page_label.text()
        assert "of 125" in view.page_label.text()
        assert "Total: 125" in view.counter_label.text()
        view.deleteLater()

    def test_one_action_button_per_page_row(self, qapp):
        view, _ = _view_250(qapp)
        view.next_btn.click()
        view.next_btn.click()   # last page
        view.prev_btn.click()
        btns = view.table.viewport().findChildren(QPushButton)
        assert len(btns) == view.table.rowCount() == 100
        view.deleteLater()

    def test_investigate_click_then_rebuild_no_crash(self, qapp):
        """btn.click() then a synchronous rebuild must not crash."""
        view, bridge = _view_250(qapp)
        btn = view.table.cellWidget(0, AlertsView.ACTION_COLUMN)
        btn.click()
        bridge.investigate_target.assert_called_once()
        view.refresh()
        view._set_row_status(0, "Resolved")
        assert view.table.rowCount() == 100
        view.deleteLater()


class TestExport:
    def test_export_csv_all_filtered(self, qapp, tmp_path, monkeypatch):
        view, _ = _view_250(qapp)
        view.priority_filter.setCurrentText("Critical")  # 125 rows, 2 pages
        out = tmp_path / "alerts.csv"
        monkeypatch.setattr(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(out), "CSV (*.csv)"),
        )
        view._on_export()
        rows = list(csv.reader(open(out, newline="", encoding="utf-8")))
        assert rows[0] == EXPORT_FIELDS
        assert len(rows) == 1 + 125  # all filtered rows, not just page 1
        view.deleteLater()

    def test_export_json(self, qapp, tmp_path, monkeypatch):
        view, _ = _view_250(qapp)
        out = tmp_path / "alerts.json"
        monkeypatch.setattr(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(out), "JSON (*.json)"),
        )
        view._on_export()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 250
        view.deleteLater()

    def test_export_cancel_no_file(self, qapp, monkeypatch):
        view, _ = _view_250(qapp)
        monkeypatch.setattr(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            lambda *a, **k: ("", ""),
        )
        view._on_export()  # must not raise
        view.deleteLater()
