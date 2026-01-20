"""UI/UX Layer for SOC Copilot - v0.3.0 Dashboard UX Redesign"""

from .main_window import MainWindow
from .dashboard import Dashboard
from .alerts_view import AlertsView
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel
from .splash_screen import SplashScreen, create_splash
from .about_dialog import AboutDialog
from .system_status_bar import SystemStatusBar, PermissionBanner, KillSwitchBanner
from .dashboard_components import (
    ThreatLevelBanner,
    RecentAlertsTimeline,
    EmptyStateCard,
    QuickActionsBar,
    CompactMetricCard,
    SystemHealthGrid
)

__all__ = [
    "MainWindow", 
    "Dashboard",
    "AlertsView",
    "ControllerBridge", 
    "ConfigPanel",
    "SplashScreen",
    "create_splash",
    "AboutDialog",
    "SystemStatusBar",
    "PermissionBanner",
    "KillSwitchBanner",
    "ThreatLevelBanner",
    "RecentAlertsTimeline",
    "EmptyStateCard",
    "QuickActionsBar",
    "CompactMetricCard",
    "SystemHealthGrid"
]
