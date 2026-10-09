"""Tests for UX-9: clickable header status chips."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QApplication

from soc_copilot.mcp.provider_registry import ProviderState, ProviderStatus
from soc_copilot.phase4.ui.status_chips import (
    CHIP_ORDER, StatusChipBar, chip_states,
)
from tests.qt_helpers import destroy


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _stats(online=False, shutdown=False, integrity=None, strict=False):
    return {
        "shutdown_flag": shutdown,
        "security": {
            "online_enrichment_enabled": online,
            "strict_model_integrity": strict,
            "model_integrity": integrity or {},
        },
    }


def _provider(key, state):
    return ProviderStatus(key=key, display_name=key.title(), agent="A",
                          state=state)


class TestChipStates:
    def test_all_chips_present(self):
        assert set(chip_states({})) == set(CHIP_ORDER)

    def test_offline_defaults(self):
        s = chip_states(_stats())
        assert s["enrichment"][:2] == ("neutral", "Enrichment: Offline")
        assert s["kill_switch"][:2] == ("good", "Kill switch: Off")
        assert s["integrity"][:2] == ("info", "Integrity: Dev mode")
        assert s["providers"][:2] == ("neutral", "Providers: Off")
        assert s["drift"][:2] == ("neutral", "Drift: N/A")

    def test_kill_switch_on(self):
        assert chip_states(_stats(shutdown=True))["kill_switch"][:2] == (
            "bad", "Kill switch: ON")

    def test_integrity(self):
        ok = chip_states(_stats(integrity={"is_valid": True,
                                           "verified_files": ["a", "b"]},
                                strict=True))["integrity"]
        assert ok[:2] == ("good", "Integrity: Strict")
        assert "2 model files" in ok[2]
        bad = chip_states(_stats(integrity={"is_valid": False,
                                            "error": "hash mismatch"}))["integrity"]
        assert bad[:2] == ("bad", "Integrity: Failed")
        assert "hash mismatch" in bad[2]

    def test_providers_online(self):
        providers = [
            _provider("whois", ProviderState.AVAILABLE),
            _provider("shodan", ProviderState.MISSING_KEY),
        ]
        s = chip_states(_stats(online=True), providers=providers)
        assert s["enrichment"][0] == "warn"
        assert s["providers"][:2] == ("good", "Providers: 1/2")
        assert "Shodan: Missing key" in s["providers"][2]

    def test_providers_offline_warns(self):
        providers = [_provider("whois", ProviderState.OFFLINE)]
        s = chip_states(_stats(online=True), providers=providers)
        assert s["providers"][:2] == ("warn", "Providers: 0/1")

    @pytest.mark.parametrize("level,tone", [
        ("NONE", "good"), ("LOW", "good"), ("MODERATE", "warn"),
        ("HIGH", "bad"), ("CRITICAL", "bad"),
    ])
    def test_drift_levels(self, level, tone):
        s = chip_states({}, drift={"available": True, "level": level})
        assert s["drift"][0] == tone
        assert s["drift"][1] == f"Drift: {level.title()}"

    def test_drift_collecting(self):
        s = chip_states({}, drift={"available": True, "level": None})
        assert s["drift"][:2] == ("info", "Drift: Collecting")


class TestChipBar:
    def test_click_emits_chip_name(self, qapp):
        bar = StatusChipBar()
        clicked = []
        bar.chip_clicked.connect(clicked.append)
        bar.chips["drift"].click()
        assert clicked == ["drift"]
        destroy(bar)

    def test_update_states_sets_text_and_tooltip(self, qapp):
        bar = StatusChipBar()
        bar.update_states(chip_states(_stats(shutdown=True)))
        chip = bar.chips["kill_switch"]
        assert chip.text() == "Kill switch: ON"
        assert chip.tone == "bad"
        assert "Click to open Settings" in chip.toolTip()
        destroy(bar)


class TestStatusBarIntegration:
    def _bridge(self, stats):
        bridge = Mock()
        bridge.get_stats.return_value = stats
        bridge.get_drift_status.return_value = {"available": True,
                                                "level": "MODERATE"}
        bridge.get_provider_statuses.return_value = []
        return bridge

    def test_status_bar_shows_chips(self, qapp):
        from soc_copilot.phase4.ui.system_status_bar import SystemStatusBar
        bar = SystemStatusBar(self._bridge(_stats(shutdown=True)))
        chips = bar.chip_bar.chips
        assert chips["kill_switch"].text() == "Kill switch: ON"
        assert chips["drift"].text() == "Drift: Moderate"
        destroy(bar)

    def test_status_bar_relays_click(self, qapp):
        from soc_copilot.phase4.ui.system_status_bar import SystemStatusBar
        bar = SystemStatusBar(self._bridge(_stats()))
        got = []
        bar.settings_requested.connect(got.append)
        bar.chip_bar.chips["providers"].click()
        assert got == ["providers"]
        destroy(bar)

    def test_probe_result_overrides_local_provider_status(self, qapp):
        from soc_copilot.phase4.ui.system_status_bar import SystemStatusBar
        bar = SystemStatusBar(self._bridge(_stats(online=True)))
        bar.set_probed_providers([_provider("whois", ProviderState.OFFLINE)])
        assert bar.chip_bar.chips["providers"].tone == "warn"
        destroy(bar)


class TestMainWindowIntegration:
    def test_chip_click_opens_settings_section(self, qapp, tmp_path):
        from soc_copilot.phase4.controller.app_controller import AppController
        from soc_copilot.phase4.ui.main_window import MainWindow
        controller = AppController(str(tmp_path / "models"))
        controller._pipeline = Mock()
        w = MainWindow(controller)
        shown = []
        w.config_panel.show_section = shown.append
        w.system_status_bar.chip_bar.chips["drift"].click()
        assert w.page_stack.currentIndex() == 5
        assert shown == ["drift"]
        destroy(w)

    def test_show_section_accepts_all_chips(self, qapp, tmp_path):
        from soc_copilot.phase4.ui.config_panel import ConfigPanel
        panel = ConfigPanel(bridge=None)
        for name in CHIP_ORDER:
            panel.show_section(name)  # must not raise
        panel.show_section("unknown")
        destroy(panel)
