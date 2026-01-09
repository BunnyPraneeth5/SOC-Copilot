"""Training data loader for Kaggle datasets.

Handles loading, concatenation, column normalization, and label mapping
for training ML models on Kaggle security datasets.
"""

import json
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


# SOC Copilot label taxonomy
SOC_LABELS = ["Benign", "DDoS", "BruteForce", "Malware", "Exfiltration"]


# Default label mappings for common Kaggle security datasets
# Maps original Kaggle labels to SOC taxonomy
DEFAULT_LABEL_MAPPINGS: dict[str, str] = {
    # Benign variants
    "benign": "Benign",
    "BENIGN": "Benign",
    "normal": "Benign",
    "Normal": "Benign",
    
    # DDoS variants
    "ddos": "DDoS",
    "DDoS": "DDoS",
    "DDOS": "DDoS",
    "DoS": "DDoS",
    "dos": "DDoS",
    "DoS GoldenEye": "DDoS",
    "DoS Hulk": "DDoS",
    "DoS Slowhttptest": "DDoS",
    "DoS slowloris": "DDoS",
    "DoS Slowloris": "DDoS",
    "DDoS-HOIC": "DDoS",
    "DDoS-LOIC-UDP": "DDoS",
    "DDoS-LOIC-HTTP": "DDoS",
    "DDoS-SlowLoris": "DDoS",
    "DDoS attacks-GoldenEye": "DDoS",
    "DDoS attacks-Slowloris": "DDoS",
    "DDOS attack-HOIC": "DDoS",
    "DDOS attack-LOIC-UDP": "DDoS",
    
    # BruteForce variants
    "bruteforce": "BruteForce",
    "BruteForce": "BruteForce",
    "Brute Force": "BruteForce",
    "FTP-Patator": "BruteForce",
    "SSH-Patator": "BruteForce",
    "FTP-BruteForce": "BruteForce",
    "SSH-BruteForce": "BruteForce",
    "Brute Force -Web": "BruteForce",
    "Brute Force -XSS": "BruteForce",
    "SQL Injection": "BruteForce",
    
    # Malware variants
    "malware": "Malware",
    "Malware": "Malware",
    "bot": "Malware",
    "Bot": "Malware",
    "Botnet": "Malware",
    "Trojan": "Malware",
    "Worm": "Malware",
    "Backdoor": "Malware",
    "Ransomware": "Malware",
    
    # Exfiltration variants
    "exfiltration": "Exfiltration",
    "Exfiltration": "Exfiltration",
    "Infiltration": "Exfiltration",
    "infiltration": "Exfiltration",
    "DataExfiltration": "Exfiltration",
    
    # Reconnaissance -> map to least severe for now
    "PortScan": "BruteForce",
    "Heartbleed": "Malware",
    "Web Attack": "BruteForce",
}


class DataLoaderConfig(BaseModel):
    """Configuration for training data loading."""
    
    # Path to Kaggle datasets
    datasets_dir: str = "data/datasets/kaggle"
    
    # Label column name(s) to search for
    label_columns: list[str] = Field(
        default_factory=lambda: ["Label", "label", "Attack", "attack", "class", "Class"]
    )
    
    # Custom label mappings (extends defaults)
    label_mappings: dict[str, str] = Field(default_factory=dict)
    
    # Columns to drop (common non-feature columns)
    drop_columns: list[str] = Field(
        default_factory=lambda: [
            "Flow ID", "Source IP", "Destination IP", "Timestamp",
            "Src IP", "Dst IP", "Src Port", "Dst Port",
        ]
    )
    
    # Maximum rows per file (for memory management)
    max_rows_per_file: int | None = None
    
    # Random seed for reproducibility
    random_seed: int = 42


