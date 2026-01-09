"""Statistical feature extractor.

Computes statistical aggregations per entity (e.g., per source IP)
including counts, means, standard deviations, percentiles, and entropy.
"""

from typing import Any
from collections import Counter
import math

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
    entropy,
    safe_divide,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class StatisticalFeatureConfig(BaseModel):
    """Configuration for statistical feature extraction."""
    
    # Entity field to group by (e.g., "src_ip" for per-IP stats)
    entity_field: str = "src_ip"
    
    # Numeric fields to compute statistics on
    numeric_fields: list[str] = Field(
        default_factory=lambda: ["bytes_total", "bytes_in", "bytes_out"]
    )
    
    # Categorical fields to compute entropy on
    categorical_fields: list[str] = Field(
        default_factory=lambda: ["dst_ip", "dst_port", "action", "protocol"]
    )
    
    # Percentiles to compute
    percentiles: list[int] = Field(default_factory=lambda: [25, 50, 75, 95])
    
    # Time window for rolling statistics (in records, not time)
    window_size: int = 100
    
    # Prefix for generated feature names
    feature_prefix: str = "stat"


class StatisticalFeatureExtractor(BaseFeatureExtractor):
    """Extracts statistical features from log data.
    
    Features computed per entity:
    - Count of records
    - Mean, stddev, min, max of numeric fields
    - Percentiles (25th, 50th, 75th, 95th)
    - Entropy of categorical field distributions
    - Unique value counts for categorical fields
    
    All features are numeric and deterministic.
    """
    
    def __init__(self, config: StatisticalFeatureConfig | None = None):
        """Initialize extractor.
        
        Args:
            config: Statistical feature configuration
        """
        super().__init__(config)
        self.config = config or StatisticalFeatureConfig()
        
        # Learning state
        self._global_stats: dict[str, dict[str, float]] = {}
        self._entity_baselines: dict[str, dict[str, float]] = {}
    
    @property
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get feature definitions."""
        definitions = []
        prefix = self.config.feature_prefix
        
        # Count feature
        definitions.append(FeatureDefinition(
            name=f"{prefix}_record_count",
            description="Number of records for this entity in window",
            feature_type=FeatureType.STATISTICAL,
            min_value=0,
        ))
        
        # Numeric field statistics
        for field in self.config.numeric_fields:
            definitions.extend([
                FeatureDefinition(
                    name=f"{prefix}_{field}_mean",
                    description=f"Mean of {field}",
                    feature_type=FeatureType.STATISTICAL,
                ),
                FeatureDefinition(
                    name=f"{prefix}_{field}_std",
                    description=f"Standard deviation of {field}",
                    feature_type=FeatureType.STATISTICAL,
                    min_value=0,
                ),
                FeatureDefinition(
                    name=f"{prefix}_{field}_min",
                    description=f"Minimum of {field}",
                    feature_type=FeatureType.STATISTICAL,
                ),
                FeatureDefinition(
                    name=f"{prefix}_{field}_max",
                    description=f"Maximum of {field}",
                    feature_type=FeatureType.STATISTICAL,
                ),
            ])
            
            # Percentile features
            for p in self.config.percentiles:
                definitions.append(FeatureDefinition(
                    name=f"{prefix}_{field}_p{p}",
                    description=f"{p}th percentile of {field}",
                    feature_type=FeatureType.STATISTICAL,
                ))
        
        # Categorical field features
        for field in self.config.categorical_fields:
            definitions.extend([
                FeatureDefinition(
                    name=f"{prefix}_{field}_unique",
                    description=f"Unique count of {field}",
                    feature_type=FeatureType.STATISTICAL,
                    numeric_type="int64",
                    min_value=0,
                ),
                FeatureDefinition(
                    name=f"{prefix}_{field}_entropy",
                    description=f"Shannon entropy of {field} distribution",
                    feature_type=FeatureType.STATISTICAL,
                    min_value=0,
                ),
            ])
        
        return definitions
    
    def fit(self, df: pd.DataFrame) -> None:
        """Learn global statistics from training data.
        
        Args:
            df: Training DataFrame
        """
        self._global_stats = {}
        
        # Compute global stats for numeric fields
        for field in self.config.numeric_fields:
            if field in df.columns:
                values = df[field].dropna()
                if len(values) > 0:
                    self._global_stats[field] = {
                        "mean": float(values.mean()),
                        "std": float(values.std()) if len(values) > 1 else 0.0,
                        "min": float(values.min()),
                        "max": float(values.max()),
                    }
        
        # Compute per-entity baselines
        if self.config.entity_field in df.columns:
            grouped = df.groupby(self.config.entity_field)
            
            for entity, group in grouped:
                entity_stats = {}
                for field in self.config.numeric_fields:
                    if field in group.columns:
                        values = group[field].dropna()
                        if len(values) > 0:
                            entity_stats[f"{field}_mean"] = float(values.mean())
                
                self._entity_baselines[str(entity)] = entity_stats
        
        self._fitted = True
        
        logger.info(
            "statistical_features_fit",
            entities=len(self._entity_baselines),
            numeric_fields=len(self.config.numeric_fields),
        )
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract statistical features.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with statistical features added
        """
        result = df.copy()
        prefix = self.config.feature_prefix
        entity_field = self.config.entity_field
        
        # Initialize feature columns
        for feat_def in self.feature_definitions:
            result[feat_def.name] = feat_def.default_value
        
        if entity_field not in result.columns:
            logger.warning(
                "entity_field_missing",
                field=entity_field,
            )
            return result
        
        # Group by entity
        grouped = result.groupby(entity_field)
        
        # Compute features per entity
        for entity, indices in grouped.groups.items():
            entity_data = result.loc[indices]
            
            # Record count
            result.loc[indices, f"{prefix}_record_count"] = len(entity_data)
            
            # Numeric field statistics
            for field in self.config.numeric_fields:
                if field in entity_data.columns:
                    values = entity_data[field].dropna().values
                    
                    if len(values) > 0:
                        result.loc[indices, f"{prefix}_{field}_mean"] = float(np.mean(values))
                        result.loc[indices, f"{prefix}_{field}_std"] = (
                            float(np.std(values)) if len(values) > 1 else 0.0
                        )
                        result.loc[indices, f"{prefix}_{field}_min"] = float(np.min(values))
                        result.loc[indices, f"{prefix}_{field}_max"] = float(np.max(values))
                        
                        for p in self.config.percentiles:
                            result.loc[indices, f"{prefix}_{field}_p{p}"] = float(
                                np.percentile(values, p)
                            )
            
            # Categorical field statistics
            for field in self.config.categorical_fields:
                if field in entity_data.columns:
                    values = entity_data[field].dropna()
                    
                    # Unique count
                    unique_count = values.nunique()
                    result.loc[indices, f"{prefix}_{field}_unique"] = unique_count
                    
                    # Entropy
                    if len(values) > 0:
                        counts = Counter(values)
                        total = sum(counts.values())
                        probs = np.array([c / total for c in counts.values()])
                        ent = entropy(probs)
                        result.loc[indices, f"{prefix}_{field}_entropy"] = ent
        
        self._validate_output(result[self.feature_names])
        
        logger.info(
            "statistical_features_extracted",
            records=len(result),
            features=len(self.feature_names),
        )
        
        return result
    
    def get_global_stats(self) -> dict[str, dict[str, float]]:
        """Get learned global statistics.
        
        Returns:
            Dict of field -> stat_name -> value
        """
        return self._global_stats.copy()
