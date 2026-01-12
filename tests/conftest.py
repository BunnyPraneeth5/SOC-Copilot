"""Pytest configuration for Qt tests"""

import pytest
import sys


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
