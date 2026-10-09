"""Main window: sidebar navigation, header status chips, page stack.

System status is shown once, in the header chips; the bottom status bar
only carries short transient messages ("Exported 6 alerts").
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QStatusBar, QMenuBar, QMenu,
    QStackedWidget, QPushButton, QFrame, QLabel, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF, QFont
from PyQt6.QtCore import QPointF

from .dashboard_v2 import Dashboard
from .alerts_view import AlertsView
from .alert_details import AlertDetailsPanel
from .assistant_panel import AssistantPanel
from .controller_bridge import ControllerBridge
from .config_panel import ConfigPanel
from .about_dialog import AboutDialog
from .system_status_bar import SystemStatusBar, PermissionBanner, KillSwitchBanner
from .all_logs_view import AllLogsView
from .report_drawer import ReportDrawer
from .notifications import AlertNotifier
from .theme import ThemeManager, set_role
from .motion import fade_in
from .icons import icon_label, set_icon


def _palette():
    return ThemeManager.instance().palette


class NavButton(QPushButton):
    """Sidebar navigation item: icon, label and a count badge."""

    def __init__(self, icon: str, text: str, index: int):
        # Leading spaces = gap between icon and label (QSS has no icon gap)
        super().__init__(f"  {text}")
        self.label = text
        self.index = index
        self.icon_name = icon
        self._badge_count = 0
        self._badge_tone = "neutral"
        self.setCheckable(True)
        self.setFixedHeight(38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        inner = QHBoxLayout(self)
        inner.setContentsMargins(0, 0, 10, 0)
        inner.addStretch()
        self.badge = QLabel("")
        self.badge.setProperty("role", "navBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setFixedHeight(18)
        self.badge.setMinimumWidth(22)
        self.badge.hide()
        self.badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        inner.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignVCenter)

        self._update_style(False)
        ThemeManager.instance().theme_changed.connect(self._on_theme_change)

    def _on_theme_change(self):
        self._update_style(self.isChecked())

    def _update_style(self, active: bool):
        p = _palette()
        set_icon(self, self.icon_name, "accent" if active else "text_muted", 18)
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {p.surface_alt};
                    color: {p.text};
                    border: none;
                    border-left: 3px solid {p.accent};
                    border-radius: 6px;
                    padding: 0px 12px 0px 11px;
                    font-size: 13px;
                    font-weight: 600;
                    text-align: left;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {p.text_muted};
                    border: none;
                    border-radius: 6px;
                    padding: 0px 12px 0px 14px;
                    font-size: 13px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background-color: {p.surface};
                    color: {p.text};
                }}
            """)

    def setActive(self, active: bool):
        self.setChecked(active)
        self._update_style(active)

    def set_badge(self, count: int, color: str | None = None):
        """Show ``count`` in a pill; red when ``color`` is the critical colour."""
        self._badge_count = count
        critical = color is not None and color == _palette().sev_critical
        self._badge_tone = "critical" if critical else "neutral"
        if count > 0:
            self.badge.setText("99+" if count > 99 else str(count))
            self.badge.setProperty("tone", self._badge_tone)
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
            self.badge.show()
        else:
            self.badge.hide()


