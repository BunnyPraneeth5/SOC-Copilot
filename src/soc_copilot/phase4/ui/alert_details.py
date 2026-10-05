"""Optimized alert details panel with breadcrumb navigation"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QScrollArea, QPushButton, QFrame, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from .theme import ThemeManager, severity_color, set_role


def _palette():
    return ThemeManager.instance().palette


class DetailField(QFrame):
    """Styled detail field widget"""

    def __init__(self, label: str, value: str, color: str | None = None):
        super().__init__()
        p = _palette()
        color = color or p.text
        self.setStyleSheet(f"""
            DetailField {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        
        lbl = QLabel(label)
        lbl.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 10px; font-weight: bold;"
        )
        
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
        self._back_btn = back_btn
        self._style_back_button()
        back_btn.clicked.connect(self.back_clicked.emit)
        header.addWidget(back_btn)
        
        header.addStretch()
        
        # Title
        self.title_label = QLabel("🔍 Alert Investigation")
        self.title_label.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.addWidget(self.title_label)
        
        header.addStretch()
        layout.addLayout(header)
        
        # Scroll area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        
        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout()
        self.details_layout.setSpacing(12)
        self.details_widget.setLayout(self.details_layout)
        
        scroll.setWidget(self.details_widget)
        layout.addWidget(scroll)
        
        self.setLayout(layout)
        self._last_show_args = None
        self._show_placeholder()

    def _style_back_button(self):
        self._back_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {_palette().accent};
                border: 1px solid {_palette().accent};
                border-radius: 4px;
                padding: 8px 15px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {_palette().accent};
                color: {_palette().text_inverse};
            }}
        """)

    def _apply_theme(self):
        """Re-apply palette styles and re-render the current alert."""
        self._style_back_button()
        if self._last_show_args is not None:
            self.show_alert(*self._last_show_args)
        else:
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
            f"color: {_palette().text_muted}; font-size: 13px; padding: 40px;"
        )
        self.details_layout.addWidget(placeholder)
    
    def _clear_details(self):
        """Clear details panel"""
        while self.details_layout.count():
            item = self.details_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()
    
    def show_alert(
        self,
        batch_id: str,
        alert_classification: str | None = None,
        alert_id: str | None = None,
    ):
        """Display alert details with enhanced layout.

        Prefer matching by ``alert_id`` when given; fall back to the first
        alert with ``alert_classification`` (older callers only pass the
        classification text).
        """
        self._last_show_args = (batch_id, alert_classification, alert_id)
        try:
            result = self.bridge.get_alert_by_id(batch_id)
            if not result:
                return

            # Find matching alert
            alert = None
            if alert_id:
                for a in result.alerts:
                    if getattr(a, "alert_id", None) == alert_id:
                        alert = a
                        break
            if alert is None and alert_classification:
                for a in result.alerts:
                    if a.classification == alert_classification:
                        alert = a
                        break

            if not alert:
                return
            
            self._clear_details()
            
            # Priority badge
            priority_color = severity_color(alert.priority)
            priority_section = QHBoxLayout()
            priority_badge = QLabel(f"  {alert.priority.upper()}  ")
            priority_badge.setStyleSheet(f"""
                background-color: {priority_color};
                color: {_palette().text_inverse};
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
            class_label.setStyleSheet(
                f"color: {_palette().accent}; padding: 10px 0;"
            )
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
                _palette().sev_high if alert.anomaly_score > 0.5
                else _palette().text
            ))

            metrics_grid.addWidget(DetailField(
                "RISK SCORE",
                f"{alert.risk_score:.3f}",
                _palette().sev_critical if alert.risk_score > 0.7
                else _palette().sev_medium
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
                        _palette().accent
                    ))

                if alert.destination_ip:
                    network_section.addWidget(DetailField(
                        "DESTINATION IP",
                        alert.destination_ip,
                        _palette().accent
                    ))
                
                self.details_layout.addLayout(network_section)
            
            # Metadata
            meta_section = QHBoxLayout()
            meta_section.setSpacing(10)
            
            meta_section.addWidget(DetailField(
                "ALERT ID",
                alert.alert_id[:16] + "...",
                _palette().text_muted
            ))

            meta_section.addWidget(DetailField(
                "BATCH ID",
                batch_id[:16] + "...",
                _palette().text_muted
            ))
            
            self.details_layout.addLayout(meta_section)
            
            # Reasoning section
            self._add_section("🧠 Analysis Reasoning", alert.reasoning)
            
            # Suggested action
            self._add_section(
                "✅ Suggested Action", alert.suggested_action, _palette().success
            )

            # Analyst feedback
            self._add_feedback_section(alert)

            self.details_layout.addStretch()
        
        except Exception as e:
            self._show_error(str(e))
    
    def _get_confidence_color(self, confidence: float) -> str:
        """Get color based on confidence level"""
        p = _palette()
        if confidence >= 0.8:
            return p.success
        elif confidence >= 0.6:
            return p.sev_medium
        return p.sev_high

    def _add_section(self, title: str, content: str, accent_color: str | None = None):
        accent_color = accent_color or _palette().accent
        """Add content section"""
        # Section header
        header = QLabel(title)
        header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {accent_color}; padding: 10px 0 5px 0;")
        self.details_layout.addWidget(header)
        
        # Content box
        content_frame = QFrame()
        content_frame.setObjectName("sectionContent")
        content_frame.setStyleSheet(f"""
            QFrame#sectionContent {{
                background-color: {_palette().surface};
                border-left: 3px solid {accent_color};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(12, 12, 12, 12)
        
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet(
            f"color: {_palette().text}; font-size: 12px; line-height: 1.5;"
        )
        content_layout.addWidget(content_label)
        
        content_frame.setLayout(content_layout)
        self.details_layout.addWidget(content_frame)
    
    # ------------------------------------------------------------------
    # Analyst feedback (Phase-2 wiring)
    # ------------------------------------------------------------------

    _FEEDBACK_CLASSES = [
        "Benign", "DDoS", "BruteForce", "Malware", "Exfiltration",
        "Suspicious", "PrivilegeEscalation",
    ]

    def _feedback_enabled(self) -> bool:
        """Whether the controller reports a feedback store."""
        try:
            stats = self.bridge.get_stats() or {}
            phase2 = stats.get("phase2") or {}
            return bool(phase2.get("feedback_enabled", False))
        except Exception:
            return False

    def _add_feedback_section(self, alert):
        """Add the analyst feedback controls for the shown alert."""
        header = QLabel("🗳 Analyst Feedback")
        header.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        header.setStyleSheet(
            f"color: {_palette().accent}; padding: 10px 0 5px 0;"
        )
        self.details_layout.addWidget(header)

        frame = QFrame()
        frame.setObjectName("feedbackSection")
        frame.setStyleSheet(f"""
            QFrame#feedbackSection {{
                background-color: {_palette().surface};
                border-left: 3px solid {_palette().accent};
                border-radius: 4px;
                padding: 12px;
            }}
        """)
        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(8)

        self._feedback_history_label = QLabel("")
        self._feedback_history_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        frame_layout.addWidget(self._feedback_history_label)

        buttons_row = QHBoxLayout()
        self._accept_button = QPushButton("Accept (true positive)")
        self._reject_button = QPushButton("Reject (false positive)")
        self._accept_button.clicked.connect(
            lambda _c=False: self._submit_feedback(alert.alert_id, "accept")
        )
        self._reject_button.clicked.connect(
            lambda _c=False: self._submit_feedback(alert.alert_id, "reject")
        )
        buttons_row.addWidget(self._accept_button)
        buttons_row.addWidget(self._reject_button)
        frame_layout.addLayout(buttons_row)

        reclassify_row = QHBoxLayout()
        self._reclassify_combo = QComboBox()
        self._reclassify_combo.addItems(self._FEEDBACK_CLASSES)
        self._reclassify_button = QPushButton("Reclassify")
        self._reclassify_button.clicked.connect(
            lambda _c=False: self._submit_feedback(
                alert.alert_id,
                "reclassify",
                label=self._reclassify_combo.currentText(),
            )
        )
        reclassify_row.addWidget(self._reclassify_combo)
        reclassify_row.addWidget(self._reclassify_button)
        frame_layout.addLayout(reclassify_row)

        self._comment_edit = QLineEdit()
        self._comment_edit.setPlaceholderText("Optional comment…")
        frame_layout.addWidget(self._comment_edit)

        self._feedback_status_label = QLabel("")
        self._feedback_status_label.setStyleSheet(
            f"color: {_palette().success}; font-size: 12px;"
        )
        frame_layout.addWidget(self._feedback_status_label)

        enabled = self._feedback_enabled()
        for widget in (
            self._accept_button,
            self._reject_button,
            self._reclassify_combo,
            self._reclassify_button,
            self._comment_edit,
        ):
            widget.setEnabled(enabled)
            if not enabled:
                widget.setToolTip("Feedback store not available")

        frame.setLayout(frame_layout)
        self.details_layout.addWidget(frame)

        self._update_feedback_history(alert.alert_id)

    def _update_feedback_history(self, alert_id: str):
        """Refresh the 'previous feedback' line for an alert."""
        try:
            entries = self.bridge.get_feedback_for_alert(alert_id) or []
        except Exception:
            entries = []
        if entries:
            latest = entries[0]
            self._feedback_history_label.setText(
                f"Previous feedback: {latest.get('analyst_action', '?')} "
                f"({latest.get('timestamp', '')})"
            )
        else:
            self._feedback_history_label.setText("No feedback yet")

    def _submit_feedback(self, alert_id: str, action: str, label=None):
        """Send feedback to the controller via the bridge."""
        comment = self._comment_edit.text().strip() or None
        try:
            self.bridge.submit_feedback(alert_id, action, label=label, comment=comment)
            self._feedback_status_label.setStyleSheet(
                f"color: {_palette().success}; font-size: 12px;"
            )
            self._feedback_status_label.setText(f"Feedback recorded: {action}")
            self._update_feedback_history(alert_id)
        except Exception as e:
            self._feedback_status_label.setStyleSheet(
                f"color: {_palette().sev_critical}; font-size: 12px;"
            )
            self._feedback_status_label.setText(f"Error: {e}")

    def _show_error(self, error: str):
        """Show error state"""
        self._clear_details()
        error_label = QLabel(f"❌ Error loading alert details:\n{error}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet(
            f"color: {_palette().sev_critical}; padding: 40px;"
        )
        self.details_layout.addWidget(error_label)