class TrainingDataLoader:
    """Loads and prepares training data from Kaggle datasets.
    
    Features:
    - Recursive CSV loading from dataset directories
    - Automatic column name normalization
    - Label mapping to SOC taxonomy
    - Train/test splitting
    - Benign-only filtering for unsupervised models
    
    Usage:
        loader = TrainingDataLoader(config)
        df = loader.load_dataset("CICIDS2017")
        X_train, X_test, y_train, y_test = loader.prepare_train_test(df)
        X_benign = loader.get_benign_only(df)
    """
    
    def __init__(self, config: DataLoaderConfig | None = None):
        """Initialize loader.
        
        Args:
            config: Data loading configuration
        """
        self.config = config or DataLoaderConfig()
        
        # Merge default and custom label mappings
        self._label_mappings = {**DEFAULT_LABEL_MAPPINGS, **self.config.label_mappings}
        
        # Track statistics
        self._stats: dict[str, Any] = {}
    
    def list_datasets(self) -> list[str]:
        """List available datasets.
        
        Returns:
            List of dataset directory names
        """
        datasets_path = Path(self.config.datasets_dir)
        if not datasets_path.exists():
            return []
        
        return [d.name for d in datasets_path.iterdir() if d.is_dir()]
    
    def load_dataset(self, dataset_name: str) -> pd.DataFrame:
        """Load all CSV files from a dataset directory.
        
        Args:
            dataset_name: Name of the dataset directory
            
        Returns:
            Concatenated DataFrame with normalized columns
        """
        dataset_path = Path(self.config.datasets_dir) / dataset_name
        
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")
        
        csv_files = list(dataset_path.glob("**/*.csv"))
        if not csv_files:
            raise ValueError(f"No CSV files found in: {dataset_path}")
        
        logger.info(
            "loading_dataset",
            dataset=dataset_name,
            csv_files=len(csv_files),
        )
        
        dfs = []
        for csv_file in sorted(csv_files):
            try:
                df = self._load_csv(csv_file)
                if df is not None and len(df) > 0:
                    dfs.append(df)
                    logger.debug(
                        "loaded_csv",
                        file=csv_file.name,
                        rows=len(df),
                    )
            except Exception as e:
                logger.warning(
                    "csv_load_error",
                    file=str(csv_file),
                    error=str(e),
                )
        
        if not dfs:
            raise ValueError(f"No valid data loaded from: {dataset_path}")
        
        # Concatenate all dataframes
        combined = pd.concat(dfs, ignore_index=True)
        
        # Normalize columns
        combined = self._normalize_columns(combined)
        
        # Map labels
        combined = self._map_labels(combined)
        
        self._stats = {
            "dataset": dataset_name,
            "files_loaded": len(dfs),
            "total_rows": len(combined),
            "columns": len(combined.columns),
        }
        
        logger.info(
            "dataset_loaded",
            **self._stats,
        )
        
        return combined
    
    def _load_csv(self, filepath: Path) -> pd.DataFrame | None:
        """Load a single CSV file.
        
        Args:
            filepath: Path to CSV file
            
        Returns:
            DataFrame or None if loading fails
        """
        try:
            df = pd.read_csv(
                filepath,
                low_memory=False,
                nrows=self.config.max_rows_per_file,
                encoding="utf-8",
                on_bad_lines="skip",
            )
            return df
        except Exception:
            # Try with latin-1 encoding as fallback
            try:
                df = pd.read_csv(
                    filepath,
                    low_memory=False,
                    nrows=self.config.max_rows_per_file,
                    encoding="latin-1",
                    on_bad_lines="skip",
                )
                return df
            except Exception:
                return None
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with normalized column names
        """
        # Strip whitespace and convert to lowercase
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
        
        # Drop configured columns
        drop_cols = [c.lower().replace(" ", "_") for c in self.config.drop_columns]
        existing_drop = [c for c in drop_cols if c in df.columns]
        if existing_drop:
            df = df.drop(columns=existing_drop, errors="ignore")
        
        return df
    
    def _map_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map labels to SOC taxonomy.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with mapped labels in 'label' column
        """
        # Find label column
        label_col = None
        normalized_label_cols = [c.lower().replace(" ", "_") for c in self.config.label_columns]
        
        for col in df.columns:
            if col in normalized_label_cols:
                label_col = col
                break
        
        if label_col is None:
            logger.warning("no_label_column_found")
            df["label"] = "Unknown"
            return df
        
        # Map labels
        original_labels = df[label_col].unique()
        df["label"] = df[label_col].apply(
            lambda x: self._label_mappings.get(str(x).strip(), "Unknown")
        )
        
        # Report mapping statistics
        label_counts = df["label"].value_counts()
        unmapped = (df["label"] == "Unknown").sum()
        
        logger.info(
            "labels_mapped",
            original_unique=len(original_labels),
            unmapped_count=unmapped,
            label_distribution=label_counts.to_dict(),
        )
        
        return df
    
    def get_benign_only(self, df: pd.DataFrame) -> pd.DataFrame:
        """Filter to only benign records for unsupervised training.
        
        Args:
            df: Input DataFrame with 'label' column
            
        Returns:
            DataFrame with only Benign records
        """
        if "label" not in df.columns:
            raise ValueError("DataFrame must have 'label' column")
        
        benign_df = df[df["label"] == "Benign"].copy()
        
        logger.info(
            "benign_filtered",
            total_rows=len(df),
            benign_rows=len(benign_df),
            benign_ratio=len(benign_df) / len(df) if len(df) > 0 else 0,
        )
        
        return benign_df
    
    def prepare_features(
        self,
        df: pd.DataFrame,
        feature_columns: list[str] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, list[str]]:
        """Prepare feature matrix and labels.
        
        Args:
            df: Input DataFrame
            feature_columns: Specific columns to use as features
            
        Returns:
            Tuple of (X feature matrix, y labels, feature_names)
        """
        if "label" not in df.columns:
            raise ValueError("DataFrame must have 'label' column")
        
        y = df["label"].values
        
        if feature_columns:
            # Use specified columns
            missing = [c for c in feature_columns if c not in df.columns]
            if missing:
                raise ValueError(f"Missing feature columns: {missing}")
            X = df[feature_columns].values
            feature_names = feature_columns
        else:
            # Use all numeric columns except label
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if "label" in numeric_cols:
                numeric_cols.remove("label")
            X = df[numeric_cols].values
            feature_names = numeric_cols
        
        # Handle NaN/Inf values
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        
        logger.info(
            "features_prepared",
            samples=X.shape[0],
            features=X.shape[1],
        )
        
        return X, y, feature_names
    
    def train_test_split(
        self,
        X: np.ndarray,
        y: np.ndarray,
        test_size: float = 0.2,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Split data into train and test sets.
        
        Args:
            X: Feature matrix
            y: Labels
            test_size: Fraction for test set
            
        Returns:
            Tuple of (X_train, X_test, y_train, y_test)
        """
        from sklearn.model_selection import train_test_split
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=test_size,
            random_state=self.config.random_seed,
            stratify=y,
        )
        
        logger.info(
            "train_test_split",
            train_samples=len(X_train),
            test_samples=len(X_test),
        )
        
        return X_train, X_test, y_train, y_test
    
    def get_label_mapping(self) -> dict[str, str]:
        """Get the label mapping dictionary.
        
        Returns:
            Dict of original_label -> soc_label
        """
        return self._label_mappings.copy()
    
    def save_label_mapping(self, filepath: str | Path) -> None:
        """Save label mapping to JSON file.
        
        Args:
            filepath: Output path for label_map.json
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, "w") as f:
            json.dump({
                "soc_labels": SOC_LABELS,
                "mappings": self._label_mappings,
            }, f, indent=2)
        
        logger.info("label_mapping_saved", path=str(filepath))
    
    def get_stats(self) -> dict[str, Any]:
        """Get loading statistics.
        
        Returns:
            Dict with loading stats
        """
        return self._stats.copy()
