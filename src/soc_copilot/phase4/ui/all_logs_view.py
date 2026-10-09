"""All Logs view with table displaying benign and alert logs"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QLabel, QPushButton, QComboBox, QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

from .theme import ThemeManager
from .motion import show_toast


def _palette():
    return ThemeManager.instance().palette


class AllLogsView(QWidget):
    """Scalable logs table for displaying all processed events"""
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._log_cache = {}  # log_id -> log data
        self._current_filter = "All"
        self._search_text = ""
        self._dirty = False
        self._init_ui()

        # Event-driven refresh (debounced in the bridge)
        self.bridge.resultsUpdated.connect(self._on_results_updated)

        self.refresh()

    def _on_results_updated(self):
        """Refresh on new results, deferring work while hidden."""
        if self.isVisible():
            self._incremental_refresh()
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
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header
        header = self._create_header()
        layout.addLayout(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Time", "Classification", "Source IP", "Raw Log", "Status"
        ])
        
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(32)
        
        self.table.setUpdatesEnabled(True)
        
        layout.addWidget(self.table)
        
        # Empty state label
        self.empty_label = QLabel("No logs to display yet.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-style: italic; padding: 20px;"
        )
        self.empty_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.empty_label)

        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        """Re-apply palette-derived styles after a theme switch."""
        p = _palette()
        self.empty_label.setStyleSheet(
            f"color: {p.text_muted}; font-style: italic; padding: 20px;"
        )
        if getattr(self, "counter_label", None) is not None:
            self.counter_label.setStyleSheet(
                f"color: {p.text_muted}; font-size: 11px;"
            )
            self._filter_label.setStyleSheet(
                f"color: {p.text_muted}; font-size: 12px;"
            )
            self.class_filter.setStyleSheet(self._combo_style(p))
            self.search_box.setStyleSheet(self._search_style(p))
            self._refresh_btn.setStyleSheet(self._refresh_style(p))
        self.refresh()

    @staticmethod
    def _combo_style(p) -> str:
        return f"""
            QComboBox {{
                background-color: {p.surface_alt};
                color: {p.text};
                border: 1px solid {p.scrollbar};
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 100px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {p.surface_alt};
                color: {p.text};
                selection-background-color: {p.accent};
                selection-color: {p.text_inverse};
            }}
        """

    @staticmethod
    def _search_style(p) -> str:
        return f"""
            QLineEdit {{
                background-color: {p.surface_alt};
                color: {p.text};
                border: 1px solid {p.scrollbar};
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 200px;
            }}
        """

    @staticmethod
    def _refresh_style(p) -> str:
        return f"""
            QPushButton {{
                background-color: {p.surface_alt};
                color: {p.text};
                border: 1px solid {p.scrollbar};
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {p.scrollbar}; }}
        """

    def _create_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title = QLabel("📋 All Logs")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        self.counter_label = QLabel("Loading...")
        self.counter_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 11px;"
        )
        
        title_layout.addWidget(title)
        title_layout.addWidget(self.counter_label)
        header.addLayout(title_layout)
        
        header.addStretch()
        
        # Classification filter
        self._filter_label = QLabel("Filter:")
        self._filter_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        header.addWidget(self._filter_label)

        self.class_filter = QComboBox()
        self.class_filter.addItems(["All", "Alerts Only", "Benign Only"])
        p = _palette()
        self.class_filter.setStyleSheet(self._combo_style(p))
        self.class_filter.currentTextChanged.connect(self._on_filter_changed)
        header.addWidget(self.class_filter)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search raw logs...")
        self.search_box.setStyleSheet(self._search_style(p))
        self.search_box.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_box)

        refresh_btn = QPushButton("🔄")
        self._refresh_btn = refresh_btn
        refresh_btn.setToolTip("Refresh logs")
        refresh_btn.setStyleSheet(self._refresh_style(p))
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        self.clear_btn = QPushButton("Clear logs")
        self.clear_btn.setProperty("variant", "dangerOutline")
        self.clear_btn.setToolTip("Permanently delete all analysed logs and their alerts")
        self.clear_btn.clicked.connect(self._on_clear_logs)
        header.addWidget(self.clear_btn)

        return header

    # ----- clear logs ----------------------------------------------------

    def _stored_counts(self) -> tuple:
        """(logs, alerts) across every stored result, not just this page."""
        try:
            results = self.bridge.get_all_results()
        except Exception:
            results = None
        if not isinstance(results, list):
            return len(self._log_cache), 0
        logs = sum(len(getattr(r, "logs", []) or []) for r in results)
        alerts = sum(len(getattr(r, "alerts", []) or []) for r in results)
        return logs, alerts

    def _confirm_clear(self, logs: int, alerts: int) -> bool:
        """Ask before deleting; Cancel is the default button."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Clear all logs?")
        log_word = "log entry" if logs == 1 else "log entries"
        alert_part = (
            f" and the {alerts} alert{'s' if alerts != 1 else ''} found in them"
            if alerts else ""
        )
        box.setText(
            f"<b>This permanently deletes {logs} {log_word}{alert_part}.</b>"
        )
        box.setInformativeText(
            "Cleared logs and alerts will not be shown again, including "
            "their triage status. This cannot be undone.\n\n"
            "Analyst feedback and the audit trail are kept."
        )
        clear = box.addButton("Clear logs", QMessageBox.ButtonRole.DestructiveRole)
        clear.setProperty("variant", "danger")
        cancel = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is clear

    def _on_clear_logs(self):
        logs, alerts = self._stored_counts()
        if logs == 0 and alerts == 0:
            show_toast(self, "There are no logs to clear", "info")
            return
        if not self._confirm_clear(logs, alerts):
            return
        try:
            removed = self.bridge.clear_logs(confirmed=True)
        except Exception as exc:
            QMessageBox.critical(self, "Clear failed", f"Could not clear logs:\n{exc}")
            return
        removed = removed if isinstance(removed, dict) else {"logs": logs, "alerts": alerts}
        self.refresh()
        message = f"Cleared {removed.get('logs', 0)} logs and {removed.get('alerts', 0)} alerts"
        show_toast(self, message, "success")
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message, 5000)

    def refresh(self):
        try:
            # We access the raw results to get all logs instead of alerts
            # get_latest_alerts() bypasses the alert-only filter
            results = self.bridge.get_latest_alerts(limit=50) # Get latest 50 batches
            
            self._log_cache.clear()
            logs_data = []
            
            for result in results:
                # Assuming the controller sets `logs` list
                if hasattr(result, 'logs'):
                    for lg in result.logs:
                        log_dict = {
                            "key": lg.log_id,
                            "time": lg.timestamp.strftime("%H:%M:%S") if hasattr(lg.timestamp, 'strftime') else str(lg.timestamp),
                            "classification": lg.classification,
                            "source_ip": lg.source_ip or "N/A",
                            "raw_log": lg.raw_log[:200] + ("..." if len(lg.raw_log) > 200 else ""),
                            "is_alert": lg.is_alert,
                            "status": "Alert" if lg.is_alert else "Benign"
                        }
                        self._log_cache[lg.log_id] = log_dict
                        logs_data.append(log_dict)
            
            self._update_counter(logs_data)
            self.clear_btn.setEnabled(bool(logs_data))
            
            if not logs_data:
                self.table.setRowCount(0)
                self.empty_label.show()
                self.table.hide()
                return
            
            self.empty_label.hide()
            self.table.show()
            
            filtered = self._apply_filters(logs_data)
            self._update_table(filtered)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
    def _incremental_refresh(self):
        try:
            results = self.bridge.get_latest_alerts(limit=10)
            if not results and self._log_cache:
                self.refresh()  # store was cleared
                return

            new_logs = []
            for result in results:
                if hasattr(result, 'logs'):
                    for lg in result.logs:
                        if lg.log_id not in self._log_cache:
                            log_dict = {
                                "key": lg.log_id,
                                "time": lg.timestamp.strftime("%H:%M:%S") if hasattr(lg.timestamp, 'strftime') else str(lg.timestamp),
                                "classification": lg.classification,
                                "source_ip": lg.source_ip or "N/A",
                                "raw_log": lg.raw_log[:200] + ("..." if len(lg.raw_log) > 200 else ""),
                                "is_alert": lg.is_alert,
                                "status": "Alert" if lg.is_alert else "Benign"
                            }
                            self._log_cache[lg.log_id] = log_dict
                            new_logs.append(log_dict)
            
            if new_logs:
                all_logs = list(self._log_cache.values())
                self._update_counter(all_logs)
                filtered = self._apply_filters(all_logs)
                self._update_table(filtered, True)
                
        except Exception as e:
            import traceback
            traceback.print_exc()

    def _apply_filters(self, logs_data: list) -> list:
        filtered = logs_data
        
        if self._current_filter == "Alerts Only":
            filtered = [l for l in filtered if l["is_alert"]]
        elif self._current_filter == "Benign Only":
            filtered = [l for l in filtered if not l["is_alert"]]
            
        if self._search_text:
            text = self._search_text.lower()
            filtered = [l for l in filtered if text in l["raw_log"].lower() or text in l["classification"].lower()]
            
        return filtered

    def _update_counter(self, logs_data: list):
        total = len(logs_data)
        alerts = sum(1 for l in logs_data if l["is_alert"])
        self.counter_label.setText(f"Total: {total} │ Alerts: {alerts}")

    def _on_filter_changed(self, text: str):
        self._current_filter = text
        self._update_table(self._apply_filters(list(self._log_cache.values())))

    def _on_search_changed(self, text: str):
        self._search_text = text
        self._update_table(self._apply_filters(list(self._log_cache.values())))

    def set_search_text(self, text: str):
        """Set the search box programmatically (UX-7 'Show logs for IP')."""
        self.search_box.setText(text)

    def _update_table(self, logs_data: list, preserve_scroll: bool = False):
        scroll_pos = self.table.verticalScrollBar().value() if preserve_scroll else 0
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(logs_data))
        
        for row, lg in enumerate(logs_data):
            items = [
                QTableWidgetItem(lg["time"]),
                QTableWidgetItem(lg["classification"]),
                QTableWidgetItem(lg["source_ip"]),
                QTableWidgetItem(lg["raw_log"]),
                QTableWidgetItem(lg["status"])
            ]
            
            for col, item in enumerate(items):
                # Apply tooltips
                item.setToolTip(item.text())
                self.table.setItem(row, col, item)
            
            # Color coding
            color = (QColor(_palette().sev_critical) if lg["is_alert"]
                     else QColor(_palette().text))
            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    item.setForeground(color)
                    
        self.table.setUpdatesEnabled(True)
        if preserve_scroll:
            self.table.verticalScrollBar().setValue(scroll_pos)
