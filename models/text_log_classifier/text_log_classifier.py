"""
Text Log Classifier — ML model trained on text log features.

A separate Random Forest model specifically designed for classifying
security events from custom text log formats (UserLogin, LoginAttempt,
FileExecution, DataTransfer, etc.).

Unlike the network-flow model (trained on CICIDS2017 with 78 features),
this model uses 12 security-relevant features extracted from parsed log
entries to classify events into: Benign, BruteForce, Malware,
Exfiltration, or Suspicious.
"""

import re
import uuid
import numpy as np
import joblib
from pathlib import Path
from datetime import datetime
from typing import Optional

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

from soc_copilot.core.logging import get_logger
from soc_copilot.security.model_integrity import verify_model_file
from soc_copilot.security.network import is_external_ip

logger = get_logger(__name__)

# Known threat IPs (sample list — expandable)
KNOWN_THREAT_IPS = {
    "185.220.101.45", "45.67.89.101", "23.129.64.0",
    "198.96.155.3", "185.56.80.65", "91.219.236.0",
    "62.102.148.68", "194.165.16.0", "5.188.86.0",
    "185.100.87.0", "193.169.255.0", "171.25.193.0",
}

FEATURE_NAMES = [
    "event_type_encoded",
    "login_attempts",
    "data_size_mb",
    "is_external_src_ip",
    "is_external_dst_ip",
    "has_exe_file",
    "has_payload_keyword",
    "login_success",
    "hour_of_day",
    "is_business_hours",
    "has_known_threat_ip",
    "user_is_admin",
]

EVENT_TYPE_MAP = {
    "UserLogin": 0,
    "LoginAttempt": 1,
    "FileExecution": 2,
    "DataTransfer": 3,
}


# ============================================================================
# Feature Extractor
# ============================================================================

class TextLogFeatureExtractor:
    """Extracts 12 ML features from a parsed text log entry."""

    @staticmethod
    def is_external_ip(ip: str) -> bool:
        return is_external_ip(ip)

    def extract(self, parsed: dict) -> np.ndarray:
        """Extract feature vector from a parsed log dict.

        Args:
            parsed: Dict from AppController._parse_raw_log()

        Returns:
            np.ndarray of shape (12,)
        """
        event_type = parsed.get("event_type", "")
        src_ip = parsed.get("src_ip", "")
        dst_ip = parsed.get("dst_ip", "")
        action = parsed.get("action", "")
        user = parsed.get("user", "")
        raw_log = parsed.get("raw_log", "")
        timestamp = parsed.get("timestamp", "")

        # Feature 1: Event type (encoded)
        event_type_encoded = EVENT_TYPE_MAP.get(event_type, -1)

        # Feature 2: Login attempts
        login_attempts = int(parsed.get("login_attempts", 0))

        # Feature 3: Data transfer size
        data_size_mb = int(parsed.get("data_size_mb", 0))

        # Feature 4-5: External IP flags
        is_external_src = int(self.is_external_ip(src_ip))
        is_external_dst = int(self.is_external_ip(dst_ip))

        # Feature 6-7: Malicious file indicators
        has_exe = int(".exe" in action.lower() or ".exe" in raw_log.lower())
        has_payload = int("payload" in raw_log.lower())

        # Feature 8: Login success
        login_success = int("success=true" in raw_log.lower() or "status=SUCCESS" in raw_log)

        # Feature 9-10: Temporal features
        hour = 12  # default
        if timestamp:
            try:
                hour_match = re.search(r"T?(\d{2}):\d{2}:\d{2}", timestamp)
                if hour_match:
                    hour = int(hour_match.group(1))
            except (ValueError, AttributeError):
                pass
        is_business_hours = int(9 <= hour <= 17)

        # Feature 11: Known threat IP
        has_threat_ip = int(
            src_ip in KNOWN_THREAT_IPS or dst_ip in KNOWN_THREAT_IPS
        )

        # Feature 12: Admin user
        user_is_admin = int(user.lower() in ("admin", "root", "administrator"))

        return np.array([
            event_type_encoded,
            login_attempts,
            data_size_mb,
            is_external_src,
            is_external_dst,
            has_exe,
            has_payload,
            login_success,
            hour,
            is_business_hours,
            has_threat_ip,
            user_is_admin,
        ], dtype=np.float64)


# ============================================================================
# Classifier (Inference)
# ============================================================================

