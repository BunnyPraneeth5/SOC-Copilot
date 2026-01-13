"""Main window application shell"""

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QTabWidget, QStatusBar, QMenuBar, QMenu)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF
from PyQt6.QtCore import QPointF

from .dashboard import Dashboard
from .alerts_view import AlertsView
from .alert_details import AlertDetailsPanel
from .assistant_panel import AssistantPanel
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel
from .about_dialog import AboutDialog


class MainWindow(QMainWindow):
    """SOC Copilot main application window"""
    
    VERSION = "0.1.0"
    
    def __init__(self, controller):
        super().__init__()
        self.bridge = ControllerBridge(controller)
        self._init_ui()
        self._init_menu()
        self._set_window_icon()
    
    def _init_ui(self):
        self.setWindowTitle("SOC Copilot - Real-Time Security Analysis")
        self.setGeometry(100, 100, 1400, 900)
        
        # Apply dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
            }
            QTableWidget {
                background-color: #2b2b2b;
                alternate-background-color: #333333;
                gridline-color: #444444;
            }
            QHeaderView::section {
                background-color: #3c3c3c;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #444444;
            }
        """)
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout()
        
        # Dashboard at top
        self.dashboard = Dashboard(self.bridge)
        layout.addWidget(self.dashboard)
        
        # Main content area
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Alerts table
        self.alerts_view = AlertsView(self.bridge)
        self.alerts_view.alert_selected.connect(self._on_alert_selected)
        splitter.addWidget(self.alerts_view)
        
        # Right: Tabs for details and assistant
        tabs = QTabWidget()
        
        self.details_panel = AlertDetailsPanel(self.bridge)
        tabs.addTab(self.details_panel, "Alert Details")
        
        self.assistant_panel = AssistantPanel()
        tabs.addTab(self.assistant_panel, "Assistant")
        
        self.config_panel = ConfigPanel(self.bridge)
        tabs.addTab(self.config_panel, "Configuration")
        
        splitter.addWidget(tabs)
        
        # Set splitter sizes (60% alerts, 40% details)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        central.setLayout(layout)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status_bar()
        
        # Update status bar periodically
        from PyQt6.QtCore import QTimer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status_bar)
        self.status_timer.start(3000)
    
    def _update_status_bar(self):
        """Update status bar with system info"""
        try:
            stats = self.bridge.get_stats()
            
            status_parts = []
            
            # Ingestion status
            running = stats.get('running', False)
            shutdown_flag = stats.get('shutdown_flag', False)
            sources_count = stats.get('sources_count', 0)
            
            if shutdown_flag:
                status_parts.append("⏸️ Ingestion: Stopped")
            elif running and sources_count > 0:
                status_parts.append("▶️ Ingestion: Active")
            elif sources_count > 0:
                status_parts.append("⏸️ Ingestion: Configured")
            else:
                status_parts.append("⏹️ Ingestion: Not Started")
            
            # Kill switch (if active, show warning)
            # Note: If kill switch is active, app wouldn't start, but check anyway
            
            # Permission status (if available from system log integration)
            permission_check = stats.get('permission_check')
            if permission_check and not permission_check.get('has_permission', True):
                status_parts.append("⚠️ Permissions: Limited")
            
            # Dropped records warning
            dropped = stats.get('dropped_count', 0)
            if dropped > 0:
                status_parts.append(f"⚠️ Dropped: {dropped}")
            
            self.status_bar.showMessage(" | ".join(status_parts) if status_parts else "Ready")
            
        except Exception:
            self.status_bar.showMessage("Status unavailable")
    
    def _on_alert_selected(self, batch_id: str, alert_classification: str):
        """Handle alert selection"""
        try:
            # Show details
            self.details_panel.show_alert(batch_id, alert_classification)
            
            # Get alert for assistant
            result = self.bridge.get_alert_by_id(batch_id)
            if result:
                for alert in result.alerts:
                    if alert.classification == alert_classification:
                        self.assistant_panel.explain_alert(alert)
                        break
            
            self.status_bar.showMessage(f"Viewing alert: {alert_classification}")
        
        except Exception as e:
            self.status_bar.showMessage(f"Error: {str(e)}")
    
    def _init_menu(self):
        """Initialize menu bar with Help menu"""
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #2b2b2b;
                color: #ffffff;
                padding: 2px;
            }
            QMenuBar::item {
                padding: 5px 10px;
            }
            QMenuBar::item:selected {
                background-color: #3c3c3c;
            }
            QMenu {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444444;
            }
            QMenu::item:selected {
                background-color: #00d4ff;
                color: #1e1e1e;
            }
        """)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About SOC Copilot", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
        # Documentation link (placeholder)
        docs_action = QAction("&Documentation", self)
        docs_action.setEnabled(False)  # Disabled for now
        help_menu.addAction(docs_action)
    
    def _set_window_icon(self):
        """Set the window icon programmatically"""
        icon = QIcon(self._create_icon_pixmap())
        self.setWindowIcon(icon)
    
    def _create_icon_pixmap(self) -> QPixmap:
        """Create shield icon programmatically for window icon"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw shield shape
        painter.setPen(QPen(QColor("#00d4ff"), 2))
        painter.setBrush(QColor("#1e3a5f"))
        
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
        
        # Draw magnifying glass inside shield
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

