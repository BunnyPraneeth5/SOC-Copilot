"""Phase-2 Sprint-11: Explainability Enhancements (Non-Invasive Wrapper).

Enriches Phase-1 alerts with explanation metadata via composition.
Does NOT modify Phase-1 Alert class or scoring logic.
"""

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class AlertExplanation:
    """Explanation metadata for an alert (read-only, descriptive)."""
    
    def __init__(self):
        self.summary = ""
        self.model_signals = {}
        self.contributing_features = []
        self.rationale = ""
        self.notes = []
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "summary": self.summary,
            "model_signals": self.model_signals,
            "contributing_features": self.contributing_features,
            "rationale": self.rationale,
            "notes": self.notes
        }


class ExplainedAlert:
    """Wrapper that adds explanation metadata to Phase-1 Alert.
    
    Uses composition to preserve Phase-1 Alert immutability.
    """
    
    def __init__(self, alert, explanation: AlertExplanation):
        """Wrap alert with explanation.
        
        Args:
            alert: Phase-1 Alert object (unchanged)
            explanation: AlertExplanation metadata
        """
        self.alert = alert  # Original Phase-1 alert
        self.explanation = explanation
    
    def __getattr__(self, name):
        """Delegate attribute access to wrapped alert."""
        return getattr(self.alert, name)
    
    def to_dict(self):
        """Convert to dictionary with explanation."""
        # Get Phase-1 alert dict
        alert_dict = {
            "alert_id": self.alert.alert_id,
            "priority": self.alert.priority.value,
            "risk_level": self.alert.risk_level.value,
            "threat_category": self.alert.threat_category.value,
            "classification": self.alert.classification,
            "classification_confidence": self.alert.classification_confidence,
            "anomaly_score": self.alert.anomaly_score,
            "combined_risk_score": self.alert.combined_risk_score,
            "reasoning": self.alert.reasoning,
            "suggested_action": self.alert.suggested_action,
            "mitre_tactics": self.alert.mitre_tactics,
            "mitre_techniques": self.alert.mitre_techniques,
        }
        
        # Add explanation
        alert_dict["explanation"] = self.explanation.to_dict()
        
        return alert_dict


class AlertExplainer:
    """Generates explanation metadata for alerts (non-invasive)."""
    
    def __init__(self, top_n_features: int = 3):
        """Initialize explainer.
        
        Args:
            top_n_features: Number of top contributing features to include
        """
        self.top_n_features = top_n_features
    
    def explain_alert(self, alert, feature_data: dict = None) -> ExplainedAlert:
        """Generate explanation for an alert.
        
        Args:
            alert: Phase-1 Alert object
            feature_data: Optional feature values/stats for contribution analysis
            
        Returns:
            ExplainedAlert wrapper with explanation metadata
        """
        explanation = AlertExplanation()
        
        # Generate summary
        explanation.summary = self._generate_summary(alert)
        
        # Model signals
        explanation.model_signals = self._extract_model_signals(alert)
        
        # Contributing features (if data available)
        if feature_data:
            explanation.contributing_features = self._identify_contributing_features(
                alert, feature_data
            )
        
        # Decision rationale
        explanation.rationale = self._generate_rationale(alert)
        
        # Contextual notes
        explanation.notes = self._generate_notes(alert)
        
        return ExplainedAlert(alert, explanation)
    
    def _generate_summary(self, alert) -> str:
        """Generate human-readable summary."""
        anomaly_level = "high" if alert.anomaly_score > 0.7 else "moderate" if alert.anomaly_score > 0.4 else "low"
        confidence_level = "high" if alert.classification_confidence > 0.8 else "moderate" if alert.classification_confidence > 0.6 else "low"
        
        return f"{anomaly_level.capitalize()} anomaly detected with {confidence_level} confidence classification as {alert.classification}."
    
    def _extract_model_signals(self, alert) -> dict:
        """Extract model signal information."""
        signals = {
            "isolation_forest": {
                "anomaly_score": alert.anomaly_score,
                "interpretation": self._interpret_anomaly_score(alert.anomaly_score)
            },
            "random_forest": {
                "predicted_class": alert.classification,
                "confidence": alert.classification_confidence,
                "interpretation": self._interpret_classification(alert.classification, alert.classification_confidence)
            }
        }
        return signals
    
    def _interpret_anomaly_score(self, score: float) -> str:
        """Interpret anomaly score in plain language."""
        if score > 0.8:
            return "Highly unusual behavior detected"
        elif score > 0.6:
            return "Moderately unusual behavior detected"
        elif score > 0.4:
            return "Slightly unusual behavior detected"
        else:
            return "Behavior within normal range"
    
    def _interpret_classification(self, classification: str, confidence: float) -> str:
        """Interpret classification in plain language."""
        conf_text = "strong" if confidence > 0.8 else "moderate" if confidence > 0.6 else "weak"
        return f"Pattern shows {conf_text} resemblance to {classification} attack type"
    
    def _identify_contributing_features(self, alert, feature_data: dict) -> list:
        """Identify top contributing features (simple heuristic).
        
        Args:
            alert: Alert object
            feature_data: Dict with feature values and optional stats
            
        Returns:
            List of contributing feature descriptions
        """
        contributing = []
        
        # Simple heuristic: look for features with high values or unusual patterns
        # This is a placeholder - real implementation would use feature importance
        
        if "dst_port" in feature_data:
            port = feature_data["dst_port"]
            if port and port not in [80, 443, 22, 21, 25]:
                contributing.append({
                    "feature": "dst_port",
                    "value": port,
                    "reason": "Uncommon destination port"
                })
        
        if "packet_count" in feature_data:
            count = feature_data["packet_count"]
            if count and count > 1000:
                contributing.append({
                    "feature": "packet_count",
                    "value": count,
                    "reason": "High packet volume"
                })
        
        if "bytes_sent" in feature_data:
            bytes_val = feature_data["bytes_sent"]
            if bytes_val and bytes_val > 100000:
                contributing.append({
                    "feature": "bytes_sent",
                    "value": bytes_val,
                    "reason": "Large data transfer"
                })
        
        return contributing[:self.top_n_features]
    
    def _generate_rationale(self, alert) -> str:
        """Generate decision rationale."""
        anomaly_desc = "high" if alert.anomaly_score > 0.7 else "moderate" if alert.anomaly_score > 0.4 else "low"
        conf_desc = "high" if alert.classification_confidence > 0.8 else "moderate" if alert.classification_confidence > 0.6 else "low"
        
        rationale = f"{anomaly_desc.capitalize()} anomaly score ({alert.anomaly_score:.2f}) combined with {conf_desc} {alert.classification} confidence ({alert.classification_confidence:.2f}) "
        rationale += f"resulted in {alert.priority.value} priority alert."
        
        return rationale
    
    def _generate_notes(self, alert) -> list:
        """Generate contextual notes."""
        notes = []
        
        # Note about risk level
        if alert.risk_level.value == "CRITICAL":
            notes.append("Immediate investigation recommended")
        elif alert.risk_level.value == "HIGH":
            notes.append("Prompt investigation recommended")
        
        # Note about confidence
        if alert.classification_confidence < 0.6:
            notes.append("Classification confidence is moderate - manual verification suggested")
        
        # Note about MITRE mapping
        if alert.mitre_tactics:
            notes.append(f"Mapped to MITRE ATT&CK tactics: {', '.join(alert.mitre_tactics)}")
        
        return notes
