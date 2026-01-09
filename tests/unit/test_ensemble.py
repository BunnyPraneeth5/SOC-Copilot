"""Unit tests for ensemble logic."""

import pytest

from soc_copilot.models.ensemble.coordinator import (
    EnsembleCoordinator,
    EnsembleConfig,
    EnsembleResult,
    RiskLevel,
    AlertPriority,
    ThreatCategory,
    THREAT_SEVERITY,
)
from soc_copilot.models.ensemble.alert_generator import (
    AlertGenerator,
    Alert,
    AlertStatus,
    format_alert_summary,
    MITRE_MAPPING,
)


# =============================================================================
# Ensemble Coordinator Tests
# =============================================================================

class TestThreatSeverity:
    """Tests for threat severity mapping."""
    
    def test_benign_lowest(self):
        """Benign should have lowest severity."""
        assert THREAT_SEVERITY[ThreatCategory.BENIGN] == 0.0
    
    def test_exfiltration_highest(self):
        """Exfiltration should have highest severity."""
        assert THREAT_SEVERITY[ThreatCategory.EXFILTRATION] == 1.0
    
    def test_all_categories_have_severity(self):
        """All threat categories should have severity."""
        for category in ThreatCategory:
            assert category in THREAT_SEVERITY


class TestEnsembleCoordinator:
    """Tests for ensemble coordinator."""
    
    @pytest.fixture
    def coordinator(self):
        return EnsembleCoordinator()
    
    def test_low_risk_benign(self, coordinator):
        """Benign with low anomaly should be low risk."""
        result = coordinator.score(
            anomaly_score=0.2,
            classification="Benign",
            class_confidence=0.9,
        )
        
        assert result.risk_level == RiskLevel.LOW
        assert result.alert_priority == AlertPriority.P4_INFO
        assert not result.requires_alert
    
    def test_critical_risk_malware(self, coordinator):
        """Malware with high anomaly should be critical."""
        result = coordinator.score(
            anomaly_score=0.9,
            classification="Malware",
            class_confidence=0.95,
        )
        
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.alert_priority == AlertPriority.P0_CRITICAL
        assert result.requires_alert
    
    def test_medium_risk_ddos(self, coordinator):
        """DDoS with moderate anomaly should be medium risk."""
        result = coordinator.score(
            anomaly_score=0.5,
            classification="DDoS",
            class_confidence=0.7,
        )
        
        assert result.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]
    
    def test_high_risk_exfiltration(self, coordinator):
        """Exfiltration should be high risk."""
        result = coordinator.score(
            anomaly_score=0.6,
            classification="Exfiltration",
            class_confidence=0.8,
        )
        
        assert result.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert result.requires_alert
    
    def test_reasoning_included(self, coordinator):
        """Result should include reasoning."""
        result = coordinator.score(
            anomaly_score=0.8,
            classification="BruteForce",
            class_confidence=0.85,
        )
        
        assert len(result.reasoning) > 0
        assert result.suggested_action != ""
    
    def test_contributing_factors(self, coordinator):
        """Result should include contributing factors."""
        result = coordinator.score(
            anomaly_score=0.7,
            classification="DDoS",
            class_confidence=0.9,
        )
        
        assert "anomaly_contribution" in result.contributing_factors
        assert "classification_contribution" in result.contributing_factors
    
    def test_low_confidence_handling(self, coordinator):
        """Low confidence should add uncertainty reasoning."""
        result = coordinator.score(
            anomaly_score=0.5,
            classification="Malware",
            class_confidence=0.3,  # Very low
        )
        
        assert any("confidence" in r.lower() for r in result.reasoning)
    
    def test_suggested_actions(self, coordinator):
        """Different threats should have different actions."""
        malware = coordinator.score(0.8, "Malware", 0.9)
        ddos = coordinator.score(0.8, "DDoS", 0.9)
        benign = coordinator.score(0.2, "Benign", 0.9)
        
        # Critical malware should require immediate action
        assert "investig" in malware.suggested_action.lower()
        assert "monitor" in benign.suggested_action.lower()


class TestEnsembleConfig:
    """Tests for ensemble configuration."""
    
    def test_default_weights(self):
        """Default weights should sum to 1."""
        config = EnsembleConfig()
        assert config.anomaly_weight + config.classification_weight == 1.0
    
    def test_conservative_defaults(self):
        """Defaults should be conservative."""
        config = EnsembleConfig()
        # Higher thresholds = more conservative
        assert config.anomaly_critical >= 0.8
        assert config.confidence_high >= 0.8


# =============================================================================
# Alert Generator Tests
# =============================================================================

