"""Feature engineering pipeline.

Orchestrates multiple feature extractors into a unified pipeline
that produces a complete feature vector for ML models.
"""

from typing import Any

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.data.feature_engineering.base import (
    BaseFeatureExtractor,
    FeatureDefinition,
    FeatureType,
)
from soc_copilot.data.feature_engineering.statistical_features import (
    StatisticalFeatureExtractor,
    StatisticalFeatureConfig,
)
from soc_copilot.data.feature_engineering.temporal_features import (
    TemporalFeatureExtractor,
    TemporalFeatureConfig,
)
from soc_copilot.data.feature_engineering.behavioral_features import (
    BehavioralFeatureExtractor,
    BehavioralFeatureConfig,
)
from soc_copilot.data.feature_engineering.network_features import (
    NetworkFeatureExtractor,
    NetworkFeatureConfig,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class FeaturePipelineConfig(BaseModel):
    """Configuration for feature engineering pipeline."""
    
    # Enable/disable feature types
    enable_statistical: bool = True
    enable_temporal: bool = True
    enable_behavioral: bool = True
    enable_network: bool = True
    
    # Per-extractor configs (optional overrides)
    statistical_config: StatisticalFeatureConfig | None = None
    temporal_config: TemporalFeatureConfig | None = None
    behavioral_config: BehavioralFeatureConfig | None = None
    network_config: NetworkFeatureConfig | None = None
    
    # Output configuration
    drop_original_columns: bool = False
    drop_non_numeric: bool = True
    fill_na_value: float = 0.0
    
    # Feature selection
    exclude_features: list[str] = Field(default_factory=list)
    include_only: list[str] | None = None  # If set, only these features are output


class FeatureEngineeringPipeline:
    """Orchestrates feature extraction from multiple sources.
    
    Combines:
    - Statistical features (aggregations, entropy)
    - Temporal features (time patterns)
    - Behavioral features (session analysis, deviation)
    - Network features (connection patterns)
    
    Produces a complete numeric feature vector suitable for ML models.
    
    Usage:
        pipeline = FeatureEngineeringPipeline(config)
        pipeline.fit(training_df)
        feature_df = pipeline.transform(df)
    """
    
    def __init__(self, config: FeaturePipelineConfig | None = None):
        """Initialize pipeline.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or FeaturePipelineConfig()
        
        # Initialize extractors
        self._extractors: dict[str, BaseFeatureExtractor] = {}
        self._init_extractors()
        
        self._fitted = False
    
    def _init_extractors(self) -> None:
        """Initialize configured feature extractors."""
        if self.config.enable_statistical:
            self._extractors["statistical"] = StatisticalFeatureExtractor(
                self.config.statistical_config
            )
        
        if self.config.enable_temporal:
            self._extractors["temporal"] = TemporalFeatureExtractor(
                self.config.temporal_config
            )
        
        if self.config.enable_behavioral:
            self._extractors["behavioral"] = BehavioralFeatureExtractor(
                self.config.behavioral_config
            )
        
        if self.config.enable_network:
            self._extractors["network"] = NetworkFeatureExtractor(
                self.config.network_config
            )
    
    @property
    def is_fitted(self) -> bool:
        """Whether the pipeline has been fitted."""
        return self._fitted
    
    @property
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get all feature definitions from all extractors.
        
        Returns:
            Combined list of feature definitions
        """
        definitions = []
        for extractor in self._extractors.values():
            definitions.extend(extractor.feature_definitions)
        
        # Filter by configuration
        if self.config.include_only:
            definitions = [d for d in definitions if d.name in self.config.include_only]
        
        definitions = [d for d in definitions if d.name not in self.config.exclude_features]
        
        return definitions
    
    @property
    def feature_names(self) -> list[str]:
        """Get all feature names.
        
        Returns:
            List of feature names
        """
        return [d.name for d in self.feature_definitions]
    
    def fit(self, df: pd.DataFrame) -> None:
        """Fit all extractors on training data.
        
        Args:
            df: Training DataFrame
        """
        for name, extractor in self._extractors.items():
            logger.info("fitting_extractor", extractor=name)
            extractor.fit(df)
        
        self._fitted = True
        
        logger.info(
            "feature_pipeline_fit_complete",
            extractors=len(self._extractors),
            total_features=len(self.feature_names),
        )
    
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract all features from data.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with all features extracted
        """
        if not self._fitted:
            logger.warning("pipeline_not_fitted", message="Auto-fitting on input")
            self.fit(df)
        
        result = df.copy()
        
        # Apply each extractor
        for name, extractor in self._extractors.items():
            logger.debug("extracting_features", extractor=name)
            result = extractor.transform(result)
        
        # Post-processing
        result = self._postprocess(result)
        
        logger.info(
            "feature_pipeline_transform_complete",
            records=len(result),
            features=len([c for c in result.columns if c in self.feature_names]),
        )
        
        return result
    
    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one step.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with all features
        """
        self.fit(df)
        return self.transform(df)
    
    def _postprocess(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply post-processing to feature DataFrame.
        
        Args:
            df: DataFrame with extracted features
            
        Returns:
            Post-processed DataFrame
        """
        result = df.copy()
        
        # Drop original non-feature columns if configured
        if self.config.drop_original_columns:
            feature_cols = set(self.feature_names)
            cols_to_drop = [c for c in result.columns if c not in feature_cols]
            result = result.drop(columns=cols_to_drop, errors="ignore")
        
        # Fill NaN values
        for col in self.feature_names:
            if col in result.columns:
                result[col] = result[col].fillna(self.config.fill_na_value)
        
        # Drop non-numeric columns if configured
        if self.config.drop_non_numeric:
            for col in result.columns:
                if not np.issubdtype(result[col].dtype, np.number):
                    if col in self.feature_names:
                        # Convert to numeric if possible
                        result[col] = pd.to_numeric(result[col], errors="coerce")
                        result[col] = result[col].fillna(self.config.fill_na_value)
        
        return result
    
    def get_feature_matrix(self, df: pd.DataFrame) -> np.ndarray:
        """Get feature values as numpy array.
        
        Args:
            df: DataFrame with features
            
        Returns:
            2D numpy array of feature values
        """
        feature_cols = [c for c in self.feature_names if c in df.columns]
        return df[feature_cols].values
    
    def get_extractor(self, name: str) -> BaseFeatureExtractor | None:
        """Get a specific extractor by name.
        
        Args:
            name: Extractor name (statistical, temporal, behavioral, network)
            
        Returns:
            Extractor instance or None
        """
        return self._extractors.get(name)


def create_default_pipeline() -> FeatureEngineeringPipeline:
    """Create a pipeline with default configuration.
    
    Returns:
        Configured FeatureEngineeringPipeline
    """
    return FeatureEngineeringPipeline(FeaturePipelineConfig())
