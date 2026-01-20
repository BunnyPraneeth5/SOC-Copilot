"""Optimized Main Window with Sidebar Navigation and Nav Badges

Improvements over previous version:
- Removed duplicated counters from sidebar (moved to dashboard)
- Added nav badges for alert counts on sidebar buttons
- Simplified sidebar to show only status + navigation
- Connected dashboard signals for filtered navigation
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QMenuBar, QMenu,
    QStackedWidget, QPushButton, QFrame, QLabel
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF, QFont
from PyQt6.QtCore import QPointF

from .dashboard_v2 import Dashboard
from .alerts_view import AlertsView
from .alert_details import AlertDetailsPanel
from .assistant_panel import AssistantPanel
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel
from .about_dialog import AboutDialog
from .system_status_bar import SystemStatusBar, PermissionBanner, KillSwitchBanner


class NavButton(QPushButton):
    """Sidebar navigation button with optional badge"""
    
    def __init__(self, icon: str, text: str, index: int):
        super().__init__(f"{icon}  {text}")
        self.index = index
        self._badge_count = 0
        self._badge_color = "#ff4444"
        self.setCheckable(True)
        self.setFixedHeight(45)
        self._update_style(False)
    
    def _update_style(self, active: bool):
        if active:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #00d4ff;
                    color: #0a0a1a;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 15px;
                    font-size: 13px;
                    font-weight: bold;
                    text-align: left;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #888888;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 15px;
                    font-size: 13px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #1a2744;
                    color: #ffffff;
                }
            """)
    
    def setActive(self, active: bool):
        self.setChecked(active)
        self._update_style(active)
    
    def set_badge(self, count: int, color: str = "#ff4444"):
        """Set badge count on button"""
        self._badge_count = count
        self._badge_color = color
        self._update_text()
    
    def _update_text(self):
        # Get base text (icon + name)
        text_parts = self.text().split("  ")
        base_text = "  ".join(text_parts[:2]) if len(text_parts) >= 2 else self.text()
        
        if self._badge_count > 0:
            if self._badge_count > 99:
                badge_text = "99+"
            else:
                badge_text = str(self._badge_count)
            self.setText(f"{base_text}  ({badge_text})")
        else:
            self.setText(base_text)


