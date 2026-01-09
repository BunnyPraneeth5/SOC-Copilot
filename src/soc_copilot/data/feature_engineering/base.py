"""Base classes and utilities for feature engineering.

Provides common infrastructure for all feature extractors.
"""

from abc import ABC, abstractmethod
from typing import Any
from enum import Enum

import pandas as pd
import numpy as np
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class FeatureType(str, Enum):
    """Type of feature for documentation and validation."""
    
    STATISTICAL = "statistical"
    TEMPORAL = "temporal"
    BEHAVIORAL = "behavioral"
    NETWORK = "network"
    DERIVED = "derived"


class FeatureDefinition(BaseModel):
    """Definition of a single feature."""
    
    name: str
    description: str
    feature_type: FeatureType
    numeric_type: str = "float64"  # float64, int64, etc.
    default_value: float | int = 0
    min_value: float | None = None
    max_value: float | None = None
    is_nullable: bool = False


class BaseFeatureExtractor(ABC):
    """Base class for all feature extractors.
    
    All extractors must:
    - Produce numeric outputs only
    - Be deterministic (same input = same output)
    - Handle missing values gracefully
    - Provide feature definitions for explainability
    """
    
    def __init__(self, config: Any = None):
        """Initialize extractor with optional configuration.
        
        Args:
            config: Extractor-specific configuration
        """
        self.config = config
        self._fitted = False
    
    @property
    @abstractmethod
    def feature_definitions(self) -> list[FeatureDefinition]:
        """Get definitions of all features produced by this extractor.
        
        Returns:
            List of FeatureDefinition objects
        """
        ...
    
    @property
    def feature_names(self) -> list[str]:
        """Get names of all features produced.
        
        Returns:
            List of feature names
        """
        return [f.name for f in self.feature_definitions]
    
    @abstractmethod
    def fit(self, df: pd.DataFrame) -> None:
        """Learn parameters from training data.
        
        Args:
            df: Training DataFrame
        """
        ...
    
    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract features from data.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with extracted features
        """
        ...
    
    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fit and transform in one step.
        
        Args:
            df: Input DataFrame
            
        Returns:
            DataFrame with extracted features
        """
        self.fit(df)
        return self.transform(df)
    
    @property
    def is_fitted(self) -> bool:
        """Whether the extractor has been fitted."""
        return self._fitted
    
    def _validate_output(self, df: pd.DataFrame) -> None:
        """Validate that output features are numeric.
        
        Args:
            df: Output DataFrame to validate
            
        Raises:
            ValueError: If non-numeric features found
        """
        for col in df.columns:
            if not np.issubdtype(df[col].dtype, np.number):
                raise ValueError(
                    f"Feature {col} is not numeric: {df[col].dtype}"
                )


def safe_divide(
    numerator: np.ndarray | pd.Series,
    denominator: np.ndarray | pd.Series,
    default: float = 0.0,
) -> np.ndarray:
    """Safely divide arrays, handling division by zero.
    
    Args:
        numerator: Numerator values
        denominator: Denominator values
        default: Value to use when denominator is zero
        
    Returns:
        Result array with default values where denominator was zero
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.where(
            denominator != 0,
            numerator / denominator,
            default,
        )
    return result


def entropy(probabilities: np.ndarray) -> float:
    """Calculate Shannon entropy.
    
    Args:
        probabilities: Array of probabilities (must sum to 1)
        
    Returns:
        Entropy value in bits
    """
    # Filter out zeros to avoid log(0)
    p = probabilities[probabilities > 0]
    if len(p) == 0:
        return 0.0
    return -np.sum(p * np.log2(p))


def calculate_percentile(
    values: np.ndarray,
    percentile: float,
) -> float:
    """Calculate percentile of values.
    
    Args:
        values: Input array
        percentile: Percentile to calculate (0-100)
        
    Returns:
        Percentile value
    """
    if len(values) == 0:
        return 0.0
    return float(np.percentile(values, percentile))
