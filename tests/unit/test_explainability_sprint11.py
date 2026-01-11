"""Unit tests for Sprint-11 Explainability Enhancements."""

import pytest
from unittest.mock import Mock

from soc_copilot.phase2.explainability import (
    AlertExplainer,
    ExplainedAlert,
    AlertExplanation,
)


@pytest.fixture
def mock_alert():
    """Create mock Phase-1 alert."""
    alert = Mock()
    alert.alert_id = "test-alert-123"
    alert.priority = Mock(value="P1-High")
    alert.risk_level = Mock(value="HIGH")
    alert.threat_category = Mock(value="BruteForce")
    alert.classification = "BruteForce"
    alert.classification_confidence = 0.85
    alert.anomaly_score = 0.72
    alert.combined_risk_score = 0.78
    alert.reasoning = "Test reasoning"
    alert.suggested_action = "Test action"
    alert.mitre_tactics = ["TA0006"]
    alert.mitre_techniques = ["T1110"]
    return alert


@pytest.fixture
def explainer():
    """Create alert explainer."""
    return AlertExplainer(top_n_features=3)


class TestAlertExplanation:
    """Tests for AlertExplanation."""
    
    def test_create_explanation(self):
        """Should create explanation object."""
        exp = AlertExplanation()
        
        assert exp.summary == ""
        assert exp.model_signals == {}
        assert exp.contributing_features == []
        assert exp.rationale == ""
        assert exp.notes == []
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        exp = AlertExplanation()
        exp.summary = "Test summary"
        exp.model_signals = {"test": "signal"}
        
        data = exp.to_dict()
        
        assert data["summary"] == "Test summary"
        assert data["model_signals"] == {"test": "signal"}


class TestExplainedAlert:
    """Tests for ExplainedAlert wrapper."""
    
    def test_wrap_alert(self, mock_alert):
        """Should wrap alert with explanation."""
        explanation = AlertExplanation()
        explanation.summary = "Test explanation"
        
        explained = ExplainedAlert(mock_alert, explanation)
        
        assert explained.alert == mock_alert
        assert explained.explanation == explanation
    
    def test_delegate_attributes(self, mock_alert):
        """Should delegate attribute access to wrapped alert."""
        explanation = AlertExplanation()
        explained = ExplainedAlert(mock_alert, explanation)
        
        # Should access wrapped alert attributes
        assert explained.alert_id == "test-alert-123"
        assert explained.classification == "BruteForce"
        assert explained.anomaly_score == 0.72
    
    def test_to_dict_includes_explanation(self, mock_alert):
        """Should include explanation in dict output."""
        explanation = AlertExplanation()
        explanation.summary = "Test summary"
        explained = ExplainedAlert(mock_alert, explanation)
        
        data = explained.to_dict()
        
        assert "alert_id" in data
        assert "explanation" in data
        assert data["explanation"]["summary"] == "Test summary"
    
    def test_preserves_phase1_alert(self, mock_alert):
        """Should not modify Phase-1 alert."""
        # Mock doesn't have explanation initially
        explanation = AlertExplanation()
        explained = ExplainedAlert(mock_alert, explanation)
        
        # Wrapped alert should be unchanged
        assert explained.alert == mock_alert
        # Explanation is on wrapper, not original alert
        assert hasattr(explained, "explanation")
        assert explained.explanation == explanation