class Sidebar(QFrame):
    """Simplified navigation sidebar with status indicator and nav badges"""
    
    nav_changed = pyqtSignal(int)
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
        self._start_polling()
    
    def _init_ui(self):
        self.setFixedWidth(200)
        self.setStyleSheet("""
            QFrame {
                background-color: #0f1629;
                border-right: 1px solid #1a2744;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 15, 12, 15)
        layout.setSpacing(8)
        
        # Logo/Title
        title = QLabel("🛡️ SOC Copilot")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff; padding: 10px 0;")
        layout.addWidget(title)
        
        # Simple status frame (replacing the counter cards)
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #1a2744;
                border-radius: 8px;
            }
        """)
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(4)
        
        self.status_indicator = QLabel("● Initializing...")
        self.status_indicator.setFont(QFont("Segoe UI", 11))
        self.status_indicator.setStyleSheet("color: #ffa000;")
        status_layout.addWidget(self.status_indicator)
        
        self.status_detail = QLabel("Loading ML models")
        self.status_detail.setFont(QFont("Segoe UI", 9))
        self.status_detail.setStyleSheet("color: #888888;")
        status_layout.addWidget(self.status_detail)
        
        status_frame.setLayout(status_layout)
        layout.addWidget(status_frame)
        
        # Navigation buttons
        layout.addSpacing(15)
        nav_label = QLabel("NAVIGATION")
        nav_label.setStyleSheet("color: #555; font-size: 10px; font-weight: bold;")
        layout.addWidget(nav_label)
        
        self.nav_buttons = []
        nav_items = [
            ("📊", "Dashboard", 0),
            ("🚨", "Alerts", 1),
            ("🔍", "Investigation", 2),
            ("🤖", "Assistant", 3),
            ("⚙️", "Settings", 4),
        ]
        
        for icon, text, idx in nav_items:
            btn = NavButton(icon, text, idx)
            btn.clicked.connect(lambda checked, i=idx: self._on_nav_click(i))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        
        # Set first button active
        self.nav_buttons[0].setActive(True)
        
        layout.addStretch()
        
        # Version info
        version_label = QLabel("v0.3.0")
        version_label.setStyleSheet("color: #444444; font-size: 10px;")
        layout.addWidget(version_label)
        
        self.setLayout(layout)
    
    def _on_nav_click(self, index: int):
        for btn in self.nav_buttons:
            btn.setActive(btn.index == index)
        self.nav_changed.emit(index)
    
    def _start_polling(self):
        """Poll for status and badge updates (reduced to 3 seconds)"""
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._update_status)
        self.poll_timer.start(3000)  # Reduced from 1000ms
        self._update_status()
    
    def _update_status(self):
        try:
            stats = self.bridge.get_stats()
            
            # Update status indicator
            if stats.get("shutdown_flag"):
                self.status_indicator.setText("🛑 Kill Switch Active")
                self.status_indicator.setStyleSheet("color: #ff4444;")
                self.status_detail.setText("ML processing halted")
            elif stats.get("pipeline_loaded"):
                self.status_indicator.setText("● Online")
                self.status_indicator.setStyleSheet("color: #4CAF50;")
                
                sources = stats.get("sources_count", 0)
                results = stats.get("results_stored", 0)
                self.status_detail.setText(f"{sources} sources • {results} results")
            else:
                self.status_indicator.setText("● Initializing...")
                self.status_indicator.setStyleSheet("color: #ffa000;")
                self.status_detail.setText("Loading ML models")
            
            # Update nav badges
            alerts = self.bridge.get_latest_alerts(limit=100)
            total_alerts = sum(len(r.alerts) for r in alerts)
            critical_count = sum(
                1 for r in alerts for a in r.alerts 
                if "critical" in a.priority.lower()
            )
            
            # Alerts button badge
            if critical_count > 0:
                self.nav_buttons[1].set_badge(total_alerts, "#ff4444")
            elif total_alerts > 0:
                self.nav_buttons[1].set_badge(total_alerts, "#ffa000")
            else:
                self.nav_buttons[1].set_badge(0)
            
            # Dashboard badge (only for critical)
            if critical_count > 0:
                self.nav_buttons[0].set_badge(critical_count, "#ff4444")
            else:
                self.nav_buttons[0].set_badge(0)
                
        except Exception:
            self.status_indicator.setText("● Error")
            self.status_indicator.setStyleSheet("color: #ff4444;")
            self.status_detail.setText("Connection failed")


