#!/usr/bin/env python3
"""Train the text log classifier model.

Generates synthetic training data and trains a Random Forest model
specifically for classifying security events from custom text logs.

Usage:
    python scripts/train_text_log_model.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path

from models.text_log_classifier.text_log_classifier import train_and_save
from soc_copilot.security.model_integrity import update_manifest


def main():
    print("=" * 60)
    print("TEXT LOG CLASSIFIER — TRAINING")
    print("=" * 60)

    output_path = "data/models/text_log_rf_v1.joblib"
    n_samples = 10000

    print(f"\n  Samples:    {n_samples}")
    print(f"  Output:     {output_path}")
    print()

    metrics = train_and_save(output_path=output_path, n_samples=n_samples)

    print("\n  TRAINING RESULTS")
    print("  " + "-" * 40)
    print(f"  Train samples:  {metrics['train_samples']}")
    print(f"  Val samples:    {metrics['val_samples']}")
    print(f"  Features:       {metrics['n_features']}")
    print(f"  Classes:        {metrics['classes']}")
    print(f"  Train accuracy: {metrics['train_accuracy']:.4f}")
    print(f"  Val accuracy:   {metrics['val_accuracy']:.4f}")
    print()

    report = metrics["classification_report"]
    print("  PER-CLASS METRICS (Validation)")
    print("  " + "-" * 55)
    print(f"  {'Class':<15} {'Precision':>10} {'Recall':>10} {'F1-Score':>10}")
    print("  " + "-" * 55)
    for cls in metrics["classes"]:
        if cls in report:
            p = report[cls]["precision"]
            r = report[cls]["recall"]
            f1 = report[cls]["f1-score"]
            print(f"  {cls:<15} {p:>10.4f} {r:>10.4f} {f1:>10.4f}")
    print("  " + "-" * 55)
    print(f"  {'Overall':<15} {report['weighted avg']['precision']:>10.4f} "
          f"{report['weighted avg']['recall']:>10.4f} "
          f"{report['weighted avg']['f1-score']:>10.4f}")

    output = Path(output_path)
    update_manifest(output.parent, [output.name])

    print(f"\n  Model saved to: {output_path}")
    print(f"  Integrity manifest updated: {output.parent / 'model_hashes.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