class Sidebar(QFrame):
    """Navigation sidebar: brand, one-line status, nav items."""

    nav_changed = pyqtSignal(int)

    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self._init_ui()
        self._start_polling()

    def _init_ui(self):
        self.setFixedWidth(220)
        self._apply_theme()

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 18, 12, 14)
        layout.setSpacing(4)

        # Brand
        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 0)
        brand.setSpacing(10)
        brand.addWidget(icon_label("shield", "accent", 22))
        title = QLabel("SOC Copilot")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        self._title_label = title
        brand.addWidget(title)
        beta = QLabel("BETA")
        set_role(beta, "pill")
        self._beta_badge = beta
        brand.addWidget(beta, 0, Qt.AlignmentFlag.AlignVCenter)
        brand.addStretch()
        layout.addLayout(brand)
        layout.addSpacing(14)

        # One-line status (details in the tooltip and the header chips)
        status_frame = QFrame()
        status_frame.setObjectName("sidebarStatusFrame")
        self._status_frame = status_frame
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(10, 8, 10, 8)
        status_layout.setSpacing(8)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        status_layout.addWidget(self.status_dot)
        self.status_indicator = QLabel("Initializing...")
        self.status_indicator.setStyleSheet("font-size: 12px;")
        status_layout.addWidget(self.status_indicator, 1)
        status_frame.setLayout(status_layout)
        layout.addWidget(status_frame)
        # Kept for callers/tests; shown as the status tooltip
        self.status_detail = QLabel("Loading ML models")
        self.status_detail.hide()
        self._status_color = _palette().sev_medium
        self._style_status()

        layout.addSpacing(18)
        nav_label = QLabel("NAVIGATION")
        set_role(nav_label, "caption")
        nav_label.setContentsMargins(8, 0, 0, 4)
        self._nav_label = nav_label
        layout.addWidget(nav_label)

        self.nav_buttons = []
        nav_items = [
            ("grid", "Dashboard", 0),
            ("bell", "Alerts", 1),
            ("search", "Investigation", 2),
            ("message-square", "Assistant", 3),
            ("file-text", "All Logs", 4),
            ("settings", "Settings", 5),
        ]
        for icon, text, idx in nav_items:
            btn = NavButton(icon, text, idx)
            btn.clicked.connect(lambda checked, i=idx: self._on_nav_click(i))
            layout.addWidget(btn)
            self.nav_buttons.append(btn)
        self.nav_buttons[0].setActive(True)

        layout.addStretch()

        version_label = QLabel("v1.0.0-beta.1")
        set_role(version_label, "caption")
        version_label.setContentsMargins(8, 0, 0, 0)
        self._version_label = version_label
        layout.addWidget(version_label)

        self.setLayout(layout)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _apply_theme(self):
        """Re-apply palette-derived styles after a theme switch."""
        p = _palette()
        self.setStyleSheet(f"""
            Sidebar {{
                background-color: {p.input_bg};
                border-right: 1px solid {p.surface_alt};
            }}
        """)
        if getattr(self, "_status_frame", None) is not None:
            self._style_status()

    def _style_status(self):
        p = _palette()
        self._status_frame.setStyleSheet(f"""
            QFrame#sidebarStatusFrame {{
                background-color: {p.surface};
                border: 1px solid {p.surface_alt};
                border-radius: 6px;
            }}
        """)
        self.status_dot.setStyleSheet(
            f"background-color: {self._status_color}; border-radius: 4px;"
        )

    def _set_status(self, text: str, color: str, detail: str):
        self.status_indicator.setText(text)
        self.status_detail.setText(detail)
        self._status_color = color
        self._status_frame.setToolTip(detail)
        self._style_status()

    def _on_nav_click(self, index: int):
        for btn in self.nav_buttons:
            btn.setActive(btn.index == index)
        self.nav_changed.emit(index)

    def _start_polling(self):
        """Initial status update.

        Periodic polling removed (UX-3): MainWindow's consolidated status
        timer calls ``_update_status`` directly.
        """
        self._update_status()

    def _update_status(self):
        p = _palette()
        try:
            stats = self.bridge.get_stats()

            if stats.get("shutdown_flag"):
                self._set_status("Kill switch active", p.sev_critical,
                                 "ML processing halted")
            elif stats.get("pipeline_loaded"):
                sources = stats.get("sources_count", 0)
                results = stats.get("results_stored", 0)
                self._set_status("Online", p.success,
                                 f"{sources} sources · {results} results")
            else:
                self._set_status("Initializing...", p.sev_medium,
                                 "Loading ML models")

            # Nav badges
            alerts = self.bridge.get_latest_alerts(limit=100)
            total_alerts = sum(len(r.alerts) for r in alerts)
            critical_count = sum(
                1 for r in alerts for a in r.alerts
                if "critical" in a.priority.lower()
            )
            if critical_count > 0:
                self.nav_buttons[1].set_badge(total_alerts, p.sev_critical)
                self.nav_buttons[0].set_badge(critical_count, p.sev_critical)
            else:
                self.nav_buttons[1].set_badge(total_alerts)
                self.nav_buttons[0].set_badge(0)

        except Exception:
            self._set_status("Connection error", p.sev_critical,
                             "Status unavailable")


