"""Categorical encoder for preprocessing pipeline.

Encodes categorical string fields to numeric values for ML models,
with special handling for unknown categories.
"""

from typing import Any
from collections import defaultdict

from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class CategoricalEncoderConfig(BaseModel):
    """Configuration for categorical encoding."""
    
    # Fields to encode (if None, auto-detect string fields)
    categorical_fields: list[str] | None = None
    
    # Minimum frequency for a category to get its own encoding
    min_frequency: int = 1
    
    # Maximum number of categories per field (rare ones become "other")
    max_categories: int = 100
    
    # Value to use for unknown/unseen categories
    unknown_value: int = -1
    
    # Label for unknown categories
    unknown_label: str = "<UNKNOWN>"
    
    # Label for rare categories (below min_frequency or above max_categories)
    rare_label: str = "<RARE>"
    
    # Whether to add original string values with _raw suffix
    keep_original: bool = True
    
    # Prefix for encoded fields
    encoded_suffix: str = "_encoded"


class CategoryMapping:
    """Stores the mapping from category labels to numeric codes."""
    
    def __init__(self, unknown_value: int = -1):
        self.unknown_value = unknown_value
        self.label_to_code: dict[str, int] = {}
        self.code_to_label: dict[int, str] = {}
        self._next_code = 0
    
    def add(self, label: str) -> int:
        """Add a new category and return its code.
        
        Args:
            label: Category label
            
        Returns:
            Numeric code for this category
        """
        if label in self.label_to_code:
            return self.label_to_code[label]
        
        code = self._next_code
        self._next_code += 1
        self.label_to_code[label] = code
        self.code_to_label[code] = label
        return code
    
    def encode(self, label: str) -> int:
        """Encode a label to its numeric code.
        
        Args:
            label: Category label
            
        Returns:
            Numeric code, or unknown_value if not found
        """
        return self.label_to_code.get(label, self.unknown_value)
    
    def decode(self, code: int) -> str | None:
        """Decode a numeric code to its label.
        
        Args:
            code: Numeric code
            
        Returns:
            Category label, or None if not found
        """
        return self.code_to_label.get(code)
    
    def __len__(self) -> int:
        return len(self.label_to_code)


