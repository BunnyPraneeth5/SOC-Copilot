"""Temporal feature extractor.

Extracts time-based features from log timestamps including
hour of day, day of week, time deltas, and temporal patterns.
"""

from datetime import datetime
from typing import Any

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class TemporalFeatureConfig(BaseModel):
    """Configuration for temporal feature extraction."""
    
    # Timestamp field to use
    timestamp_field: str = "timestamp_normalized"
    
    # Entity field for computing time deltas between entity actions
    entity_field: str = "src_ip"
    
    # Whether to compute cyclical features (sin/cos encoding)
    use_cyclical: bool = True
    
    # Business hours definition (for is_business_hours feature)
    business_hour_start: int = 9
    business_hour_end: int = 17
    
    # Weekend days (0=Monday, 6=Sunday)
    weekend_days: list[int] = Field(default_factory=lambda: [5, 6])
    
    # Prefix for generated feature names
    feature_prefix: str = "time"


class TemporalFeatureExtractor(BaseFeatureExtractor):
    """Extracts temporal features from timestamps.
    
    Features computed:
    - Hour of day (0-23) with optional cyclical encoding
    - Day of week (0-6) with optional cyclical encoding
    - Is weekend (0/1)
    - Is business hours (0/1)
    - Time since previous event (same entity)
    - Time since previous event (global)
    - Events per hour/day rolling counts
    
    All features are numeric and deterministic.
    """
    
    def __init__(self, config: TemporalFeatureConfig | None = None):
        """Initialize extractor.
        
        Args:
            config: Temporal feature configuration
        """
        super().__init__(config)
        self.config = config or TemporalFeatureConfig()
        
        # Learning state
        self._baseline_hour_dist: np.ndarray | None = None
        self._baseline_dow_dist: np.ndarray | None = None
    
    @property
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get feature definitions."""
        definitions = []
        prefix = self.config.feature_prefix
        
        # Hour features
        if self.config.use_cyclical:
            definitions.extend([
                FeatureDefinition(
                    name=f"{prefix}_hour_sin",
                    description="Sine of hour (cyclical encoding)",
                    feature_type=FeatureType.TEMPORAL,
                    min_value=-1,
                    max_value=1,
                ),
                FeatureDefinition(
                    name=f"{prefix}_hour_cos",
                    description="Cosine of hour (cyclical encoding)",
                    feature_type=FeatureType.TEMPORAL,
                    min_value=-1,
                    max_value=1,
                ),
            ])
        else:
            definitions.append(FeatureDefinition(
                name=f"{prefix}_hour",
                description="Hour of day (0-23)",
                feature_type=FeatureType.TEMPORAL,
                numeric_type="int64",
                min_value=0,
                max_value=23,
            ))
        
        # Day of week features
        if self.config.use_cyclical:
            definitions.extend([
                FeatureDefinition(
                    name=f"{prefix}_dow_sin",
                    description="Sine of day of week (cyclical encoding)",
                    feature_type=FeatureType.TEMPORAL,
                    min_value=-1,
                    max_value=1,
                ),
                FeatureDefinition(
                    name=f"{prefix}_dow_cos",
                    description="Cosine of day of week (cyclical encoding)",
                    feature_type=FeatureType.TEMPORAL,
                    min_value=-1,
                    max_value=1,
                ),
            ])
        else:
            definitions.append(FeatureDefinition(
                name=f"{prefix}_day_of_week",
                description="Day of week (0=Monday, 6=Sunday)",
                feature_type=FeatureType.TEMPORAL,
                numeric_type="int64",
                min_value=0,
                max_value=6,
            ))
        
        # Binary temporal features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_is_weekend",
                description="Is weekend (1) or weekday (0)",
                feature_type=FeatureType.TEMPORAL,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
            FeatureDefinition(
                name=f"{prefix}_is_business_hours",
                description="Is during business hours (1) or not (0)",
                feature_type=FeatureType.TEMPORAL,
                numeric_type="int64",
                min_value=0,
                max_value=1,
            ),
        ])
        
        # Time delta features
        definitions.extend([
            FeatureDefinition(
                name=f"{prefix}_delta_entity_seconds",
                description="Seconds since previous event from same entity",
                feature_type=FeatureType.TEMPORAL,
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_delta_global_seconds",
                description="Seconds since previous event globally",
                feature_type=FeatureType.TEMPORAL,
                min_value=0,
            ),
            FeatureDefinition(
                name=f"{prefix}_events_per_hour",
                description="Rolling event count for entity in past hour",
                feature_type=FeatureType.TEMPORAL,
                min_value=0,
            ),
        ])
        
        return definitions
    
    def fit(self, df: pd.DataFrame) -> None:
        """Learn baseline temporal patterns from training data.
        
        Args:
            df: Training DataFrame
        """
        ts_field = self.config.timestamp_field
        
        if ts_field in df.columns:
            try:
                timestamps = pd.to_datetime(df[ts_field], errors="coerce")
                valid_ts = timestamps.dropna()
                
                if len(valid_ts) > 0:
                    # Learn hour distribution
                    hours = valid_ts.dt.hour
                    hour_counts = hours.value_counts().reindex(range(24), fill_value=0)
                    self._baseline_hour_dist = (hour_counts / hour_counts.sum()).values
                    
                    # Learn day of week distribution
                    dows = valid_ts.dt.dayofweek
                    dow_counts = dows.value_counts().reindex(range(7), fill_value=0)
                    self._baseline_dow_dist = (dow_counts / dow_counts.sum()).values
            except Exception as e:
                logger.warning("temporal_fit_error", error=str(e))
        
        self._fitted = True
        
        logger.info(
            "temporal_features_fit",
            has_hour_baseline=self._baseline_hour_dist is not None,
        )
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract temporal features.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with temporal features added
        """
        result = df.copy()
        prefix = self.config.feature_prefix
        ts_field = self.config.timestamp_field
        entity_field = self.config.entity_field
        
        # Initialize features with defaults using proper dtypes
        for feat_def in self.feature_definitions:
            if feat_def.numeric_type == "int64":
                result[feat_def.name] = int(feat_def.default_value)
            else:
                result[feat_def.name] = float(feat_def.default_value)
        
        if ts_field not in result.columns:
            logger.warning("timestamp_field_missing", field=ts_field)
            return result
        
        # Parse timestamps
        timestamps = pd.to_datetime(result[ts_field], errors="coerce")
        valid_mask = ~timestamps.isna()
        
        if valid_mask.sum() == 0:
            logger.warning("no_valid_timestamps")
            return result
        
        # Extract basic temporal components
        hours = timestamps.dt.hour
        dows = timestamps.dt.dayofweek
        
        # Hour features
        if self.config.use_cyclical:
            result.loc[valid_mask, f"{prefix}_hour_sin"] = np.sin(
                2 * np.pi * hours[valid_mask] / 24
            )
            result.loc[valid_mask, f"{prefix}_hour_cos"] = np.cos(
                2 * np.pi * hours[valid_mask] / 24
            )
        else:
            result.loc[valid_mask, f"{prefix}_hour"] = hours[valid_mask]
        
        # Day of week features
        if self.config.use_cyclical:
            result.loc[valid_mask, f"{prefix}_dow_sin"] = np.sin(
                2 * np.pi * dows[valid_mask] / 7
            )
            result.loc[valid_mask, f"{prefix}_dow_cos"] = np.cos(
                2 * np.pi * dows[valid_mask] / 7
            )
        else:
            result.loc[valid_mask, f"{prefix}_day_of_week"] = dows[valid_mask]
        
        # Weekend flag
        result.loc[valid_mask, f"{prefix}_is_weekend"] = dows[valid_mask].isin(
            self.config.weekend_days
        ).astype(int)
        
        # Business hours flag
        is_business = (
            (hours >= self.config.business_hour_start) &
            (hours < self.config.business_hour_end) &
            (~dows.isin(self.config.weekend_days))
        )
        result.loc[valid_mask, f"{prefix}_is_business_hours"] = is_business[valid_mask].astype(int)
        
        # Time deltas - need to sort by timestamp first
        result_sorted = result.sort_values(ts_field).copy()
        sorted_timestamps = pd.to_datetime(result_sorted[ts_field], errors="coerce")
        
        # Global time delta
        global_deltas = sorted_timestamps.diff().dt.total_seconds().fillna(0)
        result_sorted[f"{prefix}_delta_global_seconds"] = global_deltas.clip(lower=0)
        
        # Entity-specific time delta
        if entity_field in result_sorted.columns:
            # Compute time deltas within each entity group
            result_sorted[f"{prefix}_delta_entity_seconds"] = 0.0
            
            for entity in result_sorted[entity_field].unique():
                entity_mask = result_sorted[entity_field] == entity
                entity_ts = sorted_timestamps[entity_mask]
                entity_deltas = entity_ts.diff().dt.total_seconds().fillna(0)
                result_sorted.loc[entity_mask, f"{prefix}_delta_entity_seconds"] = entity_deltas.clip(lower=0).values
            
            # Events per hour rolling window
            result_sorted[f"{prefix}_events_per_hour"] = 0
            
            # Only compute for smaller datasets to avoid performance issues
            if len(result_sorted) <= 10000:
                for entity in result_sorted[entity_field].unique():
                    entity_mask = result_sorted[entity_field] == entity
                    entity_indices = result_sorted.index[entity_mask]
                    entity_ts = sorted_timestamps[entity_mask]
                    
                    counts = []
                    ts_list = entity_ts.tolist()
                    for i, t in enumerate(ts_list):
                        if pd.notna(t):
                            hour_ago = t - pd.Timedelta(hours=1)
                            count = sum(1 for prev_t in ts_list[:i+1] if pd.notna(prev_t) and prev_t >= hour_ago)
                            counts.append(count)
                        else:
                            counts.append(0)
                    
                    result_sorted.loc[entity_indices, f"{prefix}_events_per_hour"] = counts
        
        # Restore original order
        result = result_sorted.reindex(df.index)
        
        self._validate_output(result[self.feature_names])
        
        logger.info(
            "temporal_features_extracted",
            records=len(result),
            features=len(self.feature_names),
        )
        
        return result
    
    def get_baseline_distributions(self) -> dict[str, np.ndarray | None]:
        """Get learned baseline distributions.
        
        Returns:
            Dict with hour and day-of-week distributions
        """
        return {
            "hour": self._baseline_hour_dist,
            "day_of_week": self._baseline_dow_dist,
        }
