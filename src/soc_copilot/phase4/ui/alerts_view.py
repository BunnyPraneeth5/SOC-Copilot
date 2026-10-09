"""Optimized alerts table with incremental updates and scroll preservation"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QComboBox, QLineEdit, QMessageBox,
    QFileDialog,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from datetime import datetime

from .theme import ThemeManager, severity_color, set_role
from .motion import show_toast
from ..controller.result_store import TRIAGE_STATUSES


def _palette():
    return ThemeManager.instance().palette


class AlertsView(QWidget):
    """Scalable alerts table with filtering and incremental updates"""
    
    alert_selected = pyqtSignal(str, str)  # batch_id, alert_id
    show_logs_requested = pyqtSignal(str)  # IP to look up in All Logs
    
    # Column configuration constants
    TIME_COLUMN = 0
    PRIORITY_COLUMN = 1
    STATUS_COLUMN = 2
    CLASSIFICATION_COLUMN = 3
    SOURCE_IP_COLUMN = 4
    CONFIDENCE_COLUMN = 5
    BATCH_ID_COLUMN = 6
    ACTION_COLUMN = 7
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._alert_cache = {}  # alert key -> alert data
        self._current_filter = "All"
        self._current_status_filter = "All"
        self._search_text = ""
        self._page = 0
        self._page_size = 100
        self._filtered_cache = []
        self._dirty = False
        self.report_drawer = None  # optional; attached by MainWindow
        self._init_ui()
        self.bridge.reportReady.connect(self._on_report_ready)

        # Event-driven refresh: resultsUpdated fires when the results
        # store changes (debounced in the bridge).
        self.bridge.resultsUpdated.connect(self._on_results_updated)

        # Initial refresh
        self.refresh()

    def _on_results_updated(self):
        """Refresh on new results, deferring work while hidden."""
        if self.isVisible():
            self._incremental_refresh()
            self._dirty = False
        else:
            self._dirty = True

    def _triage_map(self) -> dict:
        """alert_id -> triage status (empty when bridge lacks it)."""
        getter = getattr(self.bridge, "get_triage_map", None)
        try:
            m = getter() if callable(getter) else {}
            return m if isinstance(m, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _alert_key(result, index: int, alert) -> str:
        """Unique cache key: the alert_id, else batch + position.

        Keying on batch + classification made two same-type alerts in
        one batch collide, so only one of them was ever shown.
        """
        alert_id = getattr(alert, "alert_id", None)
        if alert_id:
            return str(alert_id)
        return f"{result.batch_id}#{index}"

    @classmethod
    def _alert_dict(cls, result, alert, triage: dict, index: int = 0) -> dict:
        ts = getattr(alert, "timestamp", None)
        return {
            "key": cls._alert_key(result, index, alert),
            "batch_id": result.batch_id,
            "alert_id": alert.alert_id,
            "time": ts.strftime("%H:%M:%S")
                    if hasattr(ts, 'strftime') else str(ts),
            "timestamp": ts,  # raw value for sorting/export
            "priority": alert.priority,
            "status": triage.get(alert.alert_id, "New"),
            "classification": alert.classification,
            "source_ip": getattr(alert, 'source_ip', None) or "N/A",
            "destination_ip": getattr(alert, 'destination_ip', None) or "N/A",
            "confidence": f"{alert.confidence:.2f}"
                          if hasattr(alert, 'confidence') else "N/A",
            "risk_score": getattr(alert, "risk_score", None),
            "anomaly_score": getattr(alert, "anomaly_score", None),
            "reasoning": getattr(alert, "reasoning", "") or "",
            "suggested_action": getattr(alert, "suggested_action", "") or "",
        }

    def _results(self):
        """All stored results (falls back to latest-200 for mocks).

        Errors propagate so ``refresh`` shows the error state.
        """
        getter = getattr(self.bridge, "get_all_results", None)
        results = getter() if callable(getter) else None
        if isinstance(results, list):
            return results
        results = self.bridge.get_latest_alerts(limit=200)
        return results if isinstance(results, list) else []

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._dirty = False
            self.refresh()
    
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)
        
        # Header with counters and filters
        header = self._create_header()
        layout.addLayout(header)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Time", "Priority", "Status", "Classification", "Source IP",
            "Confidence", "Batch ID", "Action"
        ])
        self.table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.table.customContextMenuRequested.connect(
            self._on_table_context_menu
        )
        
        # Optimize table for performance
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)  # Disable during updates
        # Classification absorbs spare width; the Action column stays
        # button-sized instead of stretching across wide windows.
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            self.CLASSIFICATION_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            self.ACTION_COLUMN, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(self.ACTION_COLUMN, 130)
        self.table.verticalHeader().setDefaultSectionSize(32)  # Compact rows
        self.table.itemClicked.connect(self._on_row_clicked)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.installEventFilter(self)  # UX-7 vim-style keys
        
        # Performance: disable updates during batch operations
        self.table.setUpdatesEnabled(True)
        
        layout.addWidget(self.table)

        # Pagination bar (UX-6)
        pager = QHBoxLayout()
        pager.setContentsMargins(0, 0, 0, 0)

        page_size_label = QLabel("Rows:")
        page_size_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        self._page_size_label = page_size_label
        pager.addWidget(page_size_label)

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["50", "100", "200"])
        self.page_size_combo.setCurrentText("100")
        self.page_size_combo.setStyleSheet(self._combo_style(_palette()))
        self.page_size_combo.currentTextChanged.connect(
            self._on_page_size_changed
        )
        pager.addWidget(self.page_size_combo)

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.clicked.connect(self._on_prev_page)
        pager.addWidget(self.prev_btn)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self._on_next_page)
        pager.addWidget(self.next_btn)

        self.page_label = QLabel("Page 1 of 1")
        self.page_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        pager.addWidget(self.page_label)

        pager.addStretch()
        layout.addLayout(pager)

        # Empty state label
        self.empty_label = QLabel("")
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
            self.priority_filter.setStyleSheet(self._combo_style(p))
            self.status_filter.setStyleSheet(self._combo_style(p))
            self.page_size_combo.setStyleSheet(self._combo_style(p))
            self.search_box.setStyleSheet(self._search_style(p))
            self._refresh_btn.setStyleSheet(self._refresh_style(p))
            muted = f"color: {p.text_muted}; font-size: 12px;"
            self.page_label.setStyleSheet(muted)
            self._page_size_label.setStyleSheet(muted)
            self._status_filter_label.setStyleSheet(muted)
        self._reapply_in_flight_row_state()

    @staticmethod
    def _combo_style(p) -> str:
        return f"""
            QComboBox {{
                background-color: {p.surface_alt};
                color: {p.text};
                border: 1px solid {p.scrollbar};
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 70px;
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
                min-width: 110px;
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
        """Create header with counters and filters"""
        header = QHBoxLayout()
        
        # Title with live counter
        title_layout = QVBoxLayout()
        title = QLabel("🚨 Alerts")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))

        self.counter_label = QLabel("Loading...")
        self.counter_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 11px;"
        )
        # Wrap on narrow windows instead of forcing the header wider
        self.counter_label.setWordWrap(True)

        title_layout.addWidget(title)
        title_layout.addWidget(self.counter_label)
        header.addLayout(title_layout)
        
        header.addStretch()
        
        # Priority filter
        self._filter_label = QLabel("Filter:")
        self._filter_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        header.addWidget(self._filter_label)

        self.priority_filter = QComboBox()
        self.priority_filter.addItems(["All", "Critical", "High", "Medium", "Low"])
        p = _palette()
        self.priority_filter.setStyleSheet(self._combo_style(p))
        self.priority_filter.currentTextChanged.connect(self._on_filter_changed)
        header.addWidget(self.priority_filter)

        # Triage status filter
        status_label = QLabel("Status:")
        status_label.setStyleSheet(
            f"color: {_palette().text_muted}; font-size: 12px;"
        )
        self._status_filter_label = status_label
        header.addWidget(status_label)
        self.status_filter = QComboBox()
        self.status_filter.addItems(
            ["All", "Open", "New", "In progress", "Resolved",
             "False positive"]
        )
        self.status_filter.setStyleSheet(self._combo_style(p))
        self.status_filter.currentTextChanged.connect(
            self._on_status_filter_changed
        )
        header.addWidget(self.status_filter)

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.setToolTip("Search alerts (Ctrl+F or /)")
        self.search_box.setStyleSheet(self._search_style(p))
        self.search_box.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_box)

        # Refresh button
        refresh_btn = QPushButton("🔄")
        self._refresh_btn = refresh_btn
        refresh_btn.setToolTip("Refresh alerts")
        refresh_btn.setStyleSheet(self._refresh_style(p))
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        # Export button (UX-6)
        export_btn = QPushButton("Export…")
        self._export_btn = export_btn
        set_role(export_btn, "secondary")
        export_btn.setToolTip("Export filtered alerts as CSV or JSON (Ctrl+E)")
        export_btn.clicked.connect(self._on_export)
        header.addWidget(export_btn)

        return header
    
    def refresh(self):
        """Full refresh - rebuild cache and table"""
        try:
            results = self._results()
            triage = self._triage_map()

            # Rebuild cache
            self._alert_cache.clear()
            alerts_data = []

            for result in results:
                for i, alert in enumerate(result.alerts):
                    alert_dict = self._alert_dict(result, alert, triage, i)
                    self._alert_cache[alert_dict["key"]] = alert_dict
                    alerts_data.append(alert_dict)
            
            # Handle empty state
            if not alerts_data:
                self._remove_action_widgets()
                self.table.setRowCount(0)
                self._filtered_cache = []
                self._update_page_controls()
                self._show_empty_state()
                return

            self.empty_label.hide()
            self.table.show()

            # Apply filters and render the current page
            filtered = self._apply_filters(alerts_data)
            self._render_alerts(filtered)
        
        except Exception as e:
            self._show_error_state(str(e))
    
    def _incremental_refresh(self):
        """Incremental refresh - only update if new alerts"""
        try:
            results = self._results()
            triage = self._triage_map()

            # Merge current triage statuses into cached alerts (a status
            # change stores no new result, so handle it explicitly).
            status_changed = False
            for cached in self._alert_cache.values():
                status = triage.get(cached["alert_id"], "New")
                if cached["status"] != status:
                    cached["status"] = status
                    status_changed = True

            new_alerts = []
            for result in results:
                for i, alert in enumerate(result.alerts):
                    key = self._alert_key(result, i, alert)
                    if key not in self._alert_cache:
                        alert_dict = self._alert_dict(result, alert, triage, i)
                        self._alert_cache[key] = alert_dict
                        new_alerts.append(alert_dict)

            # Only update if there are new alerts or status changes
            if new_alerts or status_changed:
                all_alerts = list(self._alert_cache.values())
                filtered = self._apply_filters(all_alerts)
                self._render_alerts(filtered, preserve_scroll=True)
        
        except Exception:
            pass  # Silent fail for incremental updates
    
    def _apply_filters(self, alerts_data: list) -> list:
        """Apply priority filter and search"""
        filtered = alerts_data
        
        # Priority filter
        if self._current_filter != "All":
            filtered = [a for a in filtered if self._current_filter.lower() in a["priority"].lower()]

        # Triage status filter ("Open" = New + In progress)
        if self._current_status_filter == "Open":
            filtered = [
                a for a in filtered
                if a["status"] in ("New", "In progress")
            ]
        elif self._current_status_filter != "All":
            filtered = [
                a for a in filtered
                if a["status"] == self._current_status_filter
            ]

        # Search filter
        if self._search_text:
            search_lower = self._search_text.lower()
            filtered = [
                a for a in filtered
                if search_lower in a["classification"].lower()
                or search_lower in a["source_ip"].lower()
                or search_lower in a["batch_id"].lower()
            ]
        
        return filtered

    # ------------------------------------------------------------------
    # Pagination + export (UX-6)
    # ------------------------------------------------------------------

    @staticmethod
    def _sort_key(alert: dict):
        ts = alert.get("timestamp")
        return ts.isoformat() if isinstance(ts, datetime) else str(ts or "")

    def _render_alerts(self, filtered: list, preserve_scroll: bool = False):
        """Sort, paginate and render the filtered alert set."""
        filtered = sorted(filtered, key=self._sort_key, reverse=True)
        self._filtered_cache = filtered

        total = len(filtered)
        pages = max(1, -(-total // self._page_size))
        self._page = max(0, min(self._page, pages - 1))  # clamp

        start = self._page * self._page_size
        page_rows = filtered[start:start + self._page_size]

        self._update_counter(filtered)
        self._update_table_incremental(page_rows, preserve_scroll)
        self._update_page_controls()

    def _update_page_controls(self):
        total = len(getattr(self, "_filtered_cache", []))
        pages = max(1, -(-total // self._page_size))
        start = self._page * self._page_size
        end = min(total, start + self._page_size)
        shown = f"{start + 1}\u2013{end}" if total else "0"
        self.page_label.setText(
            f"Page {self._page + 1} of {pages} \u00b7 showing {shown} of {total}"
        )
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page < pages - 1)

    def _on_page_size_changed(self, text: str):
        try:
            self._page_size = int(text)
        except ValueError:
            return
        self._page = 0
        self._render_alerts(self._filtered_cache)

    def _on_prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_alerts(self._filtered_cache, preserve_scroll=False)

    def _on_next_page(self):
        total = len(self._filtered_cache)
        if (self._page + 1) * self._page_size < total:
            self._page += 1
            self._render_alerts(self._filtered_cache, preserve_scroll=False)

    def _on_export(self):
        """Export the full filtered set (all pages) as CSV or JSON."""
        from .alert_export import alerts_to_csv, alerts_to_json

        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export alerts",
            f"soc_alerts_{datetime.now().strftime('%Y%m%d_%H%M')}",
            "CSV (*.csv);;JSON (*.json)",
        )
        if not path:
            return
        try:
            is_json = path.lower().endswith(".json") or "JSON" in selected
            text = (
                alerts_to_json(self._filtered_cache)
                if is_json else alerts_to_csv(self._filtered_cache)
            )
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            window = self.window()
            if hasattr(window, "statusBar"):
                window.statusBar().showMessage(
                    f"Exported {len(self._filtered_cache)} alerts to {path}",
                    5000,
                )
            show_toast(
                self,
                f"Exported {len(self._filtered_cache)} alerts",
                "success",
            )
        except Exception as exc:
            QMessageBox.critical(
                self, "Export failed", f"Could not export alerts:\n{exc}"
            )
    
    def _update_counter(self, alerts_data: list):
        """Update alert counters"""
        total = len(alerts_data)
        critical = sum(1 for a in alerts_data if "critical" in a["priority"].lower())
        high = sum(1 for a in alerts_data if "high" in a["priority"].lower())
        medium = sum(1 for a in alerts_data if "medium" in a["priority"].lower())
        open_count = sum(
            1 for a in alerts_data
            if a.get("status", "New") in ("New", "In progress")
        )

        parts = [f"Total: {total}", f"Open: {open_count}"]
        if critical: parts.append(f"Critical: {critical}")
        if high: parts.append(f"High: {high}")
        if medium: parts.append(f"Medium: {medium}")
        
        self.counter_label.setText(" │ ".join(parts))
    
    def set_priority_filter(self, priority: str):
        """Set priority filter programmatically"""
        priority_map = {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
            "all": "All"
        }
        filter_text = priority_map.get(priority.lower(), "All")
        self.priority_filter.setCurrentText(filter_text)
    
    def _on_filter_changed(self, text: str):
        """Handle filter change"""
        self._current_filter = text
        self._page = 0  # filters reset to first page (UX-6)
        all_alerts = list(self._alert_cache.values())
        filtered = self._apply_filters(all_alerts)
        self._render_alerts(filtered)

    def _on_status_filter_changed(self, text: str):
        """Handle triage status filter change"""
        self._current_status_filter = text
        self._page = 0
        all_alerts = list(self._alert_cache.values())
        filtered = self._apply_filters(all_alerts)
        self._render_alerts(filtered)

    def _on_search_changed(self, text: str):
        """Handle search change"""
        self._search_text = text
        self._page = 0
        all_alerts = list(self._alert_cache.values())
        filtered = self._apply_filters(all_alerts)
        self._render_alerts(filtered)
    
    def _show_empty_state(self):
        """Show appropriate empty state message"""
        try:
            stats = self.bridge.get_stats()
            pipeline_active = stats.get("pipeline_loaded", False)
            
            # Get ingestion status
            running = stats.get('running', False)
            shutdown_flag = stats.get('shutdown_flag', False)
            sources_count = stats.get('sources_count', 0)
            
            if shutdown_flag:
                ingestion_status = "Stopped"
            elif running and sources_count > 0:
                ingestion_status = "Active"
            elif sources_count > 0:
                ingestion_status = "Configured"
            else:
                ingestion_status = "Not Started"
            
            if not pipeline_active:
                message = (
                    "⚠️ Pipeline not active\n\n"
                    "Models may be missing. Run:\n"
                    "python scripts/train_models.py"
                )
            elif ingestion_status == "Not Started":
                message = (
                    "📁 No log sources configured\n\n"
                    "Add log files or directories to start monitoring"
                )
            elif ingestion_status == "Stopped":
                message = (
                    "⏸️ Ingestion stopped\n\n"
                    "Restart the application to resume monitoring"
                )
            elif ingestion_status == "Active":
                message = (
                    "🔄 Monitoring active - No alerts yet\n\n"
                    "System is actively monitoring for security threats.\n"
                    "This is good - no threats detected!"
                )
            else:
                message = (
                    "✅ No alerts detected\n\n"
                    "System is ready to monitor for security threats."
                )
            
            self.empty_label.setText(message)
        except Exception:
            self.empty_label.setText("No alerts to display.")
        
        self.empty_label.show()
        self.table.hide()
    
    def _show_error_state(self, error: str):
        """Show error state"""
        self._remove_action_widgets()
        self.table.setRowCount(0)
        error_msg = error[:100] + "..." if len(error) > 100 else error
        self.empty_label.setText(f"❌ Error loading alerts:\n{error_msg}\n\nCheck logs for details.")
        self.empty_label.show()
        self.table.hide()
    
    def _update_table(self, alerts_data: list):
        """Full table update - optimized batch operation"""
        # Disable updates during batch operation
        self.table.setUpdatesEnabled(False)

        # setRowCount() does NOT remove cell widgets — dropped Investigate
        # buttons would leak and paint at stale positions (UX-5 fix).
        self._remove_action_widgets()
        self.table.setRowCount(len(alerts_data))
        
        for row, alert in enumerate(alerts_data):
            self._set_row_data(row, alert)
        
        # Re-enable updates and refresh
        self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()
    
    def _update_table_incremental(self, alerts_data: list, preserve_scroll: bool = True):
        """Incremental update - preserve scroll position"""
        # Save scroll position
        scroll_bar = self.table.verticalScrollBar()
        scroll_pos = scroll_bar.value() if preserve_scroll else 0
        
        # Disable updates
        self.table.setUpdatesEnabled(False)

        self._remove_action_widgets()
        self.table.setRowCount(len(alerts_data))
        
        for row, alert in enumerate(alerts_data):
            self._set_row_data(row, alert)
        
        # Re-enable and restore scroll
        self.table.setUpdatesEnabled(True)
        if preserve_scroll:
            scroll_bar.setValue(scroll_pos)
            
    def _remove_action_widgets(self):
        """Detach and delete every Investigate button before a rebuild.

        ``setRowCount``/``removeCellWidget`` only detach the widget — it
        stays a visible child of the viewport at its old position, which
        is how stray/duplicate Investigate buttons appeared (UX-5 fix).
        """
        for row in range(self.table.rowCount()):
            widget = self.table.cellWidget(row, self.ACTION_COLUMN)
            if widget is not None:
                self.table.removeCellWidget(row, self.ACTION_COLUMN)
                widget.hide()
                widget.setParent(None)  # detach from the viewport now
                widget.deleteLater()

    def _set_row_data(self, row: int, alert: dict):
        """Set data for a single row - reusable method"""
        items = [
            QTableWidgetItem(alert["time"]),
            QTableWidgetItem(alert["priority"]),
            QTableWidgetItem(alert.get("status", "New")),
            QTableWidgetItem(alert["classification"]),
            QTableWidgetItem(alert["source_ip"]),
            QTableWidgetItem(alert["confidence"]),
            QTableWidgetItem(alert["batch_id"])
        ]

        # Set items (keep the real alert_id on the classification cell so
        # row clicks can disambiguate alerts sharing a classification)
        for col, item in enumerate(items):
            if col == self.CLASSIFICATION_COLUMN:
                item.setData(Qt.ItemDataRole.UserRole, alert.get("alert_id"))
            self.table.setItem(row, col, item)
            
        # Create and add action button
        btn = QPushButton("Investigate")
        source_ip = alert["source_ip"]
        btn.clicked.connect(lambda checked=False, ip=source_ip: self._trigger_investigation(ip))
        self.table.setCellWidget(row, self.ACTION_COLUMN, btn)
        
        self._apply_row_visual_state(row, alert["priority"], source_ip)
        self._update_action_button(row, source_ip)

    def _apply_row_visual_state(self, row: int, priority: str, source_ip: str):
        """Apply priority and in-flight visual state to one table row."""
        in_flight = self.bridge.is_investigation_in_flight(source_ip)

        priority_lower = priority.lower()
        if in_flight:
            color = QColor(_palette().sev_info)
        elif any(k in priority_lower for k in ("critical", "high", "medium")):
            color = QColor(severity_color(priority))
        else:
            color = QColor(_palette().text)

        for col in range(self.ACTION_COLUMN):
            if col == self.STATUS_COLUMN:
                continue  # status cell keeps its own colour
            item = self.table.item(row, col)
            if item:
                item.setForeground(color)
                item.setToolTip("Investigation in progress" if in_flight else "")

        self._style_status_cell(row)

    _STATUS_COLORS = {
        "New": "info",
        "In progress": "warning",
        "Resolved": "success",
        "False positive": "text_muted",
    }

    def _style_status_cell(self, row: int):
        """Colour the Status cell by triage status (theme tokens)."""
        item = self.table.item(row, self.STATUS_COLUMN)
        if not item:
            return
        p = _palette()
        token = self._STATUS_COLORS.get(item.text(), "info")
        item.setForeground(QColor(getattr(p, token)))
        item.setToolTip(item.text())

    def _update_action_button(self, row: int, source_ip: str):
        """Update action button state for a row based on whether investigation is in-flight."""
        btn = self.table.cellWidget(row, self.ACTION_COLUMN)
        if not isinstance(btn, QPushButton):
            return
        
        in_flight = self.bridge.is_investigation_in_flight(source_ip)
        is_invalid_ip = not source_ip or source_ip.upper() == "N/A"
        
        p = _palette()
        if in_flight:
            btn.setEnabled(False)
            btn.setText("Investigating...")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {p.scrollbar};
                    color: {p.text_muted};
                    border: 1px solid {p.scrollbar};
                    border-radius: 4px;
                    padding: 2px 8px;
                }}
            """)
        elif is_invalid_ip:
            btn.setEnabled(False)
            btn.setText("N/A")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {p.text_muted};
                    border: none;
                }}
            """)
        else:
            btn.setEnabled(True)
            btn.setText("Investigate")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {p.accent};
                    color: {p.text_inverse};
                    border: none;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {p.accent_hover};
                }}
            """)

    def _reapply_in_flight_row_state(self):
        """Refresh in-flight visuals for currently displayed rows."""
        for row in range(self.table.rowCount()):
            priority_item = self.table.item(row, self.PRIORITY_COLUMN)
            source_item = self.table.item(row, self.SOURCE_IP_COLUMN)
            priority = priority_item.text() if priority_item else ""
            source_ip = source_item.text() if source_item else ""
            self._apply_row_visual_state(row, priority, source_ip)
            self._update_action_button(row, source_ip)
    
    def _on_row_clicked(self, item):
        """Handle row click with error handling"""
        try:
            row = item.row()
            batch_id = self.table.item(row, self.BATCH_ID_COLUMN).text()
            class_item = self.table.item(row, self.CLASSIFICATION_COLUMN)
            alert_id = class_item.data(Qt.ItemDataRole.UserRole) or class_item.text()
            self.alert_selected.emit(batch_id, alert_id)
        except Exception:
            pass  # Ignore click errors

    def _on_table_context_menu(self, pos):
        """Right-click context menu on a table row."""
        item = self.table.itemAt(pos)
        if item is None:
            return
        menu = self._build_row_context_menu(item.row())
        if menu is not None:
            menu.exec(self.table.viewport().mapToGlobal(pos))

    def _row_alert_dict(self, row: int) -> dict | None:
        """Find the alert dict for a visible table row."""
        class_item = self.table.item(row, self.CLASSIFICATION_COLUMN)
        alert_id = (
            class_item.data(Qt.ItemDataRole.UserRole)
            if class_item is not None else None
        )
        if not alert_id:
            return None
        for cached in self._alert_cache.values():
            if cached["alert_id"] == alert_id:
                return cached
        return None

    def _add_ip_actions(self, menu, ip: str):
        """Per-IP submenu shared with the details panel (UX-7)."""
        sub = menu.addMenu(ip)
        sub.addAction("Investigate").triggered.connect(
            lambda c=False, t=ip: self._trigger_investigation(t)
        )
        sub.addAction("Copy IP").triggered.connect(
            lambda c=False, t=ip: self._copy_to_clipboard(t)
        )
        sub.addAction("Filter alerts by this IP").triggered.connect(
            lambda c=False, t=ip: self.search_box.setText(t)
        )
        sub.addAction("Show logs for this IP").triggered.connect(
            lambda c=False, t=ip: self.show_logs_requested.emit(t)
        )

    def _copy_to_clipboard(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self._status_msg(f"Copied {text}")

    def _status_msg(self, msg: str, kind: str = "info"):
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(msg, 3000)
        if window is not self:
            show_toast(self, msg, kind)

    def _build_row_context_menu(self, row: int):
        """Row context menu; new actions get appended here."""
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(self)
        alert = self._row_alert_dict(row)

        # Per-IP actions (source / destination)
        for label, ip in (
            ("source", alert.get("source_ip") if alert else None),
            ("destination", alert.get("destination_ip") if alert else None),
        ):
            if ip and str(ip).upper() != "N/A":
                self._add_ip_actions(menu, ip)

        status_menu = menu.addMenu("Set status")
        for status in TRIAGE_STATUSES:
            action = status_menu.addAction(status)
            action.triggered.connect(
                lambda checked=False, s=status, r=row:
                    self._set_row_status(r, s)
            )

        menu.addSeparator()
        if alert:
            menu.addAction("Copy alert ID").triggered.connect(
                lambda c=False, t=alert["alert_id"]:
                    self._copy_to_clipboard(t)
            )
            menu.addAction("Open details").triggered.connect(
                lambda c=False, a=alert:
                    self.alert_selected.emit(a["batch_id"], a["alert_id"])
            )
        return menu

    def _set_row_status(self, row: int, status: str):
        """Persist a triage status change for the alert in `row`."""
        class_item = self.table.item(row, self.CLASSIFICATION_COLUMN)
        alert_id = (
            class_item.data(Qt.ItemDataRole.UserRole)
            if class_item is not None else None
        )
        if not alert_id:
            return
        try:
            self.bridge.set_alert_status(alert_id, status)
        except Exception as exc:
            QMessageBox.critical(
                self, "Status change failed",
                f"Could not set status on {alert_id}:\n{exc}",
            )
            return
        # Update locally too (bridge notification refreshes as well)
        for cached in self._alert_cache.values():
            if cached["alert_id"] == alert_id:
                cached["status"] = status
        item = self.table.item(row, self.STATUS_COLUMN)
        if item is not None:
            item.setText(status)
            self._style_status_cell(row)
        self._update_counter(list(self._alert_cache.values()))

    # ------------------------------------------------------------------
    # Keyboard shortcuts (UX-7)
    # ------------------------------------------------------------------

    _STATUS_KEYS = {
        Qt.Key.Key_1: "New",
        Qt.Key.Key_2: "In progress",
        Qt.Key.Key_3: "Resolved",
        Qt.Key.Key_4: "False positive",
    }

    def eventFilter(self, watched, event):
        """Vim-style shortcuts while the alerts table has focus."""
        from PyQt6.QtCore import QEvent
        if (
            watched is self.table
            and event.type() == QEvent.Type.KeyPress
        ):
            if self._handle_table_key(event.key()):
                return True
        return super().eventFilter(watched, event)

    def _handle_table_key(self, key) -> bool:
        row = self.table.currentRow()
        if key == Qt.Key.Key_J:
            self._move_row_selection(1)
            return True
        if key == Qt.Key.Key_K:
            self._move_row_selection(-1)
            return True
        if row < 0:
            return False
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.table.item(row, self.CLASSIFICATION_COLUMN)
            if item is not None:
                self._on_row_clicked(item)
            return True
        alert = self._row_alert_dict(row)
        if key == Qt.Key.Key_I:
            item = self.table.item(row, self.SOURCE_IP_COLUMN)
            ip = item.text() if item else ""
            if ip and ip.upper() != "N/A":
                self._trigger_investigation(ip)
            return True
        if alert is None:
            return False
        if key == Qt.Key.Key_A:
            self._row_feedback(alert, "accept")
            return True
        if key == Qt.Key.Key_R:
            self._row_feedback(alert, "reject")
            return True
        status = self._STATUS_KEYS.get(key)
        if status is not None:
            self._set_row_status(row, status)
            self._status_msg(
                f"Marked {alert['alert_id']} as {status}", "success"
            )
            return True
        return False

    def _move_row_selection(self, delta: int):
        row = self.table.currentRow() + delta
        if 0 <= row < self.table.rowCount():
            self.table.setCurrentCell(row, 0)
            self.table.selectRow(row)

    def _row_feedback(self, alert: dict, action: str):
        """Submit accept/reject feedback for the row's alert (UX-5 link)."""
        try:
            self.bridge.submit_feedback(alert["alert_id"], action)
            self._status_msg(
                f"Feedback '{action}' for {alert['alert_id']}", "success"
            )
        except Exception as exc:
            self._status_msg(f"Feedback failed: {exc}", "error")

    def _find_rows_by_ip(self, ip: str) -> list[int]:
        """Scan the table to find all row indices matching the given IP address."""
        if not ip:
            return []
        rows = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, self.SOURCE_IP_COLUMN)
            if item and item.text().strip() == ip.strip():
                rows.append(row)
        return rows

    def _trigger_investigation(self, source_ip: str):
        """Common logic to start an async investigation for an IP."""
        if not source_ip or source_ip.upper() == "N/A":
            return

        if self.bridge.is_investigation_in_flight(source_ip):
            return

        rows = self._find_rows_by_ip(source_ip)
        
        try:
            self.bridge.investigate_target(source_ip)
            if self.report_drawer is not None:
                self.report_drawer.show_loading(source_ip)
            for row in rows:
                priority_item = self.table.item(row, self.PRIORITY_COLUMN)
                priority = priority_item.text() if priority_item else "Low"
                self._apply_row_visual_state(row, priority, source_ip)
                self._update_action_button(row, source_ip)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Investigation Failed",
                f"Could not start investigation for {source_ip}:\n{exc}",
            )
            for row in rows:
                priority_item = self.table.item(row, self.PRIORITY_COLUMN)
                priority = priority_item.text() if priority_item else "Low"
                self._apply_row_visual_state(row, priority, source_ip)
                self._update_action_button(row, source_ip)

    def _on_row_double_clicked(self, item):
        """Start an async investigation for the row source IP."""
        try:
            row = item.row()
            source_item = self.table.item(row, self.SOURCE_IP_COLUMN)
            source_ip = source_item.text().strip() if source_item else ""
        except Exception:
            return  # Row may have been rebuilt during refresh.

        self._trigger_investigation(source_ip)

    def _on_report_ready(self, target, report, error):
        """Show investigation result delivered from the bridge."""
        self._reapply_in_flight_row_state()

        if error is not None:
            message = getattr(error, "message", str(error))
            if self.report_drawer is not None:
                self.report_drawer.show_error(target, message)
            else:
                QMessageBox.critical(
                    self,
                    "Investigation Failed",
                    f"Investigation failed for {target}:\n{message}",
                )
            return

        if self.report_drawer is not None:
            self.report_drawer.show_report(report)
        else:
            QMessageBox.information(
                self,
                f"Threat Report: {target}",
                self._format_threat_report(report),
            )

    def _format_threat_report(self, report) -> str:
        """Format a ThreatReport defensively for modal display."""
        if report is None:
            return "No report was returned."

        severity = getattr(getattr(report, "severity", None), "value", None)
        if severity is None:
            severity = getattr(report, "severity", "Unknown")

        lines = [
            f"Target: {getattr(report, 'target', 'Unknown')}",
            f"Severity: {severity or 'Unknown'}",
            "",
            getattr(report, "summary", "") or "No summary provided.",
        ]

        recommendations = getattr(report, "recommendations", None) or []
        if recommendations:
            lines.extend(["", "Recommendations:"])
            lines.extend(f"- {item}" for item in recommendations)

        shodan = getattr(report, "shodan", None)
        open_ports = getattr(shodan, "open_ports", None) if shodan else None
        cves = getattr(shodan, "cves", None) if shodan else None
        if open_ports:
            lines.extend(["", f"Open ports: {', '.join(str(port) for port in open_ports)}"])
        if cves:
            lines.extend(["", f"CVEs: {', '.join(str(cve) for cve in cves)}"])

        return "\n".join(lines)
