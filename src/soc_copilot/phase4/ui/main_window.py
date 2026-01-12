"""Main window application shell"""

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QSplitter, QTabWidget, QStatusBar)
from PyQt6.QtCore import Qt

from .dashboard import Dashboard
from .alerts_view import AlertsView
from .alert_details import AlertDetailsPanel
from .assistant_panel import AssistantPanel
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel


class MainWindow(QMainWindow):
    """SOC Copilot main application window"""
    
    def __init__(self, controller):
        super().__init__()
        self.bridge = ControllerBridge(controller)
        self._init_ui()
    
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
