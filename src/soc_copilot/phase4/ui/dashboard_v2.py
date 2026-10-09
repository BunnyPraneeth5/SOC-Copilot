"""SOC Dashboard page

- Page header with the primary actions (Upload logs, Refresh)
- Threat level banner
- Metric cards (total / critical / high / medium / low)
- Recent alerts table

System status lives only in the header chips (MainWindow), so it is not
repeated here.
"""

from datetime import datetime

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .components import PageHeader, severity_delegate, style_table, text_button
from .icons import ICONS, icon_label, set_icon
from .motion import count_to
from .theme import PAGE_MARGIN, PAGE_SPACING, ThemeManager, set_role


def _palette():
    return ThemeManager.instance().palette


class FileProcessingWorker(QThread):
    """Worker thread for processing uploaded log files without blocking the UI."""

    progress = pyqtSignal(int, int)       # (current_file_index, total_files)
    file_done = pyqtSignal(str, bool)     # (filepath, success)
    all_done = pyqtSignal(int, int)       # (success_count, total_count)
    error = pyqtSignal(str)               # error message

    def __init__(self, bridge, file_paths):
        super().__init__()
        self.bridge = bridge
        self.file_paths = file_paths
        self._cancelled = False

    def cancel(self):
        """Request cancellation of processing."""
        self._cancelled = True

    def run(self):
        """Process files in the background thread."""
        success_count = 0
        total = len(self.file_paths)

        for i, file_path in enumerate(self.file_paths):
            if self._cancelled:
                break
            try:
                self.bridge.add_file_source(file_path)
                success_count += 1
                self.file_done.emit(file_path, True)
            except Exception as e:
                self.file_done.emit(file_path, False)
                self.error.emit(f"Failed to process {file_path}: {str(e)}")

            self.progress.emit(i + 1, total)

        self.all_done.emit(success_count, total)


class ThreatBanner(QFrame):
    """Threat level: tinted card with an accent edge, icon and summary."""

    # level -> (palette token, icon, title)
    LEVELS = {
        "loading": ("text_muted", "clock", "Loading"),
        "critical": ("sev_critical", "alert-octagon", "Critical threat level"),
        "high": ("sev_high", "alert-triangle", "High threat level"),
        "elevated": ("sev_medium", "alert-circle", "Elevated threat level"),
        "normal": ("success", "check-circle", "Normal"),
    }

    def __init__(self):
        super().__init__()
        self.setFixedHeight(72)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(14)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(26, 26)
        layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self.level_label = QLabel("Normal")
        set_role(self.level_label, "sectionTitle")
        self.detail_label = QLabel("No critical threats detected")
        set_role(self.detail_label, "pageSubtitle")
        text_layout.addWidget(self.level_label)
        text_layout.addWidget(self.detail_label)
        layout.addLayout(text_layout)
        layout.addStretch()

        self.setLayout(layout)
        self._level_args = ("normal", 0, 0)
        self.set_level("normal", 0, 0)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        self.set_level(*self._level_args)

    def set_level(self, level: str, critical: int, high: int):
        """Update threat level"""
        self._level_args = (level, critical, high)
        p = _palette()
        token, icon, title = self.LEVELS.get(level, self.LEVELS["normal"])
        accent = getattr(p, token)

        self.setStyleSheet(f"""
            ThreatBanner {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
        """)
        set_icon(self.icon_label, icon, token, 26)
        self.level_label.setText(title)
        self.level_label.setStyleSheet(f"color: {accent};")

        if level == "loading":
            self.detail_label.setText("Loading threat analysis...")
        elif critical > 0:
            self.detail_label.setText(
                f"{critical} critical alert"
                + (" needs" if critical == 1 else "s need")
                + " immediate attention"
            )
        elif high > 0:
            self.detail_label.setText(
                f"{high} high-priority alert{'s' if high != 1 else ''} detected"
            )
        else:
            self.detail_label.setText("Routine activity only")


