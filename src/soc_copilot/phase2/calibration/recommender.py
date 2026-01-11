"""Phase-2 Sprint-10: Threshold Calibration (Manual Approval Required).

Generates threshold recommendations based on drift and feedback data.
NEVER applies changes automatically - requires explicit human approval.
"""

import shutil
import yaml
from datetime import datetime, timezone
from pathlib import Path

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class CalibrationRecommendation:
    """Threshold calibration recommendation."""
    
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.recommendations = {}
        self.justifications = {}
        self.current_values = {}
    
    def add_recommendation(self, path: str, current: float, recommended: float, justification: str):
        """Add a threshold recommendation.
        
        Args:
            path: Config path (e.g., "anomaly.high_threshold")
            current: Current threshold value
            recommended: Recommended threshold value
            justification: Reason for recommendation
        """
        self.recommendations[path] = recommended
        self.current_values[path] = current
        self.justifications[path] = justification
    
    def has_recommendations(self) -> bool:
        """Check if any recommendations exist."""
        return len(self.recommendations) > 0
    
    def to_dict(self):
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "recommendations": [
                {
                    "path": path,
                    "current": self.current_values[path],
                    "recommended": value,
                    "change": value - self.current_values[path],
                    "justification": self.justifications[path]
                }
                for path, value in self.recommendations.items()
            ]
        }


class ThresholdCalibrator:
    """Manual threshold calibration with approval workflow."""
    
    def __init__(self, config_path: str = "config/thresholds.yaml"):
        """Initialize calibrator.
        
        Args:
            config_path: Path to thresholds config file
        """
        self.config_path = Path(config_path)
        self.backup_dir = self.config_path.parent / "backups"
    
    def load_current_thresholds(self) -> dict:
        """Load current threshold configuration."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")
        
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    def generate_recommendations(self, drift_stats: dict = None, feedback_stats: dict = None) -> CalibrationRecommendation:
        """Generate threshold recommendations based on drift and feedback.
        
        Args:
            drift_stats: Drift statistics from DriftMonitor
            feedback_stats: Feedback statistics from FeedbackStore
            
        Returns:
            CalibrationRecommendation object
        """
        current = self.load_current_thresholds()
        rec = CalibrationRecommendation()
        
        # Conservative adjustments based on drift
        if drift_stats:
            anomaly_mean = drift_stats.get("anomaly_score_mean", 0)
            anomaly_change = drift_stats.get("anomaly_change_pct", 0)
            
            # If anomaly scores drifting high, suggest raising threshold slightly
            if anomaly_change > 25 and anomaly_mean > 0.6:
                current_high = current.get("anomaly", {}).get("high_threshold", 0.7)
                # Conservative: max 0.05 increase
                suggested = min(current_high + 0.05, 0.85)
                if suggested != current_high:
                    rec.add_recommendation(
                        "anomaly.high_threshold",
                        current_high,
                        suggested,
                        f"Anomaly scores increased {anomaly_change:.1f}% (mean={anomaly_mean:.2f}). Raising threshold to reduce false positives."
                    )
        
        # Adjustments based on feedback
        if feedback_stats:
            total = feedback_stats.get("total_count", 0)
            reject = feedback_stats.get("reject_count", 0)
            
            # If high rejection rate, suggest raising thresholds
            if total >= 20 and reject / total > 0.4:
                current_crit = current.get("priority", {}).get("critical", 0.85)
                suggested = min(current_crit + 0.03, 0.95)
                if suggested != current_crit:
                    rec.add_recommendation(
                        "priority.critical",
                        current_crit,
                        suggested,
                        f"High rejection rate ({reject}/{total} = {reject/total:.1%}). Raising critical threshold to reduce false positives."
                    )
        
        return rec
    
    def preview_changes(self, recommendation: CalibrationRecommendation) -> str:
        """Generate preview diff of proposed changes.
        
        Args:
            recommendation: Calibration recommendation
            
        Returns:
            Human-readable diff string
        """
        if not recommendation.has_recommendations():
            return "No threshold changes recommended."
        
        lines = ["Proposed Threshold Changes:", "=" * 60]
        
        for path, recommended in recommendation.recommendations.items():
            current = recommendation.current_values[path]
            change = recommended - current
            justification = recommendation.justifications[path]
            
            lines.append(f"\n{path}:")
            lines.append(f"  Current:     {current:.3f}")
            lines.append(f"  Recommended: {recommended:.3f} ({change:+.3f})")
            lines.append(f"  Reason: {justification}")
        
        return "\n".join(lines)
    
    def create_backup(self) -> Path:
        """Create timestamped backup of current config.
        
        Returns:
            Path to backup file
        """
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:21]  # Include microseconds
        backup_path = self.backup_dir / f"thresholds_{timestamp}.yaml"
        
        shutil.copy2(self.config_path, backup_path)
        logger.info("config_backup_created", backup_path=str(backup_path))
        
        return backup_path
    
    def apply_recommendations(self, recommendation: CalibrationRecommendation, confirmed: bool = False):
        """Apply threshold recommendations to config file.
        
        Args:
            recommendation: Calibration recommendation
            confirmed: Must be True to apply changes
            
        Raises:
            ValueError: If not confirmed
        """
        if not confirmed:
            raise ValueError("Calibration requires explicit confirmation. Use --confirm flag.")
        
        if not recommendation.has_recommendations():
            logger.info("no_recommendations_to_apply")
            return
        
        # Create backup first
        backup_path = self.create_backup()
        
        # Load current config
        config = self.load_current_thresholds()
        
        # Apply recommendations
        for path, value in recommendation.recommendations.items():
            parts = path.split(".")
            current = config
            for part in parts[:-1]:
                current = current[part]
            current[parts[-1]] = value
        
        # Write updated config
        with open(self.config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        
        logger.info("thresholds_calibrated", 
                   count=len(recommendation.recommendations),
                   backup=str(backup_path))
    
    def list_backups(self) -> list[Path]:
        """List available backup files.
        
        Returns:
            List of backup file paths, newest first
        """
        if not self.backup_dir.exists():
            return []
        
        backups = sorted(
            self.backup_dir.glob("thresholds_*.yaml"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return backups
    
    def restore_backup(self, backup_path: Path):
        """Restore config from backup.
        
        Args:
            backup_path: Path to backup file
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")
        
        # Create backup of current before restoring
        self.create_backup()
        
        # Restore
        shutil.copy2(backup_path, self.config_path)
        logger.info("config_restored", backup=str(backup_path))