class MainWindow(QMainWindow):
    """Optimized SOC Copilot main window with sidebar navigation"""

    VERSION = "1.0.0-beta.1"

    def __init__(self, controller):
        super().__init__()
        self.bridge = ControllerBridge(controller)
        self._init_ui()
        self._init_menu()
        self._set_window_icon()
        self._init_notifications()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    def _init_notifications(self):
        """Tray notifications for new P0/P1 alerts (UX-8)."""
        self.notifier = AlertNotifier(
            self.bridge, icon=self.windowIcon(), parent=self
        )
        self.notifier.open_alerts_requested.connect(self._open_alerts_from_tray)
        self.notifier.show_window_requested.connect(self._bring_to_front)
        self.config_panel.attach_notifier(self.notifier)

    def _bring_to_front(self):
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _open_alerts_from_tray(self):
        self._bring_to_front()
        self._on_nav_changed(1)

    def _apply_theme(self):
        """Re-apply palette-derived styles after a theme switch."""
        self._style_menubar()
        self._set_window_icon()
        notifier = getattr(self, "notifier", None)
        if notifier is not None:
            notifier.set_icon(self.windowIcon())

    def _fit_to_screen(self, width: int, height: int):
        """Open at the preferred size, clamped to the screen's available area.

        On a scaled laptop display (e.g. 1280x720 logical at 150%) the
        preferred 1500x950 would extend past the screen edges.
        """
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            self.setGeometry(50, 50, width, height)
            return
        avail = screen.availableGeometry()
        w = min(width, avail.width() - 40)
        h = min(height, avail.height() - 40)
        self.setGeometry(
            avail.x() + (avail.width() - w) // 2,
            avail.y() + (avail.height() - h) // 2,
            w, h,
        )

    def _init_ui(self):
        self.setWindowTitle("SOC Copilot (Beta)")
        self._fit_to_screen(1500, 950)

        # Central widget
        # (base styling comes from the global stylesheet — see theme.py)
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        self.sidebar = Sidebar(self.bridge)
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        main_layout.addWidget(self.sidebar)

        # Content area
        content_area = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # System status bar at top (consolidated)
        self.system_status_bar = SystemStatusBar(self.bridge)
        self.system_status_bar.settings_requested.connect(self._open_settings_at)
        content_layout.addWidget(self.system_status_bar)

        # Banners
        self.killswitch_banner = KillSwitchBanner()
        content_layout.addWidget(self.killswitch_banner)

        permission_status = self.bridge.get_permission_status()
        if not permission_status.get("has_permission", True):
            self.permission_banner = PermissionBanner(
                "System log access requires Administrator privileges."
            )
            content_layout.addWidget(self.permission_banner)

        # Stacked widget for navigation pages
        self.page_stack = QStackedWidget()

        # Page 0: Dashboard
        self.dashboard = Dashboard(self.bridge)
        self.dashboard.navigate_to_alerts.connect(lambda: self._on_nav_changed(1))
        self.dashboard.navigate_to_alerts_filtered.connect(self._on_navigate_alerts_filtered)
        self.dashboard.navigate_to_settings.connect(lambda: self._on_nav_changed(5))
        self.dashboard.alert_selected.connect(self._on_alert_selected)
        self.page_stack.addWidget(self.dashboard)

        # Page 1: Alerts
        self.alerts_view = AlertsView(self.bridge)
        self.alerts_view.alert_selected.connect(self._on_alert_selected)
        self.alerts_view.show_logs_requested.connect(self._show_logs_for_ip)
        self.page_stack.addWidget(self.alerts_view)

        # Page 2: Investigation (Alert Details)
        self.details_panel = AlertDetailsPanel(self.bridge)
        self.details_panel.back_clicked.connect(lambda: self._on_nav_changed(1))
        # Per-IP actions shared with the alerts table (UX-7)
        self.details_panel.investigate_requested.connect(
            self.alerts_view._trigger_investigation
        )
        self.details_panel.filter_alerts_requested.connect(
            self._filter_alerts_by_ip
        )
        self.details_panel.show_logs_requested.connect(self._show_logs_for_ip)
        self.page_stack.addWidget(self.details_panel)

        # Page 3: Assistant
        self.assistant_panel = AssistantPanel()
        self.page_stack.addWidget(self.assistant_panel)

        # Page 4: All Logs
        self.all_logs_view = AllLogsView(self.bridge)
        self.page_stack.addWidget(self.all_logs_view)

        # Page 5: Settings
        self.config_panel = ConfigPanel(self.bridge)
        self.page_stack.addWidget(self.config_panel)

        # Page stack + investigation report drawer in a horizontal splitter
        self.page_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.page_splitter.addWidget(self.page_stack)

        self.report_drawer = ReportDrawer()
        self.report_drawer.retry_requested.connect(
            self.alerts_view._trigger_investigation
        )
        self.alerts_view.report_drawer = self.report_drawer
        self.page_splitter.addWidget(self.report_drawer)
        self.page_splitter.setCollapsible(1, False)
        self.page_splitter.setStretchFactor(0, 1)
        self.page_splitter.setStretchFactor(1, 0)
        self.page_splitter.setSizes([self.width(), 0])

        content_layout.addWidget(self.page_splitter, 1)  # pages get spare height
        content_area.setLayout(content_layout)

        main_layout.addWidget(content_area)
        central.setLayout(main_layout)

        # Status bar: transient messages only (status lives in the header)
        self.status_bar = QStatusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)

        # Single consolidated status timer (UX-3): sidebar status, header
        # chips and the settings panel's indicators refresh together.
        self.status_timer = QTimer(self)  # parented: must not outlive the window
        self.status_timer.timeout.connect(self._update_status_widgets)
        self.status_timer.start(5000)

        # Keyboard shortcuts
        self._setup_shortcuts()

    # Shortcuts documented in the F1 help dialog (UX-7)
    SHORTCUTS_HELP = [
        ("Ctrl+1..5", "Switch page (Dashboard / Alerts / Investigation / Logs / Settings)"),
        ("Ctrl+F or /", "Focus alerts search"),
        ("Ctrl+E", "Export alerts (CSV/JSON)"),
        ("F5", "Refresh results"),
        ("F1 or ?", "This help"),
        ("Esc", "Close report / back to Alerts"),
        ("J / K", "Next / previous alert row"),
        ("Enter", "Open selected alert details"),
        ("I", "Investigate selected alert's source IP"),
        ("A / R", "Accept / Reject feedback on selected alert"),
        ("1 / 2 / 3 / 4", "Set status New / In progress / Resolved / False positive"),
    ]

    @staticmethod
    def _typing_in_editor() -> bool:
        """True when focus is inside a text editor (guard for / and ?)."""
        from PyQt6.QtWidgets import (
            QApplication, QLineEdit, QTextEdit, QComboBox, QAbstractSpinBox,
        )
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QTextEdit, QComboBox,
                              QAbstractSpinBox))

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for navigation and actions (UX-7)."""
        from PyQt6.QtGui import QShortcut, QKeySequence
        ctx = Qt.ShortcutContext.WindowShortcut

        # Page navigation (sidebar order; Assistant has no Ctrl+N).
        # The File-menu actions show the key in their text instead of
        # setShortcut() — a duplicate binding makes the key ambiguous and
        # neither fires.
        for key, page in (
            ("Ctrl+1", 0), ("Ctrl+2", 1), ("Ctrl+3", 2),
            ("Ctrl+4", 4), ("Ctrl+5", 5), ("Ctrl+,", 5),
        ):
            sc = QShortcut(QKeySequence(key), self, context=ctx)
            sc.activated.connect(
                lambda p=page: self._on_nav_changed(p)
            )

        # Focus alerts search
        sc = QShortcut(QKeySequence("Ctrl+F"), self, context=ctx)
        sc.activated.connect(self._focus_alerts_search)

        # Refresh / export
        sc = QShortcut(QKeySequence("F5"), self, context=ctx)
        sc.activated.connect(self._on_f5)
        sc = QShortcut(QKeySequence("Ctrl+E"), self, context=ctx)
        sc.activated.connect(self._export_alerts)

        # Escape: close drawer, else leave Investigation for Alerts
        sc = QShortcut(QKeySequence("Escape"), self, context=ctx)
        sc.activated.connect(self._on_escape)

        # Help (F1 is a QShortcut; the menu item just displays it)
        sc = QShortcut(QKeySequence("F1"), self, context=ctx)
        sc.activated.connect(self._show_shortcuts_help)

    def keyPressEvent(self, event):
        """"/" → alerts search, "?" → help; editors consume these keys
        before they reach the window, so no typing guard needed here."""
        key = event.key()
        if key == Qt.Key.Key_Slash:
            self._on_nav_changed(1)
            self.alerts_view.search_box.setFocus()
            self.alerts_view.search_box.selectAll()
            return
        if key == Qt.Key.Key_Question:
            self._show_shortcuts_help()
            return
        super().keyPressEvent(event)

    def _focus_alerts_search(self):
        if self._typing_in_editor():
            return  # "/" typed into an editor stays a keystroke
        self._on_nav_changed(1)
        self.alerts_view.search_box.setFocus()
        self.alerts_view.search_box.selectAll()

    def _export_alerts(self):
        self._on_nav_changed(1)
        self.alerts_view._on_export()

    def _on_escape(self):
        if self.report_drawer.isVisible():
            self.report_drawer.close_drawer()
            return
        if self.page_stack.currentIndex() == 2:
            self._on_nav_changed(1)

    def _show_shortcuts_help(self):
        if self._typing_in_editor():
            return
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QGridLayout, QLabel,
        )
        p = _palette()
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(460)
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        heading = QLabel("Keyboard shortcuts")
        set_role(heading, "sectionTitle")
        layout.addWidget(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        for i, (key, desc) in enumerate(self.SHORTCUTS_HELP):
            k = QLabel(key)
            k.setStyleSheet(
                f"color: {p.text}; background-color: {p.surface_alt}; "
                f"border: 1px solid {p.border}; border-radius: 4px; "
                "padding: 2px 8px; font-size: 12px; font-weight: 600;"
            )
            d = QLabel(desc)
            d.setStyleSheet(f"color: {p.text_muted}; font-size: 12px;")
            grid.addWidget(k, i, 0, Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(d, i, 1)
        layout.addLayout(grid)
        dlg.setLayout(layout)
        dlg.exec()

    def _on_f5(self):
        """F5 refreshes through the bridge's result notification (UX-3)."""
        try:
            self.bridge.request_refresh()
        except Exception:
            self._refresh_current_view()
            return
        self.status_bar.showMessage("Refresh requested", 1000)

    def _refresh_current_view(self):
        """Refresh the currently active view"""
        current_index = self.page_stack.currentIndex()
        if current_index == 0:
            self.dashboard.refresh()
        elif current_index == 1:
            self.alerts_view.refresh()
        elif current_index == 4:
            self.all_logs_view.refresh()
        self.status_bar.showMessage("View refreshed", 1000)

    def _on_nav_changed(self, index: int):
        """Handle navigation changes"""
        changed = self.page_stack.currentIndex() != index
        self.page_stack.setCurrentIndex(index)
        if changed:
            fade_in(self.page_stack.currentWidget())

        # Update sidebar buttons
        for btn in self.sidebar.nav_buttons:
            btn.setActive(btn.index == index)

        # Refresh the page being shown so nothing is stale (UX-3)
        refresh = getattr(self.page_stack.widget(index), "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass

    def _on_navigate_alerts_filtered(self, priority: str):
        """Navigate to alerts with a specific priority filter"""
        # Switch to alerts page
        self._on_nav_changed(1)

        # Apply filter if alerts_view supports it
        if hasattr(self.alerts_view, 'set_priority_filter'):
            self.alerts_view.set_priority_filter(priority)

        self.status_bar.showMessage(f"Showing {priority.title()} priority alerts", 2000)

    def _open_settings_at(self, section: str):
        """Header chip clicked: open Settings scrolled to that section."""
        self._on_nav_changed(5)
        self.config_panel.show_section(section)

    def _filter_alerts_by_ip(self, ip: str):
        """Jump to Alerts filtered to an IP (UX-7)."""
        self._on_nav_changed(1)
        self.alerts_view.search_box.setText(ip)

    def _show_logs_for_ip(self, ip: str):
        """Jump to All Logs filtered to an IP (UX-7)."""
        self._on_nav_changed(4)
        setter = getattr(self.all_logs_view, "set_search_text", None)
        if callable(setter):
            setter(ip)

    def _on_alert_selected(self, batch_id: str, alert_identifier: str):
        """Handle alert selection - navigate to investigation.

        ``alert_identifier`` is the real alert_id when the row carried one,
        otherwise the classification text; ``show_alert`` tries alert_id
        first and falls back to the classification match.
        """
        try:
            self.details_panel.show_alert(
                batch_id,
                alert_classification=alert_identifier,
                alert_id=alert_identifier,
            )

            # Switch to investigation page
            self.page_stack.setCurrentIndex(2)
            self.sidebar._on_nav_click(2)

            # Update assistant
            result = self.bridge.get_alert_by_id(batch_id)
            if result:
                for alert in result.alerts:
                    if getattr(alert, "alert_id", None) == alert_identifier:
                        self.assistant_panel.explain_alert(alert)
                        break
                else:
                    for alert in result.alerts:
                        if alert.classification == alert_identifier:
                            self.assistant_panel.explain_alert(alert)
                            break

            self.status_bar.showMessage(f"Investigating: {alert_identifier}", 3000)
        except Exception as e:
            self.status_bar.showMessage(f"Error: {str(e)}", 3000)

    def _update_status_widgets(self):
        """Consolidated periodic status refresh (one 5 s timer)."""
        self.sidebar._update_status()
        self.system_status_bar.refresh()
        self.config_panel.refresh()

    def _init_menu(self):
        """Initialize menu bar"""
        menubar = self.menuBar()
        self._style_menubar()

        # File menu
        file_menu = menubar.addMenu("&File")

        # Quick nav actions
        nav_dash = QAction("Dashboard\tCtrl+1", self)
        nav_dash.triggered.connect(lambda: self._on_nav_changed(0))
        file_menu.addAction(nav_dash)

        nav_alerts = QAction("Alerts\tCtrl+2", self)
        nav_alerts.triggered.connect(lambda: self._on_nav_changed(1))
        file_menu.addAction(nav_alerts)

        nav_logs = QAction("All Logs\tCtrl+4", self)
        nav_logs.triggered.connect(lambda: self._on_nav_changed(4))
        file_menu.addAction(nav_logs)

        nav_settings = QAction("Settings\tCtrl+,", self)
        nav_settings.triggered.connect(lambda: self._on_nav_changed(5))
        file_menu.addAction(nav_settings)

        file_menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        shortcuts_action = QAction("&Keyboard shortcuts (F1)", self)
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        help_menu.addAction(shortcuts_action)
        about_action = QAction("&About SOC Copilot", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _style_menubar(self):
        """Style the menu bar from the current palette."""
        p = _palette()
        self.menuBar().setStyleSheet(f"""
            QMenuBar {{
                background-color: {p.input_bg};
                color: {p.text};
                padding: 2px;
            }}
            QMenuBar::item {{ padding: 5px 10px; }}
            QMenuBar::item:selected {{ background-color: {p.surface_alt}; }}
            QMenu {{
                background-color: {p.input_bg};
                color: {p.text};
                border: 1px solid {p.surface_alt};
            }}
            QMenu::item:selected {{
                background-color: {p.accent};
                color: {p.text_inverse};
            }}
        """)

    def _set_window_icon(self):
        """Set window icon"""
        icon = QIcon(self._create_icon_pixmap())
        self.setWindowIcon(icon)

    def _create_icon_pixmap(self) -> QPixmap:
        """Create shield icon"""
        size = 64
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        painter.setPen(QPen(QColor(_palette().accent), 2))
        painter.setBrush(QColor(_palette().input_bg))

        x, y = 4, 4
        s = size - 8

        shield_points = [
            QPointF(x + s/2, y),
            QPointF(x + s, y + s*0.3),
            QPointF(x + s, y + s*0.6),
            QPointF(x + s/2, y + s),
            QPointF(x, y + s*0.6),
            QPointF(x, y + s*0.3),
        ]
        painter.drawPolygon(QPolygonF(shield_points))

        painter.setPen(QPen(QColor(_palette().accent), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(int(x + s*0.3), int(y + s*0.25), int(s*0.4), int(s*0.4))
        painter.drawLine(
            int(x + s*0.6), int(y + s*0.55),
            int(x + s*0.75), int(y + s*0.7)
        )

        painter.end()
        return pixmap

    def _show_about(self):
        """Show about dialog"""
        dialog = AboutDialog(self)
        dialog.exec()
