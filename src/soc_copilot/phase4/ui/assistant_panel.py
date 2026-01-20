"""Interactive Chat Assistant Panel with user input support"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
    QLabel, QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class AssistantPanel(QWidget):
    """Interactive chat assistant with Q&A input"""
    
    def __init__(self):
        super().__init__()
        self.current_alert = None
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QLabel("🤖 SOC Assistant")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #00d4ff;")
        layout.addWidget(header)
        
        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1a1a2e;
                color: #ffffff;
                border: 1px solid #2a2a4e;
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.chat_display)
        
        # Quick action buttons
        actions_frame = QFrame()
        actions_frame.setStyleSheet("background: transparent;")
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        
        self.quick_buttons = []
        quick_actions = [
            ("❓ Why", "why"),
            ("📖 Explain", "explain"),
            ("🛡️ Action", "action"),
            ("📊 Risk", "risk"),
        ]
        
        for text, cmd in quick_actions:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #16213e;
                    color: #ffffff;
                    border: 1px solid #0f3460;
                    border-radius: 5px;
                    padding: 8px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #0f3460;
                    border-color: #00d4ff;
                }
                QPushButton:disabled {
                    background-color: #1a1a2e;
                    color: #555555;
                }
            """)
            btn.clicked.connect(lambda checked, c=cmd: self._handle_quick_action(c))
            actions_layout.addWidget(btn)
            self.quick_buttons.append(btn)
        
        actions_frame.setLayout(actions_layout)
        layout.addWidget(actions_frame)
        
        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: #16213e;
                border-radius: 8px;
            }
        """)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(10, 8, 10, 8)
        
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question about the selected alert...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: transparent;
                border: none;
                color: #ffffff;
                font-size: 13px;
                padding: 5px;
            }
        """)
        self.input_field.returnPressed.connect(self._handle_user_input)
        input_layout.addWidget(self.input_field)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #00d4ff;
                color: #1a1a2e;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00a8cc;
            }
        """)
        self.send_btn.clicked.connect(self._handle_user_input)
        input_layout.addWidget(self.send_btn)
        
        input_frame.setLayout(input_layout)
        layout.addWidget(input_frame)
        
        self.setLayout(layout)
        self._show_welcome()
    
    def _show_welcome(self):
        """Show welcome message"""
        self.chat_display.clear()
        self._add_message("system", "🛡️ SOC Copilot Assistant Ready")
        self._add_message("system", "Select an alert from the table to analyze, or ask a general question.")
        self._add_message("system", "Quick commands: why, explain, action, risk")
    
    def explain_alert(self, alert):
        """Display alert explanation"""
        self.current_alert = alert
        self.chat_display.clear()
        
        self._add_message("system", f"📋 Analyzing: {alert.classification}")
        
        # Auto-generate initial explanation
        self._add_message("user", "What is this alert about?")
        
        explanation = self._generate_explanation(alert)
        self._add_message("assistant", explanation)
        
        # Enable quick buttons
        for btn in self.quick_buttons:
            btn.setEnabled(True)
    
    def _handle_user_input(self):
        """Process user input"""
        text = self.input_field.text().strip().lower()
        if not text:
            return
        
        self.input_field.clear()
        self._add_message("user", text)
        
        # Process command
        response = self._generate_response(text)
        self._add_message("assistant", response)
    
    def _handle_quick_action(self, action: str):
        """Handle quick action button click"""
        if not self.current_alert:
            self._add_message("assistant", "Please select an alert first.")
            return
        
        self._add_message("user", action.capitalize())
        
        if action == "why":
            response = self._generate_why(self.current_alert)
        elif action == "explain":
            response = self._generate_explanation(self.current_alert)
        elif action == "action":
            response = self._generate_action(self.current_alert)
        elif action == "risk":
            response = self._generate_risk(self.current_alert)
        else:
            response = "Unknown action"
        
        self._add_message("assistant", response)
    
    def _generate_response(self, question: str) -> str:
        """Generate response based on question"""
        if not self.current_alert:
            return self._answer_general(question)
        
        alert = self.current_alert
        
        if "why" in question or "reason" in question:
            return self._generate_why(alert)
        elif "action" in question or "do" in question or "fix" in question:
            return self._generate_action(alert)
        elif "risk" in question or "score" in question or "severity" in question:
            return self._generate_risk(alert)
        elif "explain" in question or "what" in question or "mean" in question:
            return self._generate_explanation(alert)
        elif "source" in question or "ip" in question or "from" in question:
            return f"Source IP: {alert.source_ip or 'Unknown'}\nDestination: {alert.destination_ip or 'Unknown'}"
        else:
            return self._answer_general(question)
    
    def _answer_general(self, question: str) -> str:
        """Answer general questions"""
        general_answers = {
            "help": "I can help you understand alerts. Select an alert and ask:\n• Why was this generated?\n• What should I do?\n• What's the risk level?",
            "hi": "Hello! I'm your SOC assistant. Select an alert to analyze.",
            "hello": "Hi there! Ready to help you investigate security alerts.",
            "commands": "Available commands:\n• why - Get reason for alert\n• explain - Full explanation\n• action - Recommended actions\n• risk - Risk assessment",
        }
        
        for key, answer in general_answers.items():
            if key in question:
                return answer
        
        return "I can help analyze security alerts. Select an alert from the table, then ask me questions about it."
    
    def _generate_why(self, alert) -> str:
        """Generate why explanation"""
        return f"""This alert was generated because:

