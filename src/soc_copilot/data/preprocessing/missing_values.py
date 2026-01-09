"""Missing value handler for preprocessing pipeline.

Provides configurable strategies for handling missing, null, and empty values
in log records before feature engineering.
"""

from enum import Enum
from typing import Any
import statistics

from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class MissingValueStrategy(str, Enum):
    """Strategy for handling missing values."""
    
    DROP = "drop"           # Remove records with missing required fields
    FILL_DEFAULT = "fill_default"  # Fill with a specified default value
    FILL_MEAN = "fill_mean"     # Fill with mean (numeric fields only)
    FILL_MEDIAN = "fill_median"   # Fill with median (numeric fields only)
    FILL_MODE = "fill_mode"     # Fill with most common value
    FILL_ZERO = "fill_zero"     # Fill numeric with 0, strings with ""
    FORWARD_FILL = "forward_fill"  # Use previous record's value
    FLAG_MISSING = "flag_missing"  # Keep null but add _missing flag


class FieldMissingConfig(BaseModel):
    """Configuration for handling missing values in a specific field."""
    
    field: str
    strategy: MissingValueStrategy = MissingValueStrategy.DROP
    default_value: Any = None
    required: bool = True


class MissingValueConfig(BaseModel):
    """Configuration for missing value handling."""
    
    # Default strategy for all fields not explicitly configured
    default_strategy: MissingValueStrategy = MissingValueStrategy.DROP
    
    # Per-field configurations
    field_configs: list[FieldMissingConfig] = Field(default_factory=list)
    
    # Fields that are always required (drop record if missing)
    required_fields: list[str] = Field(default_factory=list)
    
    # Values to treat as null/missing
    null_values: list[str] = Field(
        default_factory=lambda: ["", "null", "NULL", "None", "none", "N/A", "n/a", "-", "NaN", "nan"]
    )


def is_missing(value: Any, null_values: list[str]) -> bool:
    """Check if a value should be considered missing.
    
    Args:
        value: Value to check
        null_values: List of string values to treat as null
        
    Returns:
        True if value is missing/null
    """
    if value is None:
        return True
    if isinstance(value, float) and (value != value):  # NaN check
        return True
    if isinstance(value, str) and value.strip() in null_values:
        return True
    return False


def compute_fill_value(
    values: list[Any],
    strategy: MissingValueStrategy,
    default: Any = None,
) -> Any:
    """Compute the fill value based on strategy and existing values.
    
    Args:
        values: List of non-missing values for the field
        strategy: Fill strategy to use
        default: Default value for FILL_DEFAULT strategy
        
    Returns:
        Value to use for filling missing entries
    """
    if strategy == MissingValueStrategy.FILL_DEFAULT:
        return default
    
    if strategy == MissingValueStrategy.FILL_ZERO:
        return 0
    
    if not values:
        return default
    
    # Try to convert to numeric for mean/median
    if strategy in (MissingValueStrategy.FILL_MEAN, MissingValueStrategy.FILL_MEDIAN):
        numeric_values = []
        for v in values:
            try:
                numeric_values.append(float(v))
            except (ValueError, TypeError):
                continue
        
        if not numeric_values:
            return default
        
        if strategy == MissingValueStrategy.FILL_MEAN:
            return statistics.mean(numeric_values)
        else:  # FILL_MEDIAN
            return statistics.median(numeric_values)
    
    if strategy == MissingValueStrategy.FILL_MODE:
        # Find most common value
        from collections import Counter
        counter = Counter(values)
        if counter:
            return counter.most_common(1)[0][0]
        return default
    
    return default


