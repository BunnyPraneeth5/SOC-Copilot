"""Interactive SOC Dashboard with Zone-Based Layout and Visual Hierarchy

Zone Layout:
- Zone A: Status Strip (40px) - Consolidated 3 LEDs
- Zone B: Threat Summary Banner (80px) - Primary visual hierarchy
- Zone C: Metric Cards Row (120px) - Alert breakdown with trends
- Zone D+E: System Health + Quick Actions (combined row)
- Zone F: Recent Alerts Timeline (flex height) - Clickable alerts
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, 
    QPushButton, QFileDialog, QProgressBar, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from datetime import datetime

from .dashboard_components import (
    ThreatLevelBanner,
    RecentAlertsTimeline,
    QuickActionsBar,
    CompactMetricCard,
    SystemHealthGrid,
    EmptyStateCard
)
from .state_constants import (
    get_pipeline_state, get_ingestion_state, get_governance_state,
    format_ingestion_label,
    PIPELINE_STATES, INGESTION_STATES, GOVERNANCE_STATES
)


class FileProcessingWorker(QThread):
    """Worker thread for processing uploaded log files without blocking the UI."""
    
    # Signals to communicate with the main thread
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


class Dashboard(QWidget):
    """Modern SOC Dashboard with Zone-Based Layout
    
    Visual Hierarchy (2-Second Rule):
    1. Threat Level Banner - understand threat state in <1 second
    2. Metric Cards - breakdown by priority in 1-2 seconds
    3. System Health + Recent Alerts - details on demand
    """
    
    navigate_to_alerts = pyqtSignal()
    navigate_to_alerts_filtered = pyqtSignal(str)  # priority filter
    navigate_to_settings = pyqtSignal()
    alert_selected = pyqtSignal(str, str)  # batch_id, classification
    
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._last_counts = {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0}
        self._status_text = ""
        self._empty_state_text = ""
        self._worker = None  # Background file processing thread
        self._init_ui()
        
        # Adaptive polling - 3 seconds (reduced from 1.5s for performance)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)
        
        # Initial refresh
        self.refresh()
    
    # ─────────────────────────────────────────────────────────────────────
    # Test Compatibility Properties
    # ─────────────────────────────────────────────────────────────────────
    
    @property
    def status_label(self):
        """Mock status label for test compatibility"""
        class MockLabel:
            def __init__(self, text): self._text = text
            def text(self): return self._text
        return MockLabel(self._status_text)
    
    @property
    def empty_state_label(self):
        """Mock empty state label for test compatibility"""
        class MockLabel:
            def __init__(self, text): self._text = text
            def text(self): return self._text
        return MockLabel(self._empty_state_text)
    
    def _get_ingestion_status(self, stats: dict) -> str:
        """Derive ingestion status from stats - used by tests"""
        running = stats.get("running", False)
        sources = stats.get("sources_count", 0)
        shutdown = stats.get("shutdown_flag", False)
        state = get_ingestion_state(running, sources, shutdown)
        return INGESTION_STATES[state].label
    
    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 15, 20, 15)
        
        # ─────────────────────────────────────────────────────────────
        # ZONE B: Threat Summary Banner (Primary Hierarchy)
        # ─────────────────────────────────────────────────────────────
        self.threat_banner = ThreatLevelBanner()
        self.threat_banner.view_alerts_clicked.connect(self.navigate_to_alerts.emit)
        layout.addWidget(self.threat_banner)
        
        # ─────────────────────────────────────────────────────────────
        # ZONE C: Metric Cards Row (Secondary Hierarchy)
        # ─────────────────────────────────────────────────────────────
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(12)
        
        self.total_card = CompactMetricCard("Total Alerts", "total")
        self.critical_card = CompactMetricCard("Critical", "critical")
        self.high_card = CompactMetricCard("High", "high")
        self.medium_card = CompactMetricCard("Medium", "medium")
        self.low_card = CompactMetricCard("Low", "low")
        
        # Connect card clicks to filtered navigation
        self.total_card.clicked.connect(lambda p: self.navigate_to_alerts.emit())
        self.critical_card.clicked.connect(lambda p: self.navigate_to_alerts_filtered.emit("critical"))
        self.high_card.clicked.connect(lambda p: self.navigate_to_alerts_filtered.emit("high"))
        self.medium_card.clicked.connect(lambda p: self.navigate_to_alerts_filtered.emit("medium"))
        self.low_card.clicked.connect(lambda p: self.navigate_to_alerts_filtered.emit("low"))
        
        metrics_layout.addWidget(self.total_card)
        metrics_layout.addWidget(self.critical_card)
        metrics_layout.addWidget(self.high_card)
        metrics_layout.addWidget(self.medium_card)
        metrics_layout.addWidget(self.low_card)
        
        layout.addLayout(metrics_layout)
        
        # ─────────────────────────────────────────────────────────────
        # ZONE D+E: System Health + Quick Actions Row
        # ─────────────────────────────────────────────────────────────
        middle_row = QHBoxLayout()
        middle_row.setSpacing(15)
        
        # System Health Grid (compact)
        self.health_grid = SystemHealthGrid()
        self.health_grid.setFixedWidth(300)
        middle_row.addWidget(self.health_grid)
        
        # Quick Actions
        self.quick_actions = QuickActionsBar()
        self.quick_actions.upload_clicked.connect(self._upload_logs)
        self.quick_actions.alerts_clicked.connect(self.navigate_to_alerts.emit)
        self.quick_actions.settings_clicked.connect(self.navigate_to_settings.emit)
        self.quick_actions.refresh_clicked.connect(self._manual_refresh)
        middle_row.addWidget(self.quick_actions, 1)
        
        layout.addLayout(middle_row)
        
        # ─────────────────────────────────────────────────────────────
        # Progress bar for file uploads (hidden by default)
        # ─────────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #1a1a2e;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4ff, stop:1 #00ff88);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # ─────────────────────────────────────────────────────────────
        # ZONE F: Recent Alerts Timeline (Tertiary - scrollable)
        # ─────────────────────────────────────────────────────────────
        self.alerts_timeline = RecentAlertsTimeline()
        self.alerts_timeline.alert_clicked.connect(self.alert_selected.emit)
        self.alerts_timeline.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.alerts_timeline, 1)
        
        # ─────────────────────────────────────────────────────────────
        # Footer: Last update time
        # ─────────────────────────────────────────────────────────────
        footer = QHBoxLayout()
        self.last_update_label = QLabel("")
        self.last_update_label.setFont(QFont("Segoe UI", 10))
        self.last_update_label.setStyleSheet("color: #555555;")
        footer.addStretch()
        footer.addWidget(self.last_update_label)
        layout.addLayout(footer)
        
        self.setLayout(layout)
    
    def refresh(self):
        """Refresh dashboard with current data"""
        try:
            results = self.bridge.get_latest_alerts(limit=100)
            stats = self.bridge.get_stats()
            
            # Count by priority
            total = critical = high = medium = low = 0
            alerts_data = []
            
            for result in results:
                for alert in result.alerts:
                    total += 1
                    p = alert.priority.lower()
                    
                    if "critical" in p:
                        critical += 1
                        priority = "critical"
                    elif "high" in p:
                        high += 1
                        priority = "high"
                    elif "medium" in p:
                        medium += 1
                        priority = "medium"
                    else:
                        low += 1
                        priority = "low"
                    
                    # Collect alert data for timeline
                    alerts_data.append({
                        "batch_id": result.batch_id,
                        "classification": alert.classification,
                        "priority": priority,
                        "source_ip": getattr(alert, "source_ip", "") or "",
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
            
            # Calculate trends (difference from last refresh)
            trends = {
                "total": total - self._last_counts["total"],
                "critical": critical - self._last_counts["critical"],
                "high": high - self._last_counts["high"],
                "medium": medium - self._last_counts["medium"],
                "low": low - self._last_counts["low"]
            }
            
            # Update last counts
            self._last_counts = {
                "total": total, "critical": critical, 
                "high": high, "medium": medium, "low": low
            }
            
            # Update Threat Level Banner (Primary Hierarchy)
            self.threat_banner.set_threat_level(critical, high, medium, total)
            
            # Update Metric Cards with trends
            self.total_card.set_value(total, trends["total"])
            self.critical_card.set_value(critical, trends["critical"])
            self.high_card.set_value(high, trends["high"])
            self.medium_card.set_value(medium, trends["medium"])
            self.low_card.set_value(low, trends["low"])
            
            # Update Recent Alerts Timeline (with results count for benign feedback)
            results_count = stats.get("results_stored", 0)
            self.alerts_timeline.update_alerts(alerts_data, results_count)
            
            # Update System Health Grid
            self._update_system_health()
            
            # Update test compatibility status text
            self._update_status_text(stats)
            
            # Update footer
            self.last_update_label.setText(
                f"Last updated: {datetime.now().strftime('%H:%M:%S')}"
            )
            
        except Exception as e:
            self._status_text = f"Error: {str(e)[:30]}"
            self._empty_state_text = "Unable to load data"
            self.last_update_label.setText(f"Error: {str(e)[:40]}")
    
    def _update_status_text(self, stats: dict):
        """Update status text fields for test compatibility"""
        # Determine status based on system state
        pipeline_loaded = stats.get("pipeline_loaded", False)
        running = stats.get("running", False)
        shutdown = stats.get("shutdown_flag", False)
        sources = stats.get("sources_count", 0)
        dropped = stats.get("dropped_count", 0)
        dedup = stats.get("deduplication", {})
        suppressed = dedup.get("suppressed_count", 0)
        security = stats.get("security", {})
        
        if not pipeline_loaded:
            self._status_text = "Inactive"
            self._empty_state_text = "Pipeline inactive"
        elif shutdown:
            self._status_text = "Stopped"
            self._empty_state_text = "Ingestion stopped"
        elif running and sources > 0:
            status_parts = ["Active"]
            if dropped > 0:
                status_parts.append(f"Dropped: {dropped}")
            if suppressed > 0:
                status_parts.append(f"Suppressed: {suppressed}")
            if security.get("strict_model_integrity"):
                status_parts.append("Strict integrity")
            if security.get("online_enrichment_enabled"):
                status_parts.append("Online enrichment")
            self._status_text = " • ".join(status_parts)
            self._empty_state_text = ""
        elif sources > 0:
            self._status_text = "Configured"
            self._empty_state_text = ""
        else:
            self._status_text = "Not Started"
            self._empty_state_text = "No log sources configured"
    
    def _update_system_health(self):
        """Update system health indicators using centralized state mappings"""
        try:
            stats = self.bridge.get_stats()
            
            # Pipeline status
            pipeline_state = get_pipeline_state(stats.get("pipeline_loaded", False))
            pipeline_cfg = PIPELINE_STATES[pipeline_state]
            self.health_grid.update_status(
                "pipeline", pipeline_state, pipeline_cfg.label, pipeline_cfg.color
            )
            
            # Ingestion status
            running = stats.get("running", False)
            sources = stats.get("sources_count", 0)
            shutdown = stats.get("shutdown_flag", False)
            ingestion_state = get_ingestion_state(running, sources, shutdown)
            ingestion_cfg = INGESTION_STATES[ingestion_state]
            ingestion_label = format_ingestion_label(ingestion_state, sources)
            self.health_grid.update_status(
                "ingestion", ingestion_state, ingestion_label, ingestion_cfg.color
            )
            
            # Governance status
            permission_check = stats.get("permission_check", {})
            has_permission = permission_check.get("has_permission", True)
            governance_state = get_governance_state(shutdown, has_permission)
            governance_cfg = GOVERNANCE_STATES[governance_state]
            self.health_grid.update_status(
                "governance", governance_state, governance_cfg.label, governance_cfg.color
            )
                
        except Exception:
            pass
    
    def _manual_refresh(self):
        """Manual refresh with visual feedback"""
        self.quick_actions.set_refreshing(True)
        self.refresh()
        QTimer.singleShot(500, lambda: self.quick_actions.set_refreshing(False))
    
    def _upload_logs(self):
        """Upload and analyze log files with responsive UI (async via worker thread)"""
        # Prevent overlapping uploads
        if self._worker is not None and self._worker.isRunning():
            return
        
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Log Files", "",
            "Log Files (*.json *.jsonl *.csv *.tsv *.log *.syslog *.txt *.evtx);;JSON (*.json *.jsonl);;CSV/TSV (*.csv *.tsv);;Text Logs (*.log *.syslog *.txt);;Windows EVTX (*.evtx);;All (*.*)"
        )
        
        if not files:
            return
        
        # Show progress bar
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(files))
        self.progress_bar.setValue(0)
        
        # Update status to indicate processing
        self._status_text = f"Processing {len(files)} file(s)..."
        self.last_update_label.setText("Processing files...")
        
        # Create and start worker thread
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
        self.refresh()
        self._status_text = f"Processed {success_count}/{total_count} file(s)"
        self.last_update_label.setText(
            f"Processed {success_count}/{total_count} files at {datetime.now().strftime('%H:%M:%S')}"
        )
    
    def _on_worker_finished(self):
        """Clean up worker reference and hide progress bar after a short delay."""
        QTimer.singleShot(1000, self._hide_progress)
        self._worker = None
    
    def _hide_progress(self):
        self.progress_bar.setVisible(False)
