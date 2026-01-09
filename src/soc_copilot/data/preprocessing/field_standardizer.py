"""Field standardizer for preprocessing pipeline.

Normalizes field names to canonical form for consistent feature engineering
across different log sources.
"""

from typing import Any
import re

from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


# Default field mappings: source_name -> canonical_name
DEFAULT_FIELD_MAPPINGS = {
    # IP addresses
    "source_ip": "src_ip",
    "sourceip": "src_ip",
    "srcip": "src_ip",
    "SrcIP": "src_ip",
    "SourceIP": "src_ip",
    "IpAddress": "src_ip",
    "ip_address": "src_ip",
    "client_ip": "src_ip",
    "ClientIP": "src_ip",
    
    "dest_ip": "dst_ip",
    "destip": "dst_ip",
    "destination_ip": "dst_ip",
    "DstIP": "dst_ip",
    "DestIP": "dst_ip",
    "DestinationIP": "dst_ip",
    "target_ip": "dst_ip",
    "TargetIP": "dst_ip",
    "server_ip": "dst_ip",
    
    # Ports
    "source_port": "src_port",
    "sourceport": "src_port",
    "srcport": "src_port",
    "SrcPort": "src_port",
    "SourcePort": "src_port",
    
    "dest_port": "dst_port",
    "destport": "dst_port",
    "destination_port": "dst_port",
    "DstPort": "dst_port",
    "DestPort": "dst_port",
    "DestinationPort": "dst_port",
    "target_port": "dst_port",
    "port": "dst_port",
    "Port": "dst_port",
    
    # User fields
    "username": "user",
    "user_name": "user",
    "UserName": "user",
    "userName": "user",
    "account": "user",
    "Account": "user",
    "account_name": "user",
    "AccountName": "user",
    "login": "user",
    
    # Host fields
    "hostname": "host",
    "host_name": "host",
    "HostName": "host",
    "computer": "host",
    "Computer": "host",
    "ComputerName": "host",
    "computer_name": "host",
    "machine": "host",
    "server": "host",
    "workstation": "host",
    
    # Protocol
    "proto": "protocol",
    "Protocol": "protocol",
    "ip_protocol": "protocol",
    
    # Action/Event
    "event_type": "action",
    "eventType": "action",
    "EventType": "action",
    "activity": "action",
    "Activity": "action",
    "operation": "action",
    "Operation": "action",
    
    # Status/Result
    "status": "result",
    "Status": "result",
    "outcome": "result",
    "Outcome": "result",
    "success": "result",
    "result_code": "result",
    
    # Bytes
    "bytes_sent": "bytes_out",
    "BytesSent": "bytes_out",
    "bytesSent": "bytes_out",
    "bytes_out": "bytes_out",
    "OutBytes": "bytes_out",
    
    "bytes_received": "bytes_in",
    "BytesReceived": "bytes_in",
    "bytesReceived": "bytes_in",
    "bytes_in": "bytes_in",
    "InBytes": "bytes_in",
    
    "total_bytes": "bytes_total",
    "TotalBytes": "bytes_total",
    "bytes": "bytes_total",
    "Bytes": "bytes_total",
}


class FieldStandardizerConfig(BaseModel):
    """Configuration for field standardization."""
    
    # Field name mappings (source -> canonical)
    field_mappings: dict[str, str] = Field(default_factory=lambda: DEFAULT_FIELD_MAPPINGS.copy())
    
    # Whether to convert all field names to lowercase
    lowercase_fields: bool = True
    
    # Whether to replace special characters in field names
    normalize_special_chars: bool = True
    
    # Character to use for special char replacement
    replacement_char: str = "_"
    
    # Fields to drop (after normalization)
    drop_fields: list[str] = Field(default_factory=list)
    
    # Fields to keep (if set, only these fields are kept)
    keep_fields: list[str] | None = None
    
    # Whether to keep unmapped fields
    keep_unmapped: bool = True


