"""Base abstract classes for SOC Copilot components.

Provides interfaces for parsers, anomaly detectors, and classifiers
to ensure modularity and future extensibility.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from enum import Enum

import numpy as np
from pydantic import BaseModel


# =============================================================================
# Enums
# =============================================================================

class AlertPriority(str, Enum):
    """Alert priority levels."""
    
    PASS = "pass"           # No alert
    LOW = "low"             # Low priority
    MEDIUM = "medium"       # Medium priority
    HIGH = "high"           # High priority
    CRITICAL = "critical"   # Critical priority


class AttackClass(str, Enum):
    """Known attack classifications."""
    
    BENIGN = "Benign"
    DDOS = "DDoS"
    BRUTE_FORCE = "BruteForce"
    MALWARE = "Malware"
    EXFILTRATION = "Exfiltration"
    RECONNAISSANCE = "Reconnaissance"
    INJECTION = "Injection"
    UNKNOWN = "Unknown"


# =============================================================================
# Data Models
# =============================================================================

class ParsedRecord(BaseModel):
    """A single parsed log record."""
    
    timestamp: str
    raw: dict[str, Any]
    source_file: str | None = None
    source_format: str | None = None


class AnomalyResult(BaseModel):
    """Result from anomaly detection."""
    
    score: float  # 0.0 (normal) to 1.0 (highly anomalous)
    is_anomaly: bool
    contributing_features: list[str] = []


class ClassificationResult(BaseModel):
    """Result from attack classification."""
    
    predicted_class: AttackClass
    confidence: float  # 0.0 to 1.0
    probabilities: dict[str, float] = {}


class EnsembleResult(BaseModel):
    """Combined result from ensemble controller."""
    
    anomaly: AnomalyResult
    classification: ClassificationResult
    priority: AlertPriority
    final_score: float
    reasoning: str


# =============================================================================
# Base Parser
# =============================================================================

class BaseParser(ABC):
    """Abstract base class for log parsers.
    
    All log format parsers (JSON, CSV, Syslog, EVTX) must implement this interface.
    """
    
    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """List of file extensions this parser supports (e.g., ['.json', '.jsonl'])."""
        ...
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name (e.g., 'JSON', 'Syslog')."""
        ...
    
    @abstractmethod
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        """Parse a log file and return parsed records.
        
        Args:
            filepath: Path to the log file
            
        Returns:
            List of parsed log records
            
        Raises:
            ParseError: If the file cannot be parsed
        """
        ...
    
    @abstractmethod
    def parse_line(self, line: str) -> ParsedRecord | None:
        """Parse a single line of log data.
        
        Args:
            line: Single line from a log file
            
        Returns:
            Parsed record, or None if line should be skipped
        """
        ...
    
    def can_parse(self, filepath: Path) -> bool:
        """Check if this parser can handle the given file.
        
        Args:
            filepath: Path to check
            
        Returns:
            True if this parser supports the file type
        """
        return filepath.suffix.lower() in self.supported_extensions


# =============================================================================
# Base Anomaly Detector
# =============================================================================

class BaseDetector(ABC):
    """Abstract base class for anomaly detectors.
    
    All anomaly detection models (Isolation Forest, future Autoencoder)
    must implement this interface.
    """
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the detector model."""
        ...
    
    @property
    @abstractmethod
    def is_fitted(self) -> bool:
        """Whether the model has been trained."""
        ...
    
    @abstractmethod
    def fit(self, X: np.ndarray) -> None:
        """Train the detector on normal data.
        
        Args:
            X: Training data (n_samples, n_features)
        """
        ...
    
    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict whether samples are anomalies.
        
        Args:
            X: Samples to predict (n_samples, n_features)
            
        Returns:
            Array of predictions: 1 for anomaly, 0 for normal
        """
        ...
    
    @abstractmethod
    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        """Calculate anomaly scores for samples.
        
        Args:
            X: Samples to score (n_samples, n_features)
            
        Returns:
            Array of scores from 0.0 (normal) to 1.0 (anomalous)
        """
        ...
    
    @abstractmethod
    def detect(self, X: np.ndarray) -> list[AnomalyResult]:
        """Full detection with anomaly results.
        
        Args:
            X: Samples to detect (n_samples, n_features)
            
        Returns:
            List of AnomalyResult objects
        """
        ...
    
    @abstractmethod
    def save(self, filepath: Path) -> None:
        """Save the trained model to disk.
        
        Args:
            filepath: Path to save the model
        """
        ...
    
    @abstractmethod
    def load(self, filepath: Path) -> None:
        """Load a trained model from disk.
        
        Args:
            filepath: Path to the saved model
        """
        ...


# =============================================================================
# Base Classifier
# =============================================================================

class BaseClassifier(ABC):
    """Abstract base class for attack classifiers.
    
    All classification models (Random Forest, future deep learning)
    must implement this interface.
    """
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the classifier model."""
        ...
    
    @property
    @abstractmethod
    def classes(self) -> list[AttackClass]:
        """List of attack classes this classifier can predict."""
        ...
    
    @property
    @abstractmethod
    def is_fitted(self) -> bool:
        """Whether the model has been trained."""
        ...
    
    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train the classifier.
        
        Args:
            X: Training features (n_samples, n_features)
            y: Training labels (n_samples,)
        """
        ...
    
    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict attack classes.
        
        Args:
            X: Samples to classify (n_samples, n_features)
            
        Returns:
            Array of predicted class indices
        """
        ...
    
    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities.
        
        Args:
            X: Samples to classify (n_samples, n_features)
            
        Returns:
            Array of probabilities (n_samples, n_classes)
        """
        ...
    
    @abstractmethod
    def classify(self, X: np.ndarray) -> list[ClassificationResult]:
        """Full classification with results.
        
        Args:
            X: Samples to classify (n_samples, n_features)
            
        Returns:
            List of ClassificationResult objects
        """
        ...
    
    @abstractmethod
    def save(self, filepath: Path) -> None:
        """Save the trained model to disk.
        
        Args:
            filepath: Path to save the model
        """
        ...
    
    @abstractmethod
    def load(self, filepath: Path) -> None:
        """Load a trained model from disk.
        
        Args:
            filepath: Path to the saved model
        """
        ...


# =============================================================================
# Exceptions
# =============================================================================

class SOCCopilotError(Exception):
    """Base exception for SOC Copilot."""
    pass


class ParseError(SOCCopilotError):
    """Error during log parsing."""
    
    def __init__(self, message: str, line_number: int | None = None, raw_data: str | None = None):
        self.line_number = line_number
        self.raw_data = raw_data
        super().__init__(message)


class ModelNotFittedError(SOCCopilotError):
    """Model used before being trained."""
    pass


class ConfigurationError(SOCCopilotError):
    """Invalid configuration."""
    pass
