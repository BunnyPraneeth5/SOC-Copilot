"""Isolation Forest anomaly-score calibration (benign percentile).

The legacy sigmoid squeezed every flow into ~0.42-0.55, so the anomaly
signal could never raise an alert. Calibration ranks a raw score against
held-out benign flows.
"""

import json
from types import SimpleNamespace

import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from soc_copilot.models.inference.anomaly_calibration import (
    CALIBRATION_FILENAME,
    AnomalyCalibration,
    build_calibration,
    calibrate_from_holdout,
    load_calibration,
    save_calibration,
)
from soc_copilot.models.inference.engine import InferenceConfig, ModelInference
from soc_copilot.security.model_integrity import update_manifest


@pytest.fixture()
def uniform():
    return AnomalyCalibration.from_dict(build_calibration(np.linspace(0.0, 1.0, 10001), "test"))


class TestMapping:
    def test_typical_benign_is_half(self, uniform):
        assert uniform(0.5) == pytest.approx(0.5, abs=1e-3)

    def test_rank_against_benign(self, uniform):
        # raw 0.09: 91% of benign flows score higher (look more normal)
        assert uniform(0.09) == pytest.approx(0.91, abs=1e-3)

    def test_beyond_benign_range(self, uniform):
        assert uniform(-5.0) == 1.0
        assert uniform(5.0) == 0.0

    def test_monotonic_lower_raw_is_more_anomalous(self, uniform):
        raws = np.linspace(-0.2, 1.2, 200)
        values = [uniform(r) for r in raws]
        assert all(a >= b for a, b in zip(values, values[1:]))

    def test_ties_in_benign_scores(self):
        scores = np.concatenate([np.zeros(500), np.ones(500)])
        cal = AnomalyCalibration.from_dict(build_calibration(scores, "ties"))
        assert cal(0.0) == pytest.approx(0.5, abs=0.01)
        assert cal(1.0) == 0.0
        assert cal(-0.1) == 1.0

    def test_spreads_scores_where_sigmoid_did_not(self, uniform):
        """Sigmoid of raw 0.1 vs 0.9 differs by ~0.2; calibration by 0.8."""
        sigmoid = lambda r: 1 / (1 + np.exp(r))  # noqa: E731
        assert sigmoid(0.1) - sigmoid(0.9) < 0.25
        assert uniform(0.1) - uniform(0.9) > 0.75


class TestValidation:
    def test_needs_enough_samples(self):
        with pytest.raises(ValueError):
            build_calibration(np.arange(50.0), "few")

    def test_rejects_descending_or_nan(self):
        with pytest.raises(ValueError):
            AnomalyCalibration([0.3, 0.2, 0.1])
        with pytest.raises(ValueError):
            AnomalyCalibration([0.1, float("nan"), 0.3])

    def test_rejects_unknown_method(self):
        data = build_calibration(np.linspace(0, 1, 200), "x")
        data["method"] = "something_else"
        with pytest.raises(ValueError):
            AnomalyCalibration.from_dict(data)

    def test_ignores_non_finite_scores(self):
        scores = np.concatenate([np.linspace(0, 1, 200), [np.inf, np.nan]])
        assert build_calibration(scores, "x")["samples"] == 200


class TestLoading:
    def test_missing_file_means_no_calibration(self, tmp_path):
        assert load_calibration(tmp_path) is None

    def test_loads_when_in_manifest(self, tmp_path):
        save_calibration(tmp_path, build_calibration(np.linspace(0, 1, 500), "x"))
        update_manifest(tmp_path, [CALIBRATION_FILENAME])
        assert load_calibration(tmp_path).samples == 500

    def test_tampered_file_is_rejected(self, tmp_path):
        save_calibration(tmp_path, build_calibration(np.linspace(0, 1, 500), "x"))
        update_manifest(tmp_path, [CALIBRATION_FILENAME])
        path = tmp_path / CALIBRATION_FILENAME
        data = json.loads(path.read_text())
        data["quantiles"] = [q - 10 for q in data["quantiles"]]  # silences alerts
        path.write_text(json.dumps(data))
        with pytest.raises(RuntimeError, match="integrity"):
            load_calibration(tmp_path)

    def test_malformed_file_is_rejected(self, tmp_path):
        (tmp_path / CALIBRATION_FILENAME).write_text("{not json")
        update_manifest(tmp_path, [CALIBRATION_FILENAME])
        with pytest.raises(RuntimeError, match="Invalid"):
            load_calibration(tmp_path)


@pytest.fixture()
def models_dir(tmp_path):
    """Tiny trained Isolation Forest + manifest, like data/models."""
    rng = np.random.default_rng(0)
    X = rng.normal(0, 1, (3000, 4))
    scaler = StandardScaler().fit(X[:2000])
    model = IsolationForest(n_estimators=50, random_state=0).fit(scaler.transform(X[:2000]))
    joblib.dump({"model": model, "scaler": scaler}, tmp_path / "isolation_forest_v1.joblib")
    (tmp_path / "feature_order.json").write_text(json.dumps({"feature_names": list("abcd")}))
    update_manifest(tmp_path, ["isolation_forest_v1.joblib", "feature_order.json"])
    return SimpleNamespace(path=tmp_path, holdout=X[2000:], model=model, scaler=scaler)


def _engine(models_dir):
    engine = ModelInference(InferenceConfig(models_dir=str(models_dir.path)))
    engine.load_models()
    return engine


class TestEngine:
    def test_uncalibrated_engine_keeps_legacy_sigmoid(self, models_dir):
        engine = _engine(models_dir)
        assert not engine.anomaly_calibrated
        normal = engine.score_anomaly(np.zeros(4))
        outlier = engine.score_anomaly(np.full(4, 8.0))
        assert 0.35 < normal < outlier < 0.65  # the old, squeezed range

    def test_calibrated_engine_spreads_scores(self, models_dir):
        calibrate_from_holdout(models_dir.path, models_dir.model, models_dir.scaler,
                               models_dir.holdout, "synthetic")
        update_manifest(models_dir.path, [CALIBRATION_FILENAME])
        engine = _engine(models_dir)
        assert engine.anomaly_calibrated
        assert engine.score_anomaly(np.zeros(4)) < 0.3  # centre of normal data
        assert engine.score_anomaly(np.full(4, 8.0)) == 1.0  # far outside it
        typical = [engine.score_anomaly(x) for x in models_dir.holdout[:300]]
        assert 0.4 < float(np.median(typical)) < 0.6

    def test_tampered_calibration_stops_loading(self, models_dir):
        calibrate_from_holdout(models_dir.path, models_dir.model, models_dir.scaler,
                               models_dir.holdout, "synthetic")
        update_manifest(models_dir.path, [CALIBRATION_FILENAME])
        path = models_dir.path / CALIBRATION_FILENAME
        path.write_text(path.read_text().replace('"samples": 1000', '"samples": 1001'))
        with pytest.raises(RuntimeError):
            _engine(models_dir)
