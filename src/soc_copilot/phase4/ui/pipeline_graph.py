"""Live pipeline graph (Milestone 6a).

A ``QGraphicsView`` showing the analysis pipeline as nodes joined by
curved edges: a text lane (text-log ML/rules, brute-force correlation) and
a flow lane (routing, then the ML pipeline: preprocess, features,
detection) merging into alerts and store. Each node shows the status of
the stage for the current batch, fed by ``StageEvent``s that
``ControllerBridge.pipelineStageUpdated`` relays from the controller.

The three ML stages sit in an "ML pipeline" group that can be collapsed
into a single node; the collapsed node shows the stage it is on and the
worst outcome inside it, so a failure is never hidden.

All colours are theme tokens resolved at paint time, so a theme switch
only needs a repaint.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QSizePolicy,
)

from soc_copilot.phase4.ui.icons import pixmap
from soc_copilot.phase4.ui.theme import FONT_FAMILY, ThemeManager

# Stage keys match soc_copilot.phase4.controller.schemas.PIPELINE_STAGES
# (not imported: the UI only needs the strings carried by StageEvent).
ML_STAGES = ("preprocess", "features", "detect")
ML_GROUP = "ml"

IDLE, ACTIVE, DONE, SKIPPED, FAILED, BLOCKED = (
    "idle", "active", "done", "skipped", "failed", "blocked",
)

STATUS_TEXT = {
    IDLE: "Idle",
    ACTIVE: "Running",
    DONE: "Done",
    SKIPPED: "Skipped",
    FAILED: "Failed",
    BLOCKED: "Blocked",
}

# status -> palette token for border, status text and tinted fill
STATUS_TOKEN = {
    IDLE: "border",
    ACTIVE: "accent",
    DONE: "success",
    SKIPPED: "text_muted",
    FAILED: "danger",
    BLOCKED: "warning",
}


@dataclass(frozen=True)
class StageSpec:
    key: str
    label: str
    icon: str


STAGES = (
    StageSpec("ingest", "Ingest", "upload"),
    StageSpec("text_detect", "Text ML", "file-text"),
    StageSpec("bf_correlate", "Brute force", "shield"),
    StageSpec("flow_route", "Routing", "activity"),
    StageSpec("preprocess", "Preprocess", "settings"),
    StageSpec("features", "Features", "bar-chart"),
    StageSpec("detect", "Detection", "zap"),
    StageSpec("alerts", "Alerts", "alert-triangle"),
    StageSpec("store", "Store", "database"),
)
STAGE_LABELS = {s.key: s.label for s in STAGES}
ML_GROUP_SPEC = StageSpec(ML_GROUP, "ML pipeline", "cpu")

EDGES = (
    ("ingest", "text_detect"),
    ("ingest", "flow_route"),
    ("text_detect", "bf_correlate"),
    ("bf_correlate", "alerts"),
    ("flow_route", "preprocess"),
    ("preprocess", "features"),
    ("features", "detect"),
    ("detect", "alerts"),
    ("alerts", "store"),
)

# Layout (scene units; the view scales the scene to fit)
NODE_W = 116
ML_NODE_W = 160  # collapsed group also shows the current sub-stage
NODE_H = 46
COL_STEP = 150
LANE_Y = {"text": 0, "mid": 59, "flow": 118}
GROUP_PAD = 10
GROUP_HEADER = 22

# (column, lane) per stage, expanded and collapsed ML group
LAYOUT_EXPANDED = {
    "ingest": (0, "mid"),
    "text_detect": (1, "text"),
    "bf_correlate": (2, "text"),
    "flow_route": (1, "flow"),
    "preprocess": (2, "flow"),
    "features": (3, "flow"),
    "detect": (4, "flow"),
    "alerts": (5, "mid"),
    "store": (6, "mid"),
}
LAYOUT_COLLAPSED = {
    "ingest": (0, "mid"),
    "text_detect": (1, "text"),
    "bf_correlate": (2, "text"),
    "flow_route": (1, "flow"),
    ML_GROUP: (2, "flow"),
    "alerts": (3, "mid"),
    "store": (4, "mid"),
}


def _token(name: str) -> QColor:
    return QColor(getattr(ThemeManager.instance().palette, name))


def _tinted(name: str, alpha: int) -> QColor:
    c = _token(name)
    c.setAlpha(alpha)
    return c


def _font(px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def aggregate_status(statuses: list[str]) -> str:
    """Single status for a group of stages (collapsed ML node).

    Failure wins, then blocked, then running. All skipped is skipped, all
    idle is idle, everything finished is done; a partly finished group
    with nothing running is between stages, so it still counts as running.
    """
    s = set(statuses)
    for status in (FAILED, BLOCKED, ACTIVE):
        if status in s:
            return status
    if s == {SKIPPED}:
        return SKIPPED
    if s == {IDLE}:
        return IDLE
    if IDLE not in s:
        return DONE
    return ACTIVE


# ---------------------------------------------------------------------------
# Scene items
# ---------------------------------------------------------------------------

class NodeItem(QGraphicsObject):
    """One stage: rounded card with icon, label and status line."""

    def __init__(self, spec: StageSpec, on_click=None, width: int = NODE_W):
        super().__init__()
        self.spec = spec
        self.width = width
        self.status = IDLE
        self.detail = ""
        self.note = ""  # extra status text, e.g. current ML sub-stage
        self._on_click = on_click
        self.setAcceptHoverEvents(on_click is not None)
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_tooltip()

    @property
    def key(self) -> str:
        return self.spec.key

    def status_text(self) -> str:
        text = STATUS_TEXT[self.status]
        return f"{text} · {self.note}" if self.note else text

    def set_status(self, status: str, detail: str = "", note: str = "") -> None:
        self.status = status
        self.detail = detail
        self.note = note
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self) -> None:
        tip = f"{self.spec.label}: {self.status_text()}"
        if self.detail:
            tip += f"\n{self.detail}"
        if self._on_click is not None:
            tip += "\nClick to expand"
        self.setToolTip(tip)

    def boundingRect(self) -> QRectF:
        return QRectF(-1, -1, self.width + 2, NODE_H + 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        token = STATUS_TOKEN[self.status]
        w = self.width
        rect = QRectF(0, 0, w, NODE_H)

        if self.status == IDLE:
            fill = _token("surface_alt")
        elif self.status == SKIPPED:
            fill = QColor(Qt.GlobalColor.transparent)
        else:
            fill = _tinted(token, 46)
        pen = QPen(_token(token), 1.5 if self.status == ACTIVE else 1.0)
        if self.status == SKIPPED:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)

        muted = self.status in (IDLE, SKIPPED)
        icon_token = "text_muted" if muted else token
        px = pixmap(self.spec.icon, icon_token, 32)
        painter.drawPixmap(QRectF(10, 15, 16, 16), px, QRectF(px.rect()))

        text_x = 34
        painter.setPen(_token("text_muted" if self.status == SKIPPED else "text"))
        painter.setFont(_font(12, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(text_x, 6, w - text_x - 18, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self.spec.label,
        )
        painter.setPen(_token("text_muted" if muted else token))
        painter.setFont(_font(11))
        status = painter.fontMetrics().elidedText(
            self.status_text(), Qt.TextElideMode.ElideRight,
            int(w - text_x - 6),
        )
        painter.drawText(
            QRectF(text_x, 24, w - text_x - 6, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            status,
        )

        if self._on_click is not None:  # collapsed group: expand marker
            chev = pixmap("chevron-right", "text_muted", 24)
            painter.drawPixmap(QRectF(w - 16, 4, 12, 12), chev, QRectF(chev.rect()))

    def mousePressEvent(self, event) -> None:
        if self._on_click is not None and event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class GroupFrame(QGraphicsObject):
    """Dashed frame + clickable "ML pipeline" header around the ML stages."""

    def __init__(self, on_click):
        super().__init__()
        self._rect = QRectF()
        self._on_click = on_click
        self.setZValue(-1)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("ML pipeline: click to collapse")

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = rect

    def header_rect(self) -> QRectF:
        return QRectF(self._rect.left(), self._rect.top(), self._rect.width(), GROUP_HEADER)

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-1, -1, 1, 1)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.header_rect())  # only the header takes clicks
        return path

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pen = QPen(_token("border"), 1.0, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(_tinted("surface_alt", 90)))
        painter.drawRoundedRect(self._rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        chev = pixmap("chevron-left", "text_muted", 24)
        # chevron-left rotated a quarter turn reads as "collapse"
        painter.save()
        centre = QPointF(self._rect.left() + 16, self._rect.top() + 12)
        painter.translate(centre)
        painter.rotate(-90)
        painter.drawPixmap(QRectF(-6, -6, 12, 12), chev, QRectF(chev.rect()))
        painter.restore()

        painter.setPen(_token("text_muted"))
        painter.setFont(_font(11, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(self._rect.left() + 26, self._rect.top() + 3, 200, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "ML pipeline",
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class EdgeItem(QGraphicsItem):
    """Curved connection; its colour follows the two endpoint statuses."""

    def __init__(self, src: NodeItem, dst: NodeItem):
        super().__init__()
        self.src = src
        self.dst = dst
        self.setZValue(-0.5)
        self._path = QPainterPath()
        self._head = QPolygonF()
        self.update_geometry()

    def set_endpoints(self, src: NodeItem, dst: NodeItem) -> None:
        self.src, self.dst = src, dst
        self.update_geometry()

    def update_geometry(self) -> None:
        self.prepareGeometryChange()
        a = self.src.pos() + QPointF(self.src.width, NODE_H / 2)
        b = self.dst.pos() + QPointF(0, NODE_H / 2) - QPointF(6, 0)
        bend = max((b.x() - a.x()) / 2, 12)
        path = QPainterPath(a)
        path.cubicTo(a + QPointF(bend, 0), b - QPointF(bend, 0), b)
        self._path = path
        self._head = QPolygonF([b + QPointF(6, 0), b + QPointF(0, -4), b + QPointF(0, 4)])

    def style(self) -> tuple[str, float, bool]:
        """(token, width, dashed) for the current endpoint statuses."""
        s, d = self.src.status, self.dst.status
        if SKIPPED in (s, d):
            return "text_muted", 1.0, True
        if s == DONE and d == ACTIVE:
            return "accent", 2.0, False
        if s == DONE and d in (DONE, FAILED, BLOCKED):
            return "success", 1.5, False
        return "border", 1.0, False

    def boundingRect(self) -> QRectF:
        return self._path.boundingRect().united(self._head.boundingRect()).adjusted(-3, -3, 3, 3)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        token, width, dashed = self.style()
        color = _token(token)
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(self._head)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------

class PipelineGraphWidget(QGraphicsView):
    """Read-only graph of the analysis pipeline for the latest batch."""

    mlCollapsedChanged = pyqtSignal(bool)
    MAX_SCALE = 1.25

    def __init__(self, parent=None, ml_collapsed: bool = False):
        super().__init__(parent)
        self.setObjectName("pipelineGraph")
        self.setAccessibleName("Pipeline graph")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(90)
        self.setStyleSheet("background: transparent;")

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self._batch_id: str | None = None
        self._ml_collapsed = ml_collapsed
        self.nodes: dict[str, NodeItem] = {}
        for spec in STAGES:
            node = NodeItem(spec)
            self._scene.addItem(node)
            self.nodes[spec.key] = node
        self.ml_node = NodeItem(ML_GROUP_SPEC, on_click=self._expand_ml, width=ML_NODE_W)
        self._scene.addItem(self.ml_node)
        self.group_frame = GroupFrame(on_click=self._collapse_ml)
        self._scene.addItem(self.group_frame)
        self.edges: list[tuple[str, str, EdgeItem]] = []
        for src, dst in EDGES:
            edge = EdgeItem(self.nodes[src], self.nodes[dst])
            self._scene.addItem(edge)
            self.edges.append((src, dst, edge))

        self._layout()
        self._update_description()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # -- state -------------------------------------------------------------

    @property
    def batch_id(self) -> str | None:
        return self._batch_id

    def status(self, stage: str) -> str:
        if stage == ML_GROUP:
            return self.ml_node.status
        return self.nodes[stage].status

    def detail(self, stage: str) -> str:
        if stage == ML_GROUP:
            return self.ml_node.detail
        return self.nodes[stage].detail

    def reset(self) -> None:
        """All stages back to idle (no batch)."""
        self._batch_id = None
        for node in self.nodes.values():
            node.set_status(IDLE)
        self._refresh_ml_node()
        self._refresh_edges()
        self._update_description()

    def apply_event(self, event) -> None:
        """Apply one ``StageEvent``; a new ``batch_id`` starts a fresh run."""
        node = self.nodes.get(getattr(event, "stage", None))
        status = getattr(event, "status", None)
        if node is None or status not in STATUS_TEXT:
            return
        if event.batch_id != self._batch_id:
            self.reset()
            self._batch_id = event.batch_id
        node.set_status(status, event.detail or "")
        self._refresh_ml_node()
        self._refresh_edges()
        self._update_description()

    def _refresh_ml_node(self) -> None:
        statuses = [self.nodes[s].status for s in ML_STAGES]
        status = aggregate_status(statuses)
        current = next(
            (s for s in ML_STAGES if self.nodes[s].status in (FAILED, ACTIVE)),
            None,
        )
        if current is None and status == ACTIVE:  # between two sub-stages
            current = next(s for s in ML_STAGES if self.nodes[s].status == IDLE)
        note = STAGE_LABELS[current] if current and status in (ACTIVE, FAILED) else ""
        detail = "\n".join(
            f"{STAGE_LABELS[s]}: {self.nodes[s].status_text()}"
            + (f" ({self.nodes[s].detail})" if self.nodes[s].detail else "")
            for s in ML_STAGES
        )
        self.ml_node.set_status(status, detail, note)

    def _refresh_edges(self) -> None:
        for _, _, edge in self.edges:
            edge.update()

    def _update_description(self) -> None:
        parts = [f"{spec.label} {STATUS_TEXT[self.nodes[spec.key].status].lower()}"
                 for spec in STAGES]
        self.setAccessibleDescription("; ".join(parts))

    # -- ML group ----------------------------------------------------------

    @property
    def ml_collapsed(self) -> bool:
        return self._ml_collapsed

    def set_ml_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._ml_collapsed:
            return
        self._ml_collapsed = collapsed
        self._layout()
        self.mlCollapsedChanged.emit(collapsed)

    def _collapse_ml(self) -> None:
        self.set_ml_collapsed(True)

    def _expand_ml(self) -> None:
        self.set_ml_collapsed(False)

    # -- layout ------------------------------------------------------------

    def _layout(self) -> None:
        collapsed = self._ml_collapsed
        layout = LAYOUT_COLLAPSED if collapsed else LAYOUT_EXPANDED
        ml_col = LAYOUT_COLLAPSED[ML_GROUP][0]

        def place(item, key):
            col, lane = layout[key]
            # columns right of the wider collapsed group shift over
            shift = ML_NODE_W - NODE_W if collapsed and col > ml_col else 0
            item.setPos(col * COL_STEP + shift, LANE_Y[lane])

        for key, node in self.nodes.items():
            visible = key in layout
            node.setVisible(visible)
            if visible:
                place(node, key)
        self.ml_node.setVisible(collapsed)
        if collapsed:
            place(self.ml_node, ML_GROUP)

        self.group_frame.setVisible(not collapsed)
        if not collapsed:
            first = self.nodes[ML_STAGES[0]].pos()
            last = self.nodes[ML_STAGES[-1]].pos()
            self.group_frame.set_rect(QRectF(
                first.x() - GROUP_PAD,
                first.y() - GROUP_HEADER - 6,
                last.x() - first.x() + NODE_W + 2 * GROUP_PAD,
                NODE_H + GROUP_HEADER + 6 + GROUP_PAD,
            ))

        for src, dst, edge in self.edges:
            a, b = self._endpoint(src), self._endpoint(dst)
            internal = a is b
            edge.setVisible(not internal)
            if not internal:
                edge.set_endpoints(a, b)

        bounds = QRectF()
        for item in self._scene.items():
            if item.isVisible():
                bounds = bounds.united(item.mapRectToScene(item.boundingRect()))
        self._scene.setSceneRect(bounds.adjusted(-8, -8, 8, 8))
        self._fit()

    def _endpoint(self, stage: str) -> NodeItem:
        if self._ml_collapsed and stage in ML_STAGES:
            return self.ml_node
        return self.nodes[stage]

    def _fit(self) -> None:
        rect = self._scene.sceneRect()
        view = self.viewport().rect()
        if rect.isEmpty() or view.isEmpty():
            return
        scale = min(view.width() / rect.width(), view.height() / rect.height(), self.MAX_SCALE)
        self.setTransform(QTransform.fromScale(scale, scale))
        self.centerOn(rect.center())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit()

    def heightForScene(self, width: int) -> int:
        """Height that shows the scene at ``width`` without letterboxing."""
        rect = self._scene.sceneRect()
        scale = min(width / rect.width(), self.MAX_SCALE)
        return int(rect.height() * scale) + 2

    def _on_theme_changed(self, *_args) -> None:
        self._scene.update()
        self.viewport().update()

    def wheelEvent(self, event) -> None:
        event.ignore()  # never scroll/zoom the graph; let the page scroll
