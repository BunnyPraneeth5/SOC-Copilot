"""Confidently classified known attacks alert even at Medium risk.

Port scans, brute force and many DoS flows look normal to the Isolation
Forest, so classifier and anomaly score together stay at Medium risk and
no alert was raised, even at 99% classifier confidence.
"""

import pytest

from soc_copilot.models.ensemble.coordinator import (
    AlertPriority,
    EnsembleConfig,
    EnsembleCoordinator,
    RiskLevel,
)


@pytest.fixture()
def coordinator():
    return EnsembleCoordinator()


def _score(coordinator, classification, confidence, anomaly=0.45):
    return coordinator.score(
        anomaly_score=anomaly,
        classification=classification,
        class_confidence=confidence,
    )


@pytest.mark.parametrize("classification", ["BruteForce", "DDoS"])
def test_confident_known_attack_alerts_at_medium_risk(coordinator, classification):
    result = _score(coordinator, classification, 0.99)
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.alert_priority == AlertPriority.P2_MEDIUM
    assert result.requires_alert
    assert any("does not look unusual" in r for r in result.reasoning)


def test_threshold_is_inclusive(coordinator):
    assert _score(coordinator, "BruteForce", 0.95).requires_alert
    assert not _score(coordinator, "BruteForce", 0.94).requires_alert


def test_less_confident_attack_unchanged(coordinator):
    result = _score(coordinator, "DDoS", 0.80)
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.alert_priority == AlertPriority.P3_LOW
    assert not result.requires_alert
    assert not any("does not look unusual" in r for r in result.reasoning)


@pytest.mark.parametrize("classification", ["Benign", "Unknown", "SomethingNew"])
def test_benign_and_unknown_never_use_the_rule(coordinator, classification):
    result = _score(coordinator, classification, 0.99)
    assert result.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert not result.requires_alert
    assert not any("does not look unusual" in r for r in result.reasoning)


def test_low_risk_attack_not_promoted(coordinator):
    # DDoS at 99% with a very normal anomaly score stays below Medium
    result = _score(coordinator, "DDoS", 0.99, anomaly=0.0)
    assert result.risk_level == RiskLevel.LOW
    assert not result.requires_alert


def test_high_and_critical_priorities_unchanged(coordinator):
    assert _score(coordinator, "Exfiltration", 0.99, anomaly=0.99).alert_priority == AlertPriority.P0_CRITICAL
    high = _score(coordinator, "BruteForce", 0.99, anomaly=0.8)
    assert high.risk_level == RiskLevel.HIGH
    assert high.alert_priority == AlertPriority.P2_MEDIUM
    assert not any("does not look unusual" in r for r in high.reasoning)


def test_threshold_is_configurable():
    strict = EnsembleCoordinator(EnsembleConfig(confident_attack_min_confidence=1.01))
    assert not _score(strict, "BruteForce", 0.99).requires_alert
