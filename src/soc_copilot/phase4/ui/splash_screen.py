"""Splash screen for SOC Copilot application startup"""

from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QLinearGradient, QPen


class SplashScreen(QSplashScreen):
    """Professional splash screen for SOC Copilot startup"""
    
    def __init__(self):
        # Create a custom pixmap for the splash
        pixmap = self._create_splash_pixmap()
        super().__init__(pixmap)
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        
    def _create_splash_pixmap(self) -> QPixmap:
        """Create a professional splash screen programmatically"""
        width, height = 600, 400
        pixmap = QPixmap(width, height)
        pixmap.fill(QColor("#1e1e1e"))
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw gradient background accent
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0, QColor("#1e3a5f"))
        gradient.setColorAt(1, QColor("#1e1e1e"))
        painter.fillRect(0, 0, width, 120, gradient)
        
        # Draw shield icon (simplified)
        self._draw_shield_icon(painter, 50, 140, 100)
        
        # Draw title "SOC Copilot"
        title_font = QFont("Segoe UI", 42, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(170, 200, "SOC")
        
        painter.setPen(QColor("#00d4ff"))
        painter.drawText(280, 200, "Copilot")
        
        # Draw subtitle
        subtitle_font = QFont("Segoe UI", 14)
        painter.setFont(subtitle_font)
        painter.setPen(QColor("#888888"))
        painter.drawText(170, 235, "Real-Time Security Analysis")
        
        # Draw loading bar background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#333333"))
        painter.drawRoundedRect(50, 340, 500, 8, 4, 4)
        
        # Draw version
        version_font = QFont("Segoe UI", 10)
        painter.setFont(version_font)
        painter.setPen(QColor("#666666"))
        painter.drawText(50, 380, "Version 0.1.0")
        
        # Draw copyright/branding
        painter.drawText(400, 380, "© SOC Copilot Team")
        
        painter.end()
        return pixmap
    
    def _draw_shield_icon(self, painter: QPainter, x: int, y: int, size: int):
        """Draw a simplified shield icon"""
        # Shield body
        painter.setPen(QPen(QColor("#00d4ff"), 3))
        painter.setBrush(QColor("#1e3a5f"))
        
        # Draw shield shape using polygon
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QPolygonF
        
        shield_points = [
            QPointF(x + size/2, y),                    # Top center
            QPointF(x + size, y + size*0.3),           # Top right
            QPointF(x + size, y + size*0.6),           # Middle right
            QPointF(x + size/2, y + size),             # Bottom center (point)
            QPointF(x, y + size*0.6),                  # Middle left
            QPointF(x, y + size*0.3),                  # Top left
        ]
        
        painter.drawPolygon(QPolygonF(shield_points))
        
        # Draw magnifying glass inside shield
        painter.setPen(QPen(QColor("#00d4ff"), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        
        # Circle part of magnifying glass
        glass_x = x + size*0.35
        glass_y = y + size*0.3
        glass_size = size*0.35
        painter.drawEllipse(int(glass_x), int(glass_y), int(glass_size), int(glass_size))
        
        # Handle of magnifying glass
        painter.drawLine(
            int(glass_x + glass_size*0.8), int(glass_y + glass_size*0.8),
            int(glass_x + glass_size*1.3), int(glass_y + glass_size*1.3)
        )
    
    def show_message(self, message: str):
        """Show a status message on the splash screen"""
        self.showMessage(
            f"  {message}",
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
            QColor("#00d4ff")
        )
        QApplication.processEvents()
    
    def update_progress(self, message: str, delay_ms: int = 100):
        """Update splash with progress message and optional delay"""
        self.show_message(message)
        if delay_ms > 0:
            # Process events to update display
            QTimer.singleShot(delay_ms, lambda: None)
            QApplication.processEvents()


def create_splash() -> SplashScreen:
    """Factory function to create splash screen"""
    splash = SplashScreen()
    splash.show()
    splash.show_message("Initializing...")
    QApplication.processEvents()
    return splash
