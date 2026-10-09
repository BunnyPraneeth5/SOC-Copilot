"""Header status chips (UX-9).

Compact, clickable chips in the header — the only place the app shows
system status: pipeline, ingestion, online enrichment, the emergency kill
switch, model integrity, threat-intel providers and model drift. Each has
a coloured dot and a tooltip with details; clicking a chip asks
MainWindow to open Settings at that section.

``chip_states`` is a pure function so the mapping from backend status to
chip tone/text is testable without widgets.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from .theme import ThemeManager

CHIP_ORDER = ("pipeline", "ingestion", "enrichment", "kill_switch",
              "integrity", "providers", "drift")

# tone -> palette attribute for the chip's dot/border colour
_TONE_COLOR = {
    "good": "success",
    "warn": "warning",
    "bad": "danger",
    "info": "info",
    "neutral": "text_muted",
}


def _providers_state(online: bool, providers) -> tuple:
    if not online:
        return ("neutral", "Providers: Off",
                "Online enrichment is off, so no provider is queried.")
    if providers is None:
        return ("neutral", "Providers: ?", "Provider status unavailable.")
    total = len(providers)
    usable = sum(1 for s in providers if getattr(s, "usable", False))
    lines = [
        f"{getattr(s, 'display_name', s.key)}: {s.state.value}"
        + (f" — {s.detail}" if getattr(s, "detail", "") else "")
        for s in providers
    ]
    offline = any(s.state.value == "Offline" for s in providers)
    if usable == 0 or offline:
        tone = "warn"
    else:
        tone = "good"
    return (tone, f"Providers: {usable}/{total}", "\n".join(lines))


def _drift_state(drift) -> tuple:
    if not drift or not drift.get("available"):
        return ("neutral", "Drift: N/A", "Drift monitoring is not available.")
    level = drift.get("level")
    if not level:
        return ("info", "Drift: Collecting",
                "Not enough analysed data yet for a drift report.")
    level = str(level).upper()
    tone = {"NONE": "good", "LOW": "good", "MODERATE": "warn",
            "HIGH": "bad", "CRITICAL": "bad"}.get(level, "neutral")
    tip = drift.get("summary") or f"Latest drift level: {level.title()}"
    return (tone, f"Drift: {level.title()}", str(tip))


def _pipeline_state(stats: dict, security: dict) -> tuple:
    if not stats.get("pipeline_loaded"):
        return ("warn", "Pipeline: Loading", "ML models are initialising.")
    text_model = (security.get("text_log_model", {}) or {}).get("loaded")
    lines = ["ML models loaded — ready for analysis",
             "Text-log model: " + ("loaded" if text_model else "rules fallback")]
    return ("good", "Pipeline: Active", "\n".join(lines))


def _ingestion_state(stats: dict) -> tuple:
    running = stats.get("running", False)
    sources = stats.get("sources_count", 0)
    dropped = stats.get("dropped_count", 0)
    lines = [f"Sources: {sources}",
             f"Buffer: {stats.get('size', 0)}/{stats.get('max_size', 10000)}"]
    if dropped:
        lines.append(f"Dropped: {dropped}")
    suppressed = (stats.get("deduplication", {}) or {}).get("suppressed_count", 0)
    if suppressed:
        lines.append(f"Suppressed benign duplicates: {suppressed}")
    if not (stats.get("permission_check", {}) or {}).get("has_permission", True):
        lines.append("Permissions: Limited — run as admin for system logs")
    tip = "\n".join(lines)
    if stats.get("shutdown_flag"):
        return ("warn", "Ingestion: Stopped", tip)
    if running and sources > 0:
        return ("warn" if dropped else "info", f"Ingestion: Active ({sources})", tip)
    if sources > 0:
        return ("neutral", f"Ingestion: Configured ({sources})", tip)
    return ("neutral", "Ingestion: Not Started", tip)


def chip_states(stats: dict, drift: dict | None = None,
                providers: list | None = None) -> dict:
    """Map backend status to ``{chip: (tone, text, tooltip)}``."""
    stats = stats or {}
    security = stats.get("security", {}) or {}
    online = bool(security.get("online_enrichment_enabled", False))
    strict = bool(security.get("strict_model_integrity", False))
    integrity = security.get("model_integrity", {}) or {}

    states = {
        "pipeline": _pipeline_state(stats, security),
        "ingestion": _ingestion_state(stats),
    }
    if online:
        states["enrichment"] = ("warn", "Enrichment: Online",
                                "Online threat-intel lookups are enabled — "
                                "indicators are sent to external providers.")
    else:
        states["enrichment"] = ("neutral", "Enrichment: Offline",
                                "Offline mode: investigation reports use "
                                "local data only.")

    if stats.get("shutdown_flag"):
        states["kill_switch"] = ("bad", "Kill switch: ON",
                                 "Emergency stop active — ML processing halted.")
    else:
        states["kill_switch"] = ("good", "Kill switch: Off",
                                 "Emergency stop is not engaged.")

    # Same wording as the Settings "Model Integrity" indicator
    verified = len(integrity.get("verified_files", []) or [])
    if integrity.get("is_valid") is False:
        detail = integrity.get("error") or "Model hash check failed."
        states["integrity"] = ("bad", "Integrity: Failed", str(detail))
    elif strict:
        states["integrity"] = ("good", "Integrity: Strict",
                               f"Strict model integrity on — {verified} "
                               "model files verified.")
    else:
        states["integrity"] = ("info", "Integrity: Dev mode",
                               "Strict model integrity is off "
                               f"({verified} model files verified).")

    states["providers"] = _providers_state(online, providers)
    states["drift"] = _drift_state(drift)
    return states


class StatusChip(QPushButton):
    """Flat pill button: coloured border/dot by tone, opens Settings."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.tone = "neutral"
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._restyle()
        ThemeManager.instance().theme_changed.connect(self._restyle)

    def set_state(self, tone: str, text: str, tooltip: str = "") -> None:
        self.tone = tone if tone in _TONE_COLOR else "neutral"
        self.setText(text)
        self.setToolTip(f"{tooltip}\n\nClick to open Settings".strip())
        self.setAccessibleName(text)
        self._restyle()

    @staticmethod
    def _dot(color: str) -> QIcon:
        px = QPixmap(16, 16)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(4, 4, 8, 8)
        painter.end()
        return QIcon(px)

    def _restyle(self) -> None:
        p = ThemeManager.instance().palette
        color = getattr(p, _TONE_COLOR[self.tone])
        self.setIcon(self._dot(color))
        self.setIconSize(QSize(12, 12))
        # Neutral outline; only problems get a coloured one
        border = p.danger if self.tone == "bad" else p.surface_alt
        self.setStyleSheet(f"""
            QPushButton {{
                color: {p.text};
                background-color: {p.surface};
                border: 1px solid {border};
                border-radius: 12px;
                min-height: 22px;
                padding: 0px 10px 0px 6px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background-color: {p.surface_alt}; border-color: {p.border}; }}
            QPushButton:focus {{ border: 1px solid {p.accent}; }}
        """)


class StatusChipBar(QWidget):
    """Row of the five status chips."""

    chip_clicked = pyqtSignal(str)  # chip name

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.chips = {}
        for name in CHIP_ORDER:
            chip = StatusChip(name)
            chip.clicked.connect(lambda _=False, n=name: self.chip_clicked.emit(n))
            layout.addWidget(chip)
            self.chips[name] = chip
        self.setLayout(layout)

    def update_states(self, states: dict) -> None:
        for name, (tone, text, tip) in states.items():
            chip = self.chips.get(name)
            if chip is not None:
                chip.set_state(tone, text, tip)
