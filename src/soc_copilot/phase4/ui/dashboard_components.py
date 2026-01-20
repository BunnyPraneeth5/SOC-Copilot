"""Dashboard UX Components - Threat Level Banner, Recent Alerts Timeline, and Empty States"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QScrollArea, QGraphicsDropShadowEffect, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor
from datetime import datetime


class ThreatLevelBanner(QFrame):
    """Primary visual hierarchy - shows overall threat level at a glance"""
    
    THREAT_LEVELS = {
        "critical": {"bg": "#1a0000", "fg": "#ff4444", "border": "#ff4444", "icon": "⚫", "label": "CRITICAL"},
        "high": {"bg": "#2d1a00", "fg": "#ff8800", "border": "#ff8800", "icon": "🔴", "label": "HIGH"},
        "elevated": {"bg": "#2d2d00", "fg": "#ffaa00", "border": "#ffaa00", "icon": "🟡", "label": "ELEVATED"},
        "clear": {"bg": "#0d2818", "fg": "#4CAF50", "border": "#4CAF50", "icon": "🟢", "label": "CLEAR"}
    }
    
    view_alerts_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._current_level = "clear"
        self._action_count = 0
        self._init_ui()
    
    def _init_ui(self):
        self.setFixedHeight(80)
        self._apply_style("clear")
        
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(20)
        
        # Left side: Threat level pill
        self.threat_container = QFrame()
        self.threat_container.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.3);
                border-radius: 20px;
                padding: 5px 15px;
            }
        """)
        threat_layout = QHBoxLayout()
        threat_layout.setContentsMargins(15, 8, 15, 8)
        threat_layout.setSpacing(10)
        
        self.threat_icon = QLabel("🟢")
        self.threat_icon.setFont(QFont("Segoe UI Emoji", 16))
        threat_layout.addWidget(self.threat_icon)
        
        self.threat_label = QLabel("THREAT LEVEL:")
        self.threat_label.setFont(QFont("Segoe UI", 11))
        self.threat_label.setStyleSheet("color: rgba(255, 255, 255, 0.8);")
        threat_layout.addWidget(self.threat_label)
        
        self.threat_value = QLabel("CLEAR")
        self.threat_value.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.threat_value.setStyleSheet("color: #4CAF50;")
        threat_layout.addWidget(self.threat_value)
        
        self.threat_container.setLayout(threat_layout)
        layout.addWidget(self.threat_container)
        
        # Center: Action required text
        center_layout = QVBoxLayout()
        center_layout.setSpacing(2)
        
        self.action_count_label = QLabel("0 Alerts")
        self.action_count_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        self.action_count_label.setStyleSheet("color: white;")
        center_layout.addWidget(self.action_count_label)
        
        self.action_text = QLabel("All systems nominal")
        self.action_text.setFont(QFont("Segoe UI", 11))
        self.action_text.setStyleSheet("color: rgba(255, 255, 255, 0.7);")
        center_layout.addWidget(self.action_text)
        
        layout.addLayout(center_layout, 1)
        
        # Right side: View alerts button
        self.view_btn = QPushButton("View Alerts →")
        self.view_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.view_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.15);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.3);
                padding: 12px 24px;
                border-radius: 8px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.25);
                border-color: rgba(255, 255, 255, 0.5);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.35);
            }
        """)
        self.view_btn.clicked.connect(self.view_alerts_clicked.emit)
        layout.addWidget(self.view_btn)
        
        self.setLayout(layout)
        
        # Add shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
    
    def _apply_style(self, level: str):
        config = self.THREAT_LEVELS.get(level, self.THREAT_LEVELS["clear"])
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {config['bg']}, stop:1 #0a0a1a);
                border: 2px solid {config['border']};
                border-radius: 12px;
            }}
        """)
    
    def set_threat_level(self, critical: int, high: int, medium: int, total: int):
        """Update threat level based on alert counts"""
        if critical > 0:
            level = "critical"
            action_text = f"{critical} Critical Alert{'s' if critical > 1 else ''} Need Immediate Attention"
        elif high > 0:
            level = "high"
            action_text = f"{high} High Priority Alert{'s' if high > 1 else ''} Require Review"
        elif medium > 0:
            level = "elevated"
            action_text = f"{medium} Medium Priority Alert{'s' if medium > 1 else ''} Detected"
        else:
            level = "clear"
            action_text = "All systems nominal • No threats detected"
        
        config = self.THREAT_LEVELS[level]
        self._current_level = level
        self._action_count = total
        
        # Update visuals
        self._apply_style(level)
        self.threat_icon.setText(config["icon"])
        self.threat_value.setText(config["label"])
        self.threat_value.setStyleSheet(f"color: {config['fg']};")
        
        self.action_count_label.setText(f"{total} Alert{'s' if total != 1 else ''}")
        self.action_text.setText(action_text)
        
        # Hide button if no alerts
        self.view_btn.setVisible(total > 0)


