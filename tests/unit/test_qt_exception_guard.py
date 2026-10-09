"""Regression tests for the full-suite crash (exit 127 / 0xC0000409).

An exception raised inside a Qt callback makes PyQt6 call qFatal() when
the default sys.excepthook is installed. The report drawer's "Copied" →
"Copy" reset was a bare ``QTimer.singleShot`` lambda that outlived the
drawer; it fired in a later test and aborted the run.
"""

import sys
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

from soc_copilot.main import install_excepthook
from soc_copilot.phase4.ui.report_drawer import ReportDrawer
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _spin(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_copy_reset_timer_dies_with_drawer(qapp):
    drawer = ReportDrawer()
    drawer._copy_reset.setInterval(10)
    drawer.copy_btn.setText("Copied")
    drawer._copy_reset.start()
    destroy(drawer)
    # Before the fix the pending reset touched the deleted button here;
    # the autouse guard in conftest fails the test on any such error.
    _spin(60)


def test_copy_reset_restores_label(qapp):
    drawer = ReportDrawer()
    drawer._copy_reset.setInterval(10)
    drawer.copy_btn.setText("Copied")
    drawer._copy_reset.start()
    _spin(60)
    assert drawer.copy_btn.text() == "Copy"
    destroy(drawer)


def test_app_excepthook_logs_instead_of_aborting(monkeypatch):
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    logger = Mock()
    install_excepthook(logger)
    try:
        raise RuntimeError("wrapped C/C++ object has been deleted")
    except RuntimeError as exc:
        sys.excepthook(type(exc), exc, exc.__traceback__)
    logger.error.assert_called_once()
    _, kwargs = logger.error.call_args
    assert "RuntimeError" in kwargs["error"]
    assert "Traceback" in kwargs["traceback"]
