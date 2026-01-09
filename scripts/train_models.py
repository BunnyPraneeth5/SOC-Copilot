#!/usr/bin/env python3
"""Training script for SOC Copilot ML models.

This script trains both Isolation Forest and Random Forest models
using Kaggle datasets. It is designed to be run offline/manually.

Usage:
    python scripts/train_models.py --dataset CICIDS2017
    python scripts/train_models.py --dataset CICIDS2017 --test-size 0.2

Requirements:
    - Kaggle datasets must be placed in data/datasets/kaggle/<dataset_name>/
    - Each dataset should contain CSV files with labeled network traffic
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "models" / "isolation_forest"))
sys.path.insert(0, str(project_root / "models" / "random_forest"))

import numpy as np

from soc_copilot.models.training.data_loader import (
    TrainingDataLoader,
    DataLoaderConfig,
)
from soc_copilot.core.logging import get_logger

# Import trainers from models directory
from trainer import IsolationForestTrainer, IsolationForestConfig


logger = get_logger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Train SOC Copilot ML models on Kaggle datasets"
    )
    
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Name of the dataset directory under data/datasets/kaggle/",
    )
    
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Fraction of data to use for testing (default: 0.2)",
    )
    
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/models",
        help="Output directory for trained models",
    )
    
    parser.add_argument(
        "--n-estimators",
        type=int,
        default=100,
        help="Number of trees in forest models",
    )
    
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Maximum rows per CSV file (for memory management)",
    )
    
    return parser.parse_args()


def main():
    """Main training pipeline."""
    args = parse_args()
    
    print(f"\n{'='*60}")
    print("SOC Copilot Model Training")
    print(f"{'='*60}\n")
    
    # Initialize data loader
    loader_config = DataLoaderConfig(
        max_rows_per_file=args.max_rows,
    )
    loader = TrainingDataLoader(loader_config)
    
    # Check available datasets
    datasets = loader.list_datasets()
    if not datasets:
        print("ERROR: No datasets found in data/datasets/kaggle/")
        print("Please download and extract Kaggle datasets first.")
        sys.exit(1)
    
    print(f"Available datasets: {datasets}")
    
    if args.dataset not in datasets:
        print(f"ERROR: Dataset '{args.dataset}' not found.")
        print(f"Available: {datasets}")
        sys.exit(1)
    
    # Load dataset
    print(f"\nLoading dataset: {args.dataset}...")
    df = loader.load_dataset(args.dataset)
    print(f"Loaded {len(df)} records with {len(df.columns)} columns")
    
    # Show label distribution
    print("\nLabel distribution:")
    print(df["label"].value_counts())
    
    # Prepare features (use all numeric columns)
    X, y, feature_names = loader.prepare_features(df)
    print(f"\nFeature matrix: {X.shape}")
    print(f"Features: {len(feature_names)}")
    
    # Split data
    X_train, X_test, y_train, y_test = loader.train_test_split(
        X, y, test_size=args.test_size
    )
    print(f"\nTrain samples: {len(X_train)}")
    print(f"Test samples: {len(X_test)}")
    
    # =========================================================================
    # Train Isolation Forest (benign only)
    # =========================================================================
    print(f"\n{'='*60}")
    print("Training Isolation Forest (Benign Only)")
    print(f"{'='*60}\n")
    
    # Filter training data to benign only
    benign_mask = y_train == "Benign"
    X_benign = X_train[benign_mask]
    
    print(f"Benign training samples: {len(X_benign)}")
    
    if len(X_benign) == 0:
        print("WARNING: No benign samples found. Skipping Isolation Forest training.")
    else:
        if_config = IsolationForestConfig(
            n_estimators=args.n_estimators,
            model_output_dir=args.output_dir,
        )
        if_trainer = IsolationForestTrainer(if_config)
        if_trainer.train(X_benign, feature_names)
        
        # Evaluate on test set
        test_scores = if_trainer.score(X_test)
        benign_test_mask = y_test == "Benign"
        
        benign_scores = test_scores[benign_test_mask]
        attack_scores = test_scores[~benign_test_mask]
        
        print(f"\nAnomaly Score Statistics:")
        print(f"  Benign mean: {np.mean(benign_scores):.4f} (should be low)")
        print(f"  Attack mean: {np.mean(attack_scores):.4f} (should be high)")
        
        # Save model
        if_paths = if_trainer.save()
        print(f"\nIsolation Forest saved to: {if_paths['model']}")
    
    # =========================================================================
    # Train Random Forest (full labeled data)
    # =========================================================================
    print(f"\n{'='*60}")
    print("Training Random Forest (Multi-class)")
    print(f"{'='*60}\n")
    
    # Need to import from random_forest trainer
    sys.path.insert(0, str(project_root / "models" / "random_forest"))
    from trainer import RandomForestTrainer, RandomForestConfig
    
    rf_config = RandomForestConfig(
        n_estimators=args.n_estimators,
        model_output_dir=args.output_dir,
    )
    rf_trainer = RandomForestTrainer(rf_config)
    
    train_stats = rf_trainer.train(
        X_train, y_train, feature_names,
        X_val=X_test, y_val=y_test,
    )
    
    print(f"\nTraining accuracy: {train_stats['train_accuracy']:.4f}")
    if "val_accuracy" in train_stats:
        print(f"Validation accuracy: {train_stats['val_accuracy']:.4f}")
    
    # Detailed evaluation
    eval_results = rf_trainer.evaluate(X_test, y_test)
    print(f"\nTest accuracy: {eval_results['accuracy']:.4f}")
    
    # Feature importance
    importance = rf_trainer.get_feature_importance()
    top_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)[:10]
    print("\nTop 10 important features:")
    for name, imp in top_features:
        print(f"  {name}: {imp:.4f}")
    
    # Save model
    rf_paths = rf_trainer.save()
    print(f"\nRandom Forest saved to: {rf_paths['model']}")
    
    # Save label mapping
    loader.save_label_mapping(Path(args.output_dir) / "label_map.json")
    
    # =========================================================================
    # Summary
    # =========================================================================
    print(f"\n{'='*60}")
    print("Training Complete")
    print(f"{'='*60}\n")
    
    print("Models saved to:")
    print(f"  - {args.output_dir}/isolation_forest_v1.joblib")
    print(f"  - {args.output_dir}/random_forest_v1.joblib")
    print(f"  - {args.output_dir}/feature_order.json")
    print(f"  - {args.output_dir}/label_map.json")
    
    print("\nTo use in inference:")
    print("  from soc_copilot.models import create_inference_engine")
    print("  engine = create_inference_engine()")
    print("  result = engine.infer(features)")


if __name__ == "__main__":
    main()
