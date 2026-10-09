"""Configuration Status Panel with system logs toggle

Provides UI controls for configuration without modifying ML models,
pipeline logic, or auto-starting ingestion.
"""

import platform
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGroupBox, QGridLayout, QPushButton, QComboBox, QCheckBox, QScrollArea,
    QSystemTrayIcon,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ..config import ConfigManager
from ..kill_switch import KillSwitch
from .theme import ThemeManager, set_role
from .motion import crossfade_window
from .notifications import NOTIFY_PRIORITIES
from .state_constants import (
    get_ingestion_state, get_governance_state,
    INGESTION_STATES, GOVERNANCE_STATES,
    GovernanceState
)


def _palette():
    return ThemeManager.instance().palette


class ToggleSwitch(QFrame):
    """Custom toggle switch widget"""
    
    def __init__(self, initial_state: bool = False, on_toggle=None):
        super().__init__()
        self._state = initial_state
        self._on_toggle = on_toggle
        self._init_ui()
        self._update_style()
    
    def _init_ui(self):
        self.setFixedSize(60, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        
        self.knob = QLabel()
        self.knob.setFixedSize(24, 24)
        
        if self._state:
            layout.addStretch()
            layout.addWidget(self.knob)
        else:
            layout.addWidget(self.knob)
            layout.addStretch()
        
        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._update_style)

    def _update_style(self):
        p = _palette()
        if self._state:
            self.setStyleSheet(f"""
                ToggleSwitch {{
                    background-color: {p.success};
                    border-radius: 15px;
                    border: 2px solid {p.success};
                }}
            """)
            self.knob.setStyleSheet(f"""
                QLabel {{
                    background-color: {p.text};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                ToggleSwitch {{
                    background-color: {p.text_muted};
                    border-radius: 15px;
                    border: 2px solid {p.border};
                }}
            """)
            self.knob.setStyleSheet(f"""
                QLabel {{
                    background-color: {p.surface_alt};
                    border-radius: 12px;
                }}
            """)
    
    def mousePressEvent(self, event):
        self._state = not self._state
        self._update_style()
        self._rebuild_layout()
        if self._on_toggle:
            self._on_toggle(self._state)
    
    def _rebuild_layout(self):
        """Rebuild layout to move knob"""
        layout = self.layout()
        while layout.count():
            item = layout.takeAt(0)
            # Don't delete the knob widget
        
        if self._state:
            layout.addStretch()
            layout.addWidget(self.knob)
        else:
            layout.addWidget(self.knob)
            layout.addStretch()
    
    def is_on(self) -> bool:
        return self._state
    
    def set_state(self, state: bool):
        if self._state != state:
            self._state = state
            self._update_style()
            self._rebuild_layout()


class StatusIndicator(QFrame):
    """Status indicator with colored dot and label"""
    
    def __init__(self, label: str, status: str = "Unknown", color: str | None = None):
        super().__init__()
        self._init_ui(label, status, color or _palette().text_muted)
    
    def _init_ui(self, label: str, status: str, color: str):
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Colored indicator dot
        self.dot = QLabel("●")
        self.dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        layout.addWidget(self.dot)
        
        # Label
        self._label_widget = QLabel(f"{label}:")
        self._label_widget.setStyleSheet(
            f"color: {_palette().text_muted}; font-weight: bold;"
        )
        layout.addWidget(self._label_widget)

        # Status value
        self.status_label = QLabel(status)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)
        self._color = color
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        self._label_widget.setStyleSheet(
            f"color: {_palette().text_muted}; font-weight: bold;"
        )
        self._update_dot()

    def _update_dot(self):
        self.dot.setStyleSheet(f"color: {self._color}; font-size: 16px;")

    def update_status(self, status: str, color: str):
        """Update status text and color"""
        self._color = color
        self.status_label.setText(status)
        self._update_dot()


