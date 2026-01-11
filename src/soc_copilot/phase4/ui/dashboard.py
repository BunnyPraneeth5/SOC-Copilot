"""Dashboard with metrics overview"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class Dashboard(QWidget):
    """Metrics overview dashboard"""
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
        
        # Auto-refresh every 3 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("SOC Copilot Dashboard")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Metrics row
        metrics_layout = QHBoxLayout()
        
        self.total_label = self._create_metric_card("Total Alerts", "0")
        self.critical_label = self._create_metric_card("Critical", "0", "#ff4444")
        self.high_label = self._create_metric_card("High", "0", "#ff8800")
        self.medium_label = self._create_metric_card("Medium", "0", "#ffaa00")
        
        metrics_layout.addWidget(self.total_label)
        metrics_layout.addWidget(self.critical_label)
        metrics_layout.addWidget(self.high_label)
        metrics_layout.addWidget(self.medium_label)
        
        layout.addLayout(metrics_layout)
        
        # Status
        self.status_label = QLabel("Status: Ready")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def _create_metric_card(self, title: str, value: str, color: str = "#4CAF50") -> QFrame:
        """Create metric card widget"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.Box)
        frame.setStyleSheet(f"background-color: {color}; border-radius: 5px; padding: 10px;")
        
        layout = QVBoxLayout()
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 10))
        title_label.setStyleSheet("color: white;")
        
        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 20, QFont.Weight.Bold))
        value_label.setStyleSheet("color: white;")
        value_label.setObjectName("value")
        
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        frame.setLayout(layout)
        
        return frame
    
    def refresh(self):
        """Refresh dashboard metrics"""
        try:
            results = self.bridge.get_latest_alerts(limit=100)
            
            # Count alerts by priority
            total = 0
            critical = 0
            high = 0
            medium = 0
            
            for result in results:
                for alert in result.alerts:
                    total += 1
                    if "Critical" in alert.priority:
                        critical += 1
                    elif "High" in alert.priority:
                        high += 1
                    elif "Medium" in alert.priority:
                        medium += 1
            
            # Update labels
            self.total_label.findChild(QLabel, "value").setText(str(total))
            self.critical_label.findChild(QLabel, "value").setText(str(critical))
            self.high_label.findChild(QLabel, "value").setText(str(high))
            self.medium_label.findChild(QLabel, "value").setText(str(medium))
            
            stats = self.bridge.get_stats()
            status = "Active" if stats.get("pipeline_loaded") else "Inactive"
            self.status_label.setText(f"Status: {status} | Results: {stats.get('results_stored', 0)}")
            
        except Exception:
            pass
