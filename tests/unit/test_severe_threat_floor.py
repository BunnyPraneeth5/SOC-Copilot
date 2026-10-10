"""Low-confidence Malware/Exfiltration predictions are not severe threats.

With heavy class weighting the RF labels ambiguous benign flows Malware at
~55-65% confidence; Malware's severity (0.9) plus the severe-threat boost
turned those guesses into P1 alerts.
"""

import pytest

from soc_copilot.models.ensemble.coordinator import (
    THREAT_SEVERITY,
    AlertPriority,
    EnsembleConfig,
    EnsembleCoordinator,
    ThreatCategory,
)


@pytest.fixture()
def coordinator():
    return EnsembleCoordinator()


def _score(coordinator, classification, confidence, anomaly=0.9):
    return coordinator.score(
        anomaly_score=anomaly,
        classification=classification,
        class_confidence=confidence,
    )


@pytest.mark.parametrize("classification", ["Malware", "Exfiltration"])
def test_uncertain_severe_prediction_does_not_alert(coordinator, classification):
    result = _score(coordinator, classification, 0.55)
    assert result.classification == classification  # still shown as such
    assert result.contributing_factors["threat_severity"] == THREAT_SEVERITY[ThreatCategory.UNKNOWN]
    assert not result.requires_alert
    assert not any("Risk boosted" in r for r in result.reasoning)
    assert any("not treated as a severe threat" in r for r in result.reasoning)


@pytest.mark.parametrize("classification", ["Malware", "Exfiltration"])
def test_confident_severe_prediction_unchanged(coordinator, classification):
    result = _score(coordinator, classification, 0.99)
    assert result.contributing_factors["threat_severity"] == THREAT_SEVERITY[
        ThreatCategory(classification)
    ]
    assert result.alert_priority in (AlertPriority.P0_CRITICAL, AlertPriority.P1_HIGH)
    assert not any("not treated as a severe threat" in r for r in result.reasoning)


def test_floor_is_inclusive(coordinator):
    at_floor = _score(coordinator, "Malware", 0.60)
    below = _score(coordinator, "Malware", 0.59)
    assert at_floor.contributing_factors["threat_severity"] == THREAT_SEVERITY[ThreatCategory.MALWARE]
    assert below.contributing_factors["threat_severity"] == THREAT_SEVERITY[ThreatCategory.UNKNOWN]


@pytest.mark.parametrize("classification", ["BruteForce", "DDoS"])
def test_other_classes_unaffected(coordinator, classification):
    result = _score(coordinator, classification, 0.55)
    assert result.contributing_factors["threat_severity"] == THREAT_SEVERITY[
        ThreatCategory(classification)
    ]
    assert not any("not treated as a severe threat" in r for r in result.reasoning)


def test_no_p1_path_below_floor_even_with_custom_weights():
    # Weights that let an uncertain Malware guess reach High (not Critical)
    config = EnsembleConfig(anomaly_weight=0.7, classification_weight=0.3)
    result = EnsembleCoordinator(config).score(
        anomaly_score=1.0, classification="Malware", class_confidence=0.55
    )
    assert result.risk_level.value == "High"
    assert result.alert_priority == AlertPriority.P2_MEDIUM  # not the P1 severe path


def test_floor_is_configurable():
    off = EnsembleCoordinator(EnsembleConfig(severe_threat_min_confidence=0.0))
    result = off.score(anomaly_score=0.9, classification="Malware", class_confidence=0.55)
    assert result.contributing_factors["threat_severity"] == THREAT_SEVERITY[ThreatCategory.MALWARE]
