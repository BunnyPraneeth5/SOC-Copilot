"""Chat-like assistant panel (no LLM, uses explainability only)"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AssistantPanel(QWidget):
    """Chat-like explanation panel using predefined templates"""
    
    def __init__(self):
        super().__init__()
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Analyst Assistant")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: 1px solid #444;
                padding: 10px;
            }
        """)
        layout.addWidget(self.chat_display)
        
        self.setLayout(layout)
        self._show_welcome()
    
    def _show_welcome(self):
        """Show welcome message"""
        self.chat_display.clear()
        self._add_message("system", "SOC Copilot Assistant Ready")
        self._add_message("system", "Select an alert to see explanation")
    
    def explain_alert(self, alert):
        """Generate explanation using templates (no LLM)"""
        self.chat_display.clear()
        
        # Question 1: Why was this alert generated?
        self._add_message("user", "Why was this alert generated?")
        
        explanation = self._generate_why_explanation(alert)
        self._add_message("assistant", explanation)
        
        # Question 2: What does this mean?
        self._add_message("user", "What does this mean?")
        
        meaning = self._generate_meaning_explanation(alert)
        self._add_message("assistant", meaning)
        
        # Question 3: What should I do?
        self._add_message("user", "What should I do?")
        self._add_message("assistant", alert.suggested_action)
    
    def _generate_why_explanation(self, alert) -> str:
        """Generate 'why' explanation from alert metadata"""
        parts = []
        
        parts.append(f"This {alert.priority} alert was generated because:")
        parts.append(f"• Classification: {alert.classification} (confidence: {alert.confidence:.0%})")
        parts.append(f"• Anomaly score: {alert.anomaly_score:.3f}")
        parts.append(f"• Risk score: {alert.risk_score:.3f}")
        
        if alert.source_ip:
            parts.append(f"• Source: {alert.source_ip}")
        
        parts.append(f"\nReasoning: {alert.reasoning}")
        
        return "\n".join(parts)
    
    def _generate_meaning_explanation(self, alert) -> str:
        """Generate 'meaning' explanation from classification"""
        templates = {
            "BruteForce": "A brute force attack involves repeated login attempts to guess credentials. This pattern suggests an attacker is trying to gain unauthorized access.",
            "PortScan": "A port scan is reconnaissance activity where an attacker probes your network to find open ports and services. This is often a precursor to an attack.",
            "DDoS": "A Distributed Denial of Service attack attempts to overwhelm your systems with traffic, making services unavailable to legitimate users.",
            "SQLInjection": "SQL injection is an attack that exploits vulnerabilities in database queries to access or manipulate data. This is a critical security risk.",
            "XSS": "Cross-Site Scripting allows attackers to inject malicious scripts into web pages viewed by other users, potentially stealing data or hijacking sessions."
        }
        
        explanation = templates.get(alert.classification, 
                                   f"This {alert.classification} pattern indicates potentially malicious activity that requires investigation.")
        
        return explanation
    
    def _add_message(self, role: str, text: str):
        """Add message to chat display"""
        if role == "user":
            self.chat_display.append(f'<div style="color: #4CAF50; font-weight: bold;">Q: {text}</div>')
        elif role == "assistant":
            self.chat_display.append(f'<div style="color: #2196F3;">A: {text}</div>')
        else:
            self.chat_display.append(f'<div style="color: #888; font-style: italic;">{text}</div>')
        
        self.chat_display.append("")  # Blank line