def normalize_field_name(
    name: str,
    lowercase: bool = True,
    normalize_special: bool = True,
    replacement: str = "_",
) -> str:
    """Normalize a field name.
    
    Args:
        name: Original field name
        lowercase: Convert to lowercase
        normalize_special: Replace special characters
        replacement: Replacement character
        
    Returns:
        Normalized field name
    """
    result = name
    
    if normalize_special:
        # Replace dots, brackets, spaces with replacement char
        result = re.sub(r"[\.\[\]\s\-\/\\]+", replacement, result)
        # Remove leading/trailing replacement chars
        result = result.strip(replacement)
        # Collapse multiple replacement chars
        result = re.sub(rf"{re.escape(replacement)}+", replacement, result)
    
    if lowercase:
        result = result.lower()
    
    return result


class FieldStandardizer:
    """Standardizes field names to canonical form.
    
    Features:
    - Configurable field name mappings
    - Case normalization
    - Special character handling
    - Field filtering (keep/drop lists)
    - Preserves unmapped fields optionally
    
    Usage:
        config = FieldStandardizerConfig(
            field_mappings={"src": "src_ip", "dst": "dst_ip"},
            lowercase_fields=True,
        )
        standardizer = FieldStandardizer(config)
        standardized = standardizer.process(records)
    """
    
    def __init__(self, config: FieldStandardizerConfig | None = None):
        """Initialize standardizer with configuration.
        
        Args:
            config: Field standardization configuration
        """
        self.config = config or FieldStandardizerConfig()
        
        # Build normalized lookup for case-insensitive matching
        self._normalized_mappings: dict[str, str] = {}
        for source, target in self.config.field_mappings.items():
            normalized_source = normalize_field_name(
                source,
                self.config.lowercase_fields,
                self.config.normalize_special_chars,
                self.config.replacement_char,
            )
            self._normalized_mappings[normalized_source] = target
        
        # Statistics
        self._stats = {
            "total_records": 0,
            "fields_mapped": 0,
            "fields_dropped": 0,
        }
    
    def map_field_name(self, name: str) -> str | None:
        """Map a field name to its canonical form.
        
        Args:
            name: Original field name
            
        Returns:
            Canonical name, or None if field should be dropped
        """
        # Normalize the name first
        normalized = normalize_field_name(
            name,
            self.config.lowercase_fields,
            self.config.normalize_special_chars,
            self.config.replacement_char,
        )
        
        # Check if in drop list
        if normalized in self.config.drop_fields:
            return None
        
        # Check if we have a mapping
        if normalized in self._normalized_mappings:
            return self._normalized_mappings[normalized]
        
        # Check keep list if specified
        if self.config.keep_fields is not None:
            if normalized not in self.config.keep_fields:
                return None
        
        # Return normalized name if keeping unmapped fields
        if self.config.keep_unmapped:
            return normalized
        
        return None
    
    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Standardize field names in all records.
        
        Args:
            records: List of record dicts to process
            
        Returns:
            List of processed records with standardized field names
        """
        self._stats = {
            "total_records": len(records),
            "fields_mapped": 0,
            "fields_dropped": 0,
        }
        
        results: list[dict[str, Any]] = []
        
        for record in records:
            processed = self._process_record(record)
            results.append(processed)
        
        logger.info(
            "field_standardizer_complete",
            **self._stats,
        )
        
        return results
    
    def _process_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Process a single record.
        
        Args:
            record: Record dict to process
            
        Returns:
            Record with standardized field names
        """
        result: dict[str, Any] = {}
        
        for field, value in record.items():
            mapped_name = self.map_field_name(field)
            
            if mapped_name is None:
                self._stats["fields_dropped"] += 1
                continue
            
            if mapped_name != field:
                self._stats["fields_mapped"] += 1
            
            # Handle field conflicts (first value wins)
            if mapped_name not in result:
                result[mapped_name] = value
        
        return result
    
    def get_stats(self) -> dict[str, int]:
        """Get processing statistics.
        
        Returns:
            Dict with processing counts
        """
        return self._stats.copy()
