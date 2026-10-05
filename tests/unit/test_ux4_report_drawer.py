"""Tests for UX-4: investigation report drawer + markdown formatting."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from soc_copilot.mcp.models import (
    AbuseIPDBResult, AsnInfo, DnsInfo, GeoInfo, ReconResult,
    ReputationResult, ShodanResult, ThreatReport, ThreatSeverity,
    VirusTotalResult, WhoisInfo,
)
from soc_copilot.phase4.ui.report_drawer import ReportDrawer
from soc_copilot.phase4.ui.report_format import report_mode, report_to_markdown
from soc_copilot.phase4.ui.theme import ThemeManager


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _reset_theme():
    yield
    tm = ThemeManager.instance()
    tm._colorblind = False
    tm.set_theme("dark")


def _rich_report():
    return ThreatReport(
        target="45.67.89.101",
        severity=ThreatSeverity.CRITICAL,
        summary="Host exhibits active brute-force behaviour.",
        recommendations=["Block 45.67.89.101", "Rotate credentials"],
        recon=ReconResult(
            ip="45.67.89.101",
            whois=WhoisInfo(org="EvilHosting", registrar="BadReg",
                            country="NL"),
            dns=DnsInfo(hostname="bot-101.example.net"),
            asn=AsnInfo(asn="AS9009", asn_name="M247", asn_cidr="45.67.0.0/16",
                        asn_country="NL"),
            geo=GeoInfo(city="Amsterdam", region="NH", country="Netherlands",
                        isp="M247 Europe"),
        ),
        reputation=ReputationResult(
            ip="45.67.89.101",
            abuseipdb=AbuseIPDBResult(
                confidence_score=97, total_reports=512,
                usage_type="Data Center/Web Hosting", isp="M247",
                domain="m247.com",
            ),
            virustotal=VirusTotalResult(
                malicious=42, suspicious=3, harmless=20, undetected=7,
                detection_ratio=0.625,
            ),
        ),
        shodan=ShodanResult(
            ip="45.67.89.101",
            open_ports=[22, 80, 443, 3389],
            services=[{"port": 22, "product": "OpenSSH"}],
            cves=["CVE-2023-38408", "CVE-2024-6387"],
            os="Linux",
            hostnames=["bot-101.example.net"],
        ),
        generated_at=datetime(2026, 7, 10, 14, 30, 0),
        llm_model="nvidia_nim/llama-3.3-70b",
    )


def _partial_report():
    return ThreatReport(
        target="8.8.8.8",
        severity=ThreatSeverity.UNKNOWN,
        summary="Partial report (ReportAgent skipped)",
        recon=ReconResult(ip="8.8.8.8"),
        generated_at=datetime(2026, 7, 10, 14, 31, 0),
    )


def _local_report():
    return ThreatReport(
        target="10.0.0.1",
        severity=ThreatSeverity.UNKNOWN,
        summary="Local-only report (enrichment disabled)",
    )


# ---------------------------------------------------------------------------
# report_format
# ---------------------------------------------------------------------------

class TestReportFormat:
    def test_modes(self):
        assert report_mode(_rich_report()) == "AI report"
        assert report_mode(_partial_report()) == "Partial"
        assert report_mode(_local_report()) == "Local-only"

    def test_markdown_all_sections(self):
        md = report_to_markdown(_rich_report())
        assert md.startswith("# Threat Report: 45.67.89.101")
        assert "**Severity:** CRITICAL" in md
        assert "**Mode:** AI report" in md
        assert "llama-3.3-70b" in md
        for section in ("## Summary", "## Recommendations", "## Recon",
                        "## Reputation", "## Exposure (Shodan)"):
            assert section in md
        assert "EvilHosting" in md and "AS9009" in md and "Amsterdam" in md
        assert "97" in md  # AbuseIPDB confidence
        assert "63%" in md or "62%" in md or "0.625" in md
        assert "3389" in md and "CVE-2024-6387" in md

    def test_markdown_skips_absent_sections(self):
        md = report_to_markdown(_partial_report())
        assert "## Summary" in md
        assert "## Reputation" not in md
        assert "## Exposure (Shodan)" not in md
        assert "## Recon" not in md  # present but all-empty fields
        assert "**Severity:** UNKNOWN" in md

    def test_markdown_missing_generated_at(self):
        from types import SimpleNamespace
        report = SimpleNamespace(
            target="10.0.0.1", severity=ThreatSeverity.UNKNOWN,
            summary="local", recommendations=[], recon=None,
            reputation=None, shodan=None, generated_at=None,
            llm_model=None,
        )
        md = report_to_markdown(report)
        assert "**Generated:** Unknown" in md

    def test_markdown_none_report(self):
        assert "No report" in report_to_markdown(None)


# ---------------------------------------------------------------------------
# ReportDrawer widget
# ---------------------------------------------------------------------------

@pytest.fixture()
def drawer(qapp):
    d = ReportDrawer()
    yield d
    d.deleteLater()


class TestReportDrawer:
    def test_hidden_by_default(self, drawer):
        assert not drawer.isVisible()

    def test_loading_state(self, drawer):
        drawer.show_loading("1.2.3.4")
        assert drawer.isVisible()
        assert "1.2.3.4" in drawer._loading_label.text()
        assert drawer.stack.currentIndex() == 0

    def test_show_report(self, drawer):
        drawer.show_report(_rich_report())
        assert drawer.isVisible()
        assert drawer.stack.currentIndex() == 1
        texts = [
            w.text() for w in drawer._report_body.findChildren(type(drawer._title_label))
        ]
        assert any("45.67.89.101" in t for t in texts)
        assert any("CRITICAL" in t for t in texts)
        assert any("AI report" in t for t in texts)
        assert any("EvilHosting" in t for t in texts)
        assert any("CVE-2024-6387" in t for t in texts)

    def test_error_state_and_retry(self, drawer):
        calls = []
        drawer.retry_requested.connect(calls.append)
        drawer.show_error("9.9.9.9", "boom")
        assert drawer.stack.currentIndex() == 2
        assert "9.9.9.9" in drawer._error_label.text()
        drawer.retry_btn.click()
        assert calls == ["9.9.9.9"]

    def test_copy_puts_markdown_on_clipboard(self, drawer):
        drawer.show_report(_rich_report())
        drawer._copy_markdown()
        text = QApplication.clipboard().text()
        assert text.startswith("# Threat Report: 45.67.89.101")

    def test_export_writes_file(self, drawer, tmp_path, monkeypatch):
        target = tmp_path / "out.md"
        monkeypatch.setattr(
            "PyQt6.QtWidgets.QFileDialog.getSaveFileName",
            staticmethod(lambda *a, **k: (str(target), "Markdown (*.md)")),
        )
        drawer.show_report(_rich_report())
        drawer._export_markdown()
        assert target.read_text(encoding="utf-8").startswith("# Threat Report")

    def test_history_caps_at_ten_and_switches(self, drawer):
        for i in range(12):
            drawer.show_report(_local_report())
        assert drawer.history_combo.count() == 10
        drawer.show_report(_rich_report())
        drawer.history_combo.setCurrentIndex(1)  # previous report
        assert drawer._current_report.severity == ThreatSeverity.UNKNOWN

    def test_esc_closes(self, drawer):
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent, Qt
        drawer.show_report(_rich_report())
        assert drawer.isVisible()
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        drawer.keyPressEvent(ev)
        assert not drawer.isVisible()

    def test_theme_switch_restyles(self, drawer, qapp):
        drawer.show_report(_rich_report())
        ThemeManager.instance().set_theme("light")
        assert drawer.stack.currentIndex() == 1
        ThemeManager.instance().set_theme("dark")

    def test_theme_switch_leaves_single_badges_and_meta(self, drawer, qapp):
        """Re-render on theme change must detach old widgets (UX-4 fix)."""
        drawer.show_report(_rich_report())
        ThemeManager.instance().set_theme("light")
        QApplication.processEvents()
        from PyQt6.QtWidgets import QLabel
        sev = drawer._report_body.findChildren(QLabel, "sevBadge")
        mode = drawer._report_body.findChildren(QLabel, "modeBadge")
        meta = drawer._report_body.findChildren(QLabel, "reportMeta")
        assert len(sev) == 1 and len(mode) == 1 and len(meta) == 1
        assert "CRITICAL" in sev[0].text()
        ThemeManager.instance().set_theme("dark")

    def test_copy_export_disabled_on_loading_and_error(self, drawer):
        drawer.show_loading("1.2.3.4")
        assert not drawer.copy_btn.isEnabled()
        drawer.show_error("1.2.3.4", "boom")
        assert not drawer.copy_btn.isEnabled()
        assert not drawer.export_btn.isEnabled()
        drawer.show_report(_rich_report())
        assert drawer.copy_btn.isEnabled() and drawer.export_btn.isEnabled()

    def test_report_scrolls_not_clips(self, qapp):
        """Content taller than the viewport must scroll, not squeeze."""
        drawer = ReportDrawer()
        drawer.resize(430, 500)
        drawer.show()
        drawer.show_report(_rich_report())
        QApplication.processEvents()
        sb = drawer._report_scroll.verticalScrollBar()
        # content taller than viewport → scrollbar range appears
        assert sb.maximum() > 0
        from PyQt6.QtWidgets import QLabel
        for child in drawer._report_body.findChildren(QLabel):
            # word-wrap labels: heightForWidth is the authoritative hint
            want = child.heightForWidth(child.width())
            if want > 0:
                assert child.height() >= want
        drawer.deleteLater()

    def test_disabled_button_stylesheet(self, qapp):
        from soc_copilot.phase4.ui.theme import build_stylesheet, DARK, LIGHT
        for p in (DARK, LIGHT):
            ss = build_stylesheet(p)
            assert "QPushButton:disabled" in ss
            assert "QPushButton[variant]:disabled" in ss

    def test_history_row_visible_with_entries(self, drawer):
        assert not drawer._history_row.isVisible()
        drawer.show_report(_rich_report())
        assert drawer._history_row.isVisible()
        assert drawer.history_combo.count() == 1
        assert "45.67.89.101" in drawer.history_combo.itemText(0)
        assert "—" in drawer.history_combo.itemText(0)


# ---------------------------------------------------------------------------
# AlertsView integration (drawer attached vs standalone fallback)
# ---------------------------------------------------------------------------

class TestAlertsViewIntegration:
    def _view(self, qapp, tmp_path):
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        bridge = ControllerBridge(controller)
        return AlertsView(bridge), bridge

    def test_drawer_shows_report_no_messagebox(self, qapp, tmp_path, monkeypatch):
        view, bridge = self._view(qapp, tmp_path)
        drawer = ReportDrawer()
        view.report_drawer = drawer

        def fail(*a, **k):
            pytest.fail("QMessageBox shown while drawer attached")

        monkeypatch.setattr(QMessageBox, "information", staticmethod(fail))
        monkeypatch.setattr(QMessageBox, "critical", staticmethod(fail))

        view._on_report_ready("45.67.89.101", _rich_report(), None)
        assert drawer.isVisible()
        assert drawer.stack.currentIndex() == 1

        view._on_report_ready("9.9.9.9", None, Mock(message="oops"))
        assert drawer.stack.currentIndex() == 2
        view.deleteLater()
        drawer.deleteLater()
        bridge.deleteLater()

    def test_messagebox_fallback_without_drawer(self, qapp, tmp_path, monkeypatch):
        view, bridge = self._view(qapp, tmp_path)
        shown = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda *a, **k: shown.append(a)),
        )
        view._on_report_ready("45.67.89.101", _rich_report(), None)
        assert shown
        view.deleteLater()
        bridge.deleteLater()

    def test_mainwindow_has_drawer_in_splitter(self, qapp, tmp_path):
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        assert w.alerts_view.report_drawer is w.report_drawer
        assert not w.report_drawer.isVisible()
        # report arrives -> drawer opens, no QMessageBox
        w.alerts_view._on_report_ready("45.67.89.101", _rich_report(), None)
        # embedded widget: isVisible() needs shown ancestors; isHidden()
        # reflects the drawer's own visible state
        assert not w.report_drawer.isHidden()
        w.deleteLater()
