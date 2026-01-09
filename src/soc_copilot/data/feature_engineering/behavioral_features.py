"""Behavioral feature extractor.

Computes features based on entity behavior patterns, session analysis,
and deviation from established baselines.
"""

from typing import Any
from collections import defaultdict

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
    safe_divide,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class BehavioralFeatureConfig(BaseModel):
    """Configuration for behavioral feature extraction."""
    
    # Entity field to analyze behavior for
    entity_field: str = "src_ip"
    
    # Timestamp field for session analysis
    timestamp_field: str = "timestamp_normalized"
    
    # Session timeout in seconds (gap > this = new session)
    session_timeout: int = 1800  # 30 minutes
    
    # Fields to track for behavioral deviation
    action_field: str = "action"
    
    # Numeric fields to track mean deviation
    deviation_fields: list[str] = Field(
        default_factory=lambda: ["bytes_total", "dst_port"]
    )
    
    # Number of standard deviations for anomaly flagging
    deviation_threshold: float = 2.0
    
    # Prefix for generated feature names
    feature_prefix: str = "behav"


class BehavioralFeatureExtractor(BaseFeatureExtractor):
    """Extracts behavioral features from log data.
    
    Features computed per entity:
    - Session count and duration
    - Actions per session
    - Deviation from baseline activity
    - First-time action/destination flags
    - Behavior change indicators
    
    All features are numeric and deterministic.
    """
    
    def __init__(self, config: BehavioralFeatureConfig | None = None):
        """Initialize extractor.
        
        Args:
            config: Behavioral feature configuration
        """
        super().__init__(config)
        self.config = config or BehavioralFeatureConfig()
        
        # Learning state - entity baselines
        self._entity_actions: dict[str, set[str]] = defaultdict(set)
        self._entity_destinations: dict[str, set[str]] = defaultdict(set)
        self._entity_field_means: dict[str, dict[str, float]] = defaultdict(dict)
        self._entity_field_stds: dict[str, dict[str, float]] = defaultdict(dict)
    
    @property
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get feature definitions."""
        definitions = []
        prefix = self.config.feature_prefix
        
        # Session features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_session_id",
                description="Session number for this entity",
                feature_type=FeatureType.BEHAVIORAL,
                numeric_type="int64",
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_events_in_session",
                description="Number of events in current session",
                feature_type=FeatureType.BEHAVIORAL,
                numeric_type="int64",
                min_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_session_duration_seconds",
                description="Duration of current session in seconds",
                feature_type=FeatureType.BEHAVIORAL,
                min_value=0,
            ),
        ])
        
        # First-time flags
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_is_new_action",
                description="First time seeing this action from entity (1/0)",
                feature_type=FeatureType.BEHAVIORAL,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_is_new_destination",
                description="First time seeing this destination from entity (1/0)",
                feature_type=FeatureType.BEHAVIORAL,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
        ])
        
        # Deviation features
        for field in self.config.deviation_fields:
            definitions.extend([
                FeatureDefinition(
                    name=f"{prefix}_{field}_zscore",
                    description=f"Z-score deviation of {field} from entity baseline",
                    feature_type=FeatureType.BEHAVIORAL,
                ),
                FeatureDefinition(
                    name=f"{prefix}_{field}_is_anomalous",
                    description=f"Is {field} anomalously different from baseline (1/0)",
                    feature_type=FeatureType.BEHAVIORAL,
                    numeric_type="int64",
                    min_value=0,
                    max_value=1,
                ),
            ])
        
        # Aggregate deviation
        definitions.append(FeatureDefinition(
            name=f"{prefix}_deviation_score",
            description="Aggregate behavioral deviation score",
            feature_type=FeatureType.BEHAVIORAL,
            min_value=0,
        ))
        
        return definitions
    
    def fit(self, df: pd.DataFrame) -> None:
        """Learn entity baselines from training data.
        
        Args:
            df: Training DataFrame
        """
        entity_field = self.config.entity_field
        action_field = self.config.action_field
        
        if entity_field not in df.columns:
            logger.warning("entity_field_missing", field=entity_field)
            self._fitted = True
            return
        
        # Group by entity
        grouped = df.groupby(entity_field)
        
        for entity, group in grouped:
            entity_key = str(entity)
            
            # Track known actions
            if action_field in group.columns:
                self._entity_actions[entity_key] = set(group[action_field].dropna().unique())
            
            # Track known destinations
            if "dst_ip" in group.columns:
                self._entity_destinations[entity_key] = set(group["dst_ip"].dropna().unique())
            
            # Compute baselines for deviation fields
            for field in self.config.deviation_fields:
                if field in group.columns:
                    values = group[field].dropna()
                    if len(values) > 0:
                        self._entity_field_means[entity_key][field] = float(values.mean())
                        self._entity_field_stds[entity_key][field] = (
                            float(values.std()) if len(values) > 1 else 0.0
                        )
        
        self._fitted = True
        
        logger.info(
            "behavioral_features_fit",
            entities=len(self._entity_actions),
        )
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract behavioral features.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with behavioral features added
        """
        result = df.copy()
        prefix = self.config.feature_prefix
        entity_field = self.config.entity_field
        ts_field = self.config.timestamp_field
        action_field = self.config.action_field
        
        # Initialize features with defaults using proper dtypes
        for feat_def in self.feature_definitions:
            if feat_def.numeric_type == "int64":
                result[feat_def.name] = int(feat_def.default_value)
            else:
                result[feat_def.name] = float(feat_def.default_value)
        
        if entity_field not in result.columns:
            logger.warning("entity_field_missing", field=entity_field)
            return result
        
        # Sort by timestamp for session detection
        if ts_field in result.columns:
            result_sorted = result.sort_values(ts_field).copy()
        else:
            result_sorted = result.copy()
        
        # Track running state for session detection
        entity_last_time: dict[str, pd.Timestamp] = {}
        entity_session_id: dict[str, int] = defaultdict(int)
        entity_session_start: dict[str, pd.Timestamp] = {}
        entity_session_events: dict[str, int] = defaultdict(int)
        entity_seen_actions: dict[str, set[str]] = defaultdict(set)
        entity_seen_dests: dict[str, set[str]] = defaultdict(set)
        
        # Process each record
        for idx in result_sorted.index:
            entity = str(result_sorted.at[idx, entity_field])
            
            # Parse timestamp
            current_time = None
            if ts_field in result_sorted.columns:
                try:
                    current_time = pd.to_datetime(result_sorted.at[idx, ts_field])
                except Exception:
                    pass
            
            # Session detection
            if current_time is not None and entity in entity_last_time:
                time_gap = (current_time - entity_last_time[entity]).total_seconds()
                if time_gap > self.config.session_timeout:
                    entity_session_id[entity] += 1
                    entity_session_start[entity] = current_time
                    entity_session_events[entity] = 0
            elif current_time is not None and entity not in entity_session_start:
                entity_session_start[entity] = current_time
            
            entity_session_events[entity] += 1
            if current_time is not None:
                entity_last_time[entity] = current_time
            
            # Session features
            result_sorted.at[idx, f"{prefix}_session_id"] = entity_session_id[entity]
            result_sorted.at[idx, f"{prefix}_events_in_session"] = entity_session_events[entity]
            
            if current_time is not None and entity in entity_session_start:
                duration = (current_time - entity_session_start[entity]).total_seconds()
                result_sorted.at[idx, f"{prefix}_session_duration_seconds"] = max(0, duration)
            
            # First-time action detection
            if action_field in result_sorted.columns:
                action = result_sorted.at[idx, action_field]
                if pd.notna(action):
                    action_str = str(action)
                    baseline_actions = self._entity_actions.get(entity, set())
                    if action_str not in baseline_actions and action_str not in entity_seen_actions[entity]:
                        result_sorted.at[idx, f"{prefix}_is_new_action"] = 1
                    entity_seen_actions[entity].add(action_str)
            
            # First-time destination detection
            if "dst_ip" in result_sorted.columns:
                dst = result_sorted.at[idx, "dst_ip"]
                if pd.notna(dst):
                    dst_str = str(dst)
                    baseline_dests = self._entity_destinations.get(entity, set())
                    if dst_str not in baseline_dests and dst_str not in entity_seen_dests[entity]:
                        result_sorted.at[idx, f"{prefix}_is_new_destination"] = 1
                    entity_seen_dests[entity].add(dst_str)
            
            # Deviation features
            deviation_scores = []
            for field in self.config.deviation_fields:
                if field in result_sorted.columns:
                    value = result_sorted.at[idx, field]
                    if pd.notna(value):
                        try:
                            value = float(value)
                            mean = self._entity_field_means.get(entity, {}).get(field, value)
                            std = self._entity_field_stds.get(entity, {}).get(field, 0)
                            
                            if std > 0:
                                zscore = (value - mean) / std
                            else:
                                zscore = 0.0
                            
                            result_sorted.at[idx, f"{prefix}_{field}_zscore"] = zscore
                            
                            is_anomalous = abs(zscore) > self.config.deviation_threshold
                            result_sorted.at[idx, f"{prefix}_{field}_is_anomalous"] = int(is_anomalous)
                            
                            deviation_scores.append(abs(zscore))
                        except (ValueError, TypeError):
                            pass
            
            # Aggregate deviation score
            if deviation_scores:
                result_sorted.at[idx, f"{prefix}_deviation_score"] = np.mean(deviation_scores)
        
        # Restore original order
        result = result_sorted.reindex(df.index)
        
        self._validate_output(result[self.feature_names])
        
        logger.info(
            "behavioral_features_extracted",
            records=len(result),
            features=len(self.feature_names),
        )
        
        return result
    
    def get_entity_baselines(self) -> dict[str, dict[str, Any]]:
        """Get learned entity baselines.
        
        Returns:
            Dict of entity -> baseline info
        """
        baselines = {}
        for entity in set(self._entity_actions.keys()) | set(self._entity_field_means.keys()):
            baselines[entity] = {
                "known_actions": list(self._entity_actions.get(entity, set())),
                "known_destinations": list(self._entity_destinations.get(entity, set())),
                "field_means": self._entity_field_means.get(entity, {}),
                "field_stds": self._entity_field_stds.get(entity, {}),
            }
        return baselines
