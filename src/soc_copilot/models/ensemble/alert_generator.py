"""Alert generation for SOC Copilot.

Transforms ensemble results into actionable SOC alerts with
structured metadata for SIEM integration.
"""

from datetime import datetime
from enum import Enum
from typing import Any
import uuid

from pydantic import BaseModel, Field

from soc_copilot.models.ensemble.coordinator import (
    EnsembleResult,
    RiskLevel,
    AlertPriority,
    ThreatCategory,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class AlertStatus(str, Enum):
    """Alert status lifecycle."""
    
    NEW = "New"
    ACKNOWLEDGED = "Acknowledged"
    INVESTIGATING = "Investigating"
    RESOLVED = "Resolved"
    FALSE_POSITIVE = "FalsePositive"
    ESCALATED = "Escalated"


class Alert(BaseModel):
    """SOC Alert model."""
    
    # Identity
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    # Classification
    priority: AlertPriority
    risk_level: RiskLevel
    threat_category: ThreatCategory
    
    # Scores
    anomaly_score: float
    classification_confidence: float
    combined_risk_score: float
    
    # Context
    classification: str
    reasoning: list[str]
    suggested_action: str
    
    # MITRE ATT&CK mapping (optional)
    mitre_tactics: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    
    # Source information
    source_ip: str | None = None
    destination_ip: str | None = None
    source_port: int | None = None
    destination_port: int | None = None
    protocol: str | None = None
    
    # Workflow
    status: AlertStatus = AlertStatus.NEW
    assigned_to: str | None = None
    notes: list[str] = Field(default_factory=list)
    
    # Raw data reference
    raw_record_id: str | None = None


# MITRE ATT&CK mapping for threat categories
MITRE_MAPPING = {
    ThreatCategory.DDOS: {
        "tactics": ["Impact"],
        "techniques": ["T1499 - Endpoint Denial of Service"],
    },
    ThreatCategory.BRUTEFORCE: {
        "tactics": ["Credential Access", "Initial Access"],
        "techniques": ["T1110 - Brute Force", "T1078 - Valid Accounts"],
    },
    ThreatCategory.MALWARE: {
        "tactics": ["Execution", "Persistence", "Defense Evasion"],
        "techniques": ["T1059 - Command and Scripting", "T1547 - Boot or Logon Autostart"],
    },
    ThreatCategory.EXFILTRATION: {
        "tactics": ["Exfiltration", "Collection"],
        "techniques": ["T1041 - Exfiltration Over C2", "T1560 - Archive Collected Data"],
    },
}


class AlertGenerator:
    """Generates SOC alerts from ensemble results.
    
    Transforms EnsembleResult into structured Alert objects
    ready for SIEM/SOAR integration.
    """
    
    def __init__(self, include_mitre: bool = True):
        """Initialize generator.
        
        Args:
            include_mitre: Whether to include MITRE ATT&CK mappings
        """
        self.include_mitre = include_mitre
    
    def generate(
        self,
        ensemble_result: EnsembleResult,
        source_context: dict[str, Any] | None = None,
    ) -> Alert | None:
        """Generate alert from ensemble result.
        
        Args:
            ensemble_result: Result from ensemble scoring
            source_context: Optional source data (IPs, ports, etc.)
            
        Returns:
            Alert if one should be generated, None otherwise
        """
        # Only generate alerts for medium+ priority
        if not ensemble_result.requires_alert:
            return None
        
        # Get MITRE mappings
        mitre = {}
        if self.include_mitre:
            mitre = MITRE_MAPPING.get(ensemble_result.threat_category, {})
        
        # Extract source context
        context = source_context or {}
        
        alert = Alert(
            priority=ensemble_result.alert_priority,
            risk_level=ensemble_result.risk_level,
            threat_category=ensemble_result.threat_category,
            anomaly_score=ensemble_result.anomaly_score,
            classification_confidence=ensemble_result.class_confidence,
            combined_risk_score=ensemble_result.combined_risk_score,
            classification=ensemble_result.classification,
            reasoning=ensemble_result.reasoning,
            suggested_action=ensemble_result.suggested_action,
            mitre_tactics=mitre.get("tactics", []),
            mitre_techniques=mitre.get("techniques", []),
            source_ip=context.get("src_ip"),
            destination_ip=context.get("dst_ip"),
            source_port=context.get("src_port"),
            destination_port=context.get("dst_port"),
            protocol=context.get("protocol"),
            raw_record_id=context.get("record_id"),
        )
        
        logger.info(
            "alert_generated",
            alert_id=alert.alert_id,
            priority=alert.priority.value,
            threat=alert.threat_category.value,
        )
        
        return alert
    
    def generate_batch(
        self,
        results: list[tuple[EnsembleResult, dict | None]],
    ) -> list[Alert]:
        """Generate alerts for batch of results.
        
        Args:
            results: List of (EnsembleResult, context) tuples
            
        Returns:
            List of generated alerts
        """
        alerts = []
        for ensemble_result, context in results:
            alert = self.generate(ensemble_result, context)
            if alert:
                alerts.append(alert)
        
        logger.info(
            "batch_alerts_generated",
            input_count=len(results),
            alert_count=len(alerts),
        )
        
        return alerts


def format_alert_summary(alert: Alert) -> str:
    """Format alert for human-readable display.
    
    Args:
        alert: Alert to format
        
    Returns:
        Formatted string summary
    """
    lines = [
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║ ALERT: {alert.priority.value} - {alert.threat_category.value}",
        f"╟──────────────────────────────────────────────────────────────╢",
        f"║ ID: {alert.alert_id[:8]}...",
        f"║ Time: {alert.timestamp}",
        f"║ Risk Level: {alert.risk_level.value}",
        f"║ Risk Score: {alert.combined_risk_score:.2f}",
        f"╟──────────────────────────────────────────────────────────────╢",
        f"║ Classification: {alert.classification} ({alert.classification_confidence:.1%})",
        f"║ Anomaly Score: {alert.anomaly_score:.2f}",
    ]
    
    if alert.source_ip or alert.destination_ip:
        lines.append(f"╟──────────────────────────────────────────────────────────────╢")
        if alert.source_ip:
            lines.append(f"║ Source: {alert.source_ip}:{alert.source_port or 'N/A'}")
        if alert.destination_ip:
            lines.append(f"║ Destination: {alert.destination_ip}:{alert.destination_port or 'N/A'}")
    
    if alert.reasoning:
        lines.append(f"╟──────────────────────────────────────────────────────────────╢")
        lines.append(f"║ Reasoning:")
        for reason in alert.reasoning:
            lines.append(f"║   • {reason}")
    
    lines.append(f"╟──────────────────────────────────────────────────────────────╢")
    lines.append(f"║ Action: {alert.suggested_action}")
    
    if alert.mitre_techniques:
        lines.append(f"╟──────────────────────────────────────────────────────────────╢")
        lines.append(f"║ MITRE ATT&CK: {', '.join(alert.mitre_techniques[:2])}")
    
    lines.append(f"╚══════════════════════════════════════════════════════════════╝")
    
    return "\n".join(lines)