class CategoricalEncoder:
    """Encodes categorical fields to numeric values.
    
    Features:
    - Auto-detection of categorical fields
    - Frequency-based category filtering
    - Unknown category handling
    - Rare category grouping
    - Reversible encoding with mappings
    
    Usage:
        encoder = CategoricalEncoder(config)
        encoder.fit(training_records)
        encoded = encoder.transform(records)
    """
    
    def __init__(self, config: CategoricalEncoderConfig | None = None):
        """Initialize encoder with configuration.
        
        Args:
            config: Encoding configuration
        """
        self.config = config or CategoricalEncoderConfig()
        
        # Field -> CategoryMapping
        self._mappings: dict[str, CategoryMapping] = {}
        
        # Track if fitted
        self._fitted = False
        
        # Statistics
        self._stats = {
            "total_records": 0,
            "fields_encoded": 0,
            "unknown_values": 0,
            "rare_values": 0,
        }
    
    @property
    def is_fitted(self) -> bool:
        """Whether the encoder has been fitted."""
        return self._fitted
    
    def get_mappings(self) -> dict[str, CategoryMapping]:
        """Get the category mappings for all fields.
        
        Returns:
            Dict of field name -> CategoryMapping
        """
        return self._mappings.copy()
    
    def fit(self, records: list[dict[str, Any]]) -> None:
        """Learn category mappings from training data.
        
        Args:
            records: Training records to learn from
        """
        self._mappings.clear()
        
        # Count frequencies for each field
        field_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # Determine which fields to encode
        fields_to_encode = self.config.categorical_fields
        if fields_to_encode is None:
            # Auto-detect string fields
            fields_to_encode = set()
            for record in records:
                for field, value in record.items():
                    if isinstance(value, str):
                        fields_to_encode.add(field)
            fields_to_encode = list(fields_to_encode)
        
        # Count category frequencies
        for record in records:
            for field in fields_to_encode:
                if field in record and record[field] is not None:
                    value = str(record[field])
                    field_counts[field][value] += 1
        
        # Build mappings
        for field in fields_to_encode:
            mapping = CategoryMapping(unknown_value=self.config.unknown_value)
            
            # Add unknown and rare labels first (reserve codes 0 and 1)
            mapping.add(self.config.unknown_label)
            mapping.add(self.config.rare_label)
            
            # Sort by frequency (descending)
            sorted_categories = sorted(
                field_counts[field].items(),
                key=lambda x: x[1],
                reverse=True,
            )
            
            # Add categories up to max, filtering by min_frequency
            for category, count in sorted_categories:
                if count < self.config.min_frequency:
                    continue
                if len(mapping) >= self.config.max_categories:
                    break
                mapping.add(category)
            
            self._mappings[field] = mapping
            
            logger.debug(
                "categorical_encoder_field_fit",
                field=field,
                categories=len(mapping),
                total_unique=len(field_counts[field]),
            )
        
        self._fitted = True
        
        logger.info(
            "categorical_encoder_fit_complete",
            fields_fitted=len(self._mappings),
            total_records=len(records),
        )
    
    def transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Transform records using learned mappings.
        
        Args:
            records: Records to transform
            
        Returns:
            Records with encoded categorical fields
            
        Raises:
            RuntimeError: If not fitted
        """
        if not self._fitted:
            raise RuntimeError("Encoder must be fitted before transform")
        
        self._stats = {
            "total_records": len(records),
            "fields_encoded": 0,
            "unknown_values": 0,
            "rare_values": 0,
        }
        
        results: list[dict[str, Any]] = []
        
        for record in records:
            processed = self._transform_record(record)
            results.append(processed)
        
        logger.info(
            "categorical_encoder_transform_complete",
            **self._stats,
        )
        
        return results
    
    def fit_transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Fit and transform in one step.
        
        Args:
            records: Records to fit and transform
            
        Returns:
            Transformed records
        """
        self.fit(records)
        return self.transform(records)
    
    def _transform_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Transform a single record.
        
        Args:
            record: Record to transform
            
        Returns:
            Record with encoded fields
        """
        result = dict(record)
        
        for field, mapping in self._mappings.items():
            if field not in record:
                continue
            
            original_value = record[field]
            if original_value is None:
                code = mapping.encode(self.config.unknown_label)
                self._stats["unknown_values"] += 1
            else:
                value_str = str(original_value)
                code = mapping.encode(value_str)
                
                if code == self.config.unknown_value:
                    # Check if it's a rare value or truly unknown
                    code = mapping.encode(self.config.rare_label)
                    self._stats["rare_values"] += 1
                elif code == mapping.encode(self.config.unknown_label):
                    self._stats["unknown_values"] += 1
            
            # Add encoded field
            encoded_field = f"{field}{self.config.encoded_suffix}"
            result[encoded_field] = code
            self._stats["fields_encoded"] += 1
            
            # Keep original if configured
            if self.config.keep_original:
                result[f"{field}_raw"] = original_value
            
            # Replace original with encoded
            result[field] = code
        
        return result
    
    def inverse_transform(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Reverse encoding to get original labels.
        
        Args:
            records: Encoded records
            
        Returns:
            Records with original string labels
        """
        if not self._fitted:
            raise RuntimeError("Encoder must be fitted before inverse_transform")
        
        results: list[dict[str, Any]] = []
        
        for record in records:
            result = dict(record)
            
            for field, mapping in self._mappings.items():
                encoded_field = f"{field}{self.config.encoded_suffix}"
                
                if encoded_field in result:
                    code = result[encoded_field]
                    label = mapping.decode(code)
                    if label is not None:
                        result[field] = label
            
            results.append(result)
        
        return results
    
    def get_stats(self) -> dict[str, int]:
        """Get processing statistics.
        
        Returns:
            Dict with encoding counts
        """
        return self._stats.copy()
