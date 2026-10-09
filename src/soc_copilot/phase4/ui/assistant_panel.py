"""Interactive Chat Assistant Panel with user input support"""

import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLabel, QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from .theme import ThemeManager, PAGE_MARGIN, PAGE_SPACING
from .components import PageHeader, text_button
from .icons import set_icon


def _palette():
    return ThemeManager.instance().palette


class AssistantPanel(QWidget):
    """Interactive chat assistant with Q&A input"""

    def __init__(self):
        super().__init__()
        self.current_alert = None
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        """Re-apply palette-derived styles after a theme switch."""
        p = _palette()
        self.chat_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {p.surface};
                color: {p.text};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
                padding: 14px;
                font-size: 13px;
            }}
        """)
        self._input_frame.setStyleSheet(f"""
            QFrame#chatInputFrame {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
            }}
        """)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: transparent;
                border: none;
                color: {p.text};
                font-size: 13px;
                padding: 4px;
            }}
        """)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(PAGE_SPACING)
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)

        self.header = PageHeader(
            "Assistant", "message-square",
            "Explains the selected alert from local analysis. Nothing leaves this machine.",
        )
        self._header = self.header.title_label
        layout.addWidget(self.header)

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display, 1)

        # Quick questions
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        self.quick_buttons = []
        quick_actions = [
            ("Why was this raised?", "why", "help-circle"),
            ("Explain", "explain", "book-open"),
            ("Recommended action", "action", "shield"),
            ("Risk", "risk", "bar-chart"),
        ]
        for text, cmd, icon in quick_actions:
            btn = text_button(text, icon)
            btn.clicked.connect(lambda checked, c=cmd: self._handle_quick_action(c))
            actions_layout.addWidget(btn)
            self.quick_buttons.append(btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # Input area
        input_frame = QFrame()
        input_frame.setObjectName("chatInputFrame")
        self._input_frame = input_frame
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(12, 6, 6, 6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask a question about the selected alert...")
        self.input_field.returnPressed.connect(self._handle_user_input)
        input_layout.addWidget(self.input_field)

        self.send_btn = text_button("Send", "send", "primary", "text_inverse")
        self.send_btn.clicked.connect(self._handle_user_input)
        input_layout.addWidget(self.send_btn)

        input_frame.setLayout(input_layout)
        layout.addWidget(input_frame)

        self.setLayout(layout)
        self._apply_theme()
        self._show_welcome()

    def _show_welcome(self):
        """Show welcome message"""
        self.chat_display.clear()
        self._add_message("system", "Assistant ready.")
        self._add_message("system", "Select an alert from the table to analyze, or ask a general question.")
        self._add_message("system", "Quick commands: why, explain, action, risk")

    def explain_alert(self, alert):
        """Display alert explanation"""
        self.current_alert = alert
        self.chat_display.clear()

        self._add_message("system", f"Analyzing: {alert.classification}")

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

{'Requires immediate attention.' if risk_level == 'HIGH' else 'Monitor and review as needed.' if risk_level == 'LOW' else 'Investigate when possible.'}"""

    def _add_message(self, role: str, text: str):
        """Add styled message to chat"""
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
        text = text.replace("\n", "<br>")

        p = _palette()
        if role == "user":
            html = (
                f'<div style="margin: 8px 0;"><span style="color: {p.text_muted}; '
                f'font-size: 11px; font-weight: 600;">YOU</span><br>'
                f'<span style="color: {p.text};">{text}</span></div>'
            )
        elif role == "assistant":
            html = (
                f'<div style="margin: 8px 0;"><span style="color: {p.accent}; '
                f'font-size: 11px; font-weight: 600;">ASSISTANT</span><br>'
                f'<span style="color: {p.text};">{text}</span></div>'
            )
        else:
            html = f'<div style="color: {p.text_muted}; margin: 4px 0;">{text}</div>'

        self.chat_display.append(html)