class ConfigPanel(QWidget):
    """Configuration Status Panel with toggle and status display
    
    Displays:
    - System Logs toggle (writes to YAML, does NOT start ingestion)
    - Restart Required warning when config changes
    - Read-only status indicators for system state
    """
    
    def __init__(self, bridge=None, project_root: Optional[Path] = None):
        super().__init__()
        self.bridge = bridge
        
        if project_root is None:
            project_root = Path(__file__).parent.parent.parent.parent.parent
        self.project_root = Path(project_root)
        
        self.config_manager = ConfigManager(self.project_root)
        self.kill_switch = KillSwitch(self.project_root)
        
        self._config_changed = False
        self._provider_check_running = False
        self._init_ui()
        if self.bridge is not None and hasattr(self.bridge, "providersChecked"):
            self.bridge.providersChecked.connect(self._on_providers_checked)
        self._refresh_status()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        
        # Title
        title = QLabel("Configuration Status")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Appearance section (theme + colour-blind-safe severities)
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QHBoxLayout()

        appearance_layout.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        tm = ThemeManager.instance()
        self.theme_combo.setCurrentIndex(0 if tm.theme_name == "dark" else 1)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        appearance_layout.addWidget(self.theme_combo)

        self.colorblind_check = QCheckBox("Colour-blind-safe severity colours")
        self.colorblind_check.setChecked(tm.colorblind)
        self.colorblind_check.toggled.connect(self._on_colorblind_toggled)
        appearance_layout.addWidget(self.colorblind_check)

        self.reduce_motion_check = QCheckBox("Reduce motion")
        self.reduce_motion_check.setToolTip(
            "Turn off page fades, sliding panels and animated counters"
        )
        self.reduce_motion_check.setChecked(tm.reduce_motion)
        self.reduce_motion_check.toggled.connect(
            ThemeManager.instance().set_reduce_motion
        )
        appearance_layout.addWidget(self.reduce_motion_check)

        appearance_layout.addStretch()
        appearance_group.setLayout(appearance_layout)
        layout.addWidget(appearance_group)

        # Desktop notifications (UX-8) — enabled once MainWindow attaches
        # its AlertNotifier
        self.notifier = None
        notifications_group = QGroupBox("Notifications")
        self._notifications_group = notifications_group
        notifications_layout = QHBoxLayout()
        self.notify_enabled_check = QCheckBox("Desktop notifications for new alerts")
        self.notify_enabled_check.setToolTip(
            "Show a system-tray notification when a new alert arrives "
            "(also available from the tray icon menu)"
        )
        self.notify_enabled_check.toggled.connect(self._on_notify_enabled_toggled)
        notifications_layout.addWidget(self.notify_enabled_check)
        self.notify_priority_checks = {}
        for priority in NOTIFY_PRIORITIES:
            check = QCheckBox(priority)
            check.toggled.connect(
                lambda on, p=priority: self._on_notify_priority_toggled(p, on)
            )
            notifications_layout.addWidget(check)
            self.notify_priority_checks[priority] = check
        notifications_layout.addStretch()
        self.notify_tray_note = QLabel("")
        set_role(self.notify_tray_note, "muted")
        notifications_layout.addWidget(self.notify_tray_note)
        notifications_group.setLayout(notifications_layout)
        notifications_group.setEnabled(False)
        layout.addWidget(notifications_group)

        # Restart warning (hidden by default)
        self.restart_warning = QFrame()
        self.restart_warning.setObjectName("restartWarning")
        self.restart_warning.setStyleSheet(f"""
            QFrame#restartWarning {{
                background-color: {_palette().warning};
                border-radius: 5px;
                padding: 10px;
            }}
        """)
        warning_layout = QHBoxLayout()
        warning_icon = QLabel("⚠️")
        warning_icon.setFont(QFont("Arial", 18))
        warning_text = QLabel("Configuration changed. Restart required for changes to take effect.")
        self._warning_text = warning_text
        warning_text.setStyleSheet(
            f"color: {_palette().text_inverse}; font-weight: bold;"
        )
        warning_layout.addWidget(warning_icon)
        warning_layout.addWidget(warning_text)
        warning_layout.addStretch()
        self.restart_warning.setLayout(warning_layout)
        self.restart_warning.setVisible(False)
        layout.addWidget(self.restart_warning)
        
        # System Logs Toggle Section
        toggle_group = QGroupBox("System Log Ingestion")
        toggle_layout = QHBoxLayout()

        toggle_label = QLabel("Enable System Logs:")
        toggle_layout.addWidget(toggle_label)
        
        initial_state = self.config_manager.get_system_logs_enabled()
        self.system_logs_toggle = ToggleSwitch(initial_state, self._on_toggle_changed)
        toggle_layout.addWidget(self.system_logs_toggle)
        
        toggle_layout.addStretch()
        
        toggle_note = QLabel("Changes require application restart")
        toggle_note.setStyleSheet(
            f"color: {_palette().text_muted}; font-style: italic;"
        )
        toggle_layout.addWidget(toggle_note)
        
        toggle_group.setLayout(toggle_layout)
        layout.addWidget(toggle_group)
        
        # Status Indicators Section
        status_group = QGroupBox("System Status")
        status_layout = QGridLayout()
        status_layout.setSpacing(10)
        
        # System Logs Enabled
        _p = _palette()
        self.logs_indicator = StatusIndicator("System Logs", "Disabled", _p.text_muted)
        status_layout.addWidget(self.logs_indicator, 0, 0)

        # Operating System
        self.os_indicator = StatusIndicator("Operating System", platform.system(), _p.info)
        status_layout.addWidget(self.os_indicator, 0, 1)

        # Permission Status
        self.perm_indicator = StatusIndicator("Permissions", "Unknown", _p.text_muted)
        status_layout.addWidget(self.perm_indicator, 1, 0)

        # Kill Switch
        self.kill_indicator = StatusIndicator("Kill Switch", "Inactive", _p.success)
        status_layout.addWidget(self.kill_indicator, 1, 1)

        # Ingestion Status
        self.ingestion_indicator = StatusIndicator("Ingestion", "Not Started", _p.text_muted)
        status_layout.addWidget(self.ingestion_indicator, 2, 0)

        # Model Integrity
        self.integrity_indicator = StatusIndicator("Model Integrity", "Unknown", _p.text_muted)
        status_layout.addWidget(self.integrity_indicator, 2, 1)

        # Online Enrichment
        self.online_indicator = StatusIndicator("Online Enrichment", "Disabled", _p.success)
        status_layout.addWidget(self.online_indicator, 3, 0)

        # Noise Suppression
        self.noise_indicator = StatusIndicator("Noise Suppression", "0 suppressed", _p.info)
        status_layout.addWidget(self.noise_indicator, 3, 1)

        # Model Drift (Phase-2 monitor)
        self.drift_indicator = StatusIndicator("Model Drift", "Unavailable", _p.text_muted)
        status_layout.addWidget(self.drift_indicator, 4, 0)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Threat Intelligence Providers Section
        providers_group = QGroupBox("Threat Intelligence Providers")
        self._providers_group = providers_group
        providers_layout = QVBoxLayout()
        providers_layout.setSpacing(5)

        self._provider_indicators = {}
        for key, label in (
            ("whois", "WHOIS / RDAP"),
            ("geoip", "GeoIP (ipwho.is)"),
            ("abuseipdb", "AbuseIPDB"),
            ("virustotal", "VirusTotal"),
            ("shodan", "Shodan"),
            ("report_llm", "Report LLM"),
        ):
            indicator = StatusIndicator(label, "Unknown", _palette().text_muted)
            self._provider_indicators[key] = indicator
            providers_layout.addWidget(indicator)

        self.check_providers_button = QPushButton("Check connectivity")
        self._style_check_button()
        self.check_providers_button.clicked.connect(self._on_check_providers)
        providers_layout.addWidget(self.check_providers_button)

        providers_group.setLayout(providers_layout)
        layout.addWidget(providers_group)

        # Info text
        info_label = QLabel(
            "Appearance changes apply immediately and are saved for next launch. "
            "This panel shows the current configuration and system status; the system "
            "logs toggle still requires a restart. All other indicators are read-only. "
            "Use 'Check connectivity' to probe threat-intelligence providers (requires online enrichment)."
        )
        self._info_label = info_label
        info_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-style: italic;"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch()

        # Scroll the settings so their height doesn't set the window's
        # minimum height (the page stack sizes to its tallest page).
        content = QWidget()
        content.setLayout(layout)
        scroll = QScrollArea()
        self._scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.setLayout(outer)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _style_check_button(self):
        self.check_providers_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {_palette().info};
                color: {_palette().text_inverse};
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }}
            QPushButton:disabled {{
                background-color: {_palette().surface_alt};
                color: {_palette().text_muted};
            }}
        """)

    def _apply_theme(self):
        """Re-apply palette-derived styles and refresh indicator colours."""
        p = _palette()
        self.restart_warning.setStyleSheet(f"""
            QFrame#restartWarning {{
                background-color: {p.warning};
                border-radius: 5px;
                padding: 10px;
            }}
        """)
        self._warning_text.setStyleSheet(
            f"color: {p.text_inverse}; font-weight: bold;"
        )
        self._style_check_button()
        self._info_label.setStyleSheet(
            f"color: {p.text_muted}; font-style: italic;"
        )
        # Keep the appearance controls in sync (no signal re-entry)
        tm = ThemeManager.instance()
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(0 if tm.theme_name == "dark" else 1)
        self.theme_combo.blockSignals(False)
        self.colorblind_check.blockSignals(True)
        self.colorblind_check.setChecked(tm.colorblind)
        self.colorblind_check.blockSignals(False)
        self._refresh_status()

    def _on_theme_changed(self, index: int):
        crossfade_window(self.window())
        ThemeManager.instance().set_theme("dark" if index == 0 else "light")

    def show_section(self, name: str) -> None:
        """Scroll to the setting behind a header status chip (UX-9)."""
        target = {
            "enrichment": self.online_indicator,
            "kill_switch": self.kill_indicator,
            "integrity": self.integrity_indicator,
            "providers": self._providers_group,
            "drift": self.drift_indicator,
            "notifications": self._notifications_group,
        }.get(name)
        if target is not None:
            self._scroll.ensureWidgetVisible(target, 0, 40)

    # ----- notifications (UX-8) -----------------------------------------

    def attach_notifier(self, notifier) -> None:
        """Bind the Notifications controls to MainWindow's AlertNotifier."""
        self.notifier = notifier
        notifier.preferences_changed.connect(self._sync_notification_controls)
        self._notifications_group.setEnabled(True)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.notify_tray_note.setText("System tray not available")
        self._sync_notification_controls()

    def _sync_notification_controls(self) -> None:
        n = self.notifier
        if n is None:
            return
        self.notify_enabled_check.blockSignals(True)
        self.notify_enabled_check.setChecked(not n.muted)
        self.notify_enabled_check.blockSignals(False)
        for priority, check in self.notify_priority_checks.items():
            check.blockSignals(True)
            check.setChecked(n.priority_enabled(priority))
            check.setEnabled(not n.muted)
            check.blockSignals(False)

    def _on_notify_enabled_toggled(self, enabled: bool) -> None:
        if self.notifier is not None:
            self.notifier.set_muted(not enabled)
            self._sync_notification_controls()

    def _on_notify_priority_toggled(self, priority: str, enabled: bool) -> None:
        if self.notifier is not None:
            self.notifier.set_priority_enabled(priority, enabled)

    def _on_colorblind_toggled(self, checked: bool):
        ThemeManager.instance().set_colorblind(checked)

    def _on_toggle_changed(self, new_state: bool):
        """Handle toggle state change"""
        success = self.config_manager.set_system_logs_enabled(new_state)
        if success:
            self._config_changed = True
            self.restart_warning.setVisible(True)
            self._update_logs_indicator(new_state)
    
    def _update_logs_indicator(self, enabled: bool):
        """Update system logs status indicator"""
        if enabled:
            self.logs_indicator.update_status("Enabled", _palette().success)
        else:
            self.logs_indicator.update_status("Disabled", _palette().text_muted)
    
    def _refresh_status(self):
        """Refresh all status indicators"""
        # System Logs
        logs_enabled = self.config_manager.get_system_logs_enabled()
        self._update_logs_indicator(logs_enabled)
        
        # Permissions (check system log access)
        try:
            from ..ingestion.system_log_reader import SystemLogReader
            reader = SystemLogReader()
            perm_check = reader.validate_system_log_access()
            if perm_check.has_permission:
                self.perm_indicator.update_status("OK", _palette().success)
            elif perm_check.requires_elevation:
                self.perm_indicator.update_status("Elevation Required", _palette().warning)
            else:
                self.perm_indicator.update_status("Limited", _palette().warning)
        except Exception:
            self.perm_indicator.update_status("Unknown", _palette().text_muted)
        
        # Kill Switch (using centralized governance state for color consistency)
        if self.kill_switch.is_active():
            gov_cfg = GOVERNANCE_STATES[GovernanceState.HALTED]
            self.kill_indicator.update_status("Active", gov_cfg.color)
        else:
            gov_cfg = GOVERNANCE_STATES[GovernanceState.OK]
            self.kill_indicator.update_status("Inactive", gov_cfg.color)
        
        # Ingestion Status (using centralized ingestion states)
        if self.bridge:
            try:
                stats = self.bridge.get_stats()
                running = stats.get('running', False)
                shutdown = stats.get('shutdown_flag', False)
                sources = stats.get('sources_count', 0)
                
                ingestion_state = get_ingestion_state(running, sources, shutdown)
                ingestion_cfg = INGESTION_STATES[ingestion_state]
                self.ingestion_indicator.update_status(ingestion_cfg.label, ingestion_cfg.color)

                security = stats.get("security", {})
                integrity = security.get("model_integrity", {})
                strict = security.get("strict_model_integrity", False)
                online = security.get("online_enrichment_enabled", False)
                dedup = stats.get("deduplication", {})

                if integrity.get("is_valid") is False:
                    self.integrity_indicator.update_status("Failed", _palette().danger)
                elif strict:
                    verified = len(integrity.get("verified_files", []))
                    self.integrity_indicator.update_status(f"Strict ({verified} verified)", _palette().success)
                else:
                    self.integrity_indicator.update_status("Dev Mode", _palette().info)

                if online:
                    self.online_indicator.update_status("Enabled", _palette().warning)
                else:
                    self.online_indicator.update_status("Disabled", _palette().success)

                suppressed = dedup.get("suppressed_count", 0)
                self.noise_indicator.update_status(f"{suppressed} suppressed", _palette().info)

                self._update_drift_indicator()
            except Exception:
                self.ingestion_indicator.update_status("Unknown", _palette().text_muted)
                self.integrity_indicator.update_status("Unknown", _palette().text_muted)
                self.online_indicator.update_status("Unknown", _palette().text_muted)
                self.noise_indicator.update_status("Unknown", _palette().text_muted)
                self.drift_indicator.update_status("Unknown", _palette().text_muted)
        else:
            not_started_cfg = INGESTION_STATES["not_started"]
            self.ingestion_indicator.update_status(not_started_cfg.label, not_started_cfg.color)
            self.integrity_indicator.update_status("Unknown", _palette().text_muted)
            self.online_indicator.update_status("Disabled", _palette().success)
            self.noise_indicator.update_status("0 suppressed", _palette().info)
            self.drift_indicator.update_status("Unavailable", _palette().text_muted)

        # Threat-intelligence provider statuses
        self._refresh_providers()

    def _update_drift_indicator(self):
        """Update the model-drift indicator from the bridge."""
        try:
            status = self.bridge.get_drift_status()
        except Exception:
            status = None
        if not status or not status.get("available"):
            self.drift_indicator.update_status("Unavailable", _palette().text_muted)
            return
        level = status.get("level")
        if not level:
            self.drift_indicator.update_status("Collecting data", _palette().info)
            return
        p = _palette()
        color = {
            "NONE": p.success,
            "LOW": p.success,
            "MODERATE": p.warning,
            "HIGH": p.danger,
            "CRITICAL": p.danger,
        }.get(str(level).upper(), p.text_muted)
        self.drift_indicator.update_status(str(level).title(), color)

    @staticmethod
    def _provider_state_colors() -> dict:
        p = _palette()
        return {
            "Configured": p.success,
            "Available": p.success,
            "Missing key": p.warning,
            "Disabled": p.text_muted,
            "Offline": p.danger,
        }

    def _refresh_providers(self):
        """Populate provider indicators from local statuses (no network)."""
        try:
            if self.bridge is not None:
                statuses = self.bridge.get_provider_statuses()
            else:
                from soc_copilot.mcp.provider_registry import get_provider_statuses
                statuses = get_provider_statuses()
        except Exception:
            return
        self._apply_provider_statuses(statuses)

    def _apply_provider_statuses(self, statuses):
        """Update indicators and the check button from a status list."""
        any_usable = False
        for status in statuses:
            indicator = self._provider_indicators.get(status.key)
            if indicator is None:
                continue
            state = status.state.value
            text = state + (f" — {status.detail}" if status.detail else "")
            color = self._provider_state_colors().get(state, _palette().text_muted)
            indicator.update_status(text, color)
            if status.usable:
                any_usable = True

        if not any_usable:
            self.check_providers_button.setEnabled(False)
            self.check_providers_button.setToolTip(
                "Enable online enrichment to check providers"
            )
        elif not self._provider_check_running:
            self.check_providers_button.setEnabled(True)
            self.check_providers_button.setToolTip("")

    def _on_check_providers(self):
        """Run the connectivity probe off the UI thread."""
        if self._provider_check_running:
            return
        self._provider_check_running = True
        self.check_providers_button.setEnabled(False)
        self.check_providers_button.setText("Checking...")

        if self.bridge is not None:
            self.bridge.check_provider_connectivity()
        else:
            # No bridge: probe synchronously (tests / headless usage only).
            import asyncio
            from soc_copilot.mcp.provider_registry import check_connectivity
            try:
                self._on_providers_checked(asyncio.run(check_connectivity()))
            except Exception:
                self._on_providers_checked(None)

    def _on_providers_checked(self, statuses):
        """Apply probe results delivered from the worker thread."""
        self._provider_check_running = False
        self.check_providers_button.setText("Check connectivity")
        self.check_providers_button.setEnabled(True)
        if statuses:
            self._apply_provider_statuses(statuses)

    def refresh(self):
        """Public method to refresh status (called by timer)"""
        self._refresh_status()
