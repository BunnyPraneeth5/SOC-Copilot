"""Alert details drill-down panel"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit, QScrollArea
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AlertDetailsPanel(QWidget):
    """Alert details and explainability panel"""
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        self.title_label = QLabel("Alert Details")
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(self.title_label)
        
        # Scroll area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout()
        self.details_widget.setLayout(self.details_layout)
        
        scroll.setWidget(self.details_widget)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder text"""
        self._clear_details()
        label = QLabel("Select an alert to view details")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.details_layout.addWidget(label)
    
    def _clear_details(self):
        """Clear details panel"""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def show_alert(self, batch_id: str, alert_classification: str):
        """Display alert details"""
        try:
            result = self.bridge.get_alert_by_id(batch_id)
            if not result:
                return
            
            # Find matching alert
            alert = None
            for a in result.alerts:
                if a.classification == alert_classification:
                    alert = a
                    break
            
            if not alert:
                return
            
            self._clear_details()
            
            # Alert metadata
            self._add_field("Alert ID", alert.alert_id)
            self._add_field("Priority", alert.priority)
            self._add_field("Classification", alert.classification)
            self._add_field("Confidence", f"{alert.confidence:.2%}")
            self._add_field("Anomaly Score", f"{alert.anomaly_score:.3f}")
            self._add_field("Risk Score", f"{alert.risk_score:.3f}")
            
            if alert.source_ip:
                self._add_field("Source IP", alert.source_ip)
            if alert.destination_ip:
                self._add_field("Destination IP", alert.destination_ip)
            
            # Explainability
            self._add_section("Reasoning")
            self._add_text(alert.reasoning)
            
            self._add_section("Suggested Action")
            self._add_text(alert.suggested_action)
            
            self.details_layout.addStretch()
        
        except Exception:
            pass
    
    def _add_field(self, label: str, value: str):
        """Add field to details"""
        widget = QLabel(f"<b>{label}:</b> {value}")
        widget.setWordWrap(True)
        self.details_layout.addWidget(widget)
    
    def _add_section(self, title: str):
        """Add section header"""
        label = QLabel(title)
        label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        label.setStyleSheet("margin-top: 10px;")
        self.details_layout.addWidget(label)
    
    def _add_text(self, text: str):
        """Add text block"""
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("padding: 5px; background-color: #f0f0f0;")
        self.details_layout.addWidget(label)
