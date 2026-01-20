"""Optimized alert details panel with breadcrumb navigation"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QScrollArea, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class DetailField(QFrame):
    """Styled detail field widget"""
    
    def __init__(self, label: str, value: str, color: str = "#ffffff"):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #1a2744;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #888888; font-size: 10px; font-weight: bold;")
        
        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        val.setWordWrap(True)
        
        layout.addWidget(lbl)
        layout.addWidget(val)
        self.setLayout(layout)


class AlertDetailsPanel(QWidget):
    """Enhanced alert details with navigation"""
    
    back_clicked = pyqtSignal()
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)
        
        # Header with back button
        header = QHBoxLayout()
        
        back_btn = QPushButton("← Back to Alerts")
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #00d4ff;
                border: 1px solid #00d4ff;
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #00d4ff;
                color: #0a0a1a;
            }
        """)
        back_btn.clicked.connect(self.back_clicked.emit)
        header.addWidget(back_btn)
        
        header.addStretch()
        
        # Title
        self.title_label = QLabel("🔍 Alert Investigation")
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #ffffff;")
        header.addWidget(self.title_label)
        
        header.addStretch()
        layout.addLayout(header)
        
        # Scroll area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
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
        """)
        
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout()
        self.details_layout.setSpacing(12)
        self.details_widget.setLayout(self.details_layout)
        
        scroll.setWidget(self.details_widget)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        self._show_placeholder()
    
    def _show_placeholder(self):
        """Show placeholder text"""
        self._clear_details()
        
        placeholder = QLabel(
            "📋 No alert selected\n\n"
            "Select an alert from the Alerts view to see detailed analysis"
        )
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(
            "color: #888888; font-size: 13px; padding: 40px;"
        )
        self.details_layout.addWidget(placeholder)
    
    def _clear_details(self):
        """Clear details panel"""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def show_alert(self, batch_id: str, alert_classification: str):
        """Display alert details with enhanced layout"""
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
            
            # Priority badge
            priority_color = self._get_priority_color(alert.priority)
            priority_section = QHBoxLayout()
            priority_badge = QLabel(f"  {alert.priority.upper()}  ")
            priority_badge.setStyleSheet(f"""
                background-color: {priority_color};
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 4px;
                padding: 6px 12px;
            """)
            priority_section.addWidget(priority_badge)
            priority_section.addStretch()
            self.details_layout.addLayout(priority_section)
            
            # Classification header
            class_label = QLabel(alert.classification)
            class_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            class_label.setStyleSheet("color: #00d4ff; padding: 10px 0;")
            class_label.setWordWrap(True)
            self.details_layout.addWidget(class_label)
            
            # Key metrics grid
            metrics_grid = QHBoxLayout()
            metrics_grid.setSpacing(10)
            
            metrics_grid.addWidget(DetailField(
                "CONFIDENCE",
                f"{alert.confidence:.1%}",
                self._get_confidence_color(alert.confidence)
            ))
            
            metrics_grid.addWidget(DetailField(
                "ANOMALY SCORE",
                f"{alert.anomaly_score:.3f}",
                "#ff8800" if alert.anomaly_score > 0.5 else "#ffffff"
            ))
            
            metrics_grid.addWidget(DetailField(
                "RISK SCORE",
                f"{alert.risk_score:.3f}",
                "#ff4444" if alert.risk_score > 0.7 else "#ffaa00"
            ))
            
            self.details_layout.addLayout(metrics_grid)
            
            # Network info if available
            if alert.source_ip or alert.destination_ip:
                network_section = QHBoxLayout()
                network_section.setSpacing(10)
                
                if alert.source_ip:
                    network_section.addWidget(DetailField(
                        "SOURCE IP",
                        alert.source_ip,
                        "#00d4ff"
                    ))
                
                if alert.destination_ip:
                    network_section.addWidget(DetailField(
                        "DESTINATION IP",
                        alert.destination_ip,
                        "#00d4ff"
                    ))
                
                self.details_layout.addLayout(network_section)
            
            # Metadata
            meta_section = QHBoxLayout()
            meta_section.setSpacing(10)
            
            meta_section.addWidget(DetailField(
                "ALERT ID",
                alert.alert_id[:16] + "...",
                "#888888"
            ))
            
            meta_section.addWidget(DetailField(
                "BATCH ID",
                batch_id[:16] + "...",
                "#888888"
            ))
            
            self.details_layout.addLayout(meta_section)
            
            # Reasoning section
            self._add_section("🧠 Analysis Reasoning", alert.reasoning)
            
            # Suggested action
            self._add_section("✅ Suggested Action", alert.suggested_action, "#4CAF50")
            
            self.details_layout.addStretch()
        
        except Exception as e:
            self._show_error(str(e))
    
    def _get_priority_color(self, priority: str) -> str:
        """Get color for priority level"""
        p = priority.lower()
        if "critical" in p:
            return "#d32f2f"
        elif "high" in p:
            return "#f57c00"
        elif "medium" in p:
            return "#ffa000"
        return "#757575"
    
    def _get_confidence_color(self, confidence: float) -> str:
        """Get color based on confidence level"""
        if confidence >= 0.8:
            return "#4CAF50"
        elif confidence >= 0.6:
            return "#ffaa00"
        return "#ff8800"
    
    def _add_section(self, title: str, content: str, accent_color: str = "#00d4ff"):
        """Add content section"""
        # Section header
        header = QLabel(title)
        header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {accent_color}; padding: 10px 0 5px 0;")
        self.details_layout.addWidget(header)
        
        # Content box
        content_frame = QFrame()
        content_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #16213e;
                border-left: 3px solid {accent_color};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet("color: #ffffff; font-size: 12px; line-height: 1.5;")
        content_layout.addWidget(content_label)
        
        content_frame.setLayout(content_layout)
        self.details_layout.addWidget(content_frame)
    
    def _show_error(self, error: str):
        """Show error state"""
        self._clear_details()
        error_label = QLabel(f"❌ Error loading alert details:\n{error}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet("color: #ff4444; padding: 40px;")
        self.details_layout.addWidget(error_label)
