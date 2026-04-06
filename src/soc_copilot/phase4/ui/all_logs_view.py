"""All Logs view with table displaying benign and alert logs"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QLabel, QPushButton, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

class AllLogsView(QWidget):
    """Scalable logs table for displaying all processed events"""
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._log_cache = {}  # log_id -> log data
        self._current_filter = "All"
        self._search_text = ""
        self._init_ui()
        
        # Fast refresh
        self.timer = QTimer()
        self.timer.timeout.connect(self._incremental_refresh)
        self.timer.start(2000)
        
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
        self.empty_label.setStyleSheet("color: #888888; font-style: italic; padding: 20px;")
        self.empty_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.empty_label)
        
        self.setLayout(layout)
        
    def _create_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title = QLabel("📋 All Logs")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        
        self.counter_label = QLabel("Loading...")
        self.counter_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        title_layout.addWidget(title)
        title_layout.addWidget(self.counter_label)
        header.addLayout(title_layout)
        
        header.addStretch()
        
        # Classification filter
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #888888; font-size: 12px;")
        header.addWidget(filter_label)
        
        self.class_filter = QComboBox()
        self.class_filter.addItems(["All", "Alerts Only", "Benign Only"])
        self.class_filter.setStyleSheet("""
            QComboBox {
                background-color: #1a2744;
                color: #ffffff;
                border: 1px solid #2a3f5f;
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 100px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #1a2744;
                color: #ffffff;
                selection-background-color: #00d4ff;
                selection-color: #0a0a1a;
            }
        """)
        self.class_filter.currentTextChanged.connect(self._on_filter_changed)
        header.addWidget(self.class_filter)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search raw logs...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #1a2744;
                color: #ffffff;
                border: 1px solid #2a3f5f;
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 200px;
            }
        """)
        self.search_box.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_box)
        
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh logs")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a2744;
                color: #ffffff;
                border: 1px solid #2a3f5f;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #2a3f5f; }
        """)
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        
        return header

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
            color = QColor("#ff4444") if lg["is_alert"] else QColor("#cccccc")
            for col in range(5):
                item = self.table.item(row, col)
                if item:
                    item.setForeground(color)
                    
        self.table.setUpdatesEnabled(True)
        if preserve_scroll:
            self.table.verticalScrollBar().setValue(scroll_pos)
