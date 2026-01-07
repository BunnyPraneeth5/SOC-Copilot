"""Unit tests for base abstract classes and data models."""

import pytest
import numpy as np
from pathlib import Path

from soc_copilot.core.base import (
    AlertPriority,
    AttackClass,
    ParsedRecord,
    AnomalyResult,
    ClassificationResult,
    EnsembleResult,
    BaseParser,
    BaseDetector,
    BaseClassifier,
    ParseError,
    ModelNotFittedError,
    ConfigurationError,
)


class TestEnums:
    """Tests for enum definitions."""
    
    def test_alert_priority_values(self):
        """AlertPriority should have expected values."""
        assert AlertPriority.PASS == "pass"
        assert AlertPriority.CRITICAL == "critical"
        
    def test_attack_class_values(self):
        """AttackClass should have expected values."""
        assert AttackClass.BENIGN == "Benign"
        assert AttackClass.DDOS == "DDoS"
        assert AttackClass.UNKNOWN == "Unknown"


class TestDataModels:
    """Tests for Pydantic data models."""
    
    def test_parsed_record(self):
        """ParsedRecord should store log data correctly."""
        record = ParsedRecord(
            timestamp="2026-01-07T12:00:00Z",
            raw={"event_id": 4624, "user": "admin"},
            source_file="test.json",
            source_format="JSON",
        )
        assert record.timestamp == "2026-01-07T12:00:00Z"
        assert record.raw["event_id"] == 4624
    
    def test_anomaly_result(self):
        """AnomalyResult should validate scores correctly."""
        result = AnomalyResult(
            score=0.85,
            is_anomaly=True,
            contributing_features=["port_entropy", "request_rate"],
        )
        assert result.score == 0.85
        assert result.is_anomaly is True
        assert len(result.contributing_features) == 2
    
    def test_classification_result(self):
        """ClassificationResult should store predictions."""
        result = ClassificationResult(
            predicted_class=AttackClass.DDOS,
            confidence=0.92,
            probabilities={"DDoS": 0.92, "Benign": 0.05, "BruteForce": 0.03},
        )
        assert result.predicted_class == AttackClass.DDOS
        assert result.confidence == 0.92
    
    def test_ensemble_result(self):
        """EnsembleResult should combine all outputs."""
        anomaly = AnomalyResult(score=0.8, is_anomaly=True)
        classification = ClassificationResult(
            predicted_class=AttackClass.MALWARE,
            confidence=0.75,
        )
        result = EnsembleResult(
            anomaly=anomaly,
            classification=classification,
            priority=AlertPriority.HIGH,
            final_score=0.78,
            reasoning="High anomaly score with malware classification",
        )
        assert result.priority == AlertPriority.HIGH
        assert result.final_score == 0.78


class TestExceptions:
    """Tests for custom exceptions."""
    
    def test_parse_error_with_context(self):
        """ParseError should store context."""
        error = ParseError(
            "Invalid JSON",
            line_number=42,
            raw_data='{"broken',
        )
        assert error.line_number == 42
        assert error.raw_data == '{"broken'
        assert "Invalid JSON" in str(error)
    
    def test_model_not_fitted_error(self):
        """ModelNotFittedError should be raisable."""
        with pytest.raises(ModelNotFittedError):
            raise ModelNotFittedError("Model must be trained before prediction")
    
    def test_configuration_error(self):
        """ConfigurationError should be raisable."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Invalid threshold value")


class MockParser(BaseParser):
    """Mock implementation of BaseParser for testing."""
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".mock"]
    
    @property
    def format_name(self) -> str:
        return "Mock"
    
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        return []
    
    def parse_line(self, line: str) -> ParsedRecord | None:
        return ParsedRecord(timestamp="2026-01-01T00:00:00Z", raw={"line": line})


class TestBaseParser:
    """Tests for BaseParser interface."""
    
    def test_can_parse_matching_extension(self, tmp_path):
        """can_parse should return True for matching extension."""
        parser = MockParser()
        assert parser.can_parse(tmp_path / "test.mock") is True
    
    def test_can_parse_non_matching_extension(self, tmp_path):
        """can_parse should return False for non-matching extension."""
        parser = MockParser()
        assert parser.can_parse(tmp_path / "test.json") is False
    
    def test_format_name(self):
        """format_name should return expected value."""
        parser = MockParser()
        assert parser.format_name == "Mock"


class MockDetector(BaseDetector):
    """Mock implementation of BaseDetector for testing."""
    
    def __init__(self):
        self._fitted = False
    
    @property
    def model_name(self) -> str:
        return "MockDetector"
    
    @property
    def is_fitted(self) -> bool:
        return self._fitted
    
    def fit(self, X: np.ndarray) -> None:
        self._fitted = True
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.zeros(len(X))
    
    def anomaly_score(self, X: np.ndarray) -> np.ndarray:
        return np.zeros(len(X))
    
    def detect(self, X: np.ndarray) -> list[AnomalyResult]:
        return [AnomalyResult(score=0.0, is_anomaly=False) for _ in range(len(X))]
    
    def save(self, filepath: Path) -> None:
        pass
    
    def load(self, filepath: Path) -> None:
        self._fitted = True


class TestBaseDetector:
    """Tests for BaseDetector interface."""
    
    def test_is_fitted_before_training(self):
        """is_fitted should be False before training."""
        detector = MockDetector()
        assert detector.is_fitted is False
    
    def test_is_fitted_after_training(self):
        """is_fitted should be True after training."""
        detector = MockDetector()
        detector.fit(np.random.randn(100, 10))
        assert detector.is_fitted is True
    
    def test_model_name(self):
        """model_name should return expected value."""
        detector = MockDetector()
        assert detector.model_name == "MockDetector"


class MockClassifier(BaseClassifier):
    """Mock implementation of BaseClassifier for testing."""
    
    def __init__(self):
        self._fitted = False
    
    @property
    def model_name(self) -> str:
        return "MockClassifier"
    
    @property
    def classes(self) -> list[AttackClass]:
        return [AttackClass.BENIGN, AttackClass.MALWARE]
    
    @property
    def is_fitted(self) -> bool:
        return self._fitted
    
    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._fitted = True
    
    def predict(self, X: np.ndarray) -> np.ndarray:
        return np.zeros(len(X), dtype=int)
    
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return np.ones((len(X), 2)) * 0.5
    
    def classify(self, X: np.ndarray) -> list[ClassificationResult]:
        return [
            ClassificationResult(predicted_class=AttackClass.BENIGN, confidence=0.5)
            for _ in range(len(X))
        ]
    
    def save(self, filepath: Path) -> None:
        pass
    
    def load(self, filepath: Path) -> None:
        self._fitted = True


class TestBaseClassifier:
    """Tests for BaseClassifier interface."""
    
    def test_classes_property(self):
        """classes should return attack classes."""
        classifier = MockClassifier()
        assert AttackClass.BENIGN in classifier.classes
    
    def test_is_fitted_before_training(self):
        """is_fitted should be False before training."""
        classifier = MockClassifier()
        assert classifier.is_fitted is False
    
    def test_is_fitted_after_training(self):
        """is_fitted should be True after training."""
        classifier = MockClassifier()
        X = np.random.randn(100, 10)
        y = np.zeros(100, dtype=int)
        classifier.fit(X, y)
        assert classifier.is_fitted is True
