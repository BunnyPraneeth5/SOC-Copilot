"""Isolation Forest score calibration against normal traffic.

The raw ``decision_function`` of the Isolation Forest is small (roughly
-0.1..0.35 on CICIDS2017), and the old ``1 / (1 + exp(raw))`` mapping
squeezed every flow, benign or attack, into about 0.42-0.55, so the
anomaly signal could never lift a detection to an alert.

Calibration ranks a flow against benign flows the model never trained on:
the anomaly score is the share of those benign flows that look more normal.
0.5 is a typical benign flow, 0.91 means "more unusual than 91% of normal
traffic", 1.0 is beyond anything seen in normal traffic.

The calibration is stored as quantiles of the benign raw scores in
``anomaly_calibration.json`` next to the models and listed in the
integrity manifest (editing it could silence alerts).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from soc_copilot.core.logging import get_logger
from soc_copilot.security.model_integrity import verify_model_file

logger = get_logger(__name__)

CALIBRATION_FILENAME = "anomaly_calibration.json"
CALIBRATION_METHOD = "benign_percentile"
QUANTILE_LEVELS = 1001  # every 0.1 percentile


def raw_anomaly_scores(model, scaler, X: np.ndarray) -> np.ndarray:
    """Raw ``decision_function`` scores, prepared exactly as at inference."""
    X = np.asarray(X, dtype=float)
    if scaler is not None:
        X = np.nan_to_num(scaler.transform(X), nan=0.0, posinf=0.0, neginf=0.0)
    return model.decision_function(X)


def build_calibration(benign_raw_scores: np.ndarray, source: str) -> dict[str, Any]:
    """Calibration data from raw scores of held-out benign flows."""
    scores = np.asarray(benign_raw_scores, dtype=float)
    scores = scores[np.isfinite(scores)]
    if len(scores) < 100:
        raise ValueError(f"Need at least 100 benign scores to calibrate, got {len(scores)}")
    levels = np.linspace(0.0, 1.0, QUANTILE_LEVELS)
    quantiles = np.quantile(scores, levels)
    return {
        "version": 1,
        "method": CALIBRATION_METHOD,
        "description": (
            "Quantiles of Isolation Forest decision_function scores on held-out "
            "benign flows; anomaly = share of benign flows that look more normal."
        ),
        "source": source,
        "samples": int(len(scores)),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "quantiles": [round(float(q), 8) for q in quantiles],
    }


def calibrate_from_holdout(
    models_dir: str | Path, model, scaler, X_benign_holdout: np.ndarray, source: str
) -> Path:
    """Score held-out benign flows and write ``anomaly_calibration.json``.

    The caller must add the file to the integrity manifest.
    """
    scores = raw_anomaly_scores(model, scaler, X_benign_holdout)
    return save_calibration(models_dir, build_calibration(scores, source))


def save_calibration(models_dir: str | Path, data: dict[str, Any]) -> Path:
    path = Path(models_dir) / CALIBRATION_FILENAME
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")
    logger.info("anomaly_calibration_saved", path=str(path), samples=data.get("samples"))
    return path


class AnomalyCalibration:
    """Maps a raw ``decision_function`` score to [0, 1] (higher = more anomalous)."""

    def __init__(self, quantiles: list[float], samples: int = 0, source: str = ""):
        q = np.asarray(quantiles, dtype=float)
        if q.ndim != 1 or len(q) < 2 or not np.all(np.isfinite(q)) or np.any(np.diff(q) < 0):
            raise ValueError("calibration quantiles must be finite and ascending")
        levels = np.linspace(0.0, 1.0, len(q))
        # Ties (flat stretches) keep the highest level: share of benign <= x
        self._x, last = np.unique(q[::-1], return_index=True)
        self._cdf = levels[::-1][last]
        self.samples = samples
        self.source = source

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AnomalyCalibration":
        if data.get("method") != CALIBRATION_METHOD:
            raise ValueError(f"unsupported calibration method {data.get('method')!r}")
        return cls(data["quantiles"], int(data.get("samples", 0)), str(data.get("source", "")))

    def __call__(self, raw_score: float) -> float:
        # Share of benign flows scoring at or below raw (less normal or equal);
        # one minus that is the share that looks more normal.
        cdf = float(np.interp(raw_score, self._x, self._cdf, left=0.0, right=1.0))
        return min(1.0, max(0.0, 1.0 - cdf))


def load_calibration(models_dir: str | Path) -> AnomalyCalibration | None:
    """Load and verify the calibration, or None when there is none.

    A calibration that fails the integrity check or is malformed raises:
    a tampered file must not silently change alerting.
    """
    path = Path(models_dir) / CALIBRATION_FILENAME
    if not path.exists():
        return None
    integrity = verify_model_file(path)
    if not integrity.is_valid:
        raise RuntimeError(f"Anomaly calibration integrity check failed: {integrity.error}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AnomalyCalibration.from_dict(data)
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f"Invalid anomaly calibration {path}: {e}") from e