class RecentAlertItem(QFrame):
    """Single alert item in the recent alerts timeline"""
    
    clicked = pyqtSignal(str, str)  # batch_id, classification
    
    PRIORITY_COLORS = {
        "critical": "#ff4444",
        "high": "#ff8800",
        "medium": "#ffaa00",
        "low": "#4CAF50"
    }
    
    def __init__(self, batch_id: str, classification: str, priority: str, 
                 source_ip: str, timestamp: str):
        super().__init__()
        self.batch_id = batch_id
        self.classification = classification
        self.priority = priority.lower()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui(classification, priority, source_ip, timestamp)
    
    def _init_ui(self, classification: str, priority: str, source_ip: str, timestamp: str):
        color = self.PRIORITY_COLORS.get(self.priority, "#888888")
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #16213e;
                border-left: 4px solid {color};
                border-radius: 6px;
                margin: 2px 0;
            }}
            QFrame:hover {{
                background-color: #1a2744;
            }}
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        # Priority indicator
        priority_label = QLabel(priority.upper()[:4])
        priority_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        priority_label.setStyleSheet(f"""
            color: {color};
            background-color: rgba({self._hex_to_rgb(color)}, 0.15);
            padding: 3px 8px;
            border-radius: 4px;
        """)
        priority_label.setFixedWidth(50)
        layout.addWidget(priority_label)
        
        # Classification
        class_label = QLabel(classification)
        class_label.setFont(QFont("Segoe UI", 11))
        class_label.setStyleSheet("color: #ffffff;")
        class_label.setWordWrap(True)
        layout.addWidget(class_label, 1)
        
        # Source IP
        if source_ip:
            ip_label = QLabel(source_ip)
            ip_label.setFont(QFont("Consolas", 10))
            ip_label.setStyleSheet("color: #888888;")
            layout.addWidget(ip_label)
        
        # Timestamp
        time_label = QLabel(timestamp)
        time_label.setFont(QFont("Segoe UI", 10))
        time_label.setStyleSheet("color: #555555;")
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(time_label)
        
        # Arrow
        arrow = QLabel("→")
        arrow.setStyleSheet("color: #555555; font-size: 14px;")
        layout.addWidget(arrow)
        
        self.setLayout(layout)
    
    def _hex_to_rgb(self, hex_color: str) -> str:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f"{r}, {g}, {b}"
    
    def mousePressEvent(self, event):
        self.clicked.emit(self.batch_id, self.classification)


