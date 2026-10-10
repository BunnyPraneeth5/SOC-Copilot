"""Dashboard "Pipeline" card (Milestone 6a).

Wraps ``PipelineGraphWidget`` with a header (title, one-line summary of the
current or last run, view toggle) and two views:

- **full**: the pipeline graph;
- **strip**: one line of status dots, for short windows.

The dashboard picks the view automatically (full only when Recent alerts
still shows at least 5 rows) until the analyst chooses one with the
chevron; that choice is saved and wins from then on. The ML group in the
graph collapses automatically on narrow cards, likewise until the analyst
toggles it.

Stage events are played back with a short minimum time per step so even
millisecond batches are visible; a newer run replaces any backlog. With
Reduce motion on (or the dashboard hidden) events apply instantly.
"""

from __future__ import annotations

from collections import deque

from PyQt6.QtCore import QRectF, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .components import icon_button
from .icons import icon_label, set_icon
from .motion import motion_enabled
from .pipeline_graph import (
    ACTIVE,
    BLOCKED,
    DONE,
    FAILED,
    IDLE,
    SKIPPED,
    STAGE_LABELS,
    STAGES,
    STATUS_TEXT,
    STATUS_TOKEN,
    PipelineGraphWidget,
)
from .theme import ThemeManager, set_role

FULL, STRIP, AUTO = "full", "strip", "auto"

KEY_VIEW = "dashboard/pipeline_view"            # auto | full | strip
KEY_ML_COLLAPSED = "dashboard/pipeline_ml_collapsed"  # unset = automatic

STEP_MS = 120            # minimum time each stage event stays on screen
MAX_QUEUE = 60
ML_AUTO_COLLAPSE_WIDTH = 900
GRAPH_MIN_H = 110
GRAPH_MAX_H = 165


def _palette():
    return ThemeManager.instance().palette


def _truthy(value) -> bool:
    return str(value).lower() in ("true", "1", "yes", "on")


