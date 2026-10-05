"""Tests for UX-2: persisted light/dark toggle + colour-blind-safe severities."""

import re
from dataclasses import replace

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QLabel

from soc_copilot.phase4.ui.theme import (
    COLORBLIND_OVERRIDES,
    DARK,
    LIGHT,
    ThemeManager,
    build_stylesheet,
    severity_color,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_rel_luminance(a), _rel_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.fixture()
def tm():
    """ThemeManager reset to dark / non-colour-blind after each test."""
    manager = ThemeManager.instance()
    yield manager
    manager._colorblind = False
    manager.set_theme("dark")


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def ini_settings(tmp_path):
    return QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)


# ---------------------------------------------------------------------------
# Persistence / precedence
# ---------------------------------------------------------------------------

class TestPreferences:
    def test_saved_setting_wins_over_env(self, tm, ini_settings, monkeypatch):
        ini_settings.setValue("appearance/theme", "dark")
        monkeypatch.setenv("SOC_COPILOT_THEME", "light")
        tm.load_preferences(ini_settings)
        assert tm.theme_name == "dark"

    def test_env_used_when_no_saved_value(self, tm, ini_settings, monkeypatch):
        monkeypatch.setenv("SOC_COPILOT_THEME", "light")
        tm.load_preferences(ini_settings)
        assert tm.theme_name == "light"

    def test_default_dark(self, tm, ini_settings, monkeypatch):
        monkeypatch.delenv("SOC_COPILOT_THEME", raising=False)
        tm.load_preferences(ini_settings)
        assert tm.theme_name == "dark"

    def test_invalid_saved_and_env_fall_back_to_dark(
        self, tm, ini_settings, monkeypatch
    ):
        ini_settings.setValue("appearance/theme", "neon")
        monkeypatch.setenv("SOC_COPILOT_THEME", "also-bad")
        tm.load_preferences(ini_settings)
        assert tm.theme_name == "dark"

    def test_save_load_round_trip(self, tm, ini_settings, monkeypatch):
        monkeypatch.delenv("SOC_COPILOT_THEME", raising=False)
        tm.load_preferences(ini_settings)
        tm.set_colorblind(True)
        tm.set_theme("light")

        fresh = QSettings(ini_settings.fileName(), QSettings.Format.IniFormat)
        assert fresh.value("appearance/theme") == "light"
        cb = fresh.value("appearance/colorblind")
        assert str(cb).lower() in ("true", "1")

        # Simulate a fresh session: reset internals without saving
        tm._base_name = "dark"
        tm._colorblind = False
        tm._rebuild_palette()
        tm.load_preferences(fresh)
        assert tm.theme_name == "light"
        assert tm.colorblind is True

    def test_colorblind_saved_flag(self, tm, ini_settings, monkeypatch):
        monkeypatch.delenv("SOC_COPILOT_THEME", raising=False)
        ini_settings.setValue("appearance/colorblind", True)
        tm.load_preferences(ini_settings)
        assert tm.colorblind is True


# ---------------------------------------------------------------------------
# Colour-blind overrides
# ---------------------------------------------------------------------------

class TestColorblind:
    def test_set_colorblind_changes_severity_and_emits(self, tm, qapp):
        emitted = []
        conn = tm.theme_changed.connect(emitted.append)
        try:
            tm.set_colorblind(True)
            assert emitted
            palette = emitted[-1]
            for token, value in COLORBLIND_OVERRIDES["dark"].items():
                assert getattr(palette, token) == value
            assert severity_color("critical") == COLORBLIND_OVERRIDES["dark"]["sev_critical"]
            # Non-severity tokens unchanged
            assert palette.accent == DARK.accent
            tm.set_colorblind(False)
            assert tm.palette.sev_critical == DARK.sev_critical
        finally:
            tm.theme_changed.disconnect(conn)

    def test_light_colorblind_uses_light_overrides(self, tm, qapp):
        tm.set_theme("light")
        tm.set_colorblind(True)
        for token, value in COLORBLIND_OVERRIDES["light"].items():
            assert getattr(tm.palette, token) == value

    def test_effective_palette_matches_replace(self, tm, qapp):
        tm.set_colorblind(True)
        expected = replace(DARK, **COLORBLIND_OVERRIDES["dark"])
        assert tm.palette == expected


# ---------------------------------------------------------------------------
# WCAG contrast
# ---------------------------------------------------------------------------

SEVERITY_TOKENS = ["sev_critical", "sev_high", "sev_medium", "sev_low", "sev_info"]


def _palettes_all_combos():
    combos = []
    for base in (DARK, LIGHT):
        combos.append((f"{base.name}-normal", base))
        combos.append(
            (f"{base.name}-cb", replace(base, **COLORBLIND_OVERRIDES[base.name]))
        )
    return combos


