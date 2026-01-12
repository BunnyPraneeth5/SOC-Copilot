"""Live alerts table view"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLabel
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont


class AlertsView(QWidget):
    """Live alerts table with auto-refresh and empty state"""
    
    alert_selected = pyqtSignal(str, str)  # batch_id, alert_id
    
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
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Time", "Priority", "Classification", "Source IP", "Confidence", "Batch ID"
        ])
        
        # Configure table
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemClicked.connect(self._on_row_clicked)
        
        # Set alternating row colors
        self.table.setAlternatingRowColors(True)
        
        layout.addWidget(self.table)
        
        # Empty state label
        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888888; font-style: italic; padding: 20px;")
        self.empty_label.setFont(QFont("Arial", 12))
        layout.addWidget(self.empty_label)
        
        self.setLayout(layout)
    
    def refresh(self):
        """Refresh alerts table with error handling and empty state"""
        try:
            results = self.bridge.get_latest_alerts(limit=50)
            
            # Collect all alerts
            alerts_data = []
            for result in results:
                for alert in result.alerts:
                    alerts_data.append({
                        "batch_id": result.batch_id,
                        "alert_id": alert.alert_id,
                        "time": alert.timestamp.strftime("%H:%M:%S") if hasattr(alert.timestamp, 'strftime') else str(alert.timestamp),
                        "priority": alert.priority,
                        "classification": alert.classification,
                        "source_ip": getattr(alert, 'source_ip', None) or "N/A",
                        "confidence": f"{alert.confidence:.2f}" if hasattr(alert, 'confidence') else "N/A"
                    })
            
            # Handle empty state with better messaging
            if not alerts_data:
                self.table.setRowCount(0)
                self._show_empty_state()
                return
            else:
                self.empty_label.hide()
                self.table.show()
            
            # Update table efficiently
            self._update_table(alerts_data)
        
        except Exception as e:
            self._show_error_state(str(e))
    
    def _show_empty_state(self):
        """Show appropriate empty state message"""
        try:
            stats = self.bridge.get_stats()
            pipeline_active = stats.get("pipeline_loaded", False)
            ingestion_running = stats.get("ingestion_running", False)
            
            if not pipeline_active:
                message = (
                    "⚠️ Pipeline not active\n\n"
                    "Models may be missing. Run:\n"
                    "python scripts/train_models.py"
                )
            elif not ingestion_running:
                message = (
                    "📁 No log sources configured\n\n"
                    "Add log files or directories to start monitoring"
                )
            else:
                message = (
                    "✅ No alerts detected\n\n"
                    "System is monitoring for security threats.\n"
                    "This is good - no threats detected!"
                )
            
            self.empty_label.setText(message)
        except Exception:
            self.empty_label.setText("No alerts to display.")
        
        self.empty_label.show()
        self.table.hide()
    
    def _show_error_state(self, error: str):
        """Show error state"""
        self.table.setRowCount(0)
        error_msg = error[:100] + "..." if len(error) > 100 else error
        self.empty_label.setText(f"❌ Error loading alerts:\n{error_msg}\n\nCheck logs for details.")
        self.empty_label.show()
        self.table.hide()
    
    def _update_table(self, alerts_data: list):
        """Update table with alerts data"""
        self.table.setRowCount(len(alerts_data))
        
        for row, alert in enumerate(alerts_data):
            # Create items safely
            items = [
                QTableWidgetItem(alert["time"]),
                QTableWidgetItem(alert["priority"]),
                QTableWidgetItem(alert["classification"]),
                QTableWidgetItem(alert["source_ip"]),
                QTableWidgetItem(alert["confidence"]),
                QTableWidgetItem(alert["batch_id"])
            ]
            
            # Set items
            for col, item in enumerate(items):
                self.table.setItem(row, col, item)
            
            # Color by priority (case insensitive)
            priority_lower = alert["priority"].lower()
            if "critical" in priority_lower:
                color = Qt.GlobalColor.red
            elif "high" in priority_lower:
                color = Qt.GlobalColor.darkYellow
            elif "medium" in priority_lower:
                color = Qt.GlobalColor.yellow
            else:
                color = Qt.GlobalColor.white
            
            # Apply color to all columns in row
            for col in range(6):
                item = self.table.item(row, col)
                if item:
                    item.setForeground(color)
        
        # Auto-resize columns to content
        self.table.resizeColumnsToContents()
    
    def _on_row_clicked(self, item):
        """Handle row click with error handling"""
        try:
            row = item.row()
            batch_id = self.table.item(row, 5).text()
            alert_id = self.table.item(row, 2).text()  # Use classification as identifier
            self.alert_selected.emit(batch_id, alert_id)
        except Exception:
            pass  # Ignore click errors
