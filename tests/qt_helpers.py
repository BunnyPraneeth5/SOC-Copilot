"""Qt test helpers."""

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication


def destroy(*widgets):
    """deleteLater + flush deferred deletes immediately.

    Hundreds of pending ``deleteLater`` objects accumulate across a long
    suite because most tests never spin the event loop; they all get
    destroyed at once when some later test calls ``processEvents``, which
    has produced access violations under load. Flushing per teardown keeps
    the backlog small.
    """
    for widget in widgets:
        if widget is None:
            continue
        try:
            widget.hide()
        except Exception:
            pass
        widget.deleteLater()
    app = QApplication.instance()
    if app is not None:
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