class PipelineStrip(QWidget):
    """Nine status dots, one per stage (compact view)."""

    DOT = 10
    GAP = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._statuses = {spec.key: IDLE for spec in STAGES}
        self.setAccessibleName("Pipeline status")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ThemeManager.instance().theme_changed.connect(self.update)
        self._refresh_tooltip()

    def sizeHint(self) -> QSize:
        n = len(STAGES)
        return QSize(n * self.DOT + (n - 1) * self.GAP + 2, self.DOT + 8)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def status(self, stage: str) -> str:
        return self._statuses[stage]

    def set_statuses(self, statuses: dict[str, str]) -> None:
        self._statuses.update(statuses)
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self) -> None:
        lines = [f"{spec.label}: {STATUS_TEXT[self._statuses[spec.key]]}" for spec in STAGES]
        self.setToolTip("\n".join(lines))
        self.setAccessibleDescription("; ".join(lines))

    def paintEvent(self, _event) -> None:
        p = _palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.DOT) / 2
        for i, spec in enumerate(STAGES):
            status = self._statuses[spec.key]
            color = QColor(getattr(p, STATUS_TOKEN[status]))
            rect = QRectF(1 + i * (self.DOT + self.GAP), y, self.DOT, self.DOT)
            if status in (IDLE, SKIPPED):
                pen = QPen(color, 1.2)
                if status == SKIPPED:
                    pen.setStyle(Qt.PenStyle.DotLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(rect.adjusted(0.6, 0.6, -0.6, -0.6))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(rect)
        painter.end()


class PipelineCard(QFrame):
    """Pipeline graph card with summary line, playback and view toggle."""

    viewChanged = pyqtSignal(str)  # FULL | STRIP

    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("pipelineCard")
        self._settings = settings or ThemeManager.instance().settings()
        self._queue: deque = deque()
        self._timer = QTimer(self)
        self._timer.setInterval(STEP_MS)
        self._timer.timeout.connect(self._play_next)
        self._last_store: dict | None = None
        self._last_time = None
        self._auto_view = FULL
        self._applying_auto_ml = False

        saved = self._settings.value(KEY_VIEW, AUTO)
        self._view_pref = saved if saved in (FULL, STRIP) else AUTO
        ml_saved = self._settings.value(KEY_ML_COLLAPSED, None)
        self._ml_pref = None if ml_saved is None else _truthy(ml_saved)

        self._init_ui()
        self._apply_theme()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_view()
        self._update_summary()

    # -- UI ------------------------------------------------------------------

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 12, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(icon_label("activity", "text_muted", 16))
        self.title_label = QLabel("Pipeline")
        set_role(self.title_label, "sectionTitle")
        header.addWidget(self.title_label)
        self.strip = PipelineStrip()
        header.addWidget(self.strip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.summary_label = QLabel()
        set_role(self.summary_label, "pageSubtitle")
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        header.addWidget(self.summary_label, 1)
        self.toggle_btn = icon_button("chevron-up", "Show compact view", "text_muted")
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        header.addWidget(self.toggle_btn)
        layout.addLayout(header)

        ml_collapsed = bool(self._ml_pref) if self._ml_pref is not None else False
        self.graph = PipelineGraphWidget(ml_collapsed=ml_collapsed)
        self.graph.mlCollapsedChanged.connect(self._on_ml_collapsed_changed)
        layout.addWidget(self.graph)

    def _apply_theme(self, *_args) -> None:
        p = _palette()
        self.setStyleSheet(f"""
            QFrame#pipelineCard {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
            }}
        """)

    # -- view (full graph / strip) --------------------------------------------

    @property
    def view(self) -> str:
        return self._auto_view if self._view_pref == AUTO else self._view_pref

    @property
    def view_preference(self) -> str:
        return self._view_pref

    def set_auto_view(self, view: str) -> None:
        """Called by the dashboard on resize; ignored once the user chose."""
        if view not in (FULL, STRIP) or view == self._auto_view:
            return
        self._auto_view = view
        if self._view_pref == AUTO:
            self._apply_view()

    def _on_toggle_clicked(self) -> None:
        self._view_pref = STRIP if self.view == FULL else FULL
        self._settings.setValue(KEY_VIEW, self._view_pref)
        self._apply_view()

    def _apply_view(self) -> None:
        full = self.view == FULL
        self.graph.setVisible(full)
        self.strip.setVisible(not full)
        if full:
            set_icon(self.toggle_btn, "chevron-up", "text_muted", 16)
            tip = "Show compact view"
        else:
            set_icon(self.toggle_btn, "chevron-down", "text_muted", 16)
            tip = "Show pipeline graph"
        self.toggle_btn.setToolTip(tip)
        self.toggle_btn.setAccessibleName(tip)
        self._fit_graph_height()
        self.viewChanged.emit(self.view)

    def full_height(self, width: int) -> int:
        """Card height in the full view at ``width`` (for the dashboard)."""
        m = self.layout().contentsMargins()
        header = max(self.toggle_btn.sizeHint().height(), self.title_label.sizeHint().height())
        return m.top() + header + self.layout().spacing() + self._graph_height(width) + m.bottom()

    def _graph_height(self, width: int) -> int:
        m = self.layout().contentsMargins()
        inner = max(width - m.left() - m.right(), 1)
        return max(GRAPH_MIN_H, min(GRAPH_MAX_H, self.graph.heightForScene(inner)))

    def _fit_graph_height(self) -> None:
        if self.view == FULL:
            # preferred height, no minimum: the graph never blocks shrinking
            # the window or gets clipped; when space is short the dashboard
            # picks the strip (unless the user chose the full view)
            self.graph.setMinimumHeight(0)
            self.graph.set_preferred_height(self._graph_height(self.width()))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._auto_ml_collapse()
        self._fit_graph_height()

    # -- ML group --------------------------------------------------------------

    def _auto_ml_collapse(self) -> None:
        if self._ml_pref is not None:
            return
        self._applying_auto_ml = True
        try:
            self.graph.set_ml_collapsed(self.width() < ML_AUTO_COLLAPSE_WIDTH)
        finally:
            self._applying_auto_ml = False

    def _on_ml_collapsed_changed(self, collapsed: bool) -> None:
        self._fit_graph_height()
        if self._applying_auto_ml:
            return
        self._ml_pref = collapsed
        self._settings.setValue(KEY_ML_COLLAPSED, collapsed)

    # -- events and playback ----------------------------------------------------

    def on_stage_event(self, event) -> None:
        """Slot for ``ControllerBridge.pipelineStageUpdated``."""
        if not motion_enabled(self):
            self._flush()
            self._apply(event, animate=False)
            return
        if self._queue and self._queue[-1].batch_id != event.batch_id:
            # a newer run arrived: drop the older backlog, jump to the new run
            self._queue.clear()
        self._queue.append(event)
        while len(self._queue) > MAX_QUEUE:
            self._queue.popleft()
        if not self._timer.isActive():
            self._play_next()
            self._timer.start()

    def _play_next(self) -> None:
        if not self._queue:
            self._timer.stop()
            return
        self._apply(self._queue.popleft(), animate=True)

    def _flush(self) -> None:
        self._timer.stop()
        while self._queue:
            self._apply(self._queue.popleft(), animate=False)

    @property
    def pending_events(self) -> int:
        return len(self._queue)

    def _apply(self, event, animate: bool) -> None:
        if event.batch_id != self.graph.batch_id:
            self._last_store = None
        self.graph.apply_event(event, animate=animate)
        if getattr(event, "stage", None) == "store" and event.status in (DONE, SKIPPED):
            self._last_store = dict(getattr(event, "data", {}) or {})
        self._last_time = getattr(event, "timestamp", None)
        self.strip.set_statuses({spec.key: self.graph.status(spec.key) for spec in STAGES})
        self._update_summary()

    # -- summary line -------------------------------------------------------------

    def summary_text(self) -> str:
        if self.graph.batch_id is None:
            return "Waiting for logs"
        statuses = {spec.key: self.graph.status(spec.key) for spec in STAGES}
        when = self._last_time.strftime("%H:%M:%S") if self._last_time else ""

        if BLOCKED in statuses.values():
            return "Blocked · kill switch is on"
        store = statuses["store"]
        failed = [k for k, s in statuses.items() if s == FAILED]
        if store == SKIPPED:
            return f"Last run {when} · ML step failed, batch dropped"
        if store == DONE:
            data = self._last_store or {}
            parts = [f"Last run {when}"]
            if "records" in data:
                parts.append(f"{data['records']:,} logs")
            if "alerts" in data:
                n = data["alerts"]
                parts.append(f"{n} alert{'' if n == 1 else 's'}")
            if "seconds" in data:
                parts.append(f"{data['seconds']:.1f} s")
            if failed:
                parts.append("ML step failed")
            return " · ".join(parts)
        running = next((k for k, s in statuses.items() if s == ACTIVE), None)
        if running is None:  # between two stages
            running = next((k for k, s in statuses.items() if s == IDLE), "store")
        return f"Running · {STAGE_LABELS[running]}"

    def _update_summary(self) -> None:
        text = self.summary_text()
        self.summary_label.setText(text)
        self.summary_label.setToolTip(text)