class MetricCard(QFrame):
    """Clickable metric: icon + label, large neutral value, coloured edge."""

    clicked = pyqtSignal(str)

    def __init__(self, title: str, icon: str, color: str):
        super().__init__()
        self.title = title
        self.color = color  # palette token or colour value
        self.icon_name = icon if icon in ICONS else "activity"
        self.setFixedHeight(92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui(title)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _resolved_color(self) -> str:
        return getattr(_palette(), self.color, self.color)

    def _apply_theme(self):
        p = _palette()
        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-top: 3px solid {self._resolved_color()};
                border-radius: 8px;
            }}
            MetricCard:hover {{
                border-color: {p.border};
                border-top: 3px solid {self._resolved_color()};
            }}
        """)

    def _init_ui(self, title: str):
        self._apply_theme()

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(icon_label(self.icon_name, self.color, 16))
        title_lbl = QLabel(title)
        set_role(title_lbl, "pageSubtitle")
        header.addWidget(title_lbl)
        header.addStretch()

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 26px; font-weight: 600;")

        layout.addLayout(header)
        layout.addWidget(self.value_label)
        layout.addStretch()
        self.setLayout(layout)

    def set_value(self, value: int):
        count_to(self.value_label, int(value))

    def mousePressEvent(self, event):
        self.clicked.emit(self.title)


class MetricCardsRow(QFrame):
    """Metric cards"""

    card_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.total_card = MetricCard("Total Alerts", "bell", "accent")
        self.critical_card = MetricCard("Critical", "alert-octagon", "sev_critical")
        self.high_card = MetricCard("High", "alert-triangle", "sev_high")
        self.medium_card = MetricCard("Medium", "alert-circle", "sev_medium")
        self.low_card = MetricCard("Low", "info", "sev_low")

        for card in [self.total_card, self.critical_card, self.high_card,
                     self.medium_card, self.low_card]:
            card.clicked.connect(self.card_clicked.emit)
            layout.addWidget(card)

        self.setLayout(layout)

    def update_metrics(self, total: int, critical: int, high: int, medium: int, low: int):
        self.total_card.set_value(total)
        self.critical_card.set_value(critical)
        self.high_card.set_value(high)
        self.medium_card.set_value(medium)
        self.low_card.set_value(low)


class QuickActionsBar(QWidget):
    """Primary actions, shown in the page header."""

    upload_clicked = pyqtSignal()
    refresh_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.refresh_btn = text_button("Refresh", "refresh")
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)
        self.upload_btn = text_button("Upload logs", "upload", "primary", "text_inverse")
        self.upload_btn.clicked.connect(self.upload_clicked.emit)

        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.upload_btn)


class RecentAlertsTimeline(QFrame):
    """Recent alerts (latest 10)"""

    alert_clicked = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()
        self._last_alerts = []
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        p = _palette()
        self.empty_label.setStyleSheet(f"color: {p.text_muted}; padding: 40px;")
        self.update_alerts(self._last_alerts)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Recent alerts")
        set_role(title, "sectionTitle")
        header.addWidget(title)
        header.addStretch()
        self.count_label = QLabel("0 alerts")
        set_role(self.count_label, "pageSubtitle")
        header.addWidget(self.count_label)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Priority", "Classification", "Source", "Confidence"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_table(self.table)
        self.table.setItemDelegateForColumn(1, severity_delegate(self.table))
        hdr = self.table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 100), (1, 130), (3, 150), (4, 110)):
            self.table.setColumnWidth(col, width)
        self.table.itemClicked.connect(self._on_row_clicked)
        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.table)

        self.empty_label = QLabel("No alerts yet. Upload logs to begin analysis.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {_palette().text_muted}; padding: 40px;")
        self.empty_label.hide()
        layout.addWidget(self.empty_label)

        self.setLayout(layout)

    def update_alerts(self, alerts_data: list):
        """Update with latest 10 alerts"""
        self._last_alerts = alerts_data
        if not alerts_data:
            self.table.hide()
            self.empty_label.show()
            self.count_label.setText("0 alerts")
            return

        self.table.show()
        self.empty_label.hide()

        recent = alerts_data[:10]
        self.count_label.setText(
            f"Showing {len(recent)} of {len(alerts_data)}"
        )

        p = _palette()
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(recent))
        for row, alert in enumerate(recent):
            items = [
                QTableWidgetItem(alert["time"]),
                QTableWidgetItem(alert["priority"]),
                QTableWidgetItem(alert["classification"]),
                QTableWidgetItem(alert["source_ip"] or "N/A"),
                QTableWidgetItem(alert["confidence"]),
            ]
            for col, item in enumerate(items):
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, alert["batch_id"])
                if col in (0, 4):
                    item.setForeground(QColor(p.text_muted))
                self.table.setItem(row, col, item)
        self.table.setUpdatesEnabled(True)

    def _on_row_clicked(self, item):
        row = item.row()
        batch_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        classification = self.table.item(row, 2).text()
        self.alert_clicked.emit(batch_id, classification)


class Dashboard(QWidget):
    """Dashboard page"""

    navigate_to_alerts = pyqtSignal()
    navigate_to_alerts_filtered = pyqtSignal(str)
    navigate_to_settings = pyqtSignal()
    alert_selected = pyqtSignal(str, str)

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._alerts_cache = []
        self._worker = None  # Background file processing thread
        self._dirty = False
        self._init_ui()

        # Event-driven refresh (debounced in the bridge)
        self.bridge.resultsUpdated.connect(self._on_results_updated)

        self.refresh()

    def _on_results_updated(self):
        """Refresh on new results, deferring work while hidden."""
        if self.isVisible():
            self.refresh()
            self._dirty = False
        else:
            self._dirty = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.refresh()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN, PAGE_MARGIN)
        layout.setSpacing(PAGE_SPACING)

        self.header = PageHeader("Dashboard", "grid", "")
        self.actions_bar = QuickActionsBar()
        self.actions_bar.upload_clicked.connect(self._upload_logs)
        self.actions_bar.refresh_clicked.connect(self.refresh)
        self.header.add_action(self.actions_bar)
        layout.addWidget(self.header)

        # Progress bar for file uploads (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self._style_progress_bar()
        layout.addWidget(self.progress_bar)

        self.threat_banner = ThreatBanner()
        layout.addWidget(self.threat_banner)

        self.metrics_row = MetricCardsRow()
        self.metrics_row.card_clicked.connect(self._on_metric_clicked)
        layout.addWidget(self.metrics_row)

        self.alerts_timeline = RecentAlertsTimeline()
        self.alerts_timeline.alert_clicked.connect(self.alert_selected.emit)
        layout.addWidget(self.alerts_timeline, 1)

        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._style_progress_bar)

    def _style_progress_bar(self):
        p = _palette()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background-color: {p.surface_alt};
            }}
            QProgressBar::chunk {{
                background-color: {p.accent};
                border-radius: 2px;
            }}
        """)

    def _set_updated(self, text: str | None = None):
        self.header.set_subtitle(
            text or f"Updated {datetime.now().strftime('%H:%M:%S')}"
        )

    def refresh(self):
        """Unified refresh - single data fetch"""
        self.threat_banner.set_level("loading", 0, 0)

        try:
            results = self.bridge.get_latest_alerts(limit=100)

            total = critical = high = medium = low = 0
            alerts_data = []

            for result in results:
                for alert in result.alerts:
                    total += 1
                    p = alert.priority.lower()
                    if "critical" in p:
                        critical += 1
                    elif "high" in p:
                        high += 1
                    elif "medium" in p:
                        medium += 1
                    elif "low" in p:
                        low += 1

                    alerts_data.append({
                        "batch_id": result.batch_id,
                        "time": alert.timestamp.strftime("%H:%M:%S") if hasattr(alert.timestamp, 'strftime') else str(alert.timestamp),
                        "priority": alert.priority,
                        "classification": alert.classification,
                        "source_ip": getattr(alert, 'source_ip', 'N/A'),
                        "confidence": f"{alert.confidence:.2f}" if hasattr(alert, 'confidence') else "N/A"
                    })

            self._alerts_cache = alerts_data

            if critical > 0:
                self.threat_banner.set_level("critical", critical, high)
            elif high > 0:
                self.threat_banner.set_level("high", critical, high)
            elif medium > 0:
                self.threat_banner.set_level("elevated", critical, high)
            else:
                self.threat_banner.set_level("normal", critical, high)

            self.metrics_row.update_metrics(total, critical, high, medium, low)
            self.alerts_timeline.update_alerts(alerts_data)
            self._set_updated()

        except Exception:
            self.threat_banner.set_level("normal", 0, 0)

    def _on_metric_clicked(self, card_title: str):
        """Handle metric card click"""
        priority_map = {
            "Critical": "critical",
            "High": "high",
            "Medium": "medium",
            "Low": "low",
            "Total Alerts": "all"
        }
        priority = priority_map.get(card_title, "all")

        if priority == "all":
            self.navigate_to_alerts.emit()
        else:
            self.navigate_to_alerts_filtered.emit(priority)

    def _upload_logs(self):
        """Upload and analyze log files asynchronously via worker thread."""
        if self._worker is not None and self._worker.isRunning():
            return

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Log Files", "",
            "Log Files (*.json *.jsonl *.csv *.log);;All (*.*)"
        )

        if not files:
            return

        self.actions_bar.upload_btn.setEnabled(False)
        self.actions_bar.upload_btn.setText(" Processing...")
        self.actions_bar.refresh_btn.setEnabled(False)

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(files))
        self.progress_bar.setValue(0)

        self._worker = FileProcessingWorker(self.bridge, files)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.all_done.connect(self._on_worker_done)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_progress(self, current, total):
        """Update progress bar from worker thread signal."""
        self.progress_bar.setValue(current)

    def _on_worker_done(self, success_count, total_count):
        """Handle worker completion — refresh dashboard with new results."""
        self.bridge.start_ingestion()
        self.bridge.request_refresh()
        self.refresh()
        self._set_updated(
            f"Processed {success_count}/{total_count} files at "
            f"{datetime.now().strftime('%H:%M:%S')}"
        )

    def _on_worker_finished(self):
        """Clean up worker reference, re-enable UI, and hide progress bar."""
        self.actions_bar.upload_btn.setEnabled(True)
        self.actions_bar.upload_btn.setText(" Upload logs")
        self.actions_bar.refresh_btn.setEnabled(True)
        QTimer.singleShot(1000, self._hide_progress)
        self._worker = None

    def _hide_progress(self):
        """Hide the progress bar after a short delay."""
        self.progress_bar.setVisible(False)
