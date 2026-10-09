"""System Status Bar - Consolidated Real-time Backend State Visualization

Two LED indicators with tooltip details:
- Pipeline: ML model status
- Ingestion: Log source, processing and permission status

followed by clickable status chips (UX-9) for enrichment, kill switch,
model integrity, threat-intel providers and drift.
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QFrame,
    QGraphicsDropShadowEffect, QToolTip
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from .theme import ThemeManager, set_role
from .status_chips import StatusChipBar, chip_states


def _palette():
    return ThemeManager.instance().palette


class StatusIndicator(QWidget):
    """LED-style status indicator with label and tooltip expansion"""

    @staticmethod
    def _color_for(name: str) -> str:
        p = _palette()
        return {
            "green": p.success,
            "yellow": p.warning,
            "red": p.danger,
            "blue": p.info,
            "gray": p.sev_low,
        }.get(name, p.sev_low)

    def __init__(self, label: str, initial_color: str = "gray"):
        super().__init__()
        self._color = initial_color
        self._details = []
        self._init_ui(label)
    
    def _init_ui(self, label: str):
        layout = QHBoxLayout()
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        
        # LED dot with glow effect
        self.led = QLabel("●")
        self.led.setFont(QFont("Segoe UI", 11))
        self._update_led_style()
        layout.addWidget(self.led)
        
        # Label
        self.label = QLabel(label)
        self.label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(self.label)

        # Value
        self.value = QLabel("")
        self.value.setFont(QFont("Segoe UI", 10))
        self.value.setStyleSheet(f"color: {_palette().accent};")
        layout.addWidget(self.value)

        # Info icon for tooltip
        self.info_icon = QLabel("ⓘ")
        self.info_icon.setFont(QFont("Segoe UI", 9))
        set_role(self.info_icon, "muted")
        self.info_icon.setCursor(Qt.CursorShape.WhatsThisCursor)
        self.info_icon.setVisible(False)
        layout.addWidget(self.info_icon)
        
        self.setLayout(layout)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        """Re-apply palette-derived styles after a theme switch."""
        p = _palette()
        self._update_led_style()
        self.value.setStyleSheet(f"color: {p.accent};")
        self.info_icon.setStyleSheet(f"color: {p.text_muted};")

    def _update_led_style(self):
        color = self._color_for(self._color)
        # Text shadow for glow effect
        self.led.setStyleSheet(f"""
            color: {color};
        """)
    
    def set_state(self, color: str, value: str = "", details: list = None):
        """Set indicator state with optional tooltip details"""
        self._color = color
        self._update_led_style()
        self.value.setText(value)
        
        if details:
            self._details = details
            self.info_icon.setVisible(True)
            tooltip_text = "\n".join([f"• {d}" for d in details])
            self.setToolTip(tooltip_text)
        else:
            self._details = []
            self.info_icon.setVisible(False)
            self.setToolTip("")
    
    def enterEvent(self, event):
        if self._details:
            self.info_icon.setStyleSheet(f"color: {_palette().accent};")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.info_icon.setStyleSheet(f"color: {_palette().text_muted};")
        super().leaveEvent(event)


class SystemStatusBar(QFrame):
    """Status bar: Pipeline + Ingestion LEDs and the UX-9 status chips."""

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
        self._separators = []
        self._apply_theme()
        self.setFixedHeight(44)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 0, 15, 0)
        layout.setSpacing(14)
        
        # Pipeline indicator (combines old Pipeline LED)
        self.pipeline_led = StatusIndicator("Pipeline")
        layout.addWidget(self.pipeline_led)
        
        # Separator
        layout.addWidget(self._separator())
        
        # Ingestion indicator (combines old Ingestion + Buffer LEDs)
        self.ingestion_led = StatusIndicator("Ingestion")
        layout.addWidget(self.ingestion_led)
        
        # Separator
        layout.addWidget(self._separator())
        
        # Status chips: enrichment, kill switch, integrity, providers, drift
        self.chip_bar = StatusChipBar()
        self.chip_bar.chip_clicked.connect(self.settings_requested.emit)
        layout.addWidget(self.chip_bar)

        layout.addStretch()

        # Last update time
        self.update_time = QLabel("")
        self.update_time.setFont(QFont("Segoe UI", 9))
        set_role(self.update_time, "muted")
        layout.addWidget(self.update_time)
        
        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            SystemStatusBar {{
                background-color: {p.input_bg};
                border-bottom: 1px solid {p.surface_alt};
            }}
        """)
        for sep in getattr(self, "_separators", []):
            sep.setStyleSheet(f"color: {p.surface_alt};")

    def _separator(self) -> QLabel:
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {_palette().surface_alt};")
        self._separators.append(sep)
        return sep
    
    def refresh(self):
        """Public refresh entry (called by MainWindow's status timer)."""
        self._update_status()
    
    def _update_status(self):
        """Poll backend for current status"""
        from datetime import datetime
        
        try:
            stats = self.bridge.get_stats()
            
            # ─────────────────────────────────────────────────────────
            # PIPELINE STATUS
            # ─────────────────────────────────────────────────────────
            pipeline_loaded = stats.get("pipeline_loaded", False)
            pipeline_details = []
            
            if pipeline_loaded:
                pipeline_details = [
                    "ML models loaded",
                    "Ready for analysis",
                ]
                text_model = stats.get("security", {}).get("text_log_model", {})
                if text_model.get("loaded"):
                    pipeline_details.append("Text log model loaded")
                else:
                    pipeline_details.append("Text log model fallback: rules")
                self.pipeline_led.set_state("green", "Active", pipeline_details)
            else:
                self.pipeline_led.set_state("yellow", "Loading", [
                    "ML models initializing",
                    "Please wait..."
                ])
            
            # ─────────────────────────────────────────────────────────
            # INGESTION STATUS (combines sources + buffer)
            # ─────────────────────────────────────────────────────────
            running = stats.get("running", False)
            sources = stats.get("sources_count", 0)
            buffer_size = stats.get("size", 0)
            max_size = stats.get("max_size", 10000)
            dropped = stats.get("dropped_count", 0)
            
            ingestion_details = [
                f"Sources: {sources}",
                f"Buffer: {buffer_size}/{max_size}"
            ]
            
            if dropped > 0:
                ingestion_details.append(f"⚠️ Dropped: {dropped}")
            permission_check = stats.get("permission_check", {})
            if not permission_check.get("has_permission", True):
                ingestion_details.append(
                    "⚠️ Limited permissions — run as admin for system logs"
                )
            dedup = stats.get("deduplication", {})
            suppressed = dedup.get("suppressed_count", 0)
            if suppressed:
                ingestion_details.append(f"Suppressed benign duplicates: {suppressed}")
            
            if running and sources > 0:
                if dropped > 0 or buffer_size > max_size * 0.8:
                    self.ingestion_led.set_state("yellow", f"Active ({sources})", ingestion_details)
                else:
                    self.ingestion_led.set_state("blue", f"Active ({sources})", ingestion_details)
            elif sources > 0:
                self.ingestion_led.set_state("gray", f"Idle ({sources})", ingestion_details)
            else:
                self.ingestion_led.set_state("gray", "Not Started", [
                    "No log sources configured",
                    "Upload logs to begin"
                ])
            
            # Status chips (UX-9)
            self._update_chips(stats)

            # Update time
            self.update_time.setText(datetime.now().strftime("%H:%M:%S"))
            
            # Emit status for listeners
            self.status_update.emit(stats)
            
        except Exception as e:
            self.pipeline_led.set_state("red", "Error")
            self.update_time.setText(f"Error: {str(e)[:15]}")

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


