"""Central theme system for the SOC Copilot UI (UX-1).

One source of truth for colours / fonts / spacing. UX-2 adds the
persisted light/dark toggle (``QSettings`` / ``SOC_COPILOT_THEME``) and
Okabe-Ito colour-blind-safe severity overrides on top of it.

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

import os
from dataclasses import dataclass, replace

from PyQt6.QtCore import QObject, QSettings, pyqtSignal


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
    border="#6c6c6c",
    scrollbar="#2a3f5f",
    text="#ffffff",
    text_muted="#898989",
    text_inverse="#0a0a1a",
    accent="#00d4ff",
    accent_hover="#00a8cc",
    success="#72c275",
    warning="#FFC107",
    danger="#f54c40",
    info="#39a1f4",
    sev_critical="#ff4444",
    sev_high="#ff8800",
    sev_medium="#ffaa00",
    sev_low="#9d9d9d",
    sev_info="#898989",
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
    border="#838fa7",
    scrollbar="#b8bfce",
    text="#1a1a2e",
    text_muted="#5a6072",
    text_inverse="#ffffff",
    accent="#007aa3",
    accent_hover="#00809c",
    success="#2b762f",
    warning="#9b5c00",
    danger="#bb2626",
    info="#1463bb",
    sev_critical="#bb2626",
    sev_high="#bd4300",
    sev_medium="#9b5c00",
    sev_low="#1463bb",
    sev_info="#5a6072",
    danger_bg="#f8d7d7",
    warning_bg="#f7ecd0",
    success_bg="#d8ecd8",
    info_bg="#d4e3f5",
)

_PALETTES = {p.name: p for p in (DARK, LIGHT)}

# Colour-blind-safe severity overrides (Okabe-Ito palette).
# Applied via dataclasses.replace() when the colour-blind flag is on;
# severities are always paired with their text label, never colour alone.
COLORBLIND_OVERRIDES = {
    "dark": {
        "sev_critical": "#E26400",  # vermillion
        "sev_high": "#E69F00",      # orange
        "sev_medium": "#F0E442",    # yellow
        "sev_low": "#56B4E9",       # sky blue
        "sev_info": "#999999",      # grey
    },
    "light": {
        "sev_critical": "#AF3900",  # dark vermillion
        "sev_high": "#946100",      # dark orange
        "sev_medium": "#766C00",    # dark yellow
        "sev_low": "#0068A3",       # blue
        "sev_info": "#5a6072",      # grey
    },
}

_SETTINGS_KEY_THEME = "appearance/theme"
_SETTINGS_KEY_COLORBLIND = "appearance/colorblind"
_SETTINGS_KEY_REDUCE_MOTION = "appearance/reduce_motion"
_ENV_THEME = "SOC_COPILOT_THEME"


# ---------------------------------------------------------------------------
# Typography / spacing tokens
# ---------------------------------------------------------------------------

FONT_FAMILY = "Segoe UI"
FONT_MONO = "Cascadia Mono"  # falls back to Consolas (see stylesheet)
FONT_SM = "10px"
FONT_MD = "12px"
FONT_LG = "13px"
FONT_XL = "16px"
RADIUS = "6px"
SPACING = 10

# Type scale (px) — page title / section title / body / caption
TYPE_PAGE_TITLE = "20px"
TYPE_SECTION = "14px"
TYPE_BODY = "13px"
TYPE_CAPTION = "11px"

# Layout rhythm: every page uses the same outer margin and gaps
PAGE_MARGIN = 24
PAGE_SPACING = 16


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
        border: none;
    }}
    QLabel[role="muted"] {{
        color: {p.text_muted};
    }}
    QLabel[role="title"] {{
        color: {p.accent};
        font-size: {FONT_XL};
        font-weight: bold;
    }}
    /* ----- type scale ----- */
    QLabel[role="pageTitle"] {{
        color: {p.text};
        font-size: {TYPE_PAGE_TITLE};
        font-weight: 600;
    }}
    QLabel[role="pageSubtitle"] {{
        color: {p.text_muted};
        font-size: {FONT_MD};
    }}
    QLabel[role="sectionTitle"] {{
        color: {p.text};
        font-size: {TYPE_SECTION};
        font-weight: 600;
    }}
    QLabel[role="caption"] {{
        color: {p.text_muted};
        font-size: {TYPE_CAPTION};
        font-weight: 600;
    }}
    QLabel[role="body"] {{
        color: {p.text};
        font-size: {TYPE_BODY};
    }}
    QLabel[role="mono"] {{
        font-family: "{FONT_MONO}", "Consolas", monospace;
        color: {p.text};
    }}
    QLabel[role="pill"] {{
        color: {p.text_muted};
        border: 1px solid {p.border};
        border-radius: 8px;
        padding: 0px 7px;
        font-size: 10px;
        font-weight: 600;
    }}
    QLabel[role="navBadge"] {{
        background-color: {p.surface_alt};
        color: {p.text};
        border-radius: 9px;
        padding: 1px 7px;
        font-size: {TYPE_CAPTION};
        font-weight: 600;
    }}
    QLabel[role="navBadge"][tone="critical"] {{
        background-color: {p.sev_critical};
        color: {p.text_inverse};
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
    QPushButton[variant="dangerOutline"] {{
        background-color: transparent;
        color: {p.danger};
        border: 1px solid {p.danger};
    }}
    QPushButton[variant="dangerOutline"]:hover {{
        background-color: {p.danger};
        color: {p.text_inverse};
    }}
    QPushButton[variant="ghost"] {{
        background-color: transparent;
        color: {p.text_muted};
        border: none;
    }}
    /* Disabled variants must look disabled — [variant] selectors above
       would otherwise win over the plain :disabled rule. */
    QPushButton[variant]:disabled {{
        background-color: {p.surface_alt};
        color: {p.text_muted};
        border: 1px solid {p.border};
        font-weight: normal;
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
    QComboBox {{
        min-width: 70px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        selection-background-color: {p.accent};
        selection-color: {p.text_inverse};
    }}
    QCheckBox, QRadioButton {{
        color: {p.text};
        background: transparent;
        spacing: 6px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {p.border};
        background-color: {p.input_bg};
    }}
    QCheckBox::indicator {{
        border-radius: 3px;
    }}
    QRadioButton::indicator {{
        border-radius: 7px;
    }}
    QCheckBox::indicator:checked {{
        background-color: {p.accent};
        border-color: {p.accent};
        image: none;
    }}
    QRadioButton::indicator:checked {{
        background-color: {p.accent};
        border-color: {p.accent};
        image: none;
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
    /* Data tables (components.style_table): row dividers instead of a
       grid, muted left-aligned column headers. */
    QTableWidget[role="data"] {{
        background-color: {p.input_bg};
        alternate-background-color: {p.input_bg};
        border: 1px solid {p.surface_alt};
        border-radius: {RADIUS};
        gridline-color: transparent;
    }}
    QTableWidget[role="data"]::item {{
        border-bottom: 1px solid {p.surface_alt};
        padding: 0px 10px;
    }}
    QTableWidget[role="data"]::item:selected {{
        background-color: {p.surface_alt};
        color: {p.text};
    }}
    QTableWidget[role="data"] QHeaderView::section {{
        background-color: {p.input_bg};
        color: {p.text_muted};
        border: none;
        border-bottom: 1px solid {p.surface_alt};
        padding: 8px 10px;
        font-size: {TYPE_CAPTION};
        font-weight: 600;
    }}
    QPushButton[variant="tableAction"] {{
        background-color: transparent;
        color: {p.accent};
        border: 1px solid {p.border};
        border-radius: 4px;
        padding: 2px 10px;
        margin: 4px 8px;
        font-size: {FONT_MD};
    }}
    QPushButton[variant="tableAction"]:hover {{
        border-color: {p.accent};
        background-color: {p.surface_alt};
    }}
    QPushButton[variant="tableAction"]:disabled {{
        color: {p.text_muted};
        border-color: {p.surface_alt};
        background-color: transparent;
    }}
    QPushButton[variant="icon"] {{
        background-color: transparent;
        border: 1px solid {p.border};
        border-radius: {RADIUS};
        padding: 5px;
    }}
    QPushButton[variant="icon"]:hover {{
        border-color: {p.accent};
        background-color: {p.surface_alt};
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
    /* ----- keyboard focus + pressed (a11y) ----- */
    /* Focus borders are 2px; padding shrinks by the extra border width
       so focused widgets keep their size instead of shifting the layout. */
    QPushButton:focus {{
        border: 2px solid {p.accent};
        padding: 5px 11px;
    }}
    QPushButton[variant="primary"]:focus,
    QPushButton[variant="danger"]:focus {{
        border: 2px solid {p.text};
        padding: 4px 10px;
    }}
    QPushButton[variant="ghost"]:focus {{
        padding: 4px 10px;
    }}
    QPushButton[variant="icon"]:focus {{
        padding: 4px;
    }}
    QPushButton[variant="tableAction"]:focus {{
        padding: 1px 9px;
    }}
    QPushButton:pressed {{
        background-color: {p.surface_alt};
    }}
    /* Filled variants keep their inverse text, so they need their own
       pressed fill — the generic surface_alt would hide the label. */
    QPushButton[variant="primary"]:pressed {{
        background-color: {p.accent_hover};
    }}
    QPushButton[variant="secondary"]:pressed {{
        background-color: {p.accent_hover};
        color: {p.text_inverse};
    }}
    QPushButton[variant="danger"]:pressed {{
        background-color: {p.sev_critical};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus,
    QPlainTextEdit:focus, QSpinBox:focus {{
        border: 2px solid {p.accent};
        padding: 3px 7px;
    }}
    QLineEdit:hover, QComboBox:hover, QTextEdit:hover,
    QPlainTextEdit:hover, QSpinBox:hover {{
        border-color: {p.accent};
    }}
    QCheckBox:focus, QRadioButton:focus {{
        color: {p.accent};
    }}
    QTabBar::tab:hover {{
        color: {p.text};
    }}
    QTableView::item:hover {{
        background-color: {p.surface_alt};
    }}

    /* ----- toast notifications (motion.show_toast) ----- */
    QLabel#toast {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-left: 4px solid {p.info};
        border-radius: {RADIUS};
        padding: 10px 14px;
        font-size: 12px;
    }}
    QLabel#toast[role="toastSuccess"] {{ border-left-color: {p.success}; }}
    QLabel#toast[role="toastWarning"] {{ border-left-color: {p.warning}; }}
    QLabel#toast[role="toastError"] {{ border-left-color: {p.danger}; }}
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
        self._base_name = "dark"
        self._colorblind = False
        self._reduce_motion = False
        self._palette = DARK
        self._settings: QSettings | None = None

    @classmethod
    def instance(cls) -> "ThemeManager":
        inst = cls._instance
        if inst is not None:
            # The C++ QObject is destroyed together with its QApplication;
            # resurrect the manager if that happened.
            try:
                from PyQt6.sip import isdeleted
                if isdeleted(inst):
                    inst = None
            except Exception:
                inst = None
        if inst is None:
            inst = ThemeManager()
            cls._instance = inst
        return inst

    @property
    def palette(self) -> Palette:
        return self._palette

    @property
    def theme_name(self) -> str:
        return self._base_name

    @property
    def colorblind(self) -> bool:
        return self._colorblind

    @property
    def reduce_motion(self) -> bool:
        return self._reduce_motion

    # ----- effective palette ------------------------------------------------

    def _rebuild_palette(self) -> None:
        base = _PALETTES[self._base_name]
        overrides = (
            COLORBLIND_OVERRIDES[self._base_name] if self._colorblind else {}
        )
        self._palette = replace(base, **overrides)

    def _refresh(self) -> None:
        """Rebuild the effective palette, re-apply QSS, notify listeners."""
        self._rebuild_palette()
        try:
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None
        if app is not None:
            self.apply(app)
        try:
            self.theme_changed.emit(self._palette)
        except RuntimeError:
            # Underlying QObject already deleted (e.g. app teardown)
            pass

    # ----- mutations ---------------------------------------------------------

    def set_theme(self, name: str) -> None:
        """Switch theme by name ('dark' | 'light')."""
        if name not in _PALETTES:
            raise ValueError(
                f"Unknown theme '{name}'; expected one of {sorted(_PALETTES)}"
            )
        self._base_name = name
        self._refresh()
        self.save_preferences()

    def set_colorblind(self, enabled: bool) -> None:
        """Toggle the colour-blind-safe severity overrides."""
        self._colorblind = bool(enabled)
        self._refresh()
        self.save_preferences()

    def set_reduce_motion(self, enabled: bool) -> None:
        """Turn UI transitions off (accessibility). No restyle needed."""
        self._reduce_motion = bool(enabled)
        self.save_preferences()

    # ----- persistence ---------------------------------------------------------

    def _settings_or_default(self, settings: QSettings | None) -> QSettings:
        if settings is not None:
            return settings
        if self._settings is None:
            self._settings = QSettings("SOC Copilot", "SOC Copilot")
        return self._settings

    def load_preferences(self, settings: QSettings | None = None) -> None:
        """Load theme preferences.

        Precedence: saved setting > SOC_COPILOT_THEME env var > "dark".
        Invalid values fall back to "dark". Colour-blind flag comes only
        from the saved setting.
        """
        if settings is not None:
            self._settings = settings
        s = self._settings_or_default(settings)
        saved = s.value(_SETTINGS_KEY_THEME, None)
        if isinstance(saved, str) and saved in _PALETTES:
            self._base_name = saved
        else:
            env = os.environ.get(_ENV_THEME, "").strip().lower()
            self._base_name = env if env in _PALETTES else "dark"
        cb = s.value(_SETTINGS_KEY_COLORBLIND, False)
        self._colorblind = str(cb).lower() in ("true", "1", "yes", "on")
        rm = s.value(_SETTINGS_KEY_REDUCE_MOTION, False)
        self._reduce_motion = str(rm).lower() in ("true", "1", "yes", "on")
        self._refresh()

    def save_preferences(self, settings: QSettings | None = None) -> None:
        """Persist current theme + colour-blind flag."""
        s = self._settings_or_default(settings)
        s.setValue(_SETTINGS_KEY_THEME, self._base_name)
        s.setValue(_SETTINGS_KEY_COLORBLIND, self._colorblind)
        s.setValue(_SETTINGS_KEY_REDUCE_MOTION, self._reduce_motion)

    def apply(self, app) -> None:
        """Apply the current palette's global stylesheet to an app."""
        app.setStyleSheet(build_stylesheet(self._palette))