class RecentAlertsTimeline(QFrame):
    """Timeline view of recent alerts - replaces activity feed"""
    
    alert_clicked = pyqtSignal(str, str)  # batch_id, classification
    
    def __init__(self):
        super().__init__()
        self._alert_items = []
        self._init_ui()
    
    def _init_ui(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #0f1629;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("📋 Recent Alerts")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        header.addWidget(title)
        
        header.addStretch()
        
        self.count_label = QLabel("0 alerts")
        self.count_label.setFont(QFont("Segoe UI", 11))
        self.count_label.setStyleSheet("color: #888888;")
        header.addWidget(self.count_label)
        
        layout.addLayout(header)
        
        # Scroll area for alerts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background-color: #0a0a1a;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #2a3f5f;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background-color: #3a5f8f; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        
        self.alerts_container = QWidget()
        self.alerts_layout = QVBoxLayout()
        self.alerts_layout.setSpacing(6)
        self.alerts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.alerts_container.setLayout(self.alerts_layout)
        
        scroll.setWidget(self.alerts_container)
        layout.addWidget(scroll, 1)
        
        self.setLayout(layout)
        
        # Show empty state initially
        self._show_empty_state()
    
    def _show_empty_state(self):
        """Show empty state when no alerts"""
        self._clear_alerts()
        
        empty_widget = QFrame()
        empty_widget.setStyleSheet("background: transparent;")
        empty_layout = QVBoxLayout()
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(15)
        
        icon = QLabel("✅")
        icon.setFont(QFont("Segoe UI Emoji", 32))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(icon)
        
        title = QLabel("All Clear")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #4CAF50;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(title)
        
        desc = QLabel("No threats detected in analyzed logs.\nAlerts will appear here when detected.")
        desc.setFont(QFont("Segoe UI", 11))
        desc.setStyleSheet("color: #888888;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(desc)
        
        empty_widget.setLayout(empty_layout)
        self.alerts_layout.addWidget(empty_widget)
        self._alert_items.append(empty_widget)
    
    def _clear_alerts(self):
        """Clear all alert items"""
        for item in self._alert_items:
            self.alerts_layout.removeWidget(item)
            item.deleteLater()
        self._alert_items.clear()
    
    def update_alerts(self, alerts_data: list):
        """Update timeline with new alerts"""
        self._clear_alerts()
        
        if not alerts_data:
            self._show_empty_state()
            self.count_label.setText("0 alerts")
            return
        
        self.count_label.setText(f"{len(alerts_data)} alert{'s' if len(alerts_data) != 1 else ''}")
        
        # Add alert items (limit to 15 for performance)
        for alert in alerts_data[:15]:
            item = RecentAlertItem(
                batch_id=alert.get("batch_id", ""),
                classification=alert.get("classification", "Unknown"),
                priority=alert.get("priority", "low"),
                source_ip=alert.get("source_ip", ""),
                timestamp=alert.get("timestamp", "")
            )
            item.clicked.connect(self.alert_clicked.emit)
            self.alerts_layout.addWidget(item)
            self._alert_items.append(item)


class EmptyStateCard(QFrame):
    """Reusable empty state component with icon, title, description, and action button"""
    
    action_clicked = pyqtSignal()
    
    def __init__(self, icon: str, title: str, description: str, 
                 action_text: str = None, state_type: str = "info"):
        super().__init__()
        self._init_ui(icon, title, description, action_text, state_type)
    
    def _init_ui(self, icon: str, title: str, description: str, 
                 action_text: str, state_type: str):
        
        colors = {
            "info": {"bg": "#16213e", "title": "#00d4ff", "border": "#1a2744"},
            "warning": {"bg": "#2d2d00", "title": "#ffaa00", "border": "#665c00"},
            "error": {"bg": "#2d1a1a", "title": "#ff4444", "border": "#4a0000"},
            "success": {"bg": "#0d2818", "title": "#4CAF50", "border": "#1a4d26"}
        }
        config = colors.get(state_type, colors["info"])
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {config['bg']};
                border: 1px solid {config['border']};
                border-radius: 12px;
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(15)
        
        icon_label = QLabel(icon)
        icon_label.setFont(QFont("Segoe UI Emoji", 40))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {config['title']};")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        desc_label = QLabel(description)
        desc_label.setFont(QFont("Segoe UI", 12))
        desc_label.setStyleSheet("color: #888888;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        if action_text:
            action_btn = QPushButton(action_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {config['title']};
                    color: #0a0a1a;
                    border: none;
                    padding: 12px 30px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    opacity: 0.9;
                }}
            """)
            action_btn.clicked.connect(self.action_clicked.emit)
            layout.addWidget(action_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.setLayout(layout)


class QuickActionsBar(QFrame):
    """Quick action buttons for common tasks"""
    
    upload_clicked = pyqtSignal()
    alerts_clicked = pyqtSignal()
    settings_clicked = pyqtSignal()
    refresh_clicked = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        self.setFixedHeight(60)
        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
            }
        """)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(15)
        
        # Upload Logs Button (Primary)
        upload_btn = self._create_button("📁 Upload Logs", primary=True)
        upload_btn.clicked.connect(self.upload_clicked.emit)
        layout.addWidget(upload_btn)
        
        # View Alerts Button
        alerts_btn = self._create_button("🚨 View Alerts")
        alerts_btn.clicked.connect(self.alerts_clicked.emit)
        layout.addWidget(alerts_btn)
        
        # Settings Button
        settings_btn = self._create_button("⚙️ Settings")
        settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(settings_btn)
        
        layout.addStretch()
        
        # Refresh Button
        self.refresh_btn = self._create_button("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)
        layout.addWidget(self.refresh_btn)
        
        self.setLayout(layout)
    
    def _create_button(self, text: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        if primary:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #00d4ff;
                    color: #0a0a1a;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #00a8cc; }
                QPushButton:pressed { background-color: #0088aa; }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #16213e;
                    color: #ffffff;
                    border: 1px solid #1a2744;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover { 
                    background-color: #1a2744;
                    border-color: #2a3f5f;
                }
                QPushButton:pressed { background-color: #0f1629; }
            """)
        
        return btn
    
    def set_refreshing(self, refreshing: bool):
        """Update refresh button state"""
        if refreshing:
            self.refresh_btn.setText("⏳ Refreshing...")
            self.refresh_btn.setEnabled(False)
        else:
            self.refresh_btn.setText("🔄 Refresh")
            self.refresh_btn.setEnabled(True)


class CompactMetricCard(QFrame):
    """Compact metric card with trend indicator"""
    
    clicked = pyqtSignal(str)  # priority filter
    
    PRIORITY_STYLES = {
        "total": {"bg": "#3F51B5", "icon": "📊"},
        "critical": {"bg": "#d32f2f", "icon": "🚨"},
        "high": {"bg": "#f57c00", "icon": "⚠️"},
        "medium": {"bg": "#ffa000", "icon": "📋"},
        "low": {"bg": "#4CAF50", "icon": "✓"}
    }
    
    def __init__(self, label: str, priority: str = "total"):
        super().__init__()
        self.label = label
        self.priority = priority
        self._value = 0
        self._trend = 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()
    
    def _init_ui(self):
        style = self.PRIORITY_STYLES.get(self.priority, self.PRIORITY_STYLES["total"])
        
        self.setFixedHeight(90)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {style['bg']}, stop:1 {self._darken(style['bg'])});
                border-radius: 10px;
            }}
            QFrame:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {self._lighten(style['bg'])}, stop:1 {style['bg']});
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)
        
        # Top row: icon + label
        top_row = QHBoxLayout()
        
        icon_label = QLabel(style["icon"])
        icon_label.setFont(QFont("Segoe UI Emoji", 12))
        top_row.addWidget(icon_label)
        
        name_label = QLabel(self.label)
        name_label.setFont(QFont("Segoe UI", 11))
        name_label.setStyleSheet("color: rgba(255, 255, 255, 0.9);")
        top_row.addWidget(name_label)
        top_row.addStretch()
        
        layout.addLayout(top_row)
        
        # Value row
        value_row = QHBoxLayout()
        
        self.value_label = QLabel("0")
        self.value_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        self.value_label.setStyleSheet("color: white;")
        value_row.addWidget(self.value_label)
        
        value_row.addStretch()
        
        # Trend indicator
        self.trend_label = QLabel("")
        self.trend_label.setFont(QFont("Segoe UI", 10))
        self.trend_label.setStyleSheet("color: rgba(255, 255, 255, 0.7);")
        value_row.addWidget(self.trend_label)
        
        layout.addLayout(value_row)
        
        self.setLayout(layout)
        
        # Add shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)
    
    def _darken(self, hex_color: str) -> str:
        c = QColor(hex_color)
        return c.darker(120).name()
    
    def _lighten(self, hex_color: str) -> str:
        c = QColor(hex_color)
        return c.lighter(115).name()
    
    def set_value(self, value: int, trend: int = 0):
        self._value = value
        self._trend = trend
        self.value_label.setText(str(value))
        
        if trend > 0:
            self.trend_label.setText(f"↑ +{trend}")
            self.trend_label.setStyleSheet("color: rgba(255, 200, 200, 0.9);")
        elif trend < 0:
            self.trend_label.setText(f"↓ {trend}")
            self.trend_label.setStyleSheet("color: rgba(200, 255, 200, 0.9);")
        else:
            self.trend_label.setText("")
    
    def mousePressEvent(self, event):
        self.clicked.emit(self.priority)


class SystemHealthGrid(QFrame):
    """Compact 2-column grid showing system health status"""
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border: 1px solid #1a2744;
                border-radius: 10px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)
        
        # Header
        title = QLabel("System Health")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #00d4ff;")
        layout.addWidget(title)
        
        # Status rows
        self.rows = {}
        row_data = [
            ("pipeline", "ML Pipeline", "●", "Loading..."),
            ("ingestion", "Log Ingestion", "●", "Not Started"),
            ("governance", "Governance", "●", "Active")
        ]
        
        for key, label, icon, default_value in row_data:
            row = QHBoxLayout()
            row.setSpacing(10)
            
            status_led = QLabel(icon)
            status_led.setFont(QFont("Segoe UI", 10))
            status_led.setStyleSheet("color: #888888;")
            status_led.setFixedWidth(15)
            
            name = QLabel(label)
            name.setFont(QFont("Segoe UI", 11))
            name.setStyleSheet("color: #ffffff;")
            
            value = QLabel(default_value)
            value.setFont(QFont("Segoe UI", 10))
            value.setStyleSheet("color: #888888;")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            
            row.addWidget(status_led)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(value)
            
            layout.addLayout(row)
            self.rows[key] = (status_led, value)
        
        self.setLayout(layout)
    
    def update_status(self, key: str, status: str, value: str, color: str = "#4CAF50"):
        """Update a status row"""
        if key in self.rows:
            led, val_label = self.rows[key]
            led.setStyleSheet(f"color: {color};")
            val_label.setText(value)
            val_label.setStyleSheet(f"color: {color};")
