"""Dashboard with metrics overview"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class Dashboard(QWidget):
    """Metrics overview dashboard with empty state handling"""
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
        
        # Auto-refresh every 5 seconds (less aggressive)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        
        # Initial refresh
        self.refresh()
    
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
        
        # Status and empty state
        self.status_label = QLabel("Status: Initializing...")
        layout.addWidget(self.status_label)
        
        self.empty_state_label = QLabel("")
        self.empty_state_label.setStyleSheet("color: #888888; font-style: italic;")
        self.empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_state_label)
        
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
        """Refresh dashboard metrics with error handling"""
        try:
            # Show loading state
            self.status_label.setText("Status: Loading...")
            
            results = self.bridge.get_latest_alerts(limit=100)
            
            # Count alerts by priority
            total = 0
            critical = 0
            high = 0
            medium = 0
            
            for result in results:
                for alert in result.alerts:
                    total += 1
                    priority_lower = alert.priority.lower()
                    if "critical" in priority_lower:
                        critical += 1
                    elif "high" in priority_lower:
                        high += 1
                    elif "medium" in priority_lower:
                        medium += 1
            
            # Update labels safely
            self._update_metric_safe(self.total_label, str(total))
            self._update_metric_safe(self.critical_label, str(critical))
            self._update_metric_safe(self.high_label, str(high))
            self._update_metric_safe(self.medium_label, str(medium))
            
            # Update status
            stats = self.bridge.get_stats()
            pipeline_status = "Active" if stats.get("pipeline_loaded") else "Inactive"
            results_count = stats.get('results_stored', 0)
            ingestion_running = stats.get('ingestion_running', False)
            
            status_parts = [f"Pipeline: {pipeline_status}"]
            if ingestion_running:
                status_parts.append("Ingestion: Active")
            status_parts.append(f"Results: {results_count}")
            
            self.status_label.setText(" | ".join(status_parts))
            
            # Handle empty state with better messaging
            self._update_empty_state(total, results_count, pipeline_status, ingestion_running)
            
        except Exception as e:
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            self.status_label.setText(f"Status: Error - {error_msg}")
            self.empty_state_label.setText("Unable to load dashboard data. Check system status and logs.")
    
    def _update_metric_safe(self, frame: QFrame, value: str):
        """Safely update metric value"""
        try:
            value_label = frame.findChild(QLabel, "value")
            if value_label:
                value_label.setText(value)
        except Exception:
            pass  # Ignore update errors
    
    def _update_empty_state(self, total: int, results_count: int, pipeline_status: str, ingestion_running: bool):
        """Update empty state message based on system state"""
        if total == 0:
            if pipeline_status != "Active":
                self.empty_state_label.setText(
                    "⚠️ Pipeline inactive. Run 'python scripts/train_models.py' if models are missing, "
                    "then restart the application."
                )
            elif not ingestion_running:
                self.empty_state_label.setText(
                    "📁 No log sources configured. Use the interface to add log files or directories to monitor."
                )
            elif results_count == 0:
                self.empty_state_label.setText(
                    "🔍 System is monitoring for threats. No alerts detected yet - this is good!"
                )
            else:
                self.empty_state_label.setText(
                    "✅ No recent alerts. System is operating normally and monitoring for threats."
                )
        else:
            self.empty_state_label.setText("")
