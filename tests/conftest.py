"""Pytest configuration for Qt tests"""

import os
import sys
import traceback

import pytest


@pytest.fixture(autouse=True)
def _isolate_soc_copilot_env(monkeypatch):
    """Keep a developer's local SOC_COPILOT_* settings from leaking into tests."""
    for name in list(os.environ):
        if name.startswith("SOC_COPILOT_"):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication for tests"""
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    yield app
    
    # Cleanup
    app.quit()


@pytest.fixture
def qtbot(qapp):
    """Provide qtbot for widget testing"""
    try:
        from pytestqt.qtbot import QtBot
        return QtBot(qapp)
    except ImportError:
        # Fallback if pytest-qt not available
        from tests.qt_helpers import destroy

        class SimpleQtBot:
            def __init__(self):
                self._widgets = []

            def addWidget(self, widget):
                # Tests assert isVisible(), so show like before — but
                # track every widget and delete them all at teardown so
                # they don't accumulate for the whole session.
                self._widgets.append(widget)
                widget.show()
                return widget

        bot = SimpleQtBot()
        yield bot
        destroy(*bot._widgets)


# Unhandled exceptions in Qt callbacks (slots, timers): with the default
# sys.excepthook PyQt6 calls qFatal() and the whole run dies silently
# (exit 127 / 0xC0000409), often several tests after the culprit. Record
# them instead and fail the test during which they surfaced.
_qt_callback_errors = []


def _record_unhandled(exc_type, exc, tb):
    _qt_callback_errors.append(
        "".join(traceback.format_exception(exc_type, exc, tb))
    )


sys.excepthook = _record_unhandled


@pytest.fixture(autouse=True)
def _fail_on_unhandled_qt_exceptions():
    _qt_callback_errors.clear()
    yield
    if _qt_callback_errors:
        errors = "\n".join(_qt_callback_errors)
        _qt_callback_errors.clear()
        pytest.fail(
            "Unhandled exception in a Qt callback (aborts the real app; may "
            "come from an earlier test's timer):\n" + errors
        )
