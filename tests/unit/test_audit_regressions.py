"""Regression tests for bugs found in the project audit."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from soc_copilot.core.base import ParsedRecord
from soc_copilot.phase4.controller.app_controller import AppController
from soc_copilot.pipeline import AnalysisStats, SOCCopilot
from soc_copilot.security.model_integrity import (
    load_manifest,
    save_manifest,
    update_manifest,
)
from soc_copilot.security.network import is_internal_ip


# ---------------------------------------------------------------------------
# network.is_internal_ip (domains must not be treated as internal)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["10.0.0.1", "192.168.1.22", "127.0.0.1", "::1"])
def test_private_ips_are_internal(value):
    assert is_internal_ip(value) is True


@pytest.mark.parametrize("value", ["8.8.8.8", "example.com", "", None, "not-an-ip"])
def test_public_ips_and_domains_are_not_internal(value):
    assert is_internal_ip(value) is False


# ---------------------------------------------------------------------------
# SOCCopilot.analyze_records keeps record/row alignment when rows are dropped
# ---------------------------------------------------------------------------

class _EchoAnalysis:
    """Analysis stub that returns the context it was given."""

    def analyze(self, vector, context):
        return SimpleNamespace(alert=None, source_context=context)


def test_analyze_records_maps_rows_to_correct_record_after_drops():
    copilot = SOCCopilot()
    copilot._loaded = True
    copilot._feature_order = []
    copilot._analysis = _EchoAnalysis()

    records = [
        ParsedRecord(timestamp="2026-01-18T02:56:01Z",
                     raw={"timestamp": "2026-01-18T02:56:01Z", "src_ip": "1.1.1.1"}),
        # No timestamp -> dropped by preprocessing
        ParsedRecord(timestamp="", raw={"src_ip": "2.2.2.2"}),
        ParsedRecord(timestamp="2026-01-18T02:58:01Z",
                     raw={"timestamp": "2026-01-18T02:58:01Z", "src_ip": "3.3.3.3"}),
    ]

    results, _ = copilot.analyze_records(records)

    assert [r.source_context["src_ip"] for r in results] == ["1.1.1.1", "3.3.3.3"]


# ---------------------------------------------------------------------------
# AppController
# ---------------------------------------------------------------------------

def _controller_with_results(results, alerts=()):
    controller = AppController("unused")
    stats = AnalysisStats()
    stats.total_records = len(results)
    stats.processed_records = len(results)
    controller._pipeline = Mock()
    controller._analyze_lines = Mock(return_value=(list(results), list(alerts), stats))
    return controller


def _ml_result(line_index, classification, src_ip):
    return SimpleNamespace(
        ensemble_result=SimpleNamespace(
            classification=classification,
            class_confidence=0.9,
            risk_level=SimpleNamespace(value="Low"),
        ),
        requires_alert=False,
        source_context={"line_index": line_index, "src_ip": src_ip},
    )


def test_log_summaries_use_line_index_not_list_position():
    # Line 1 produced no ML result; line 2's result must not shift onto line 1.
    controller = _controller_with_results([
        _ml_result(0, "Benign", "1.1.1.1"),
        _ml_result(2, "DDoS", "3.3.3.3"),
    ])

    result = controller.process_batch(
        [{"raw_line": "a"}, {"raw_line": "b"}, {"raw_line": "c"}]
    )

    assert [(log.classification, log.source_ip) for log in result.logs] == [
        ("Benign", "1.1.1.1"),
        ("Benign", None),
        ("DDoS", "3.3.3.3"),
    ]


def test_rule_alerts_use_ml_priority_labels_and_count_correctly():
    controller = _controller_with_results([])
    lines = [
        "2026-01-18 02:56:01 LoginAttempt user=admin ip=45.67.89.101 success=false attempts=23",
        "2026-01-18 02:49:12 FileExecution host=server-02 file=payload.exe",
        "2026-01-18 02:58:11 DataTransfer source=srv destination=185.220.101.45 size=900MB",
    ]

    result = controller.process_batch([{"raw_line": line} for line in lines])

    by_class = {a.classification: a.priority for a in result.alerts}
    assert by_class == {
        "BruteForce": "P0-Critical",
        "Malware": "P0-Critical",
        "Exfiltration": "P1-High",
    }
    assert result.stats.alerts_generated == len(result.alerts) == 3


def test_rule_alerts_survive_ml_pipeline_failure():
    controller = AppController("unused")
    controller._pipeline = Mock()
    controller._analyze_lines = Mock(side_effect=RuntimeError("boom"))

    result = controller.process_batch([{
        "raw_line": "2026-01-18 02:56:01 LoginAttempt user=admin ip=45.67.89.101 attempts=23"
    }])

    assert result is not None
    assert [a.classification for a in result.alerts] == ["BruteForce"]
    assert controller.get_stats()["dropped_count"] == 1


def test_sources_count_does_not_grow_per_batch():
    controller = _controller_with_results([])
    for _ in range(3):
        controller.process_batch([{
            "raw_line": "2026-01-18 02:56:01 LoginAttempt user=a ip=45.67.89.101 attempts=9"
        }])

    assert controller.get_stats()["sources_count"] == 1


# ---------------------------------------------------------------------------
# Model manifest updates after training
# ---------------------------------------------------------------------------

def test_update_manifest_only_rehashes_given_files(tmp_path):
    (tmp_path / "a.joblib").write_bytes(b"a1")
    (tmp_path / "b.joblib").write_bytes(b"b1")
    save_manifest(tmp_path, {"a.joblib": "old-a", "b.joblib": "old-b"})

    update_manifest(tmp_path, ["a.joblib"])

    manifest = load_manifest(tmp_path)
    assert manifest["a.joblib"] != "old-a"
    assert manifest["b.joblib"] == "old-b"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_cli_system_logs_toggle_updates_config(tmp_path, monkeypatch):
    from soc_copilot import cli

    config_dir = tmp_path / "config" / "ingestion"
    config_dir.mkdir(parents=True)
    (config_dir / "system_logs.yaml").write_text("enabled: true\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "SystemLogConfig", Mock())

    args = cli.setup_parser().parse_args(["system-logs", "disable", "--actor", "test"])
    assert cli.cmd_system_logs(args) == 0

    assert "enabled: false" in (config_dir / "system_logs.yaml").read_text()