class PermissionBanner(QFrame):
    """Warning banner for permission issues"""
    
    dismissed = pyqtSignal()
    
    def __init__(self, message: str, icon: str = "⚠️"):
        super().__init__()
        self._init_ui(message, icon)
    
    def _init_ui(self, message: str, icon: str):
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 10, 15, 10)

        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 14))
        layout.addWidget(icon_label)

        self._msg_label = QLabel(message)
        self._msg_label.setWordWrap(True)
        layout.addWidget(self._msg_label, 1)

        # Action button
        self._action_btn = QLabel("Run as Admin")
        self._action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self._action_btn)

        # Close button
        self._close_btn = QLabel("✕")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.mousePressEvent = lambda e: self._dismiss()
        layout.addWidget(self._close_btn)

        self._apply_theme()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

        self.setLayout(layout)

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            PermissionBanner {{
                background-color: {p.warning_bg};
                border: 1px solid {p.warning};
                border-radius: 6px;
                margin: 5px 15px;
            }}
        """)
        if getattr(self, "_msg_label", None) is not None:
            self._msg_label.setStyleSheet(f"color: {p.warning}; font-size: 12px;")
            self._action_btn.setStyleSheet(f"""
                color: {p.warning};
                font-size: 11px;
                text-decoration: underline;
                padding: 5px 10px;
            """)
            self._close_btn.setStyleSheet(
                f"color: {p.text_muted}; font-size: 14px; padding: 5px;"
            )
    
    def _dismiss(self):
        self.hide()
        self.dismissed.emit()


class KillSwitchBanner(QFrame):
    """Critical banner when kill switch is active"""
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(15, 12, 15, 12)

        icon_label = QLabel("🛑")
        icon_label.setFont(QFont("Segoe UI Emoji", 16))
        layout.addWidget(icon_label)

        self._msg = QLabel("KILL SWITCH ACTIVE")
        layout.addWidget(self._msg)

        self._desc = QLabel(
            "All ML processing halted • Edit config/kill_switch.yaml to disable"
        )
        layout.addWidget(self._desc, 1)

        self._apply_theme()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

        self.setLayout(layout)
        self.hide()  # Hidden by default

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            KillSwitchBanner {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {p.danger_bg}, stop:1 {p.danger_bg});
                border: 2px solid {p.danger};
                border-radius: 6px;
                margin: 5px 15px;
            }}
        """)
        if getattr(self, "_msg", None) is not None:
            self._msg.setStyleSheet(
                f"color: {p.sev_critical}; font-size: 14px; font-weight: bold;"
            )
            self._desc.setStyleSheet(f"color: {p.danger}; font-size: 11px;")
    
    def show_if_active(self, is_active: bool):
        if is_active:
            self.show()
        else:
            self.hide()
