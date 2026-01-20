"""Optimized alerts table with incremental updates and scroll preservation"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QLabel, QPushButton, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor


class AlertsView(QWidget):
    """Scalable alerts table with filtering and incremental updates"""
    
    alert_selected = pyqtSignal(str, str)  # batch_id, alert_id
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._alert_cache = {}  # batch_id -> alert data
        self._current_filter = "All"
        self._search_text = ""
        self._init_ui()
        
        # Fast refresh for real-time feel
        self.timer = QTimer()
        self.timer.timeout.connect(self._incremental_refresh)
        self.timer.start(2000)  # 2 seconds
        
        # Initial refresh
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
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Time", "Priority", "Classification", "Source IP", "Confidence", "Batch ID"
        ])
        
        # Optimize table for performance
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)  # Disable during updates
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(32)  # Compact rows
        self.table.itemClicked.connect(self._on_row_clicked)
        
        # Performance: disable updates during batch operations
        self.table.setUpdatesEnabled(True)
        
        layout.addWidget(self.table)
        
        # Empty state label
        self.empty_label = QLabel("")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #888888; font-style: italic; padding: 20px;")
        self.empty_label.setFont(QFont("Segoe UI", 12))
        layout.addWidget(self.empty_label)
        
        self.setLayout(layout)
    
    def _create_header(self) -> QHBoxLayout:
        """Create header with counters and filters"""
        header = QHBoxLayout()
        
        # Title with live counter
        title_layout = QVBoxLayout()
        title = QLabel("🚨 Alerts")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #ffffff;")
        
        self.counter_label = QLabel("Loading...")
        self.counter_label.setStyleSheet("color: #888888; font-size: 11px;")
        
        title_layout.addWidget(title)
        title_layout.addWidget(self.counter_label)
        header.addLayout(title_layout)
        
        header.addStretch()
        
        # Priority filter
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #888888; font-size: 12px;")
        header.addWidget(filter_label)
        
        self.priority_filter = QComboBox()
        self.priority_filter.addItems(["All", "Critical", "High", "Medium", "Low"])
        self.priority_filter.setStyleSheet("""
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
        self.priority_filter.currentTextChanged.connect(self._on_filter_changed)
        header.addWidget(self.priority_filter)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.setStyleSheet("""
            QLineEdit {
                background-color: #1a2744;
                color: #ffffff;
                border: 1px solid #2a3f5f;
                border-radius: 4px;
                padding: 5px 10px;
                min-width: 150px;
            }
        """)
        self.search_box.textChanged.connect(self._on_search_changed)
        header.addWidget(self.search_box)
        
        # Refresh button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh alerts")
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
        """Full refresh - rebuild cache and table"""
        try:
            results = self.bridge.get_latest_alerts(limit=200)  # Increased limit
            
            # Rebuild cache
            self._alert_cache.clear()
            alerts_data = []
            
            for result in results:
                for alert in result.alerts:
                    key = f"{result.batch_id}_{alert.classification}"
                    alert_dict = {
                        "key": key,
                        "batch_id": result.batch_id,
                        "alert_id": alert.alert_id,
                        "time": alert.timestamp.strftime("%H:%M:%S") if hasattr(alert.timestamp, 'strftime') else str(alert.timestamp),
                        "priority": alert.priority,
                        "classification": alert.classification,
                        "source_ip": getattr(alert, 'source_ip', None) or "N/A",
                        "confidence": f"{alert.confidence:.2f}" if hasattr(alert, 'confidence') else "N/A"
                    }
                    self._alert_cache[key] = alert_dict
                    alerts_data.append(alert_dict)
            
            # Update counter
            self._update_counter(alerts_data)
            
            # Handle empty state
            if not alerts_data:
                self.table.setRowCount(0)
                self._show_empty_state()
                return
            
            self.empty_label.hide()
            self.table.show()
            
            # Apply filters and update table
            filtered = self._apply_filters(alerts_data)
            self._update_table(filtered)
        
        except Exception as e:
            self._show_error_state(str(e))
    
    def _incremental_refresh(self):
        """Incremental refresh - only update if new alerts"""
        try:
            results = self.bridge.get_latest_alerts(limit=200)
            
            new_alerts = []
            for result in results:
                for alert in result.alerts:
                    key = f"{result.batch_id}_{alert.classification}"
                    if key not in self._alert_cache:
                        alert_dict = {
                            "key": key,
                            "batch_id": result.batch_id,
                            "alert_id": alert.alert_id,
                            "time": alert.timestamp.strftime("%H:%M:%S") if hasattr(alert.timestamp, 'strftime') else str(alert.timestamp),
                            "priority": alert.priority,
                            "classification": alert.classification,
                            "source_ip": getattr(alert, 'source_ip', None) or "N/A",
                            "confidence": f"{alert.confidence:.2f}" if hasattr(alert, 'confidence') else "N/A"
                        }
                        self._alert_cache[key] = alert_dict
                        new_alerts.append(alert_dict)
            
            # Only update if there are new alerts
            if new_alerts:
                all_alerts = list(self._alert_cache.values())
                self._update_counter(all_alerts)
                filtered = self._apply_filters(all_alerts)
                self._update_table_incremental(filtered, preserve_scroll=True)
        
        except Exception:
            pass  # Silent fail for incremental updates
    
    def _apply_filters(self, alerts_data: list) -> list:
        """Apply priority filter and search"""
        filtered = alerts_data
        
        # Priority filter
        if self._current_filter != "All":
            filtered = [a for a in filtered if self._current_filter.lower() in a["priority"].lower()]
        
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
    
    def _update_counter(self, alerts_data: list):
        """Update alert counters"""
        total = len(alerts_data)
        critical = sum(1 for a in alerts_data if "critical" in a["priority"].lower())
        high = sum(1 for a in alerts_data if "high" in a["priority"].lower())
        medium = sum(1 for a in alerts_data if "medium" in a["priority"].lower())
        
        parts = [f"Total: {total}"]
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
            "all": "All"
        }
        filter_text = priority_map.get(priority.lower(), "All")
        self.priority_filter.setCurrentText(filter_text)
    
    def _on_filter_changed(self, text: str):
        """Handle filter change"""
        self._current_filter = text
        all_alerts = list(self._alert_cache.values())
        filtered = self._apply_filters(all_alerts)
        self._update_table(filtered)
    
    def _on_search_changed(self, text: str):
        """Handle search change"""
        self._search_text = text
        all_alerts = list(self._alert_cache.values())
        filtered = self._apply_filters(all_alerts)
        self._update_table(filtered)
    
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
        self.table.setRowCount(0)
        error_msg = error[:100] + "..." if len(error) > 100 else error
        self.empty_label.setText(f"❌ Error loading alerts:\n{error_msg}\n\nCheck logs for details.")
        self.empty_label.show()
        self.table.hide()
    
    def _update_table(self, alerts_data: list):
        """Full table update - optimized batch operation"""
        # Disable updates during batch operation
        self.table.setUpdatesEnabled(False)
        
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
        
        self.table.setRowCount(len(alerts_data))
        
        for row, alert in enumerate(alerts_data):
            self._set_row_data(row, alert)
        
        # Re-enable and restore scroll
        self.table.setUpdatesEnabled(True)
        if preserve_scroll:
            scroll_bar.setValue(scroll_pos)
    
    def _set_row_data(self, row: int, alert: dict):
        """Set data for a single row - reusable method"""
        items = [
            QTableWidgetItem(alert["time"]),
            QTableWidgetItem(alert["priority"]),
            QTableWidgetItem(alert["classification"]),
            QTableWidgetItem(alert["source_ip"]),
            QTableWidgetItem(alert["confidence"]),
            QTableWidgetItem(alert["batch_id"])
        ]
        
        # Set items
        for col, item in enumerate(items):
            self.table.setItem(row, col, item)
        
        # Color by priority
        priority_lower = alert["priority"].lower()
        if "critical" in priority_lower:
            color = QColor("#ff4444")
        elif "high" in priority_lower:
            color = QColor("#ff8800")
        elif "medium" in priority_lower:
            color = QColor("#ffaa00")
        else:
            color = QColor("#ffffff")
        
        # Apply color
        for col in range(6):
            item = self.table.item(row, col)
            if item:
                item.setForeground(color)
    
    def _on_row_clicked(self, item):
        """Handle row click with error handling"""
        try:
            row = item.row()
            batch_id = self.table.item(row, 5).text()
            alert_id = self.table.item(row, 2).text()  # Use classification as identifier
            self.alert_selected.emit(batch_id, alert_id)
        except Exception:
            pass  # Ignore click errors
