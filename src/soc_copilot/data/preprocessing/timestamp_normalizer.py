"""Timestamp normalizer for preprocessing pipeline.

Converts timestamps from various formats to UTC ISO 8601 format for
consistent downstream processing.
"""

from datetime import datetime, timezone
from typing import Any
import re

from dateutil import parser as dateutil_parser
from dateutil.tz import tzutc, gettz
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


# Common timestamp field names
DEFAULT_TIMESTAMP_FIELDS = [
    "timestamp",
    "@timestamp",
    "time",
    "datetime",
    "date",
    "created",
    "created_at",
    "event_time",
    "eventTime",
    "EventTime",
    "TimeCreated",
    "TimeGenerated",
    "log_time",
    "logTime",
    "_time",
    "ts",
]

# Common timestamp patterns for faster parsing
TIMESTAMP_PATTERNS = [
    # ISO 8601
    (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", "%Y-%m-%dT%H:%M:%S"),
    # ISO 8601 with microseconds
    (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+", "%Y-%m-%dT%H:%M:%S.%f"),
    # Common log format
    (r"^\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2}", "%d/%b/%Y:%H:%M:%S"),
    # Syslog RFC 3164
    (r"^[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}", "%b %d %H:%M:%S"),
    # Windows event time
    (r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", "%Y-%m-%d %H:%M:%S"),
    # Unix epoch (seconds)
    (r"^\d{10}$", "epoch_seconds"),
    # Unix epoch (milliseconds)
    (r"^\d{13}$", "epoch_millis"),
]


class TimestampConfig(BaseModel):
    """Configuration for timestamp normalization."""
    
    # Fields to check for timestamps
    timestamp_fields: list[str] = Field(default_factory=lambda: DEFAULT_TIMESTAMP_FIELDS.copy())
    
    # Output field name for normalized timestamp
    output_field: str = "timestamp_normalized"
    
    # Keep original timestamp in _raw field
    keep_original: bool = True
    
    # Default timezone if timestamp has no tz info
    default_timezone: str = "UTC"
    
    # Target timezone for output (always UTC for SOC)
    target_timezone: str = "UTC"
    
    # Action when timestamp parsing fails
    on_parse_error: str = "keep"  # keep, drop, empty


def parse_timestamp(
    value: Any,
    default_tz: str = "UTC",
) -> datetime | None:
    """Parse a timestamp string to datetime.
    
    Attempts multiple parsing strategies:
    1. Common patterns with strptime (fast)
    2. Unix epoch detection
    3. dateutil parser (flexible but slower)
    
    Args:
        value: Timestamp value (string, int, float, or datetime)
        default_tz: Default timezone if none specified
        
    Returns:
        Parsed datetime or None if parsing fails
    """
    if value is None:
        return None
    
    # Already a datetime
    if isinstance(value, datetime):
        return value
    
    # Convert to string
    value_str = str(value).strip()
    if not value_str:
        return None
    
    # Try pattern-based parsing first (faster)
    for pattern_regex, strptime_format in TIMESTAMP_PATTERNS:
        if re.match(pattern_regex, value_str):
            try:
                if strptime_format == "epoch_seconds":
                    return datetime.fromtimestamp(int(value_str), tz=timezone.utc)
                elif strptime_format == "epoch_millis":
                    return datetime.fromtimestamp(int(value_str) / 1000, tz=timezone.utc)
                else:
                    dt = datetime.strptime(value_str[:len(strptime_format) + 10], strptime_format)
                    return dt
            except (ValueError, OSError):
                continue
    
    # Fall back to dateutil parser
    try:
        default_tzinfo = gettz(default_tz) if default_tz else None
        dt = dateutil_parser.parse(value_str, default=datetime(2000, 1, 1, tzinfo=default_tzinfo))
        return dt
    except (ValueError, dateutil_parser.ParserError):
        return None


def to_utc(dt: datetime) -> datetime:
    """Convert datetime to UTC.
    
    Args:
        dt: Datetime to convert
        
    Returns:
        Datetime in UTC timezone
    """
    if dt.tzinfo is None:
        # Assume UTC if no timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_iso8601(dt: datetime) -> str:
    """Convert datetime to ISO 8601 string.
    
    Args:
        dt: Datetime to format
        
    Returns:
        ISO 8601 formatted string with Z suffix for UTC
    """
    utc_dt = to_utc(dt)
    # Format with Z suffix for UTC
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class TimestampNormalizer:
    """Normalizes timestamps to UTC ISO 8601 format.
    
    Features:
    - Auto-detection of timestamp fields
    - Multiple input format support
    - Unix epoch handling (seconds and milliseconds)
    - Timezone conversion to UTC
    - Original timestamp preservation
    - Parse error handling options
    
    Usage:
        config = TimestampConfig(
            timestamp_fields=["time", "@timestamp"],
            output_field="timestamp_utc",
        )
        normalizer = TimestampNormalizer(config)
        normalized_records = normalizer.process(records)
    """
    
    def __init__(self, config: TimestampConfig | None = None):
        """Initialize normalizer with configuration.
        
        Args:
            config: Timestamp normalization configuration
        """
        self.config = config or TimestampConfig()
        
        # Statistics tracking
        self._stats = {
            "total_records": 0,
            "normalized": 0,
            "parse_errors": 0,
            "no_timestamp": 0,
        }
    
    def find_timestamp_field(self, record: dict[str, Any]) -> str | None:
        """Find the timestamp field in a record.
        
        Args:
            record: Record dict to search
            
        Returns:
            Field name containing timestamp, or None
        """
        for field in self.config.timestamp_fields:
            if field in record and record[field]:
                return field
            # Also check lowercase
            for key in record:
                if key.lower() == field.lower() and record[key]:
                    return key
        return None
    
    def normalize_value(self, value: Any) -> str | None:
        """Normalize a single timestamp value.
        
        Args:
            value: Timestamp value to normalize
            
        Returns:
            ISO 8601 UTC string or None if parsing fails
        """
        if value is None:
            return None
        
        dt = parse_timestamp(value, self.config.default_timezone)
        if dt is None:
            return None
        
        return to_iso8601(dt)
    
    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize timestamps in all records.
        
        Args:
            records: List of record dicts to process
            
        Returns:
            List of processed records with normalized timestamps
        """
        self._stats = {
            "total_records": len(records),
            "normalized": 0,
            "parse_errors": 0,
            "no_timestamp": 0,
        }
        
        results: list[dict[str, Any]] = []
        
        for record in records:
            processed = self._process_record(record)
            if processed is not None:
                results.append(processed)
        
        logger.info(
            "timestamp_normalizer_complete",
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
        
        # Find timestamp field
        ts_field = self.find_timestamp_field(record)
        
        if ts_field is None:
            self._stats["no_timestamp"] += 1
            # Still return record, just without normalized timestamp
            return result
        
        original_value = record[ts_field]
        normalized = self.normalize_value(original_value)
        
        if normalized is None:
            self._stats["parse_errors"] += 1
            logger.debug(
                "timestamp_parse_error",
                field=ts_field,
                value=str(original_value)[:100],
            )
            
            if self.config.on_parse_error == "drop":
                return None
            elif self.config.on_parse_error == "empty":
                result[self.config.output_field] = ""
            # else "keep" - don't add normalized field
        else:
            result[self.config.output_field] = normalized
            self._stats["normalized"] += 1
            
            # Keep original if configured
            if self.config.keep_original and ts_field != self.config.output_field:
                result[f"{ts_field}_raw"] = original_value
        
        return result
    
    def get_stats(self) -> dict[str, int]:
        """Get processing statistics.
        
        Returns:
            Dict with counts of normalized, errors, etc.
        """
        return self._stats.copy()