class MainWindow(QMainWindow):
    """Optimized SOC Copilot main window with sidebar navigation"""
    
    VERSION = "0.3.0"
    
    def __init__(self, controller):
        super().__init__()
        self.bridge = ControllerBridge(controller)
        self._init_ui()
        self._init_menu()
        self._set_window_icon()
    
    def _init_ui(self):
        self.setWindowTitle("SOC Copilot - Real-Time Security Analysis")
        self.setGeometry(50, 50, 1500, 950)
        
        # Apply modern dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0a0a1a;
                color: #ffffff;
            }
            QWidget {
                background-color: #0a0a1a;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QTabWidget::pane {
                border: none;
                background-color: #0f1629;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #0a0a1a;
                color: #888888;
                padding: 10px 20px;
                margin-right: 2px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #0f1629;
                color: #00d4ff;
                font-weight: bold;
            }
            QTableWidget {
                background-color: #0f1629;
                alternate-background-color: #12192e;
                gridline-color: #1a2744;
                border: none;
                border-radius: 8px;
                selection-background-color: #00d4ff;
                selection-color: #0a0a1a;
            }
            QHeaderView::section {
                background-color: #0a1225;
                color: #ffffff;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
            QScrollBar:vertical {
                background-color: #0a0a1a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background-color: #2a3f5f;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #3a5f8f;
            }
            QStatusBar {
                background-color: #0a1225;
                color: #888888;
                padding: 5px 15px;
            }
        """)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = Sidebar(self.bridge)
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        main_layout.addWidget(self.sidebar)
        
        # Content area
        content_area = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # System status bar at top (consolidated)
        self.system_status_bar = SystemStatusBar(self.bridge)
        content_layout.addWidget(self.system_status_bar)
        
        # Banners
        self.killswitch_banner = KillSwitchBanner()
        content_layout.addWidget(self.killswitch_banner)
        
        permission_status = self.bridge.get_permission_status()
        if not permission_status.get("has_permission", True):
            self.permission_banner = PermissionBanner(
                "System log access requires Administrator privileges."
            )
            content_layout.addWidget(self.permission_banner)
        
        # Stacked widget for navigation pages
        self.page_stack = QStackedWidget()
        
        # Page 0: Dashboard
        self.dashboard = Dashboard(self.bridge)
        self.dashboard.navigate_to_alerts.connect(lambda: self._on_nav_changed(1))
        self.dashboard.navigate_to_alerts_filtered.connect(self._on_navigate_alerts_filtered)
        self.dashboard.navigate_to_settings.connect(lambda: self._on_nav_changed(4))
        self.dashboard.alert_selected.connect(self._on_alert_selected)
        self.page_stack.addWidget(self.dashboard)
        
        # Page 1: Alerts
        self.alerts_view = AlertsView(self.bridge)
        self.alerts_view.alert_selected.connect(self._on_alert_selected)
        self.page_stack.addWidget(self.alerts_view)
        
        # Page 2: Investigation (Alert Details)
        self.details_panel = AlertDetailsPanel(self.bridge)
        self.details_panel.back_clicked.connect(lambda: self._on_nav_changed(1))
        self.page_stack.addWidget(self.details_panel)
        
        # Page 3: Assistant
        self.assistant_panel = AssistantPanel()
        self.page_stack.addWidget(self.assistant_panel)
        
        # Page 4: Settings
        self.config_panel = ConfigPanel(self.bridge)
        self.page_stack.addWidget(self.config_panel)
        
        content_layout.addWidget(self.page_stack)
        content_area.setLayout(content_layout)
        
        main_layout.addWidget(content_area)
        central.setLayout(main_layout)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status_bar()
        
        # Status bar updates (reduced to 3 seconds)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status_bar)
        self.status_timer.start(3000)
        
        # Keyboard shortcuts
        self._setup_shortcuts()
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for navigation"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        
        # Navigation shortcuts
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(lambda: self._on_nav_changed(0))
        QShortcut(QKeySequence("Ctrl+2"), self).activated.connect(lambda: self._on_nav_changed(1))
        QShortcut(QKeySequence("Ctrl+3"), self).activated.connect(lambda: self._on_nav_changed(2))
        QShortcut(QKeySequence("Ctrl+4"), self).activated.connect(lambda: self._on_nav_changed(3))
        QShortcut(QKeySequence("Ctrl+,"), self).activated.connect(lambda: self._on_nav_changed(4))
        
        # Refresh shortcut
        QShortcut(QKeySequence("F5"), self).activated.connect(self._refresh_current_view)
        
        # Escape to return to dashboard
        QShortcut(QKeySequence("Escape"), self).activated.connect(lambda: self._on_nav_changed(0))
    
    def _refresh_current_view(self):
        """Refresh the currently active view"""
        current_index = self.page_stack.currentIndex()
        if current_index == 0:
            self.dashboard.refresh()
        elif current_index == 1:
            self.alerts_view.refresh()
        self.status_bar.showMessage("View refreshed", 1000)
    
    def _on_nav_changed(self, index: int):
        """Handle navigation changes"""
        self.page_stack.setCurrentIndex(index)
        
        # Update sidebar buttons
        for btn in self.sidebar.nav_buttons:
            btn.setActive(btn.index == index)
    
    def _on_navigate_alerts_filtered(self, priority: str):
        """Navigate to alerts with a specific priority filter"""
        # Switch to alerts page
        self._on_nav_changed(1)
        
        # Apply filter if alerts_view supports it
        if hasattr(self.alerts_view, 'set_priority_filter'):
            self.alerts_view.set_priority_filter(priority)
        
        self.status_bar.showMessage(f"Showing {priority.title()} priority alerts", 2000)
    
    def _on_alert_selected(self, batch_id: str, alert_classification: str):
        """Handle alert selection - navigate to investigation"""
        try:
            self.details_panel.show_alert(batch_id, alert_classification)
            
            # Switch to investigation page
            self.page_stack.setCurrentIndex(2)
            self.sidebar._on_nav_click(2)
            
            # Update assistant
            result = self.bridge.get_alert_by_id(batch_id)
            if result:
                for alert in result.alerts:
                    if alert.classification == alert_classification:
                        self.assistant_panel.explain_alert(alert)
                        break
            
            self.status_bar.showMessage(f"Investigating: {alert_classification}", 3000)
        except Exception as e:
            self.status_bar.showMessage(f"Error: {str(e)}", 3000)
    
    def _update_status_bar(self):
        """Update status bar with real-time info"""
        try:
            stats = self.bridge.get_stats()
            
            parts = []
            
            # Pipeline
            if stats.get("pipeline_loaded"):
                parts.append("🟢 Pipeline Active")
            else:
                parts.append("🟡 Pipeline Loading")
            
            # Results
            results = stats.get("results_stored", 0)
            parts.append(f"📊 {results} results")
            
            # Ingestion
            sources = stats.get("sources_count", 0)
            if sources > 0:
                parts.append(f"📁 {sources} sources")
            
            # Kill switch warning
            if stats.get("shutdown_flag"):
                parts.append("🛑 KILL SWITCH ACTIVE")
            
            self.status_bar.showMessage(" │ ".join(parts))
            
        except Exception:
            self.status_bar.showMessage("Status unavailable")
    
    def _init_menu(self):
        """Initialize menu bar"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #0a1225;
                color: #ffffff;
                padding: 2px;
            }
            QMenuBar::item { padding: 5px 10px; }
            QMenuBar::item:selected { background-color: #1a2744; }
            QMenu {
                background-color: #0f1629;
                color: #ffffff;
                border: 1px solid #1a2744;
            }
            QMenu::item:selected {
                background-color: #00d4ff;
                color: #0a0a1a;
            }
        """)
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        # Quick nav actions
        nav_dash = QAction("📊 Dashboard", self)
        nav_dash.setShortcut("Ctrl+1")
        nav_dash.triggered.connect(lambda: self._on_nav_changed(0))
        file_menu.addAction(nav_dash)
        
        nav_alerts = QAction("🚨 Alerts", self)
        nav_alerts.setShortcut("Ctrl+2")
        nav_alerts.triggered.connect(lambda: self._on_nav_changed(1))
        file_menu.addAction(nav_alerts)
        
        nav_settings = QAction("⚙️ Settings", self)
        nav_settings.setShortcut("Ctrl+,")
        nav_settings.triggered.connect(lambda: self._on_nav_changed(4))
        file_menu.addAction(nav_settings)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About SOC Copilot", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _set_window_icon(self):
        """Set window icon"""
        icon = QIcon(self._create_icon_pixmap())
        self.setWindowIcon(icon)
    
    def _create_icon_pixmap(self) -> QPixmap:
        """Create shield icon"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.setPen(QPen(QColor("#00d4ff"), 2))
        painter.setBrush(QColor("#0f1629"))
        
        x, y = 4, 4
        s = size - 8
        
        shield_points = [
            QPointF(x + s/2, y),
            QPointF(x + s, y + s*0.3),
            QPointF(x + s, y + s*0.6),
            QPointF(x + s/2, y + s),
            QPointF(x, y + s*0.6),
            QPointF(x, y + s*0.3),
        ]
        painter.drawPolygon(QPolygonF(shield_points))
        
        painter.setPen(QPen(QColor("#00d4ff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(x + s*0.3), int(y + s*0.25), int(s*0.4), int(s*0.4))
        painter.drawLine(
            int(x + s*0.6), int(y + s*0.55),
            int(x + s*0.75), int(y + s*0.7)
        )
        
        painter.end()
        return pixmap
    
    def _show_about(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.exec()
