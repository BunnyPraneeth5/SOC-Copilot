"""Tests for UX-8: motion helpers, toasts and the reduce-motion preference."""

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget

from soc_copilot.phase4.ui import motion
from soc_copilot.phase4.ui.theme import ThemeManager
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def settings(tmp_path):
    return QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)


class TestReduceMotionPreference:
    def test_defaults_off(self, qapp, settings):
        tm = ThemeManager.instance()
        tm.load_preferences(settings)
        assert tm.reduce_motion is False

    def test_persists(self, qapp, settings):
        tm = ThemeManager.instance()
        tm.load_preferences(settings)
        tm.set_reduce_motion(True)
        tm._reduce_motion = False
        tm.load_preferences(settings)
        assert tm.reduce_motion is True
        tm.set_reduce_motion(False)

    def test_disables_motion(self, qapp, settings, monkeypatch):
        tm = ThemeManager.instance()
        tm.load_preferences(settings)
        monkeypatch.setattr(QApplication, "platformName", lambda: "windows")
        tm.set_reduce_motion(True)
        assert motion.motion_enabled() is False
        tm.set_reduce_motion(False)
        assert motion.motion_enabled() is True


class TestInstantFallbacks:
    """Off screen (and in tests) every helper applies its end state at once."""

    def test_count_to_sets_text_immediately(self, qapp):
        label = QLabel("0")
        motion.count_to(label, 42)
        assert label.text() == "42"
        motion.count_to(label, 7)
        assert label.text() == "7"
        destroy(label)

    def test_fade_in_leaves_no_effect(self, qapp):
        w = QWidget()
        motion.fade_in(w)
        assert w.graphicsEffect() is None
        destroy(w)

    def test_slide_open_restores_width_limits(self, qapp):
        w = QWidget()
        w.setMinimumWidth(320)
        w.setMaximumWidth(560)
        motion.slide_open_width(w, 440)
        assert (w.minimumWidth(), w.maximumWidth()) == (320, 560)
        destroy(w)


class TestToast:
    def test_new_toast_replaces_previous(self, qapp):
        win = QMainWindow()
        win.resize(800, 600)
        first = motion.show_toast(win, "first")
        second = motion.show_toast(win, "second", "success")
        assert first is not second
        assert second.text() == "second"
        assert second.property("role") == "toastSuccess"
        assert second.parentWidget() is win
        destroy(win)

    def test_no_widget_no_toast(self, qapp):
        assert motion.show_toast(None, "x") is None