class MissingValueHandler:
    """Handles missing values in log records.
    
    Features:
    - Configurable per-field strategies
    - Multiple fill strategies (mean, median, mode, default, zero)
    - Required field validation
    - Forward fill for time-series data
    - Missing value flagging for explainability
    
    Usage:
        config = MissingValueConfig(
            default_strategy=MissingValueStrategy.FILL_ZERO,
            required_fields=["timestamp", "src_ip"],
        )
        handler = MissingValueHandler(config)
        clean_records = handler.process(records)
    """
    
    def __init__(self, config: MissingValueConfig | None = None):
        """Initialize handler with configuration.
        
        Args:
            config: Missing value handling configuration
        """
        self.config = config or MissingValueConfig()
        
        # Build field config lookup
        self._field_configs: dict[str, FieldMissingConfig] = {
            fc.field: fc for fc in self.config.field_configs
        }
        
        # Track statistics for mean/median computation
        self._field_values: dict[str, list[Any]] = {}
        
        # Track last values for forward fill
        self._last_values: dict[str, Any] = {}
        
        # Statistics tracking
        self._stats = {
            "total_records": 0,
            "dropped_records": 0,
            "filled_values": 0,
            "flagged_missing": 0,
        }
    
    def get_strategy(self, field: str) -> MissingValueStrategy:
        """Get the strategy for a specific field.
        
        Args:
            field: Field name
            
        Returns:
            Strategy to use for this field
        """
        if field in self._field_configs:
            return self._field_configs[field].strategy
        if field in self.config.required_fields:
            return MissingValueStrategy.DROP
        return self.config.default_strategy
    
    def is_required(self, field: str) -> bool:
        """Check if a field is required.
        
        Args:
            field: Field name
            
        Returns:
            True if field is required
        """
        if field in self.config.required_fields:
            return True
        if field in self._field_configs:
            return self._field_configs[field].required
        return False
    
    def fit(self, records: list[dict[str, Any]]) -> None:
        """Compute statistics from records for mean/median/mode fill.
        
        Must be called before process() if using statistical fill strategies.
        
        Args:
            records: List of record dicts to compute statistics from
        """
        self._field_values.clear()
        
        for record in records:
            for field, value in record.items():
                if not is_missing(value, self.config.null_values):
                    if field not in self._field_values:
                        self._field_values[field] = []
                    self._field_values[field].append(value)
        
        logger.info(
            "missing_value_handler_fit",
            record_count=len(records),
            fields_analyzed=len(self._field_values),
        )
    
    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process records by handling missing values.
        
        Args:
            records: List of record dicts to process
            
        Returns:
            List of processed records (some may be dropped)
        """
        self._stats = {
            "total_records": len(records),
            "dropped_records": 0,
            "filled_values": 0,
            "flagged_missing": 0,
        }
        
        results: list[dict[str, Any]] = []
        
        for record in records:
            processed = self._process_record(record)
            if processed is not None:
                results.append(processed)
            else:
                self._stats["dropped_records"] += 1
        
        logger.info(
            "missing_value_handler_complete",
            **self._stats,
        )
        
        return results
    
    def _process_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single record.
        
        Args:
            record: Record dict to process
            
        Returns:
            Processed record or None if should be dropped
        """
        result = dict(record)
        
        # Check required fields first
        for field in self.config.required_fields:
            if field not in result or is_missing(result[field], self.config.null_values):
                logger.debug(
                    "record_dropped_missing_required",
                    field=field,
                )
                return None
        
        # Process each field
        all_fields = set(result.keys()) | set(self._field_configs.keys())
        
        for field in all_fields:
            value = result.get(field)
            
            if is_missing(value, self.config.null_values):
                strategy = self.get_strategy(field)
                
                if strategy == MissingValueStrategy.DROP:
                    if self.is_required(field):
                        return None
                    # Non-required field with DROP strategy: just skip
                    continue
                
                elif strategy == MissingValueStrategy.FLAG_MISSING:
                    result[f"{field}_missing"] = True
                    self._stats["flagged_missing"] += 1
                
                elif strategy == MissingValueStrategy.FORWARD_FILL:
                    if field in self._last_values:
                        result[field] = self._last_values[field]
                        self._stats["filled_values"] += 1
                
                else:
                    # Compute fill value
                    field_values = self._field_values.get(field, [])
                    default = None
                    if field in self._field_configs:
                        default = self._field_configs[field].default_value
                    
                    fill_value = compute_fill_value(field_values, strategy, default)
                    if fill_value is not None:
                        result[field] = fill_value
                        self._stats["filled_values"] += 1
            else:
                # Track for forward fill
                self._last_values[field] = value
        
        return result
    
    def get_stats(self) -> dict[str, int]:
        """Get processing statistics.
        
        Returns:
            Dict with counts of processed, dropped, filled, etc.
        """
        return self._stats.copy()
