"""Investigation steps graph for the report drawer (Milestone 6b).

Shows the MCP investigation as a small graph: Lookup (cache, internal
address and online-enrichment checks), then Recon, Reputation and Shodan in
parallel, then the Report agent (LLM). Fed by ``StageEvent``s that
``ControllerBridge.investigationStageUpdated`` relays from the orchestrator.

The panel has a header with a one-line summary and a collapse button; the
collapsed state is saved.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .components import icon_button
from .icons import icon_label, set_icon
from .pipeline_graph import (
    ACTIVE,
    DONE,
    FAILED,
    IDLE,
    SKIPPED,
    TIMEOUT,
    GraphSpec,
    PipelineGraphWidget,
    StageSpec,
)
from .theme import ThemeManager, set_role

# Stage keys match soc_copilot.mcp.orchestrator.INVESTIGATION_STAGES
AGENT_STAGES = ("recon", "reputation", "shodan")

INVESTIGATION_GRAPH = GraphSpec(
    name="Investigation steps",
    stages=(
        StageSpec("lookup", "Lookup", "database"),
        StageSpec("recon", "Recon", "globe"),
        StageSpec("reputation", "Reputation", "shield"),
        StageSpec("shodan", "Shodan", "search"),
        StageSpec("report", "Report", "file-text"),
    ),
    edges=(
        ("lookup", "recon"),
        ("lookup", "reputation"),
        ("lookup", "shodan"),
        ("recon", "report"),
        ("reputation", "report"),
        ("shodan", "report"),
    ),
    lanes={"top": 0, "mid": 52, "bottom": 104},
    layout={
        "lookup": (0, "mid"),
        "recon": (1, "top"),
        "reputation": (1, "mid"),
        "shodan": (1, "bottom"),
        "report": (2, "mid"),
    },
    # narrower than the dashboard graph: the drawer can be 320 px wide
    node_width=112,
    col_step=132,
)
LABELS = INVESTIGATION_GRAPH.labels

KEY_COLLAPSED = "drawer/investigation_steps_collapsed"
GRAPH_MIN_H = 90
GRAPH_MAX_H = 150


def _truthy(value) -> bool:
    return str(value).lower() in ("true", "1", "yes", "on")


def summarize(statuses: dict, lookup_detail: str = "", seconds: float | None = None) -> str:
    """One-line summary of an investigation from its stage statuses."""
    if all(s == IDLE for s in statuses.values()):
        return "Waiting for the first step"
    running = [LABELS[k] for k in AGENT_STAGES + ("lookup", "report") if statuses.get(k) == ACTIVE]
    if running:
        return "Running · " + ", ".join(running)
    if statuses.get("lookup") == DONE and all(
        statuses.get(k) == SKIPPED for k in AGENT_STAGES + ("report",)
    ):
        return lookup_detail or "Finished without lookups"
    if statuses.get("report") == IDLE:
        return "Running"
    parts = []
    for status, word in ((TIMEOUT, "timed out"), (FAILED, "failed"), (SKIPPED, "skipped")):
        n = sum(1 for k in AGENT_STAGES if statuses.get(k) == status)
        if n:
            parts.append(f"{n} {word}")
    report = statuses.get("report")
    head = "Finished" if report == DONE else "Report " + {
        TIMEOUT: "timed out", FAILED: "failed", SKIPPED: "skipped",
    }.get(report, report)
    if seconds is not None and report != IDLE:
        head += f" in {seconds:.1f} s"
    return " · ".join([head, *parts])


class InvestigationGraphPanel(QWidget):
    """Header (title, summary, collapse) + investigation steps graph."""

    def __init__(self, settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("investigationSteps")
        self._settings = settings or ThemeManager.instance().settings()
        self._collapsed = _truthy(self._settings.value(KEY_COLLAPSED, False))
        self._events: list = []
        self._lookup_detail = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 6, 10, 6)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(icon_label("activity", "text_muted", 14))
        title = QLabel("Investigation steps")
        set_role(title, "sectionTitle")
        title.setStyleSheet("font-size: 12px;")
        header.addWidget(title)
        self.summary_label = QLabel()
        set_role(self.summary_label, "pageSubtitle")
        header.addWidget(self.summary_label, 1)
        self.toggle_btn = icon_button("chevron-up", "Hide steps", "text_muted")
        self.toggle_btn.setFixedSize(26, 26)
        self.toggle_btn.clicked.connect(self._on_toggle)
        header.addWidget(self.toggle_btn)
        layout.addLayout(header)

        self.graph = PipelineGraphWidget(spec=INVESTIGATION_GRAPH)
        self.graph.setMinimumHeight(0)
        layout.addWidget(self.graph)
        self._apply_collapsed()
        self._update_summary()

    # -- state ---------------------------------------------------------------

    @property
    def events(self) -> list:
        """Stage events of the investigation shown (copy)."""
        return list(self._events)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def start(self) -> None:
        """A new investigation: clear the graph."""
        self._events = []
        self._lookup_detail = ""
        self.graph.reset()
        self._update_summary()

    def apply_event(self, event, animate: bool | None = None) -> None:
        if event.batch_id != self.graph.batch_id:
            self._events = []
            self._lookup_detail = ""
        self.graph.apply_event(event, animate=animate)
        self._events.append(event)
        if event.stage == "lookup" and event.status == DONE:
            self._lookup_detail = event.detail or ""
        self._update_summary()

    def show_events(self, events: list) -> None:
        """Show a finished investigation (history), without animation."""
        self.start()
        for event in events:
            self.apply_event(event, animate=False)

    def _seconds(self) -> float | None:
        stamps = [e.timestamp for e in self._events if isinstance(getattr(e, "timestamp", None), datetime)]
        if len(stamps) < 2:
            return None
        return (max(stamps) - min(stamps)).total_seconds()

    def summary_text(self) -> str:
        statuses = {k: self.graph.status(k) for k in LABELS}
        return summarize(statuses, self._lookup_detail, self._seconds())

    def _update_summary(self) -> None:
        text = self.summary_text()
        self.summary_label.setText(text)
        self.summary_label.setToolTip(text)

    # -- collapse --------------------------------------------------------------

    def _on_toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._settings.setValue(KEY_COLLAPSED, self._collapsed)
        self._apply_collapsed()

    def _apply_collapsed(self) -> None:
        self.graph.setVisible(not self._collapsed)
        icon, tip = ("chevron-down", "Show steps") if self._collapsed else ("chevron-up", "Hide steps")
        set_icon(self.toggle_btn, icon, "text_muted", 16)
        self.toggle_btn.setToolTip(tip)
        self.toggle_btn.setAccessibleName(tip)
        self._fit_graph()

    def _fit_graph(self) -> None:
        if self._collapsed:
            return
        m = self.layout().contentsMargins()
        width = max(self.width() - m.left() - m.right(), 1)
        height = max(GRAPH_MIN_H, min(GRAPH_MAX_H, self.graph.heightForScene(width)))
        self.graph.set_preferred_height(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_graph()
