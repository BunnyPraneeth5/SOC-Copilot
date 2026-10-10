"""Model feature vectors must carry every CICIDS value through preprocessing.

Training names features after the raw CICIDS headers ("flow_bytes/s",
"destination_port", "fwd_header_length.1"); preprocessing renames fields
("flow_bytes_s", "dst_port", "fwd_header_length_1"). The vector builder must
find each value under its preprocessed name, or the model sees zeros.
"""

import json
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest

from soc_copilot.core.base import ParsedRecord
from soc_copilot.data.preprocessing import PipelineConfig, PreprocessingPipeline
from soc_copilot.pipeline import SOCCopilot

FEATURE_ORDER = Path(__file__).resolve().parents[2] / "data" / "models" / "feature_order.json"


@pytest.fixture(scope="module")
def feature_names():
    return json.loads(FEATURE_ORDER.read_text(encoding="utf-8"))["feature_names"]


def _copilot(feature_names):
    copilot = object.__new__(SOCCopilot)
    copilot._loaded = True
    copilot._feature_order = list(feature_names)
    copilot._preprocessing = PreprocessingPipeline(PipelineConfig())
    copilot._features = Mock()
    copilot._features.transform.side_effect = lambda df: df
    copilot._analysis = Mock()
    copilot._analysis.analyze.return_value = None
    return copilot


def _flow(feature_names, offset=0.0):
    record = {
        "timestamp": "2026-10-09T04:00:00Z",
        "src_ip": "10.20.30.12",
        "dst_ip": "198.18.44.9",
    }
    # distinct non-zero value per feature, so a swap or a zero is visible
    record.update({name: i + 1.5 + offset for i, name in enumerate(feature_names)})
    return record


def _vectors(copilot, raws):
    records = [ParsedRecord(timestamp=r["timestamp"], raw=r) for r in raws]
    copilot.analyze_records(records)
    return [call.args[0] for call in copilot._analysis.analyze.call_args_list]


def test_names_that_preprocessing_renames_are_present(feature_names):
    """Guard: the test only means something if renamed names exist."""
    renamed = [n for n in feature_names if "/" in n or "." in n]
    assert renamed and "destination_port" in feature_names


def test_every_feature_reaches_the_model(feature_names):
    raws = [_flow(feature_names), _flow(feature_names, offset=1000.0)]
    vectors = _vectors(_copilot(feature_names), raws)

    assert len(vectors) == 2
    for raw, vec in zip(raws, vectors):
        expected = np.array([raw[n] for n in feature_names], dtype=float)
        lost = [n for n, v, e in zip(feature_names, vec, expected) if v != e]
        assert lost == [], f"features not reaching the model: {lost}"


def test_training_names_still_work_without_standardizer(feature_names):
    copilot = _copilot(feature_names)
    copilot._preprocessing = Mock(spec=[])  # no get_preprocessor
    row = pd.Series({n: i + 1.0 for i, n in enumerate(feature_names)})
    vec = copilot._build_feature_vector(row)
    assert list(vec) == [i + 1.0 for i in range(len(feature_names))]


def test_feature_keys_are_unique(feature_names):
    keys = _copilot(feature_names)._feature_keys()
    first = [k[0] for k in keys]
    assert len(set(first)) == len(first)


def test_missing_and_non_numeric_values_become_zero(feature_names):
    copilot = _copilot(feature_names)
    row = pd.Series({feature_names[0]: "n/a", feature_names[1]: np.nan})
    vec = copilot._build_feature_vector(row)
    assert vec[0] == 0.0 and vec[1] == 0.0