class TextLogClassifier:
    """Loads a trained text log RF model and performs inference."""

    def __init__(self):
        self.model: Optional[RandomForestClassifier] = None
        self.scaler: Optional[StandardScaler] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.extractor = TextLogFeatureExtractor()
        self._loaded = False

    def load(self, model_path: str | Path) -> None:
        """Load a trained model from disk."""
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Text log model not found: {model_path}")

        integrity = verify_model_file(model_path)
        if not integrity.is_valid:
            raise RuntimeError(f"Model integrity check failed: {integrity.error}")

        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.scaler = bundle["scaler"]
        self.label_encoder = bundle["label_encoder"]
        self._loaded = True

        logger.info(
            "text_log_model_loaded",
            path=str(model_path),
            classes=list(self.label_encoder.classes_),
        )

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def classify(self, parsed_log: dict) -> tuple[str, float, dict[str, float]]:
        """Classify a single parsed log entry.

        Args:
            parsed_log: Dict from _parse_raw_log()

        Returns:
            (classification, confidence, class_probabilities)
        """
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        features = self.extractor.extract(parsed_log).reshape(1, -1)
        features_scaled = self.scaler.transform(features)
        features_scaled = np.nan_to_num(features_scaled, nan=0.0)

        # Predict
        pred_encoded = self.model.predict(features_scaled)[0]
        classification = self.label_encoder.inverse_transform([pred_encoded])[0]

        # Probabilities
        probas = self.model.predict_proba(features_scaled)[0]
        class_probas = {
            cls: float(prob)
            for cls, prob in zip(self.label_encoder.classes_, probas)
        }
        confidence = float(max(probas))

        return classification, confidence, class_probas


# ============================================================================
# Trainer (with synthetic data generation)
# ============================================================================