• **Classification**: {alert.classification} (conf: {alert.confidence:.0%})
• **Anomaly Score**: {alert.anomaly_score:.3f}
• **Risk Score**: {alert.risk_score:.3f}
• **Priority**: {alert.priority}

{alert.reasoning}"""
    
    def _generate_explanation(self, alert) -> str:
        """Generate detailed explanation"""
        templates = {
            "BruteForce": "A brute force attack involves repeated login attempts to guess credentials. Multiple failed authentication attempts from the same source indicate credential stuffing or password guessing.",
            "PortScan": "Port scanning is reconnaissance activity where an attacker probes network ports to identify running services and potential vulnerabilities.",
            "DDoS": "Distributed Denial of Service attack floods your systems with traffic to make services unavailable. High volume traffic from multiple sources is a key indicator.",
            "DataExfiltration": "Data exfiltration involves unauthorized transfer of data outside the network. Large outbound transfers to unusual destinations indicate possible data theft.",
            "SQLInjection": "SQL injection exploits vulnerabilities in database queries to access or manipulate data through malicious input.",
            "XSS": "Cross-Site Scripting injects malicious scripts into web pages to steal data or hijack user sessions.",
            "Benign": "This activity appears to be normal network behavior with no indicators of malicious intent.",
        }
        
        base = templates.get(alert.classification, 
            f"This {alert.classification} pattern indicates potentially malicious activity requiring investigation.")
        
        return f"**{alert.classification}**\n\n{base}"
    
    def _generate_action(self, alert) -> str:
        """Generate recommended action"""
        return f"""**Recommended Actions:**

{alert.suggested_action}

**Investigation Steps:**
1. Review source IP reputation: {alert.source_ip or 'N/A'}
2. Check historical activity for this pattern
3. Correlate with other security events
4. Document findings in incident report"""
    
    def _generate_risk(self, alert) -> str:
        """Generate risk assessment"""
        risk_level = "LOW" if alert.risk_score < 0.3 else "MEDIUM" if alert.risk_score < 0.7 else "HIGH"
        
        return f"""**Risk Assessment**

• Level: **{risk_level}**
• Score: {alert.risk_score:.2f}/1.00
• Priority: {alert.priority}
• Confidence: {alert.confidence:.0%}

{'⚠️ Requires immediate attention!' if risk_level == 'HIGH' else '✅ Monitor and review as needed.' if risk_level == 'LOW' else '🔍 Investigate when possible.'}"""
    
    def _add_message(self, role: str, text: str):
        """Add styled message to chat"""
        text = text.replace("\n", "<br>")
        text = text.replace("**", "<b>").replace("**", "</b>")  # Basic bold
        
        if role == "user":
            html = f'<div style="background-color: #0f3460; padding: 10px; border-radius: 8px; margin: 5px 0;"><span style="color: #00d4ff; font-weight: bold;">You:</span> {text}</div>'
        elif role == "assistant":
            html = f'<div style="background-color: #16213e; padding: 10px; border-radius: 8px; margin: 5px 0;"><span style="color: #4CAF50; font-weight: bold;">Assistant:</span><br>{text}</div>'
        else:
            html = f'<div style="color: #888; padding: 5px; font-style: italic;">{text}</div>'
        
        self.chat_display.append(html)