class TestContrast:
    @pytest.mark.parametrize(
        "label,palette",
        _palettes_all_combos(),
        ids=[c[0] for c in _palettes_all_combos()],
    )
    def test_severity_tokens_contrast_vs_surface(self, label, palette):
        for token in SEVERITY_TOKENS:
            ratio = contrast_ratio(getattr(palette, token), palette.surface)
            assert ratio >= 3.0, f"{label} {token} vs surface: {ratio:.2f}"

    def test_light_text_contrast(self):
        assert contrast_ratio(LIGHT.text, LIGHT.bg) >= 4.5
        assert contrast_ratio(LIGHT.text, LIGHT.surface) >= 4.5
        assert contrast_ratio(LIGHT.text_muted, LIGHT.surface) >= 3.0


# ---------------------------------------------------------------------------
# Offscreen UI integration
# ---------------------------------------------------------------------------

class TestRuntimeSwitch:
    def test_app_stylesheet_contains_light_bg(self, tm, qapp):
        tm.set_theme("light")
        assert LIGHT.bg in qapp.styleSheet()
        tm.set_theme("dark")
        assert DARK.bg in qapp.styleSheet()

    def test_config_panel_appearance_controls(self, tm, qapp, tmp_path):
        from soc_copilot.phase4.ui.config_panel import ConfigPanel

        panel = ConfigPanel(bridge=None, project_root=tmp_path)
        assert panel.theme_combo.currentIndex() == (
            0 if tm.theme_name == "dark" else 1
        )
        panel.theme_combo.setCurrentIndex(1)
        assert tm.theme_name == "light"
        panel.colorblind_check.setChecked(True)
        assert tm.colorblind is True
        # Switching back through the manager keeps the combo in sync
        tm.set_theme("dark")
        assert panel.theme_combo.currentIndex() == 0
        panel.deleteLater()

    def test_status_indicator_restyles_on_switch(self, tm, qapp):
        from soc_copilot.phase4.ui.config_panel import StatusIndicator

        ind = StatusIndicator("X", "OK", tm.palette.success)
        dark_style = ind.dot.styleSheet()
        tm.set_theme("light")
        # token value identical (success), but muted label must re-render
        assert LIGHT.text_muted in ind._label_widget.styleSheet()
        tm.set_theme("dark")
        assert DARK.text_muted in ind._label_widget.styleSheet()
        ind.deleteLater()

    def test_priority_badge_color_follows_palette(self, tm, qapp):
        """Representative runtime check: severity_color tracks the palette."""
        tm.set_theme("light")
        assert severity_color("critical") == LIGHT.sev_critical
        tm.set_colorblind(True)
        assert severity_color("critical") == (
            COLORBLIND_OVERRIDES["light"]["sev_critical"]
        )
        tm.set_colorblind(False)
        tm.set_theme("dark")


class TestStyleScoping:
    """Border/background container styles must not cascade to child QLabels.

    QLabel is a QFrame subclass, so a bare ``QFrame { border: ... }`` rule
    in a widget's inline stylesheet also matches its label children.
    Container rules must use class-name or #objectName selectors.
    """

    LEAKY = re.compile(r"(QFrame|QWidget|QLabel)\s*[,{]")

    def _assert_scoped(self, widget):
        sheet = widget.styleSheet() or ""
        if "border" in sheet:
            assert "{" in sheet, f"{type(widget).__name__}: unscoped style"
            assert not self.LEAKY.search(sheet), (
                f"{type(widget).__name__}: generic selector leaks to "
                f"QLabel children: {sheet!r}"
            )
        for child in widget.findChildren(QLabel):
            child_sheet = child.styleSheet() or ""
            if "border" in child_sheet:
                assert "{" in child_sheet or child.property("role") == "badge"

    def test_threat_banner_v2(self, qapp):
        from soc_copilot.phase4.ui.dashboard_v2 import ThreatBanner
        w = ThreatBanner()
        w.set_level("critical", 2, 1)
        self._assert_scoped(w)
        w.deleteLater()

    def test_metric_card(self, qapp):
        from soc_copilot.phase4.ui.dashboard_v2 import MetricCard
        w = MetricCard("Critical", "🔥", "#ff0000")
        self._assert_scoped(w)
        w.deleteLater()

    def test_system_status_strip(self, qapp):
        from soc_copilot.phase4.ui.dashboard_v2 import SystemStatusStrip
        self._assert_scoped(SystemStatusStrip())

    def test_banners_and_cards(self, qapp):
        from soc_copilot.phase4.ui.system_status_bar import (
            KillSwitchBanner,
            PermissionBanner,
        )
        from soc_copilot.phase4.ui.dashboard_components import (
            CompactMetricCard,
            EmptyStateCard,
            ThreatLevelBanner,
        )
        self._assert_scoped(PermissionBanner("msg"))
        self._assert_scoped(KillSwitchBanner())
        self._assert_scoped(ThreatLevelBanner())
        self._assert_scoped(CompactMetricCard("t", "critical"))
        self._assert_scoped(
            EmptyStateCard("i", "t", "d", "", "warning")
        )
