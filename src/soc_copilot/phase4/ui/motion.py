"""Motion helpers: short, interruptible UI transitions.

Every helper degrades to an instant change when motion is disabled
(Settings → Appearance → Reduce motion) or the widget is not on screen,
so state is always applied synchronously and callers/tests never have to
wait for an animation to finish.
"""

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QTimer, QVariantAnimation,
    Qt, pyqtSignal,
)
from PyQt6.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QLabel, QWidget,
)

from .theme import ThemeManager, set_role

# Durations (ms) — kept short so the UI feels responsive, not decorative.
FAST = 140
NORMAL = 220
SLOW = 320

_EASE_OUT = QEasingCurve.Type.OutCubic
_EASE_IN_OUT = QEasingCurve.Type.InOutCubic


def motion_enabled(widget: QWidget | None = None) -> bool:
    """True when animations should run for ``widget``."""
    if ThemeManager.instance().reduce_motion:
        return False
    if QApplication.platformName() in ("offscreen", "minimal"):
        return False
    return widget is None or widget.isVisible()


def _keep(widget: QWidget, name: str, anim) -> None:
    """Hold a reference on the widget, stopping any previous animation."""
    prev = getattr(widget, name, None)
    if prev is not None:
        try:
            prev.stop()
        except RuntimeError:
            pass
    setattr(widget, name, anim)


def fade_in(widget: QWidget, duration: int = NORMAL) -> None:
    """Fade a widget from transparent to opaque.

    The opacity effect is removed when done: a lingering effect forces
    off-screen rendering and disables child drop shadows.
    """
    if not motion_enabled(widget):
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(_EASE_OUT)

    def _done():
        try:
            if widget.graphicsEffect() is effect:
                widget.setGraphicsEffect(None)
        except RuntimeError:
            pass

    anim.finished.connect(_done)
    _keep(widget, "_fade_anim", anim)
    anim.start()


def slide_open_width(widget: QWidget, target: int, duration: int = SLOW) -> None:
    """Grow a widget's width from 0 to ``target`` (e.g. a side drawer).

    Animates ``maximumWidth`` with the minimum relaxed to 0; both limits
    are restored afterwards so the user can still resize via the splitter.
    """
    limits = getattr(widget, "_motion_width_limits", None)
    if limits is None:
        limits = (widget.minimumWidth(), widget.maximumWidth())
        widget._motion_width_limits = limits
    final_min, final_max = limits

    def _restore():
        widget.setMinimumWidth(final_min)
        widget.setMaximumWidth(final_max)

    if not motion_enabled(widget):
        _restore()
        return
    widget.setMinimumWidth(0)
    anim = QPropertyAnimation(widget, b"maximumWidth", widget)
    anim.setDuration(duration)
    anim.setStartValue(0)
    anim.setEndValue(max(final_min, min(target, final_max)))
    anim.setEasingCurve(_EASE_OUT)
    anim.finished.connect(_restore)
    _keep(widget, "_slide_anim", anim)
    anim.start()


def count_to(label: QLabel, value: int, duration: int = SLOW,
             fmt=str) -> None:
    """Animate a numeric label from its current value to ``value``."""
    try:
        start = int(label.property("_count_value") or 0)
    except (TypeError, ValueError):
        start = 0
    label.setProperty("_count_value", int(value))
    if start == value or not motion_enabled(label):
        _keep(label, "_count_anim", None)
        label.setText(fmt(value))
        return
    anim = QVariantAnimation(label)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(int(value))
    anim.setEasingCurve(_EASE_OUT)
    anim.valueChanged.connect(lambda v: label.setText(fmt(int(v))))
    # Guarantee the exact final text even if frames are dropped
    anim.finished.connect(lambda: label.setText(fmt(int(value))))
    _keep(label, "_count_anim", anim)
    anim.start()


def crossfade_window(window: QWidget, duration: int = NORMAL) -> None:
    """Cross-fade from a snapshot of ``window`` to its new look.

    Call *before* restyling (e.g. a theme switch): the snapshot covers the
    window and fades out, revealing the restyled UI underneath.
    """
    if not motion_enabled(window):
        return
    central = getattr(window, "centralWidget", lambda: None)() or window
    pixmap = central.grab()
    overlay = QLabel(central)
    overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    overlay.setPixmap(pixmap)
    overlay.setGeometry(central.rect())
    overlay.show()
    overlay.raise_()
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", overlay)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(_EASE_IN_OUT)
    anim.finished.connect(overlay.deleteLater)
    anim.start()


class Toast(QLabel):
    """Transient notification pinned to the bottom-right of a window.

    Use :func:`show_toast`; a new toast replaces the current one.
    """

    _KIND_ROLES = {
        "info": "toastInfo",
        "success": "toastSuccess",
        "warning": "toastWarning",
        "error": "toastError",
    }

    dismissed = pyqtSignal()

    def __init__(self, parent: QWidget, message: str, kind: str = "info"):
        super().__init__(message, parent)
        self.setObjectName("toast")
        set_role(self, self._KIND_ROLES.get(kind, "toastInfo"))
        # Size to the text on one line, wrapping only past 360px
        width = min(self.sizeHint().width(), 360)
        self.setWordWrap(True)
        self.setFixedWidth(max(width, 200))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName(f"Notification: {message}")
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

    def _place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 20
        bottom_inset = 36  # clear the status bar
        self.setFixedHeight(self.heightForWidth(self.width()))
        self.move(
            parent.width() - self.width() - margin,
            parent.height() - self.height() - margin - bottom_inset,
        )

    def popup(self, timeout_ms: int) -> None:
        self._place()
        self.show()
        self.raise_()
        fade_in(self, FAST)
        self._timer.start(timeout_ms)

    def dismiss(self) -> None:
        self._timer.stop()
        if not motion_enabled(self):
            self._finish()
            return
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(NORMAL)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._finish)
        _keep(self, "_fade_anim", anim)
        anim.start()

    def _finish(self) -> None:
        self.hide()
        self.dismissed.emit()
        self.deleteLater()


class _ToastHost:
    """Tracks the live toast per window so a new one replaces the old."""

    def __init__(self):
        self._current: dict[int, Toast] = {}

    def show(self, window: QWidget, message: str, kind: str,
             timeout_ms: int) -> Toast:
        key = id(window)
        old = self._current.pop(key, None)
        if old is not None:
            try:
                old._finish()
            except RuntimeError:
                pass
        toast = Toast(window, message, kind)
        self._current[key] = toast
        toast.dismissed.connect(
            lambda k=key, t=toast: self._current.get(k) is t
            and self._current.pop(k, None)
        )
        toast.popup(timeout_ms)
        return toast


_host: _ToastHost | None = None


def show_toast(widget: QWidget | None, message: str, kind: str = "info",
               timeout_ms: int = 2600) -> Toast | None:
    """Show a toast on ``widget``'s top-level window ('info' | 'success' |
    'warning' | 'error'). Returns None when there is no window to host it."""
    global _host
    if widget is None:
        return None
    window = widget.window()
    if window is None:
        return None
    if _host is None:
        _host = _ToastHost()
    return _host.show(window, message, kind, timeout_ms)
