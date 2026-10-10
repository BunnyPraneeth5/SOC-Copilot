#!/usr/bin/env python3
"""Calibrate Isolation Forest anomaly scores for already trained models.

Reproduces the train/test split of ``train_models.py`` (same loader, same
seed and test size), scores the benign test flows the Isolation Forest never
trained on, writes ``anomaly_calibration.json`` next to the models and adds
it to the integrity manifest. ``train_models.py`` does this automatically;
use this script for models trained before calibration existed.

Usage:
    python scripts/calibrate_anomaly.py --dataset cicids2017
"""

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import joblib

from soc_copilot.models.inference.anomaly_calibration import (
    CALIBRATION_FILENAME,
    calibrate_from_holdout,
    load_calibration,
)
from soc_copilot.models.training.data_loader import DataLoaderConfig, TrainingDataLoader
from soc_copilot.security.model_integrity import update_manifest, verify_model_file


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dataset", required=True,
                        help="Dataset directory under data/datasets/kaggle/ used for training")
    parser.add_argument("--models-dir", default="data/models")
    parser.add_argument("--test-size", type=float, default=0.2,
                        help="Must match the value used for training (default 0.2)")
    parser.add_argument("--max-rows", type=int, default=None,
                        help="Must match the value used for training (default: all rows)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    models_dir = Path(args.models_dir)
    if_path = models_dir / "isolation_forest_v1.joblib"

    integrity = verify_model_file(if_path)
    if not integrity.is_valid:
        sys.exit(f"ERROR: {integrity.error}")
    artifact = joblib.load(if_path)

    loader = TrainingDataLoader(DataLoaderConfig(max_rows_per_file=args.max_rows))
    df = loader.load_dataset(args.dataset)
    X, y, feature_names = loader.prepare_features(df)
    del df
    expected = json.loads((models_dir / "feature_order.json").read_text())["feature_names"]
    if list(feature_names) != list(expected):
        sys.exit("ERROR: dataset features do not match feature_order.json")

    _, X_test, _, y_test = loader.train_test_split(X, y, test_size=args.test_size)
    benign = X_test[y_test == "Benign"]
    print(f"Scoring {len(benign)} held-out benign flows...")
    path = calibrate_from_holdout(
        models_dir, artifact["model"], artifact.get("scaler"), benign,
        source=f"{args.dataset} benign test split (test_size={args.test_size})",
    )
    update_manifest(models_dir, [CALIBRATION_FILENAME])
    calibration = load_calibration(models_dir)  # verifies the manifest entry
    print(f"Saved {path} ({calibration.samples} samples); manifest updated")


if __name__ == "__main__":
    main()
