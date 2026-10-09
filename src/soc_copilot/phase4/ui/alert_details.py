"""Optimized alert details panel with breadcrumb navigation"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QScrollArea, QPushButton, QFrame, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from .theme import ThemeManager, severity_color, set_role, PAGE_MARGIN, PAGE_SPACING
from .components import PageHeader, text_button, style_pill, status_color
from .icons import icon_label, set_icon
from ..controller.result_store import TRIAGE_STATUSES

# Triage status → palette token (UX-5)
STATUS_TOKENS = {
    "New": "info",
    "In progress": "warning",
    "Resolved": "success",
    "False positive": "text_muted",
}


def _palette():
    return ThemeManager.instance().palette


class DetailField(QFrame):
    """Card with an uppercase caption and a value."""

    def __init__(self, label: str, value: str, color: str | None = None):
        super().__init__()
        p = _palette()
        color = color or p.text
        self.setStyleSheet(f"""
            DetailField {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(4)

        lbl = QLabel(label)
        set_role(lbl, "caption")

        val = QLabel(value)
        val.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 600;")
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout.addWidget(lbl)
        layout.addWidget(val)
        self.setLayout(layout)


class AlertDetailsPanel(QWidget):
    """Enhanced alert details with navigation"""

    back_clicked = pyqtSignal()
    investigate_requested = pyqtSignal(str)      # target IP
    filter_alerts_requested = pyqtSignal(str)    # IP
    show_logs_requested = pyqtSignal(str)        # IP

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        self.header = PageHeader("Investigation", "search", "No alert selected")
        self.title_label = self.header.title_label
        back_btn = text_button("Back to alerts", "arrow-left")
        self._back_btn = back_btn
        back_btn.setToolTip("Back to Alerts (Esc)")
        back_btn.clicked.connect(self.back_clicked.emit)
        self.header.add_action(back_btn)
        layout.addWidget(self.header)

        # Scroll area for details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

        self.details_widget = QWidget()
        self.details_layout = QVBoxLayout()
        self.details_layout.setContentsMargins(0, 0, 8, 0)
        self.details_layout.setSpacing(12)
        self.details_widget.setLayout(self.details_layout)

        scroll.setWidget(self.details_widget)
        layout.addWidget(scroll)

        self.setLayout(layout)
        self._last_show_args = None
        self._show_placeholder()

    def _apply_theme(self):
        """Re-render the current alert with the new palette."""
        if self._last_show_args is not None:
            self.show_alert(*self._last_show_args)
        else:
            self._show_placeholder()

    def _show_placeholder(self):
        """Empty state: icon + hint."""
        self._clear_details()
        self.header.set_subtitle("No alert selected")
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 60, 0, 0)
        v.setSpacing(10)
        v.addWidget(icon_label("search", "text_muted", 36), 0, Qt.AlignmentFlag.AlignHCenter)
        title = QLabel("No alert selected")
        set_role(title, "sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Select an alert on the Alerts page to see its analysis.")
        set_role(hint, "pageSubtitle")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        v.addWidget(hint)
        self.details_layout.addWidget(box)
        self.details_layout.addStretch()

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
            alerts = getattr(result, "alerts", None)
            if not isinstance(alerts, (list, tuple)) or not alerts:
                return

            # Find matching alert
            alert = None
            if alert_id:
                for a in alerts:
                    if getattr(a, "alert_id", None) == alert_id:
                        alert = a
                        break
            if alert is None and alert_classification:
                for a in alerts:
                    if a.classification == alert_classification:
                        alert = a
                        break

            if not alert:
                return

            self._clear_details()

            self.header.set_subtitle(f"Alert {alert.alert_id} \u00b7 batch {batch_id}")

            # Classification + badges
            class_label = QLabel(alert.classification)
            class_label.setStyleSheet("font-size: 22px; font-weight: 600;")
            class_label.setWordWrap(True)
            self.details_layout.addWidget(class_label)

            priority_section = QHBoxLayout()
            priority_section.setSpacing(8)
            priority_badge = QLabel(alert.priority)
            style_pill(priority_badge, severity_color(alert.priority))
            priority_section.addWidget(priority_badge)

            # Triage status badge + selector (UX-5)
            self._current_alert_id = alert.alert_id
            self._status_badge = QLabel()
            self._update_status_badge()
            priority_section.addWidget(self._status_badge)
            priority_section.addSpacing(8)
            status_caption = QLabel("Set status")
            set_role(status_caption, "pageSubtitle")
            priority_section.addWidget(status_caption)
            self._status_combo = QComboBox()
            self._status_combo.addItems(TRIAGE_STATUSES)
            current = self._get_alert_status(alert.alert_id)
            self._status_combo.blockSignals(True)
            self._status_combo.setCurrentText(current)
            self._status_combo.blockSignals(False)
            self._status_combo.currentTextChanged.connect(
                self._on_status_combo_changed
            )
            priority_section.addWidget(self._status_combo)
            priority_section.addStretch()
            self.details_layout.addLayout(priority_section)
            self.details_layout.addSpacing(4)

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
                    network_section.addWidget(
                        self._ip_field("SOURCE IP", alert.source_ip)
                    )

                if alert.destination_ip:
                    network_section.addWidget(
                        self._ip_field(
                            "DESTINATION IP", alert.destination_ip
                        )
                    )

                self.details_layout.addLayout(network_section)

            # Metadata
            meta_section = QHBoxLayout()
            meta_section.setSpacing(10)

            meta_section.addWidget(DetailField(
                "ALERT ID", self._short(alert.alert_id), _palette().text_muted
            ))

            meta_section.addWidget(DetailField(
                "BATCH ID", self._short(batch_id), _palette().text_muted
            ))

            self.details_layout.addLayout(meta_section)

            self._add_section("Analysis reasoning", alert.reasoning, "cpu")
            self._add_section(
                "Suggested action", alert.suggested_action, "check-circle", "success"
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

    @staticmethod
    def _short(value: str, limit: int = 24) -> str:
        value = str(value or "")
        return value if len(value) <= limit else value[:limit] + "\u2026"

    def _section_header(self, title: str, icon: str, token: str = "text_muted"):
        row = QHBoxLayout()
        row.setContentsMargins(0, 12, 0, 2)
        row.setSpacing(8)
        row.addWidget(icon_label(icon, token, 16))
        header = QLabel(title)
        set_role(header, "sectionTitle")
        row.addWidget(header)
        row.addStretch()
        self.details_layout.addLayout(row)

    def _card(self, name: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName(name)
        p = _palette()
        frame.setStyleSheet(f"""
            QFrame#{name} {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 8px;
            }}
        """)
        return frame

    def _add_section(self, title: str, content: str, icon: str = "info",
                     token: str = "text_muted"):
        """Titled content card."""
        self._section_header(title, icon, token)
        content_frame = self._card("sectionContent")
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_label = QLabel(content or "\u2014")
        content_label.setWordWrap(True)
        content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_label.setStyleSheet(f"color: {_palette().text}; font-size: 13px;")
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

    # ------------------------------------------------------------------
    # IP context menu (UX-7)
    # ------------------------------------------------------------------

    def _ip_field(self, label: str, ip: str) -> "DetailField":
        """DetailField for an IP with a right-click action menu."""
        field = DetailField(label, ip, _palette().accent)
        field.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        field.customContextMenuRequested.connect(
            lambda pos, f=field, t=ip:
                self._show_ip_menu(t, f.mapToGlobal(pos))
        )
        field.setToolTip("Right-click for actions")
        return field

    def _show_ip_menu(self, ip: str, global_pos):
        """Per-IP actions shared with the alerts table (UX-7)."""
        from PyQt6.QtWidgets import QMenu, QApplication

        menu = QMenu(self)
        menu.addAction("Investigate").triggered.connect(
            lambda c=False, t=ip: self.investigate_requested.emit(t)
        )
        menu.addAction("Copy IP").triggered.connect(
            lambda c=False, t=ip:
                QApplication.clipboard().setText(t)
        )
        menu.addAction("Filter alerts by this IP").triggered.connect(
            lambda c=False, t=ip: self.filter_alerts_requested.emit(t)
        )
        menu.addAction("Show logs for this IP").triggered.connect(
            lambda c=False, t=ip: self.show_logs_requested.emit(t)
        )
        menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Triage status (UX-5)
    # ------------------------------------------------------------------

    def _get_alert_status(self, alert_id: str) -> str:
        getter = getattr(self.bridge, "get_alert_status", None)
        try:
            status = getter(alert_id) if callable(getter) else "New"
            return status if isinstance(status, str) else "New"
        except Exception:
            return "New"

    def _update_status_badge(self):
        status = self._get_alert_status(
            getattr(self, "_current_alert_id", "") or ""
        )
        self._status_badge.setText(status)
        style_pill(self._status_badge, status_color(status))
        self._status_badge.setToolTip("Triage status")

    def _on_status_combo_changed(self, status: str):
        alert_id = getattr(self, "_current_alert_id", None)
        if not alert_id:
            return
        try:
            self.bridge.set_alert_status(alert_id, status)
            self._update_status_badge()
        except Exception as exc:
            # Revert combo to the persisted status on failure
            self._status_combo.blockSignals(True)
            self._status_combo.setCurrentText(self._get_alert_status(alert_id))
            self._status_combo.blockSignals(False)
            self._status_badge.setToolTip(f"Change failed: {exc}")

    def _feedback_enabled(self) -> bool:
        """Whether the controller reports a feedback store."""
        try:
            stats = self.bridge.get_stats()
            if not isinstance(stats, dict):
                return False
            phase2 = stats.get("phase2")
            return (
                isinstance(phase2, dict)
                and bool(phase2.get("feedback_enabled", False))
            )
        except Exception:
            return False

    def _add_feedback_section(self, alert):
        """Add the analyst feedback controls for the shown alert."""
        self._section_header("Analyst feedback", "message-square")
        frame = self._card("feedbackSection")
        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(16, 14, 16, 14)
        frame_layout.setSpacing(10)

        self._feedback_history_label = QLabel("")
        self._feedback_history_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        frame_layout.addWidget(self._feedback_history_label)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        self._accept_button = QPushButton(" Accept (true positive)")
        set_icon(self._accept_button, "thumbs-up", "success")
        self._reject_button = QPushButton(" Reject (false positive)")
        set_icon(self._reject_button, "thumbs-down", "danger")
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
        self._reclassify_button = QPushButton(" Reclassify")
        set_icon(self._reclassify_button, "edit")
        self._reclassify_button.clicked.connect(
            lambda _c=False: self._submit_feedback(
                alert.alert_id,
                "reclassify",
                label=self._reclassify_combo.currentText(),
            )
        )
        reclassify_row.addWidget(self._reclassify_combo, 1)
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
            entries = self.bridge.get_feedback_for_alert(alert_id)
        except Exception:
            entries = []
        if not isinstance(entries, list):
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
            # Feedback drives triage status (reject ⇒ False positive, etc.)
            if getattr(self, "_status_badge", None) is not None:
                self._update_status_badge()
                if getattr(self, "_status_combo", None) is not None:
                    self._status_combo.blockSignals(True)
                    self._status_combo.setCurrentText(
                        self._get_alert_status(alert_id)
                    )
                    self._status_combo.blockSignals(False)
        except Exception as e:
            self._feedback_status_label.setStyleSheet(
                f"color: {_palette().sev_critical}; font-size: 12px;"
            )
            self._feedback_status_label.setText(f"Error: {e}")

    def _show_error(self, error: str):
        """Show error state"""
        self._clear_details()
        error_label = QLabel(f"Error loading alert details:\n{error}")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet(
            f"color: {_palette().sev_critical}; padding: 40px;"
        )
        self.details_layout.addWidget(error_label)
