"""Pytest configuration for Qt tests"""

import os
import pytest
import sys


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


# Temporary crash tracer: append each test's nodeid to a file BEFORE it
# runs (fd-level capture would hide stderr prints; a direct handle is
# flushed to disk so the last line is the test that died).
_TRACE = open(os.path.join(".cache", "test_trace.txt"), "w", buffering=1)


def pytest_runtest_setup(item):
    _TRACE.write(item.nodeid + "\n")
    _TRACE.flush()
    os.fsync(_TRACE.fileno())
