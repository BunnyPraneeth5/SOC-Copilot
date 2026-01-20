"""Ensemble coordinator for SOC Copilot.

Combines Isolation Forest anomaly scores and Random Forest classification
into unified risk assessment with alert-ready outputs.
"""

from enum import Enum
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class RiskLevel(str, Enum):
    """Risk level categories."""
    
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AlertPriority(str, Enum):
    """Alert priority levels."""
    
    P4_INFO = "P4-Info"
    P3_LOW = "P3-Low"
    P2_MEDIUM = "P2-Medium"
    P1_HIGH = "P1-High"
    P0_CRITICAL = "P0-Critical"


class ThreatCategory(str, Enum):
    """SOC threat categories."""
    
    BENIGN = "Benign"
    DDOS = "DDoS"
    BRUTEFORCE = "BruteForce"
    MALWARE = "Malware"
    EXFILTRATION = "Exfiltration"
    UNKNOWN = "Unknown"


# Threat severity mapping (for risk calculation)
THREAT_SEVERITY = {
    ThreatCategory.BENIGN: 0.0,
    ThreatCategory.DDOS: 0.6,
    ThreatCategory.BRUTEFORCE: 0.7,
    ThreatCategory.MALWARE: 0.9,
    ThreatCategory.EXFILTRATION: 1.0,
    ThreatCategory.UNKNOWN: 0.5,
}


class EnsembleConfig(BaseModel):
    """Configuration for ensemble scoring."""
    
    # Weights for combining scores
    anomaly_weight: float = 0.4
    classification_weight: float = 0.6
    
    # Anomaly score thresholds (conservative defaults)
    anomaly_low: float = 0.3
    anomaly_medium: float = 0.5
    anomaly_high: float = 0.7
    anomaly_critical: float = 0.85
    
    # Classification confidence thresholds
    confidence_low: float = 0.5
    confidence_medium: float = 0.7
    confidence_high: float = 0.85
    
    # Combined risk thresholds
    risk_low: float = 0.25
    risk_medium: float = 0.45
    risk_high: float = 0.65
    risk_critical: float = 0.80
    
    # Minimum confidence to trust classification
    min_confidence: float = 0.4


class EnsembleResult(BaseModel):
    """Result from ensemble scoring."""
    
    # Raw scores
    anomaly_score: float = 0.0
    classification: str = "Unknown"
    class_confidence: float = 0.0
    class_probabilities: dict[str, float] = Field(default_factory=dict)
    
    # Combined scores
    combined_risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    alert_priority: AlertPriority = AlertPriority.P4_INFO
    
    # Reasoning for explainability
    reasoning: list[str] = Field(default_factory=list)
    contributing_factors: dict[str, float] = Field(default_factory=dict)
    
    # Alert metadata
    requires_alert: bool = False
    suggested_action: str = "Monitor"
    threat_category: ThreatCategory = ThreatCategory.BENIGN