class TestAlertExplainer:
    """Tests for AlertExplainer."""
    
    def test_explain_alert(self, explainer, mock_alert):
        """Should generate explanation for alert."""
        explained = explainer.explain_alert(mock_alert)
        
        assert isinstance(explained, ExplainedAlert)
        assert explained.alert == mock_alert
        assert explained.explanation.summary != ""
        assert explained.explanation.model_signals != {}
        assert explained.explanation.rationale != ""
    
    def test_generate_summary(self, explainer, mock_alert):
        """Should generate human-readable summary."""
        summary = explainer._generate_summary(mock_alert)
        
        assert "anomaly" in summary.lower()
        assert "confidence" in summary.lower()
        assert mock_alert.classification in summary
    
    def test_extract_model_signals(self, explainer, mock_alert):
        """Should extract model signal information."""
        signals = explainer._extract_model_signals(mock_alert)
        
        assert "isolation_forest" in signals
        assert "random_forest" in signals
        assert signals["isolation_forest"]["anomaly_score"] == 0.72
        assert signals["random_forest"]["predicted_class"] == "BruteForce"
        assert signals["random_forest"]["confidence"] == 0.85
    
    def test_interpret_anomaly_score_high(self, explainer):
        """Should interpret high anomaly score."""
        interpretation = explainer._interpret_anomaly_score(0.85)
        
        assert "highly unusual" in interpretation.lower()
    
    def test_interpret_anomaly_score_moderate(self, explainer):
        """Should interpret moderate anomaly score."""
        interpretation = explainer._interpret_anomaly_score(0.65)
        
        assert "moderately unusual" in interpretation.lower()
    
    def test_interpret_anomaly_score_low(self, explainer):
        """Should interpret low anomaly score."""
        interpretation = explainer._interpret_anomaly_score(0.3)
        
        assert "normal" in interpretation.lower()
    
    def test_interpret_classification(self, explainer):
        """Should interpret classification."""
        interpretation = explainer._interpret_classification("BruteForce", 0.85)
        
        assert "BruteForce" in interpretation
        assert "strong" in interpretation.lower()
    
    def test_identify_contributing_features(self, explainer, mock_alert):
        """Should identify contributing features."""
        feature_data = {
            "dst_port": 8080,
            "packet_count": 1500,
            "bytes_sent": 150000
        }
        
        features = explainer._identify_contributing_features(mock_alert, feature_data)
        
        assert len(features) <= 3
        assert all("feature" in f for f in features)
        assert all("reason" in f for f in features)
    
    def test_generate_rationale(self, explainer, mock_alert):
        """Should generate decision rationale."""
        rationale = explainer._generate_rationale(mock_alert)
        
        assert "anomaly" in rationale.lower()
        assert "confidence" in rationale.lower()
        assert mock_alert.priority.value in rationale
    
    def test_generate_notes(self, explainer, mock_alert):
        """Should generate contextual notes."""
        notes = explainer._generate_notes(mock_alert)
        
        assert isinstance(notes, list)
        # Should have notes for HIGH risk level
        assert any("investigation" in note.lower() for note in notes)
    
    def test_explain_with_feature_data(self, explainer, mock_alert):
        """Should include feature contributions when data provided."""
        feature_data = {
            "dst_port": 8080,
            "packet_count": 1500
        }
        
        explained = explainer.explain_alert(mock_alert, feature_data)
        
        assert len(explained.explanation.contributing_features) > 0
    
    def test_explain_without_feature_data(self, explainer, mock_alert):
        """Should work without feature data."""
        explained = explainer.explain_alert(mock_alert)
        
        # Should still have explanation, just no contributing features
        assert explained.explanation.summary != ""
        assert explained.explanation.model_signals != {}
        assert explained.explanation.contributing_features == []


class TestExplainabilityIntegration:
    """Integration tests."""
    
    def test_full_explanation_workflow(self, explainer, mock_alert):
        """Should handle complete explanation workflow."""
        # Generate explanation
        explained = explainer.explain_alert(mock_alert)
        
        # Verify wrapper preserves alert
        assert explained.alert_id == mock_alert.alert_id
        assert explained.classification == mock_alert.classification
        
        # Verify explanation metadata
        assert explained.explanation.summary != ""
        assert "isolation_forest" in explained.explanation.model_signals
        assert "random_forest" in explained.explanation.model_signals
        assert explained.explanation.rationale != ""
        
        # Verify dict export
        data = explained.to_dict()
        assert "alert_id" in data
        assert "explanation" in data
        assert "summary" in data["explanation"]
        assert "model_signals" in data["explanation"]
    
    def test_phase1_alert_unchanged(self, explainer, mock_alert):
        """Should not modify Phase-1 alert object."""
        # Store original alert reference
        original_alert = mock_alert
        
        # Generate explanation
        explained = explainer.explain_alert(mock_alert)
        
        # Phase-1 alert should be same object
        assert explained.alert is original_alert
        
        # Wrapper should have explanation
        assert hasattr(explained, "explanation")
        assert isinstance(explained.explanation, AlertExplanation)