class TextLogTrainer:
    """Generates synthetic training data and trains the text log RF model."""

    def __init__(self, random_state: int = 42):
        self.random_state = random_state
        self.rng = np.random.RandomState(random_state)

    def generate_training_data(self, n_samples: int = 10000) -> tuple[np.ndarray, np.ndarray]:
        """Generate synthetic labeled training data.

        Creates realistic distributions for each class:
        - Benign: Normal logins, small transfers, internal IPs
        - BruteForce: High login attempts, external IPs, admin targets
        - Malware: File executions with .exe, payload keywords
        - Exfiltration: Large transfers to external IPs
        - Suspicious: Moderate anomalies (outside business hours, threat IPs)

        Returns:
            (X, y) where X is (n_samples, 12) and y is string labels
        """
        X_list = []
        y_list = []

        samples_per_class = n_samples // 5

        # --- Benign samples ---
        for _ in range(samples_per_class):
            event_type = self.rng.choice([0, 0, 0, 3])  # Mostly logins, some transfers
            login_attempts = 0
            data_size = self.rng.choice([0, 0, 0, self.rng.randint(1, 100)])
            src_ext = 0
            dst_ext = 0
            has_exe = 0
            has_payload = 0
            login_success = 1
            hour = self.rng.randint(9, 18)
            biz_hours = int(9 <= hour <= 17)
            threat_ip = 0
            is_admin = self.rng.choice([0, 0, 0, 0, 1])

            X_list.append([event_type, login_attempts, data_size, src_ext, dst_ext,
                           has_exe, has_payload, login_success, hour, biz_hours,
                           threat_ip, is_admin])
            y_list.append("Benign")

        # --- BruteForce samples ---
        for _ in range(samples_per_class):
            event_type = 1  # LoginAttempt
            login_attempts = self.rng.randint(5, 100)
            data_size = 0
            src_ext = int(self.rng.random() > 0.3)  # 70% from external
            dst_ext = 0
            has_exe = 0
            has_payload = 0
            login_success = 0  # Failed attempts
            hour = self.rng.randint(0, 24)
            biz_hours = int(9 <= hour <= 17)
            threat_ip = int(self.rng.random() > 0.5)
            is_admin = int(self.rng.random() > 0.4)  # Often target admin

            X_list.append([event_type, login_attempts, data_size, src_ext, dst_ext,
                           has_exe, has_payload, login_success, hour, biz_hours,
                           threat_ip, is_admin])
            y_list.append("BruteForce")

        # --- Malware samples ---
        for _ in range(samples_per_class):
            event_type = 2  # FileExecution
            login_attempts = 0
            data_size = self.rng.choice([0, 0, self.rng.randint(10, 500)])
            src_ext = 0
            dst_ext = int(self.rng.random() > 0.5)
            has_exe = 1
            has_payload = int(self.rng.random() > 0.3)  # 70% have payload keyword
            login_success = 0
            hour = self.rng.randint(0, 24)
            biz_hours = int(9 <= hour <= 17)
            threat_ip = int(self.rng.random() > 0.6)
            is_admin = 0

            X_list.append([event_type, login_attempts, data_size, src_ext, dst_ext,
                           has_exe, has_payload, login_success, hour, biz_hours,
                           threat_ip, is_admin])
            y_list.append("Malware")

        # --- Exfiltration samples ---
        for _ in range(samples_per_class):
            event_type = 3  # DataTransfer
            login_attempts = 0
            data_size = self.rng.randint(500, 10000)  # Large transfers
            src_ext = 0
            dst_ext = 1  # External destination
            has_exe = 0
            has_payload = 0
            login_success = 0
            hour = self.rng.choice([self.rng.randint(0, 6), self.rng.randint(20, 24)])  # Off-hours
            biz_hours = int(9 <= hour <= 17)
            threat_ip = int(self.rng.random() > 0.4)
            is_admin = 0

            X_list.append([event_type, login_attempts, data_size, src_ext, dst_ext,
                           has_exe, has_payload, login_success, hour, biz_hours,
                           threat_ip, is_admin])
            y_list.append("Exfiltration")

        # --- Suspicious samples (subtle anomalies) ---
        for _ in range(samples_per_class):
            scenario = self.rng.choice(["odd_login", "small_transfer", "off_hours_exec"])

            if scenario == "odd_login":
                event_type = 1
                login_attempts = self.rng.randint(2, 5)  # Moderate attempts
                data_size = 0
                src_ext = int(self.rng.random() > 0.5)
                dst_ext = 0
                has_exe = 0
                has_payload = 0
                login_success = 0
                hour = self.rng.choice([self.rng.randint(0, 5), self.rng.randint(22, 24)])
                biz_hours = 0
                threat_ip = int(self.rng.random() > 0.6)
                is_admin = int(self.rng.random() > 0.5)
            elif scenario == "small_transfer":
                event_type = 3
                login_attempts = 0
                data_size = self.rng.randint(100, 500)
                src_ext = 0
                dst_ext = 1
                has_exe = 0
                has_payload = 0
                login_success = 0
                hour = self.rng.randint(0, 24)
                biz_hours = int(9 <= hour <= 17)
                threat_ip = int(self.rng.random() > 0.5)
                is_admin = 0
            else:  # off_hours_exec
                event_type = 2
                login_attempts = 0
                data_size = 0
                src_ext = 0
                dst_ext = 0
                has_exe = int(self.rng.random() > 0.5)
                has_payload = 0
                login_success = 0
                hour = self.rng.choice([self.rng.randint(0, 5), self.rng.randint(22, 24)])
                biz_hours = 0
                threat_ip = 0
                is_admin = 0

            X_list.append([event_type, login_attempts, data_size, src_ext, dst_ext,
                           has_exe, has_payload, login_success, hour, biz_hours,
                           threat_ip, is_admin])
            y_list.append("Suspicious")

        X = np.array(X_list, dtype=np.float64)
        y = np.array(y_list)

        # Shuffle
        idx = self.rng.permutation(len(X))
        return X[idx], y[idx]

    def train(self, X: np.ndarray, y: np.ndarray) -> dict:
        """Train the text log Random Forest classifier.

        Returns:
            Training metrics dict
        """
        # Split into train/val
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=self.random_state, stratify=y
        )

        # Encode labels
        label_encoder = LabelEncoder()
        y_train_enc = label_encoder.fit_transform(y_train)
        y_val_enc = label_encoder.transform(y_val)

        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)

        # Train
        model = RandomForestClassifier(
            n_estimators=150,
            max_depth=15,
            min_samples_split=5,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=self.random_state,
            n_jobs=-1,
        )
        model.fit(X_train_scaled, y_train_enc)

        # Metrics
        train_pred = model.predict(X_train_scaled)
        val_pred = model.predict(X_val_scaled)
        train_acc = accuracy_score(y_train_enc, train_pred)
        val_acc = accuracy_score(y_val_enc, val_pred)

        report = classification_report(
            y_val_enc, val_pred,
            target_names=label_encoder.classes_,
            output_dict=True,
        )

        metrics = {
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "n_features": X_train.shape[1],
            "feature_names": FEATURE_NAMES,
            "classes": list(label_encoder.classes_),
            "train_accuracy": float(train_acc),
            "val_accuracy": float(val_acc),
            "classification_report": report,
            "trained_at": datetime.now().isoformat(),
        }

        # Store for saving
        self._model = model
        self._scaler = scaler
        self._label_encoder = label_encoder
        self._metrics = metrics

        logger.info(
            "text_log_model_trained",
            train_accuracy=f"{train_acc:.4f}",
            val_accuracy=f"{val_acc:.4f}",
            classes=list(label_encoder.classes_),
        )

        return metrics

    def save(self, output_path: str | Path) -> None:
        """Save the trained model bundle to disk."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        bundle = {
            "model": self._model,
            "scaler": self._scaler,
            "label_encoder": self._label_encoder,
            "feature_names": FEATURE_NAMES,
            "metrics": self._metrics,
            "version": "v1",
        }
        joblib.dump(bundle, output_path)

        logger.info("text_log_model_saved", path=str(output_path))


# ============================================================================
# Convenience function
# ============================================================================

def train_and_save(
    output_path: str = "data/models/text_log_rf_v1.joblib",
    n_samples: int = 10000,
) -> dict:
    """One-liner: generate data, train, save, return metrics."""
    trainer = TextLogTrainer()
    X, y = trainer.generate_training_data(n_samples=n_samples)
    metrics = trainer.train(X, y)
    trainer.save(output_path)
    return metrics
