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

Live system logs: ingestion sends a small batch every few seconds. Routine
batches (no alerts, nothing failed) only update a quiet "System logs: live"
line; batches that raise alerts or fail are shown and recorded like an
upload, so the graph always shows something worth looking at.

Replay (Milestone 6b): the card records the last ``MAX_RUNS`` runs in
memory; the play button replays one step by step. A replay is something the
analyst asked for, so it steps even with Reduce motion on (without fades or
packets). A live run arriving mid-replay takes over at once.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace

from PyQt6.QtCore import QRectF, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QSizePolicy, QVBoxLayout, QWidget,
)

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
MAX_RUNS = 20            # runs kept in memory for replay
REPLAY_TAG = "#replay"
SOURCE_SYSTEM_LOGS = "system_logs"  # = controller.schemas.SOURCE_SYSTEM_LOGS
MAX_PENDING_BATCHES = 5  # system batches held until they finish
LIVE_MAX_W = 300         # px for the live system-log line in the header
ML_AUTO_COLLAPSE_WIDTH = 900
GRAPH_MIN_H = 110
GRAPH_MAX_H = 165


def _palette():
    return ThemeManager.instance().palette


def _truthy(value) -> bool:
    return str(value).lower() in ("true", "1", "yes", "on")


def _source_name(source, label) -> str:
    """Short name of where a run came from, for labels and the summary."""
    if source == SOURCE_SYSTEM_LOGS:
        return "system logs"
    return label or ""


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
        self._runs: deque = deque(maxlen=MAX_RUNS)  # [{"id", "events", ...}]
        self._origins: dict = {}        # batch_id -> (source, label)
        self._pending_system: dict = {}  # batch_id -> events, until it ends
        self._replay_seq = 0
        self._replay_menu: QMenu | None = None
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
        # quiet live line for routine system-log batches; in the header so
        # the card is no taller (the full graph must still fit)
        self.live_label = QLabel()
        set_role(self.live_label, "pageSubtitle")
        self.live_label.setStyleSheet("font-size: 11px;")
        self.live_label.setMaximumWidth(LIVE_MAX_W)
        self.live_label.setVisible(False)
        self._live_text = ""
        header.addWidget(self.live_label)
        self.replay_btn = icon_button("play", "Replay a recent run", "text_muted")
        self.replay_btn.clicked.connect(self._show_replay_menu)
        header.addWidget(self.replay_btn)
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
        source, _ = self._origin(event)
        if source == SOURCE_SYSTEM_LOGS:
            self._on_system_event(event)
            return
        self._show_live(event)

    def _show_live(self, event) -> None:
        """A live run event for the graph (uploads, notable system batches)."""
        self._record(event)
        if self._queue and self.is_replay(self._queue[0].batch_id):
            # a live run takes over from a replay at once
            self._timer.stop()
            self._queue.clear()
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
        # fades/packets only with motion; a replay still steps without them
        self._apply(self._queue.popleft(), animate=motion_enabled(self))

    def _flush(self) -> None:
        self._timer.stop()
        while self._queue:
            self._apply(self._queue.popleft(), animate=False)

    @property
    def pending_events(self) -> int:
        return len(self._queue)

    # -- recording and replay -----------------------------------------------------

    @staticmethod
    def is_replay(batch_id) -> bool:
        return REPLAY_TAG in str(batch_id or "")

    def _origin(self, event) -> tuple:
        """(source, label) of the event's batch; uploads by default."""
        data = getattr(event, "data", None) or {}
        if event.stage == "ingest" and "source" in data:
            self._origins[event.batch_id] = (data["source"], data.get("source_label", ""))
            while len(self._origins) > 4 * MAX_RUNS:
                self._origins.pop(next(iter(self._origins)))
        return self._origins.get(event.batch_id, ("upload", ""))

    # -- live system logs ------------------------------------------------------

    @staticmethod
    def _batch_finished(event) -> bool:
        return ((event.stage == "store" and event.status in (DONE, SKIPPED))
                or (event.stage == "ingest" and event.status in (BLOCKED, SKIPPED)))

    @staticmethod
    def _batch_alerts(events) -> int:
        for e in reversed(events):
            data = getattr(e, "data", None) or {}
            if e.stage in ("store", "alerts") and e.status == DONE and "alerts" in data:
                return int(data["alerts"])
        return 0

    @classmethod
    def is_notable(cls, events) -> bool:
        """A system batch worth the graph: alerts, a failure or a block."""
        return (cls._batch_alerts(events) > 0
                or any(e.status in (FAILED, BLOCKED) for e in events))

    def _on_system_event(self, event) -> None:
        events = self._pending_system.setdefault(event.batch_id, [])
        events.append(event)
        while len(self._pending_system) > MAX_PENDING_BATCHES:  # never finished
            self._pending_system.pop(next(iter(self._pending_system)))
        if not self._batch_finished(event):
            return
        events = self._pending_system.pop(event.batch_id)
        self._update_live_line(events)
        if self.is_notable(events):
            for e in events:
                self._show_live(e)

    def live_text(self, events) -> str:
        stamp = getattr(events[-1], "timestamp", None)
        when = f" at {stamp.strftime('%H:%M:%S')}" if stamp else ""
        records = next((e.data.get("records") for e in events
                        if e.stage == "ingest" and e.status == DONE and e.data), None)
        if any(e.status == BLOCKED for e in events):
            outcome = "blocked by kill switch"
        elif any(e.status == FAILED for e in events):
            outcome = "analysis failed"
        else:
            n = self._batch_alerts(events)
            outcome = "no alerts" if n == 0 else f"{n} alert{'' if n == 1 else 's'}"
        count = f"{records} event{'' if records == 1 else 's'}" if records is not None else "batch"
        return f"System logs: live · {count}{when} · {outcome}"

    def _update_live_line(self, events) -> None:
        self._live_text = self.live_text(events)
        self.live_label.setToolTip(
            f"{self._live_text}\n\nLive Windows event ingestion. Batches "
            "without alerts only update this line; batches with alerts or "
            "failures appear on the graph."
        )
        self.live_label.setVisible(True)
        self._elide_live()

    @property
    def live_status(self) -> str:
        """Full live system-log line (the label may show it shortened)."""
        return self._live_text

    def _elide_live(self) -> None:
        fm = self.live_label.fontMetrics()
        self.live_label.setText(fm.elidedText(
            self._live_text, Qt.TextElideMode.ElideRight, LIVE_MAX_W))

    # -- recording -------------------------------------------------------------

    def _record(self, event) -> None:
        if not self._runs or self._runs[-1]["id"] != event.batch_id:
            source, label = self._origins.get(event.batch_id, ("upload", ""))
            self._runs.append({"id": event.batch_id, "events": [],
                               "source": source, "label": label})
        self._runs[-1]["events"].append(event)

    def recent_runs(self) -> list[dict]:
        """Recorded runs, newest first."""
        return list(reversed(self._runs))

    @staticmethod
    def run_label(run: dict) -> str:
        events = run["events"]
        stamp = getattr(events[0], "timestamp", None) if events else None
        parts = [stamp.strftime("%H:%M:%S") if stamp else "Run"]
        name = _source_name(run.get("source"), run.get("label"))
        if name:
            parts.append(name)
        final = {e.stage: e for e in events if e.status != ACTIVE}
        store = final.get("store")
        if any(e.status == BLOCKED for e in events):
            parts.append("blocked by kill switch")
        elif store is not None and store.status == DONE:
            data = store.data or {}
            if "records" in data:
                parts.append(f"{data['records']:,} logs")
            if "alerts" in data:
                n = data["alerts"]
                parts.append(f"{n} alert{'' if n == 1 else 's'}")
        elif store is not None and store.status == SKIPPED:
            parts.append("batch dropped")
        else:
            parts.append("incomplete")
        return " · ".join(parts)

    def replay(self, index: int = 0) -> bool:
        """Replay recorded run ``index`` (0 = newest) step by step."""
        runs = self.recent_runs()
        if not 0 <= index < len(runs) or not runs[index]["events"]:
            return False
        self._replay_seq += 1
        replay_id = f"{runs[index]['id']}{REPLAY_TAG}{self._replay_seq}"
        self._timer.stop()
        self._queue.clear()
        self._queue.extend(replace(e, batch_id=replay_id) for e in runs[index]["events"])
        self._play_next()
        self._timer.start()
        return True

    def build_replay_menu(self) -> QMenu:
        menu = QMenu(self)
        runs = self.recent_runs()
        if not runs:
            empty = menu.addAction("No runs yet: upload logs first")
            empty.setEnabled(False)
        for i, run in enumerate(runs):
            action = menu.addAction(("Replay last run · " if i == 0 else "") + self.run_label(run))
            action.triggered.connect(lambda _checked=False, i=i: self.replay(i))
        return menu

    def _show_replay_menu(self) -> None:
        if self._replay_menu is not None:
            self._replay_menu.deleteLater()
        self._replay_menu = self.build_replay_menu()
        self._replay_menu.popup(self.replay_btn.mapToGlobal(self.replay_btn.rect().bottomLeft()))

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
        text = self._summary_body()
        return f"Replay · {text}" if self.is_replay(self.graph.batch_id) else text

    def _summary_body(self) -> str:
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
            name = _source_name(*self._origins.get(self.graph.batch_id.split(REPLAY_TAG)[0], (None, None)))
            if name:
                parts.append(name)
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
