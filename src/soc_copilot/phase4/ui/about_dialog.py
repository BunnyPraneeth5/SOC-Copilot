"""About dialog for SOC Copilot"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QPen
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF

from .theme import ThemeManager


def _palette():
    return ThemeManager.instance().palette


class AboutDialog(QDialog):
    """About dialog showing application information"""
    
    VERSION = "1.0.0-beta.1"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About SOC Copilot")
        self.setFixedSize(450, 420)
        self.setModal(True)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # Icon
        icon_label = QLabel()
        icon_label.setPixmap(self._create_icon_pixmap())
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)
        
        # Title
        title = QLabel("SOC Copilot")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_palette().accent};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Version with beta badge
        version = QLabel(f"Version {self.VERSION}")
        version.setFont(QFont("Segoe UI", 12))
        version.setStyleSheet(f"color: {_palette().text_muted};")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        
        # Beta disclaimer
        beta_label = QLabel(
            "⚠ Beta Release — This is a pre-release version.\n"
            "Features may change. Report issues on GitHub."
        )
        beta_label.setFont(QFont("Segoe UI", 9))
        beta_label.setStyleSheet(
            f"color: {_palette().sev_medium}; background-color: {_palette().warning_bg}; "
            "border-radius: 4px; padding: 6px;"
        )
        beta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        beta_label.setWordWrap(True)
        layout.addWidget(beta_label)
        
        # Description
        desc = QLabel(
            "Offline Security Operations Center Analysis Tool\n"
            "Hybrid ML Detection (Isolation Forest + Random Forest)"
        )
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet(f"color: {_palette().text};")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {_palette().border};")
        layout.addWidget(line)
        
        # Features
        features = QLabel(
            "✓ Fully Offline Operation\n"
            "✓ Real-time Log Analysis\n"
            "✓ Governance Controls\n"
            "✓ SOC-Grade Security"
        )
        features.setFont(QFont("Segoe UI", 10))
        features.setStyleSheet(f"color: {_palette().text};")
        features.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(features)
        
        # Copyright
        copyright_label = QLabel("© 2026 SOC Copilot Team • MIT License")
        copyright_label.setFont(QFont("Segoe UI", 9))
        copyright_label.setStyleSheet(f"color: {_palette().text_muted};")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(copyright_label)
        
        # Close button
        layout.addStretch()
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(100)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {_palette().accent};
                color: {_palette().text_inverse};
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {_palette().accent_hover};
            }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        # Dialog styling (matches palette surface color)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {_palette().surface};
            }}
            QLabel {{
                color: {_palette().text};
            }}
        """)
    
    def _create_icon_pixmap(self) -> QPixmap:
        """Create shield icon programmatically"""
        size = 80
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw shield
        painter.setPen(QPen(QColor(_palette().accent), 2))
        painter.setBrush(QColor(_palette().info_bg))
        
        x, y = 5, 5
        s = size - 10
        
        shield_points = [
            QPointF(x + s/2, y),
            QPointF(x + s, y + s*0.3),
            QPointF(x + s, y + s*0.6),
            QPointF(x + s/2, y + s),
            QPointF(x, y + s*0.6),
            QPointF(x, y + s*0.3),
        ]
        painter.drawPolygon(QPolygonF(shield_points))
        
        # Magnifying glass
        painter.setPen(QPen(QColor(_palette().accent), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(x + s*0.3), int(y + s*0.25), int(s*0.4), int(s*0.4))
        painter.drawLine(
            int(x + s*0.6), int(y + s*0.55),
            int(x + s*0.75), int(y + s*0.7)
        )
        
        painter.end()
        return pixmap
