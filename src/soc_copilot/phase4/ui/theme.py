"""Central theme system for the SOC Copilot UI (UX-1).

One source of truth for colours / fonts / spacing. UX-2 will add a
persisted light/dark toggle on top of ``ThemeManager.set_theme``.

Colour mapping (legacy inline hex -> token) — DARK palette preserves the
existing look:

    #0a0a1a          bg            window / page background
    #16213e #1a1a2e  surface       cards, detail fields, panels
    #1a2744 #2a2a4e  surface_alt   card borders, secondary surfaces
    #0f1629 #0a1225  input_bg      line edits, tables, scroll areas
    #444444          border        group boxes, generic borders
    #2a3f5f          scrollbar     scroll handles, table header accents
    #ffffff          text          primary text
    #888888 #666666  text_muted    secondary / disabled text
      (+ #555 #888 #777 #999 #aaa #ccc #616161 #757575 #424242 #555555)
    #00d4ff          accent        cyan brand colour
    #00a8cc #00b4df  accent_hover  hover accent (+ #0088aa)
    #4CAF50 #388E3C  success       ok / active (+ #00ff88)
    #FFC107 #ffcc00  warning       warnings, amber states
    #f44336 #ff0000  danger        errors, destructive (+ #d32f2f)
    #2196F3 #3F51B5  info          informational blue
    #ff4444 #d32f2f  sev_critical  P0-Critical
    #ff8800 #f57c00  sev_high      P1-High
    #ffaa00 #ffa000  sev_medium    P2-Medium
    #757575          sev_low       P3-Low (was #ffffff-else fallbacks)
    #888888          sev_info      P4-Info / unknown priority fallback
    #4a0000 #2d0000  danger_bg     red banner backgrounds
      (+ #2d1a1a #1a0000 #4a2000 -> warning_bg overlap, nearest token)
    #2d2d00 #665c00  warning_bg    amber banner backgrounds
      (+ #2d1a00 #2a2000 #4a4000)
    #1a4d26 #0d2818  success_bg    green banner backgrounds (+ #004a2a)
    #0f3460 #1e3a5f  info_bg       blue banner backgrounds (+ #3a5f8f)
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, pyqtSignal


# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Palette:
    """Semantic colour tokens for one theme."""

    name: str
    bg: str
    surface: str
    surface_alt: str
    input_bg: str
    border: str
    scrollbar: str
    text: str
    text_muted: str
    text_inverse: str
    accent: str
    accent_hover: str
    success: str
    warning: str
    danger: str
    info: str
    sev_critical: str
    sev_high: str
    sev_medium: str
    sev_low: str
    sev_info: str
    danger_bg: str
    warning_bg: str
    success_bg: str
    info_bg: str


DARK = Palette(
    name="dark",
    bg="#0a0a1a",
    surface="#16213e",
    surface_alt="#1a2744",
    input_bg="#0f1629",
    border="#444444",
    scrollbar="#2a3f5f",
    text="#ffffff",
    text_muted="#888888",
    text_inverse="#0a0a1a",
    accent="#00d4ff",
    accent_hover="#00a8cc",
    success="#4CAF50",
    warning="#FFC107",
    danger="#f44336",
    info="#2196F3",
    sev_critical="#ff4444",
    sev_high="#ff8800",
    sev_medium="#ffaa00",
    sev_low="#757575",
    sev_info="#888888",
    danger_bg="#4a0000",
    warning_bg="#2d2d00",
    success_bg="#1a4d26",
    info_bg="#0f3460",
)

LIGHT = Palette(
    name="light",
    bg="#f5f6fa",
    surface="#ffffff",
    surface_alt="#e8eaf2",
    input_bg="#ffffff",
    border="#c8cdd8",
    scrollbar="#b8bfce",
    text="#1a1a2e",
    text_muted="#5a6072",
    text_inverse="#ffffff",
    accent="#007ea8",
    accent_hover="#00a8cc",
    success="#2e7d32",
    warning="#b26a00",
    danger="#c62828",
    info="#1565c0",
    sev_critical="#c62828",
    sev_high="#e65100",
    sev_medium="#f9a825",
    sev_low="#1565c0",
    sev_info="#5a6072",
    danger_bg="#f8d7d7",
    warning_bg="#f7ecd0",
    success_bg="#d8ecd8",
    info_bg="#d4e3f5",
)

_PALETTES = {p.name: p for p in (DARK, LIGHT)}


# ---------------------------------------------------------------------------
# Typography / spacing tokens
# ---------------------------------------------------------------------------

FONT_FAMILY = "Segoe UI"
FONT_SM = "10px"
FONT_MD = "12px"
FONT_LG = "13px"
FONT_XL = "16px"
RADIUS = "6px"
SPACING = 10


# ---------------------------------------------------------------------------
# Global stylesheet
# ---------------------------------------------------------------------------

def build_stylesheet(p: Palette) -> str:
    """Return the global QSS for a palette.

    Covers base widget styling plus named roles via Qt dynamic
    properties (``set_role``), e.g. ``QFrame[role="card"]``.
    """
    return f"""
    /* ----- base widgets ----- */
    QMainWindow, QDialog {{
        background-color: {p.bg};
        color: {p.text};
    }}
    QWidget {{
        font-family: "{FONT_FAMILY}";
        color: {p.text};
        background-color: {p.bg};
    }}
    QStatusBar {{
        background-color: {p.input_bg};
        color: {p.text_muted};
        padding: 5px 15px;
    }}
    QLabel {{
        color: {p.text};
        background: transparent;
    }}
    QLabel[role="muted"] {{
        color: {p.text_muted};
    }}
    QLabel[role="title"] {{
        color: {p.accent};
        font-size: {FONT_XL};
        font-weight: bold;
    }}
    QToolTip {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        padding: 4px;
    }}
    QMenu {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
    }}
    QMenu::item:selected {{
        background-color: {p.accent};
        color: {p.text_inverse};
    }}

    /* ----- buttons ----- */
    QPushButton {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {RADIUS};
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        border-color: {p.accent};
    }}
    QPushButton:disabled {{
        background-color: {p.surface_alt};
        color: {p.text_muted};
        border-color: {p.border};
    }}
    QPushButton[variant="primary"] {{
        background-color: {p.accent};
        color: {p.text_inverse};
        border: none;
        font-weight: bold;
    }}
    QPushButton[variant="primary"]:hover {{
        background-color: {p.accent_hover};
    }}
    QPushButton[variant="secondary"] {{
        background-color: transparent;
        color: {p.accent};
        border: 1px solid {p.accent};
    }}
    QPushButton[variant="secondary"]:hover {{
        background-color: {p.accent};
        color: {p.text_inverse};
    }}
    QPushButton[variant="danger"] {{
        background-color: {p.danger};
        color: {p.text_inverse};
        border: none;
    }}
    QPushButton[variant="ghost"] {{
        background-color: transparent;
        color: {p.text_muted};
        border: none;
    }}

    /* ----- inputs ----- */
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {{
        background-color: {p.input_bg};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {RADIUS};
        padding: 4px 8px;
        selection-background-color: {p.accent};
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        selection-background-color: {p.accent};
        selection-color: {p.text_inverse};
    }}

    /* ----- containers ----- */
    QGroupBox {{
        font-weight: bold;
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {RADIUS};
        margin-top: 10px;
        padding-top: 10px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }}
    QFrame[role="card"] {{
        background-color: {p.surface};
        border: 1px solid {p.surface_alt};
        border-radius: {RADIUS};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QTabWidget::pane {{
        border: none;
        background-color: {p.input_bg};
        border-radius: 8px;
    }}
    QTabBar::tab {{
        background-color: {p.bg};
        color: {p.text_muted};
        padding: 10px 20px;
        margin-right: 2px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    QTabBar::tab:selected {{
        background-color: {p.input_bg};
        color: {p.accent};
        font-weight: bold;
    }}

    /* ----- tables ----- */
    QTableWidget, QTableView {{
        background-color: {p.input_bg};
        alternate-background-color: {p.surface};
        color: {p.text};
        gridline-color: {p.surface_alt};
        border: 1px solid {p.border};
        selection-background-color: {p.surface_alt};
        selection-color: {p.text};
    }}
    QHeaderView::section {{
        background-color: {p.input_bg};
        color: {p.text};
        border: none;
        padding: 6px;
        font-weight: bold;
    }}

    /* ----- scrollbars ----- */
    QScrollBar:vertical {{
        background-color: {p.bg};
        width: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {p.scrollbar};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {p.info_bg};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {p.bg};
        height: 8px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {p.scrollbar};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ----- severity badge (QLabel[role="badge"][severity="..."]) ----- */
    QLabel[role="badge"][severity="critical"] {{
        background-color: {p.sev_critical}; color: {p.text_inverse};
        font-weight: bold; border-radius: 4px; padding: 4px 10px;
    }}
    QLabel[role="badge"][severity="high"] {{
        background-color: {p.sev_high}; color: {p.text_inverse};
        font-weight: bold; border-radius: 4px; padding: 4px 10px;
    }}
    QLabel[role="badge"][severity="medium"] {{
        background-color: {p.sev_medium}; color: {p.text_inverse};
        font-weight: bold; border-radius: 4px; padding: 4px 10px;
    }}
    QLabel[role="badge"][severity="low"] {{
        background-color: {p.sev_low}; color: {p.text_inverse};
        font-weight: bold; border-radius: 4px; padding: 4px 10px;
    }}
    QLabel[role="badge"][severity="info"] {{
        background-color: {p.sev_info}; color: {p.text_inverse};
        font-weight: bold; border-radius: 4px; padding: 4px 10px;
    }}
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def color(token: str) -> str:
    """Resolve a palette token name to its current hex value."""
    return getattr(ThemeManager.instance().palette, token)


def severity_key(priority: str) -> str:
    """Map any priority label form to a severity token suffix."""
    p = (priority or "").lower()
    if "critical" in p or p.startswith("p0"):
        return "critical"
    if "high" in p or p.startswith("p1"):
        return "high"
    if "medium" in p or p.startswith("p2"):
        return "medium"
    if "low" in p or p.startswith("p3"):
        return "low"
    return "info"


def severity_color(priority: str) -> str:
    """Return the palette colour for a priority label.

    Accepts "P0-Critical".."P4-Info", bare words (critical/high/medium/
    low/info); unknown values fall back to the info/muted colour.
    """
    return getattr(
        ThemeManager.instance().palette, f"sev_{severity_key(priority)}"
    )


def set_role(widget, role: str, **props) -> None:
    """Set the ``role`` dynamic property (plus extras) and re-polish."""
    widget.setProperty("role", role)
    for key, value in props.items():
        widget.setProperty(key, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


# ---------------------------------------------------------------------------
# Theme manager (singleton)
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    """Application-wide theme holder.

    ``set_theme(name)`` switches the active palette, re-applies the
    global stylesheet to ``QApplication.instance()`` and emits
    ``theme_changed``.
    """

    theme_changed = pyqtSignal(object)  # Palette

    _instance: "ThemeManager | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._palette = DARK

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def palette(self) -> Palette:
        return self._palette

    def set_theme(self, name: str) -> None:
        """Switch theme by name ('dark' | 'light')."""
        if name not in _PALETTES:
            raise ValueError(
                f"Unknown theme '{name}'; expected one of {sorted(_PALETTES)}"
            )
        self._palette = _PALETTES[name]
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None
        if app is not None:
            self.apply(app)
        self.theme_changed.emit(self._palette)

    def apply(self, app) -> None:
        """Apply the current palette's global stylesheet to an app."""
        app.setStyleSheet(build_stylesheet(self._palette))
