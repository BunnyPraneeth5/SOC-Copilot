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
        class SimpleQtBot:
            def addWidget(self, widget):
                widget.show()
        
        return SimpleQtBot()
