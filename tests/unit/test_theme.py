"""Tests for the central UI theme system (UX-1)."""

import re
from dataclasses import fields
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from soc_copilot.phase4.ui.theme import (
    DARK,
    LIGHT,
    Palette,
    ThemeManager,
    build_stylesheet,
    severity_color,
    set_role,
)

HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


def _token_values(p: Palette):
    return {f.name: getattr(p, f.name) for f in fields(Palette)}


def _color_values(p: Palette):
    return {k: v for k, v in _token_values(p).items() if k != "name"}


class TestPalette:
    @pytest.mark.parametrize("palette", [DARK, LIGHT])
    def test_all_tokens_valid_hex(self, palette):
        for name, value in _color_values(palette).items():
            assert isinstance(value, str), name
            assert HEX6.match(value), f"{name}={value!r} is not #rrggbb"

    def test_palettes_have_all_tokens(self):
        expected = {
            "name", "bg", "surface", "surface_alt", "border", "text",
            "text_muted", "text_inverse", "accent", "accent_hover",
            "success", "warning", "danger", "info", "info_bg",
            "success_bg", "warning_bg", "danger_bg", "input_bg", "scrollbar",
            "sev_critical", "sev_high", "sev_medium", "sev_low", "sev_info",
        }
        assert set(_token_values(DARK)) == expected
        assert set(_token_values(LIGHT)) == expected


class TestStylesheet:
    @pytest.mark.parametrize("palette", [DARK, LIGHT])
    def test_build_stylesheet_nonempty_and_key_selectors(self, palette):
        qss = build_stylesheet(palette)
        assert qss.strip()
        for selector in (
            "QMainWindow", "QWidget", "QLabel", "QPushButton",
            'QPushButton[variant="primary"]',
            'QPushButton[variant="secondary"]',
            'QPushButton[variant="danger"]',
            'QPushButton[variant="ghost"]',
            "QLineEdit", "QComboBox", "QTableWidget",
            "QHeaderView::section", "QScrollBar", "QGroupBox",
            "QTabWidget", "QToolTip", "QMenu",
            'QFrame[role="card"]', 'QLabel[role="muted"]',
            'QLabel[role="title"]',
            'QLabel[role="badge"][severity="critical"]',
        ):
            assert selector in qss, f"missing selector {selector}"

    def test_stylesheet_interpolates_palette(self):
        qss = build_stylesheet(DARK)
        assert DARK.bg in qss
        assert DARK.accent in qss


class TestSeverityColor:
    @pytest.mark.parametrize("label,token", [
        ("P0-Critical", "sev_critical"),
        ("P1-High", "sev_high"),
        ("P2-Medium", "sev_medium"),
        ("P3-Low", "sev_low"),
        ("P4-Info", "sev_info"),
        ("critical", "sev_critical"),
        ("high", "sev_high"),
        ("medium", "sev_medium"),
        ("low", "sev_low"),
        ("info", "sev_info"),
        ("P0-CRITICAL", "sev_critical"),
    ])
    def test_known_labels(self, label, token):
        assert severity_color(label) == getattr(DARK, token)

    def test_unknown_fallback(self):
        assert severity_color("banana") == DARK.sev_info
        assert severity_color("") == DARK.sev_info


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class TestThemeManager:
    def test_singleton(self):
        assert ThemeManager.instance() is ThemeManager.instance()

    def test_set_theme_emits_and_updates(self, qapp):
        tm = ThemeManager.instance()
        emitted = []
        conn = tm.theme_changed.connect(emitted.append)
        try:
            tm.set_theme("light")
            assert tm.palette == LIGHT
            assert emitted and emitted[-1] == LIGHT
            tm.set_theme("dark")
            assert tm.palette == DARK
        finally:
            tm.theme_changed.disconnect(conn)
            tm.set_theme("dark")  # ensure dark default for other tests

    def test_set_theme_unknown_raises(self, qapp):
        tm = ThemeManager.instance()
        with pytest.raises(ValueError):
            tm.set_theme("neon")

    def test_apply_sets_app_stylesheet(self, qapp):
        ThemeManager.instance().apply(qapp)
        assert qapp.styleSheet().strip()


class TestSetRole:
    def test_sets_properties_and_polishes(self, qapp):
        lbl = QLabel("x")
        set_role(lbl, "badge", severity="critical")
        assert lbl.property("role") == "badge"
        assert lbl.property("severity") == "critical"


class TestHexGuard:
    """No hard-coded hex colours outside theme.py / legacy dashboard.py."""

    def test_no_hex_literals_in_ui_files(self):
        ui_dir = (
            Path(__file__).resolve().parents[2]
            / "src" / "soc_copilot" / "phase4" / "ui"
        )
        pattern = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
        offenders = []
        for path in sorted(ui_dir.glob("*.py")):
            if path.name in ("theme.py", "dashboard.py"):
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    offenders.append(f"{path.name}:{lineno}: {line.strip()}")
        assert not offenders, "hex colour literals found:\n" + "\n".join(offenders)