class EnsembleCoordinator:
    """Coordinates ensemble scoring from multiple models.
    
    Combines:
    - Isolation Forest anomaly score (unsupervised)
    - Random Forest classification with probabilities (supervised)
    
    Produces:
    - Combined risk score
    - Risk level categorization
    - Alert priority
    - Explainable reasoning
    
    Uses conservative defaults to minimize false positives.
    """
    
    def __init__(self, config: EnsembleConfig | None = None):
        """Initialize coordinator.
        
        Args:
            config: Ensemble configuration
        """
        self.config = config or EnsembleConfig()
    
    def score(
        self,
        anomaly_score: float,
        classification: str,
        class_confidence: float,
        class_probabilities: dict[str, float] | None = None,
    ) -> EnsembleResult:
        """Compute ensemble score from model outputs.
        
        Args:
            anomaly_score: IF anomaly score [0, 1]
            classification: RF predicted class
            class_confidence: RF confidence for predicted class
            class_probabilities: Full probability distribution
            
        Returns:
            EnsembleResult with risk assessment
        """
        result = EnsembleResult(
            anomaly_score=anomaly_score,
            classification=classification,
            class_confidence=class_confidence,
            class_probabilities=class_probabilities or {},
        )
        
        reasoning = []
        factors = {}
        
        # Determine threat category
        result.threat_category = self._get_threat_category(classification)
        
        # Get threat severity
        threat_severity = THREAT_SEVERITY.get(result.threat_category, 0.5)
        factors["threat_severity"] = threat_severity
        
        # Classification contribution (only if confident)
        if class_confidence >= self.config.min_confidence:
            classification_contribution = threat_severity * class_confidence
            factors["classification_contribution"] = classification_contribution
            
            if result.threat_category != ThreatCategory.BENIGN:
                reasoning.append(
                    f"Classified as {classification} with {class_confidence:.1%} confidence"
                )
        else:
            classification_contribution = 0.5 * threat_severity  # Uncertain, moderate risk
            factors["classification_contribution"] = classification_contribution
            reasoning.append(
                f"Low classification confidence ({class_confidence:.1%})"
            )
        
        # Anomaly contribution
        factors["anomaly_contribution"] = anomaly_score
        if anomaly_score >= self.config.anomaly_high:
            reasoning.append(f"High anomaly score ({anomaly_score:.2f})")
        elif anomaly_score >= self.config.anomaly_medium:
            reasoning.append(f"Moderate anomaly score ({anomaly_score:.2f})")
        
        # Compute combined risk score
        combined = (
            self.config.anomaly_weight * anomaly_score +
            self.config.classification_weight * classification_contribution
        )
        
        # Boost risk for high-severity threats with high anomaly
        if (result.threat_category in [ThreatCategory.MALWARE, ThreatCategory.EXFILTRATION]
            and anomaly_score >= self.config.anomaly_medium):
            combined = min(1.0, combined * 1.2)
            reasoning.append("Risk boosted: severe threat with anomalous behavior")
        
        # Reduce risk for confident benign with low anomaly
        if (result.threat_category == ThreatCategory.BENIGN 
            and class_confidence >= self.config.confidence_high
            and anomaly_score < self.config.anomaly_medium):
            combined = combined * 0.5
            reasoning.append("Risk reduced: confident benign with normal behavior")
        
        result.combined_risk_score = combined
        result.contributing_factors = factors
        
        # Determine risk level
        result.risk_level = self._get_risk_level(combined)
        
        # Determine alert priority
        result.alert_priority = self._get_alert_priority(
            result.risk_level,
            result.threat_category,
            class_confidence,
        )
        
        # Determine if alert is required
        result.requires_alert = result.alert_priority.value <= AlertPriority.P2_MEDIUM.value
        
        # Suggested action
        result.suggested_action = self._get_suggested_action(
            result.risk_level,
            result.threat_category,
        )
        
        result.reasoning = reasoning
        
        # Only log non-benign events to reduce spam
        if result.threat_category != ThreatCategory.BENIGN or result.risk_level != RiskLevel.LOW:
            logger.debug(
                "ensemble_score_computed",
                risk_score=combined,
                risk_level=result.risk_level.value,
                classification=classification,
            )
        
        return result
    
    def _get_threat_category(self, classification: str) -> ThreatCategory:
        """Map classification to threat category."""
        mapping = {
            "Benign": ThreatCategory.BENIGN,
            "DDoS": ThreatCategory.DDOS,
            "BruteForce": ThreatCategory.BRUTEFORCE,
            "Malware": ThreatCategory.MALWARE,
            "Exfiltration": ThreatCategory.EXFILTRATION,
        }
        return mapping.get(classification, ThreatCategory.UNKNOWN)
    
    def _get_risk_level(self, combined_score: float) -> RiskLevel:
        """Determine risk level from combined score."""
        if combined_score >= self.config.risk_critical:
            return RiskLevel.CRITICAL
        elif combined_score >= self.config.risk_high:
            return RiskLevel.HIGH
        elif combined_score >= self.config.risk_medium:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _get_alert_priority(
        self,
        risk_level: RiskLevel,
        threat_category: ThreatCategory,
        confidence: float,
    ) -> AlertPriority:
        """Determine alert priority.
        
        Uses conservative approach to minimize false positives.
        """
        # Critical risk always gets P0
        if risk_level == RiskLevel.CRITICAL:
            return AlertPriority.P0_CRITICAL
        
        # High-severity threats with high risk
        if (risk_level == RiskLevel.HIGH and 
            threat_category in [ThreatCategory.MALWARE, ThreatCategory.EXFILTRATION]):
            return AlertPriority.P1_HIGH
        
        # High risk
        if risk_level == RiskLevel.HIGH:
            return AlertPriority.P2_MEDIUM
        
        # Medium risk with good confidence
        if risk_level == RiskLevel.MEDIUM and confidence >= self.config.confidence_medium:
            return AlertPriority.P3_LOW
        
        return AlertPriority.P4_INFO
    
    def _get_suggested_action(
        self,
        risk_level: RiskLevel,
        threat_category: ThreatCategory,
    ) -> str:
        """Get suggested action for SOC analyst."""
        if risk_level == RiskLevel.CRITICAL:
            return "Immediate investigation required"
        
        if risk_level == RiskLevel.HIGH:
            if threat_category == ThreatCategory.MALWARE:
                return "Isolate endpoint and investigate"
            elif threat_category == ThreatCategory.EXFILTRATION:
                return "Block connection and investigate data access"
            elif threat_category == ThreatCategory.BRUTEFORCE:
                return "Verify account status and block source"
            elif threat_category == ThreatCategory.DDOS:
                return "Apply rate limiting and monitor"
            return "Investigate within 1 hour"
        
        if risk_level == RiskLevel.MEDIUM:
            return "Review and investigate if recurring"
        
        return "Monitor"


# Decision matrix for reference
DECISION_MATRIX = """
| Anomaly Score | Classification | Confidence | Risk Level | Priority |
|---------------|----------------|------------|------------|----------|
| High (>0.7)   | Malware/Exfil  | High       | Critical   | P0       |
| High (>0.7)   | Any Attack     | High       | High       | P1       |
| High (>0.7)   | Any Attack     | Low        | Medium     | P2       |
| High (>0.7)   | Benign         | High       | Medium     | P3       |
| Med (0.5-0.7) | Malware/Exfil  | High       | High       | P1       |
| Med (0.5-0.7) | Attack         | High       | Medium     | P2       |
| Med (0.5-0.7) | Benign         | Any        | Low        | P4       |
| Low (<0.5)    | Any Attack     | High       | Medium     | P3       |
| Low (<0.5)    | Benign         | High       | Low        | P4       |
"""
