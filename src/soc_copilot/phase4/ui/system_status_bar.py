"""System status bar and banners.

The header bar is the single place the app shows system status: one row
of clickable chips (pipeline, ingestion, enrichment, kill switch, model
integrity, providers, drift). Each chip has a coloured dot, a short
value and a tooltip with the details; clicking it opens Settings at the
matching section.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy

from .components import icon_button
from .icons import icon_label
from .status_chips import StatusChipBar, chip_states
from .theme import PAGE_MARGIN, ThemeManager


def _palette():
    return ThemeManager.instance().palette


class SystemStatusBar(QFrame):
    """Header row of status chips."""

    status_update = pyqtSignal(dict)
    settings_requested = pyqtSignal(str)  # chip name -> open Settings there

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._probed_providers = None  # last "Check connectivity" result
        self._init_ui()
        checked = getattr(bridge, "providersChecked", None)
        if checked is not None and hasattr(checked, "connect"):
            try:
                checked.connect(self.set_probed_providers)
            except TypeError:
                pass  # Mock bridge attribute, not a signal
        # No own timer — refreshed by MainWindow's consolidated status timer
        self._update_status()

    def _init_ui(self):
        self._apply_theme()
        self.setFixedHeight(48)

        layout = QHBoxLayout()
        layout.setContentsMargins(PAGE_MARGIN, 0, PAGE_MARGIN, 0)
        layout.setSpacing(8)

        self.chip_bar = StatusChipBar()
        self.chip_bar.chip_clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.chip_bar)
        layout.addStretch()

        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            SystemStatusBar {{
                background-color: {p.bg};
                border-bottom: 1px solid {p.surface_alt};
            }}
        """)

    def refresh(self):
        """Public refresh entry (called by MainWindow's status timer)."""
        self._update_status()

    def _update_status(self):
        """Poll backend for current status"""
        try:
            stats = self.bridge.get_stats()
            if not isinstance(stats, dict):
                raise TypeError("stats unavailable")
            self._update_chips(stats)
            self.status_update.emit(stats)
        except Exception as e:
            self.chip_bar.chips["pipeline"].set_state(
                "bad", "Pipeline: Error", f"Status unavailable: {e}"
            )

    def _update_chips(self, stats: dict) -> None:
        try:
            drift = self.bridge.get_drift_status()
        except Exception:
            drift = None
        providers = self._probed_providers
        if providers is None:
            try:
                providers = self.bridge.get_provider_statuses()
            except Exception:
                providers = None
        if not isinstance(drift, dict):
            drift = None
        if not isinstance(providers, list):
            providers = None
        self.chip_bar.update_states(chip_states(stats, drift, providers))

    def set_probed_providers(self, statuses) -> None:
        """Show a connectivity-probe result (None = probe failed)."""
        if isinstance(statuses, list):
            self._probed_providers = statuses
        try:
            self._update_chips(self.bridge.get_stats())
        except Exception:
            pass


class _Banner(QFrame):
    """Slim tinted banner with an icon, message and optional controls."""

    def __init__(self, icon: str, token: str, bg_token: str):
        super().__init__()
        self._token, self._bg_token = token, bg_token
        # Never take spare height from the page below (on short pages the
        # banner used to grow to half the window).
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._layout = QHBoxLayout()
        self._layout.setContentsMargins(14, 8, 10, 8)
        self._layout.setSpacing(10)
        self._layout.addWidget(icon_label(icon, token, 18))
        self.setLayout(self._layout)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        p = _palette()
        accent = getattr(p, self._token)
        self.setStyleSheet(f"""
            {type(self).__name__} {{
                background-color: {getattr(p, self._bg_token)};
                border: 1px solid {accent};
                border-radius: 6px;
                margin: 8px {PAGE_MARGIN}px 0px {PAGE_MARGIN}px;
            }}
        """)
        self._style_children(p, accent)

    def _style_children(self, p, accent):
        pass


class PermissionBanner(_Banner):
    """Warning banner for permission issues"""

    dismissed = pyqtSignal()

    def __init__(self, message: str, icon: str = "alert-triangle"):
        super().__init__("alert-triangle", "warning", "warning_bg")

        self._msg_label = QLabel(message)
        self._msg_label.setWordWrap(True)
        self._layout.addWidget(self._msg_label, 1)

        self._action_btn = QLabel("Run as Admin")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout.addWidget(self._action_btn)

        self._close_btn = icon_button("x", "Dismiss", "text_muted")
        self._close_btn.setProperty("variant", "ghost")
        self._close_btn.setFixedSize(26, 26)
        self._close_btn.clicked.connect(self._dismiss)
        self._layout.addWidget(self._close_btn)
        self._apply_theme()

    def _style_children(self, p, accent):
        if getattr(self, "_action_btn", None) is None:
            return
        self._msg_label.setStyleSheet(f"color: {p.text}; font-size: 12px;")
        self._action_btn.setStyleSheet(
            f"color: {accent}; font-size: 12px; font-weight: 600; "
            "text-decoration: underline; padding: 2px 8px;"
        )

    def _dismiss(self):
        self.hide()
        self.dismissed.emit()


class KillSwitchBanner(_Banner):
    """Critical banner when kill switch is active"""

    def __init__(self):
        super().__init__("alert-octagon", "danger", "danger_bg")

        self._msg = QLabel("Kill switch active")
        self._layout.addWidget(self._msg)
        self._desc = QLabel(
            "All ML processing is halted. Edit config/kill_switch.yaml or run "
            "'soc-copilot killswitch off' to resume."
        )
        self._desc.setWordWrap(True)
        self._layout.addWidget(self._desc, 1)
        self._apply_theme()
        self.hide()  # Hidden by default

    def _style_children(self, p, accent):
        if getattr(self, "_desc", None) is None:
            return
        self._msg.setStyleSheet(f"color: {accent}; font-size: 13px; font-weight: 600;")
        self._desc.setStyleSheet(f"color: {p.text}; font-size: 12px;")

    def show_if_active(self, is_active: bool):
        if is_active:
            self.show()
        else:
            self.hide()
