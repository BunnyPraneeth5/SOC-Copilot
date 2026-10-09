"""UI/UX Layer for SOC Copilot"""

from .main_window import MainWindow
from .dashboard_v2 import Dashboard
from .alerts_view import AlertsView
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel
from .splash_screen import SplashScreen, create_splash
from .about_dialog import AboutDialog
from .system_status_bar import SystemStatusBar, PermissionBanner, KillSwitchBanner

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
]
