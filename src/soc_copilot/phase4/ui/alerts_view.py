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
        
        # Auto-refresh every 3 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        
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
                        "time": alert.timestamp.strftime("%H:%M:%S"),
                        "priority": alert.priority,
                        "classification": alert.classification,
                        "source_ip": alert.source_ip or "N/A",
                        "confidence": f"{alert.confidence:.2f}"
                    })
            
            # Handle empty state
            if not alerts_data:
                self.table.setRowCount(0)
                self.empty_label.setText("No alerts to display.\nSystem is monitoring for security threats...")
                self.empty_label.show()
                self.table.hide()
                return
            else:
                self.empty_label.hide()
                self.table.show()
            
            # Update table
            self.table.setRowCount(len(alerts_data))
            
            for row, alert in enumerate(alerts_data):
                self.table.setItem(row, 0, QTableWidgetItem(alert["time"]))
                self.table.setItem(row, 1, QTableWidgetItem(alert["priority"]))
                self.table.setItem(row, 2, QTableWidgetItem(alert["classification"]))
                self.table.setItem(row, 3, QTableWidgetItem(alert["source_ip"]))
                self.table.setItem(row, 4, QTableWidgetItem(alert["confidence"]))
                self.table.setItem(row, 5, QTableWidgetItem(alert["batch_id"]))
                
                # Color by priority
                if "Critical" in alert["priority"]:
                    color = Qt.GlobalColor.red
                elif "High" in alert["priority"]:
                    color = Qt.GlobalColor.darkYellow
                else:
                    color = Qt.GlobalColor.white
                
                for col in range(6):
                    item = self.table.item(row, col)
                    if item:
                        item.setForeground(color)
            
            # Auto-resize columns
            self.table.resizeColumnsToContents()
        
        except Exception as e:
            self.table.setRowCount(0)
            self.empty_label.setText(f"Error loading alerts: {str(e)[:100]}")
            self.empty_label.show()
            self.table.hide()
    
    def _on_row_clicked(self, item):
        """Handle row click with error handling"""
        try:
            row = item.row()
            batch_id = self.table.item(row, 5).text()
            alert_id = self.table.item(row, 2).text()  # Use classification as identifier
            self.alert_selected.emit(batch_id, alert_id)
        except Exception:
            pass  # Ignore click errors