class TestAlertGenerator:
    """Tests for alert generator."""
    
    @pytest.fixture
    def generator(self):
        return AlertGenerator()
    
    @pytest.fixture
    def high_risk_result(self):
        coordinator = EnsembleCoordinator()
        return coordinator.score(
            anomaly_score=0.85,
            classification="Malware",
            class_confidence=0.9,
        )
    
    @pytest.fixture
    def low_risk_result(self):
        coordinator = EnsembleCoordinator()
        return coordinator.score(
            anomaly_score=0.2,
            classification="Benign",
            class_confidence=0.95,
        )
    
    def test_generates_alert_for_high_risk(self, generator, high_risk_result):
        """Should generate alert for high risk."""
        alert = generator.generate(high_risk_result)
        
        assert alert is not None
        assert alert.priority in [AlertPriority.P0_CRITICAL, AlertPriority.P1_HIGH]
    
    def test_no_alert_for_low_risk(self, generator, low_risk_result):
        """Should not generate alert for low risk."""
        alert = generator.generate(low_risk_result)
        
        assert alert is None
    
    def test_alert_has_uuid(self, generator, high_risk_result):
        """Alert should have unique ID."""
        alert = generator.generate(high_risk_result)
        
        assert alert.alert_id
        assert len(alert.alert_id) > 10
    
    def test_alert_has_timestamp(self, generator, high_risk_result):
        """Alert should have timestamp."""
        alert = generator.generate(high_risk_result)
        
        assert alert.timestamp
        assert "T" in alert.timestamp  # ISO format
    
    def test_mitre_mapping_included(self, generator, high_risk_result):
        """Alert should include MITRE ATT&CK."""
        alert = generator.generate(high_risk_result)
        
        assert len(alert.mitre_tactics) > 0
        assert len(alert.mitre_techniques) > 0
    
    def test_source_context_included(self, generator, high_risk_result):
        """Alert should include source context."""
        context = {
            "src_ip": "192.168.1.100",
            "dst_ip": "10.0.0.1",
            "src_port": 12345,
            "dst_port": 443,
        }
        
        alert = generator.generate(high_risk_result, context)
        
        assert alert.source_ip == "192.168.1.100"
        assert alert.destination_ip == "10.0.0.1"
        assert alert.destination_port == 443
    
    def test_format_alert_summary(self, generator, high_risk_result):
        """Should format alert for display."""
        alert = generator.generate(high_risk_result)
        summary = format_alert_summary(alert)
        
        assert "ALERT" in summary
        assert alert.priority.value in summary
        assert "Risk Level" in summary


class TestMITREMapping:
    """Tests for MITRE ATT&CK mappings."""
    
    def test_ddos_mapping(self):
        """DDoS should map to Impact tactic."""
        mapping = MITRE_MAPPING[ThreatCategory.DDOS]
        assert "Impact" in mapping["tactics"]
    
    def test_bruteforce_mapping(self):
        """BruteForce should map to Credential Access."""
        mapping = MITRE_MAPPING[ThreatCategory.BRUTEFORCE]
        assert "Credential Access" in mapping["tactics"]
    
    def test_malware_mapping(self):
        """Malware should have execution techniques."""
        mapping = MITRE_MAPPING[ThreatCategory.MALWARE]
        assert "Execution" in mapping["tactics"]
    
    def test_exfiltration_mapping(self):
        """Exfiltration should map correctly."""
        mapping = MITRE_MAPPING[ThreatCategory.EXFILTRATION]
        assert "Exfiltration" in mapping["tactics"]


# =============================================================================
# Alert Model Tests
# =============================================================================

class TestAlertModel:
    """Tests for Alert model."""
    
    def test_default_status(self):
        """New alerts should have NEW status."""
        alert = Alert(
            priority=AlertPriority.P2_MEDIUM,
            risk_level=RiskLevel.HIGH,
            threat_category=ThreatCategory.DDOS,
            anomaly_score=0.7,
            classification_confidence=0.8,
            combined_risk_score=0.65,
            classification="DDoS",
            reasoning=["High anomaly"],
            suggested_action="Investigate",
        )
        
        assert alert.status == AlertStatus.NEW
    
    def test_alert_can_be_updated(self):
        """Alert should support workflow updates."""
        alert = Alert(
            priority=AlertPriority.P1_HIGH,
            risk_level=RiskLevel.CRITICAL,
            threat_category=ThreatCategory.MALWARE,
            anomaly_score=0.9,
            classification_confidence=0.95,
            combined_risk_score=0.85,
            classification="Malware",
            reasoning=["Critical threat"],
            suggested_action="Isolate",
        )
        
        alert.status = AlertStatus.INVESTIGATING
        alert.assigned_to = "analyst@soc.example"
        alert.notes.append("Investigating endpoint")
        
        assert alert.status == AlertStatus.INVESTIGATING
        assert alert.assigned_to == "analyst@soc.example"
        assert len(alert.notes) == 1
