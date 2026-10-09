"""Desktop notifications for high-priority alerts (UX-8).

``AlertNotifier`` watches the bridge's ``resultsUpdated`` signal and shows
a system-tray balloon for every *new* alert whose priority is enabled
(P0-Critical and P1-High by default). Alerts already stored when the app
starts are treated as seen, so launching never produces a burst.

Preferences (mute + per-priority switches) persist in QSettings.
"""

from PyQt6.QtCore import QObject, QSettings, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

NOTIFY_PRIORITIES = ("P0-Critical", "P1-High")

_KEY_MUTED = "notifications/muted"
_KEY_PRIORITY = "notifications/{}"
_MAX_LISTED = 3  # alerts named in a combined balloon


def _truthy(value) -> bool:
    return str(value).lower() in ("true", "1", "yes", "on")


def _alert_key(result, index: int, alert) -> str:
    """Same identity rule as the alerts table: alert_id, else position."""
    alert_id = getattr(alert, "alert_id", None)
    return str(alert_id) if alert_id else f"{result.batch_id}#{index}"


class AlertNotifier(QObject):
    """Tray icon + balloon notifications for new P0/P1 alerts."""

    open_alerts_requested = pyqtSignal()   # balloon clicked
    show_window_requested = pyqtSignal()   # tray icon / menu
    preferences_changed = pyqtSignal()     # mute or priority toggled
    notified = pyqtSignal(list)            # alert dicts just announced

    def __init__(self, bridge, icon: QIcon | None = None,
                 settings: QSettings | None = None, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._settings = settings or QSettings("SOC Copilot", "SOC Copilot")
        self._muted = _truthy(self._settings.value(_KEY_MUTED, False))
        self._enabled = {
            p: _truthy(self._settings.value(_KEY_PRIORITY.format(p), True))
            for p in NOTIFY_PRIORITIES
        }
        self._seen: set[str] = set()
        self._seed_seen()

        self.tray = QSystemTrayIcon(icon or QIcon(), self)
        self.tray.setToolTip("SOC Copilot")
        self.tray.messageClicked.connect(self.open_alerts_requested.emit)
        self.tray.activated.connect(self._on_tray_activated)
        self._build_menu()
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

        bridge.resultsUpdated.connect(self.check_new_alerts)

    # ----- preferences --------------------------------------------------

    @property
    def muted(self) -> bool:
        return self._muted

    def set_muted(self, muted: bool) -> None:
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self._settings.setValue(_KEY_MUTED, muted)
        self._mute_action.setChecked(muted)
        self.preferences_changed.emit()

    def priority_enabled(self, priority: str) -> bool:
        return self._enabled.get(priority, False)

    def set_priority_enabled(self, priority: str, enabled: bool) -> None:
        if priority not in self._enabled:
            raise ValueError(f"Unsupported notification priority: {priority}")
        enabled = bool(enabled)
        if self._enabled[priority] == enabled:
            return
        self._enabled[priority] = enabled
        self._settings.setValue(_KEY_PRIORITY.format(priority), enabled)
        self.preferences_changed.emit()

    # ----- tray ------------------------------------------------------------

    def _build_menu(self) -> None:
        menu = QMenu()
        show = QAction("Show SOC Copilot", menu)
        show.triggered.connect(self.show_window_requested.emit)
        menu.addAction(show)
        self._mute_action = QAction("Mute notifications", menu)
        self._mute_action.setCheckable(True)
        self._mute_action.setChecked(self._muted)
        self._mute_action.toggled.connect(self.set_muted)
        menu.addAction(self._mute_action)
        self._menu = menu  # QSystemTrayIcon does not take ownership
        self.tray.setContextMenu(menu)

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window_requested.emit()

    def set_icon(self, icon: QIcon) -> None:
        self.tray.setIcon(icon)

    # ----- detection -------------------------------------------------------

    def _iter_alerts(self):
        try:
            results = self.bridge.get_all_results()
        except Exception:
            return
        if not isinstance(results, list):
            return
        for result in results:
            for i, alert in enumerate(getattr(result, "alerts", []) or []):
                yield _alert_key(result, i, alert), result, alert

    def _seed_seen(self) -> None:
        self._seen = {key for key, _r, _a in self._iter_alerts()}

    def check_new_alerts(self) -> list:
        """Announce unseen enabled-priority alerts; return what was shown."""
        fresh = []
        for key, result, alert in self._iter_alerts():
            if key in self._seen:
                continue
            self._seen.add(key)
            if self._enabled.get(getattr(alert, "priority", ""), False):
                fresh.append({
                    "key": key,
                    "batch_id": result.batch_id,
                    "priority": alert.priority,
                    "classification": alert.classification,
                    "source_ip": getattr(alert, "source_ip", None) or "N/A",
                })
        if not fresh or self._muted:
            return []
        title, body, icon = self.format_message(fresh)
        self._show(title, body, icon)
        self.notified.emit(fresh)
        return fresh

    @staticmethod
    def format_message(alerts: list) -> tuple:
        """(title, body, icon) for one or several new alerts."""
        critical = any(a["priority"] == "P0-Critical" for a in alerts)
        icon = (QSystemTrayIcon.MessageIcon.Critical if critical
                else QSystemTrayIcon.MessageIcon.Warning)
        if len(alerts) == 1:
            a = alerts[0]
            return (f"{a['priority']}: {a['classification']}",
                    f"Source {a['source_ip']} — click to open Alerts", icon)
        # Most severe first so the listed lines are the important ones
        ordered = sorted(alerts, key=lambda a: a["priority"])
        lines = [f"{a['priority']}: {a['classification']} ({a['source_ip']})"
                 for a in ordered[:_MAX_LISTED]]
        extra = len(alerts) - _MAX_LISTED
        if extra > 0:
            lines.append(f"…and {extra} more")
        return (f"{len(alerts)} new high-priority alerts", "\n".join(lines), icon)

    def _show(self, title: str, body: str, icon) -> None:
        self.tray.showMessage(title, body, icon, 8000)
