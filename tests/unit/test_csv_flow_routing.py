"""CSV uploads must reach the ML pipeline (flow routing on CSV columns).

The bridge turns a CSV row into "key=value,..." text for ``raw_line`` but
also passes the parsed columns; routing must use the columns, while
``raw_line`` (rules, text model, All Logs) stays unchanged.
"""

import csv
import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from soc_copilot.phase4.controller.app_controller import AppController, _normalize_flow_key
from soc_copilot.phase4.ui.controller_bridge import ControllerBridge
from soc_copilot.pipeline import AnalysisStats, SOCCopilot

FEATURE_ORDER = Path(__file__).resolve().parents[2] / "data" / "models" / "feature_order.json"
FEATURES = json.loads(FEATURE_ORDER.read_text(encoding="utf-8"))["feature_names"]


@pytest.fixture()
def controller(tmp_path):
    c = AppController(str(tmp_path / "models"))
    c._text_log_classifier = None
    c._flow_feature_names = {_normalize_flow_key(n) for n in FEATURES}
    c._pipeline = Mock()
    c._routed = []

    def analyze_file(path, on_stage=None):
        c._routed = [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines()]
        stats = AnalysisStats()
        stats.total_records = len(c._routed)
        return [], [], stats

    c._pipeline.analyze_file.side_effect = analyze_file
    return c


def _csv_row(i=0):
    row = {"timestamp": "2026-10-09T04:00:00Z", "src_ip": "10.20.30.12", "dst_ip": "198.18.44.9"}
    row.update({name: str(n + i) for n, name in enumerate(FEATURES)})
    row["flow_bytes/s"] = "Infinity"
    row["fwd_packet_length_mean"] = "12.5"
    return row


def _bridge_record(row):
    """What ControllerBridge._parse_csv produces for one row."""
    return {"raw_line": ",".join(f"{k}={v}" for k, v in row.items()), **row}


class TestControllerRouting:
    def test_csv_columns_route_to_ml(self, controller):
        controller.process_batch([_bridge_record(_csv_row())])
        assert controller._pipeline.analyze_file.call_count == 1
        assert len(controller._routed) == 1

    def test_numeric_strings_become_numbers(self, controller):
        controller.process_batch([_bridge_record(_csv_row())])
        routed = controller._routed[0]
        assert routed["destination_port"] == 0 and isinstance(routed["destination_port"], int)
        assert routed["fwd_packet_length_mean"] == 12.5
        assert routed["src_ip"] == "10.20.30.12"  # not numeric, kept as text
        assert routed["_line_index"] == 0

    def test_raw_line_unchanged_for_logs_and_rules(self, controller):
        record = _bridge_record(_csv_row())
        result = controller.process_batch([record])
        assert result.logs[0].raw_log == record["raw_line"]

    def test_non_flow_csv_not_routed(self, controller):
        row = {"timestamp": "2026-10-09T04:31:12Z", "src_ip": "10.20.30.17",
               "dst_port": "443", "bytes": "8421", "action": "ALLOW"}
        controller.process_batch([_bridge_record(row)])
        assert controller._pipeline.analyze_file.call_count == 0

    def test_plain_text_records_still_use_raw_line(self, controller):
        line = json.dumps({name: n for n, name in enumerate(FEATURES)})
        controller.process_batch([{"raw_line": line}])
        assert len(controller._routed) == 1

    def test_mixed_batch_keeps_line_indexes(self, controller):
        text = {"raw_line": "Jan 18 02:56:01 host sshd[1]: Accepted publickey for a from 10.0.0.1 port 22 ssh2"}
        controller.process_batch([text, _bridge_record(_csv_row()), _bridge_record(_csv_row(1))])
        assert [r["_line_index"] for r in controller._routed] == [1, 2]


class TestStructuredFields:
    def test_conversion(self):
        fields = AppController._structured_fields(
            {"raw_line": "x", "a": " 7 ", "b": "1.5", "c": "10.0.0.1", "d": 3, None: "extra"}
        )
        assert fields == {"a": 7, "b": 1.5, "c": "10.0.0.1", "d": 3}

    @pytest.mark.parametrize("record", [None, "text", {}, {"raw_line": "only"}])
    def test_nothing_structured(self, record):
        assert AppController._structured_fields(record) is None


class TestBridgeCsvEndToEnd:
    def test_uploaded_csv_reaches_ml(self, controller, tmp_path):
        path = tmp_path / "flows.csv"
        rows = [_csv_row(i) for i in range(3)]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        bridge = ControllerBridge.__new__(ControllerBridge)
        records = ControllerBridge._parse_file(bridge, path)
        controller.process_batch(records)
        assert len(controller._routed) == 3


def test_vector_replaces_infinite_values_with_zero():
    copilot = object.__new__(SOCCopilot)
    copilot._feature_order = ["flow_bytes/s", "flow_packets/s", "flow_duration"]
    copilot._preprocessing = Mock(spec=[])
    row = pd.Series({"flow_bytes/s": float("inf"), "flow_packets/s": "-Infinity", "flow_duration": 5})
    assert list(copilot._build_feature_vector(row)) == [0.0, 0.0, 5.0]
    assert np.isfinite(copilot._build_feature_vector(row)).all()
