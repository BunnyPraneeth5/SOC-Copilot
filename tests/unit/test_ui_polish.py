"""Tests for the UI polish pass: icons, components, emoji guard."""

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidget

from soc_copilot.phase4.ui import icons
from soc_copilot.phase4.ui.components import (
    PageHeader, Switch, severity_delegate, style_table, tint,
)
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy

UI_DIR = Path(__file__).resolve().parents[2] / "src" / "soc_copilot" / "phase4" / "ui"

# Pictographic emoji, misc symbols/dingbats (⚠ ✅ ⚙ ✓ ✕), technical symbols
# (⏳ ⏸) and the emoji variation selector. Geometric shapes (● ○) and
# arrows in comments are allowed.
EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⌀-⏿⬀-⯿️]"
)


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tm(qapp, tmp_path):
    manager = ThemeManager.instance()
    manager.load_preferences(
        QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    )
    manager.set_theme("dark")
    yield manager
    manager.set_theme("dark")


class TestEmojiGuard:
    def test_no_emoji_in_ui_files(self):
        offenders = []
        for path in sorted(UI_DIR.glob("*.py")):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if EMOJI.search(line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
        assert not offenders, "emoji found (use icons.py):\n" + "\n".join(offenders)


class TestIcons:
    def test_every_icon_renders(self, qapp):
        for name in icons.ICONS:
            px = icons.pixmap(name, "text", 16)
            assert not px.isNull(), name

    def test_unknown_icon_raises(self, qapp):
        with pytest.raises(KeyError):
            icons.pixmap("does-not-exist")

    def test_label_icon_follows_theme(self, tm):
        label = icons.icon_label("shield", "accent", 16)
        dark_key = label.pixmap().cacheKey()
        tm.set_theme("light")
        assert label.pixmap().cacheKey() != dark_key
        destroy(label)

    def test_set_icon_replaces_binding(self, tm):
        btn = QPushButton()
        icons.set_icon(btn, "upload")
        icons.set_icon(btn, "download")
        assert btn._icon_binder.name == "download"
        assert not btn.icon().isNull()
        destroy(btn)


class TestComponents:
    def test_switch_is_a_checkbox(self, qapp):
        sw = Switch("Enable")
        changes = []
        sw.toggled.connect(changes.append)
        sw.resize(sw.sizeHint())
        sw.show()
        QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
        assert sw.isChecked() is True
        assert changes == [True]
        assert sw.sizeHint().width() > Switch.TRACK_W
        destroy(sw)

    def test_page_header_subtitle(self, qapp):
        header = PageHeader("Alerts", "bell")
        assert header.subtitle_label.isHidden()
        header.set_subtitle("6 alerts")
        assert not header.subtitle_label.isHidden()
        assert header.title_label.text() == "Alerts"
        destroy(header)

    def test_style_table(self, qapp):
        table = QTableWidget(2, 2)
        style_table(table)
        assert table.property("role") == "data"
        assert not table.verticalHeader().isVisible()
        assert not table.showGrid()
        destroy(table)

    def test_tint(self):
        assert tint("#ff0000", 0.5) == "rgba(255, 0, 0, 0.5)"


class TestAlertsTableBadges:
    def test_badges_keep_item_text(self, qapp):
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        from datetime import datetime
        alert = SimpleNamespace(
            alert_id="A-1", priority="P0-Critical", classification="Ransomware",
            timestamp=datetime(2026, 10, 9, 12, 0), source_ip="1.2.3.4",
            destination_ip="10.0.0.1", confidence=0.9, anomaly_score=0.5,
            risk_score=0.8, reasoning="r", suggested_action="s",
        )
        bridge = Mock()
        bridge.get_all_results.return_value = [SimpleNamespace(batch_id="b", alerts=[alert])]
        bridge.get_triage_map.return_value = {}
        bridge.is_investigation_in_flight.return_value = False
        view = AlertsView(bridge)
        view.refresh()
        assert view.table.item(0, view.PRIORITY_COLUMN).text() == "P0-Critical"
        assert view.table.item(0, view.STATUS_COLUMN).text() == "New"
        assert view.table.itemDelegateForColumn(view.PRIORITY_COLUMN) is not None
        assert not view.table.verticalHeader().isVisible()
        btn = view.table.cellWidget(0, view.ACTION_COLUMN)
        assert btn.property("variant") == "tableAction"
        destroy(view)


class TestShell:
    @pytest.fixture()
    def window(self, qapp, tmp_path):
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        yield w
        destroy(w)

    def test_window_title(self, window):
        assert window.windowTitle() == "SOC Copilot (Beta)"

    def test_nav_badge(self, window):
        btn = window.sidebar.nav_buttons[1]
        p = ThemeManager.instance().palette
        btn.set_badge(6, p.sev_critical)
        assert btn.badge.text() == "6" and not btn.badge.isHidden()
        assert btn.badge.property("tone") == "critical"
        btn.set_badge(150)
        assert btn.badge.text() == "99+"
        assert btn.badge.property("tone") == "neutral"
        btn.set_badge(0)
        assert btn.badge.isHidden()

    def test_dashboard_has_no_duplicate_status_strip(self, window):
        from soc_copilot.phase4.ui import dashboard_v2
        assert not hasattr(dashboard_v2, "SystemStatusStrip")
        assert window.dashboard.actions_bar.upload_btn.isEnabled()


class TestAssistantFormatting:
    def test_bold_markup_is_closed(self, qapp):
        from soc_copilot.phase4.ui.assistant_panel import AssistantPanel
        panel = AssistantPanel()
        panel.chat_display.clear()
        panel._add_message("assistant", "**Title**\n\nplain text")
        doc = panel.chat_display.document()
        title = doc.find("Title")
        plain = doc.find("plain text")
        assert title.charFormat().fontWeight() >= 700
        assert plain.charFormat().fontWeight() < 700
        destroy(panel)
