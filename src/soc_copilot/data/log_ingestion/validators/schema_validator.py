"""Schema validator for parsed log records.

Validates that parsed records contain required fields and conform
to expected types for downstream processing.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class FieldRequirement(BaseModel):
    """Definition of a required or optional field."""
    
    name: str
    required: bool = False
    field_type: str = "any"  # any, str, int, float, bool, list, dict
    alternatives: list[str] = Field(default_factory=list)


class LogSchema(BaseModel):
    """Schema definition for log records.
    
    Attributes:
        name: Schema name (e.g., "network_flow", "auth_event")
        fields: List of field requirements
        require_timestamp: Whether timestamp field must be non-empty
    """
    
    name: str
    fields: list[FieldRequirement] = Field(default_factory=list)
    require_timestamp: bool = True


# =============================================================================
# Predefined Schemas for Common Log Types
# =============================================================================

NETWORK_FLOW_SCHEMA = LogSchema(
    name="network_flow",
    fields=[
        FieldRequirement(
            name="src_ip",
            required=True,
            field_type="str",
            alternatives=["source_ip", "src", "srcip", "SrcIP", "SourceIP"],
        ),
        FieldRequirement(
            name="dst_ip",
            required=True,
            field_type="str",
            alternatives=["dest_ip", "dst", "dstip", "DstIP", "DestIP", "destination_ip"],
        ),
        FieldRequirement(
            name="src_port",
            required=False,
            field_type="int",
            alternatives=["source_port", "srcport", "SrcPort", "SourcePort"],
        ),
        FieldRequirement(
            name="dst_port",
            required=False,
            field_type="int",
            alternatives=["dest_port", "dstport", "DstPort", "DestPort", "destination_port"],
        ),
        FieldRequirement(
            name="protocol",
            required=False,
            field_type="str",
            alternatives=["proto", "Protocol"],
        ),
    ],
)

AUTH_EVENT_SCHEMA = LogSchema(
    name="auth_event",
    fields=[
        FieldRequirement(
            name="user",
            required=True,
            field_type="str",
            alternatives=["username", "user_name", "UserName", "Account", "account"],
        ),
        FieldRequirement(
            name="action",
            required=True,
            field_type="str",
            alternatives=["event_type", "EventType", "action_type", "Action"],
        ),
        FieldRequirement(
            name="result",
            required=False,
            field_type="str",
            alternatives=["status", "Status", "outcome", "Outcome", "success"],
        ),
    ],
)

WINDOWS_EVENT_SCHEMA = LogSchema(
    name="windows_event",
    fields=[
        FieldRequirement(
            name="EventID",
            required=True,
            field_type="str",
            alternatives=["event_id", "eventid"],
        ),
        FieldRequirement(
            name="Channel",
            required=False,
            field_type="str",
            alternatives=["channel", "log_name", "LogName"],
        ),
        FieldRequirement(
            name="Computer",
            required=False,
            field_type="str",
            alternatives=["computer", "hostname", "ComputerName"],
        ),
    ],
)

SYSLOG_SCHEMA = LogSchema(
    name="syslog",
    fields=[
        FieldRequirement(
            name="facility",
            required=False,
            field_type="int",
        ),
        FieldRequirement(
            name="severity",
            required=False,
            field_type="int",
        ),
        FieldRequirement(
            name="hostname",
            required=False,
            field_type="str",
            alternatives=["host", "source"],
        ),
        FieldRequirement(
            name="message",
            required=True,
            field_type="str",
            alternatives=["msg", "Message"],
        ),
    ],
)

# Generic schema that accepts any record with a timestamp
GENERIC_SCHEMA = LogSchema(
    name="generic",
    fields=[],
    require_timestamp=False,
)


class ValidationError(Exception):
    """Error during schema validation."""
    
    def __init__(self, message: str, field: str | None = None, expected: str | None = None):
        self.field = field
        self.expected = expected
        super().__init__(message)


class ValidationResult(BaseModel):
    """Result of validating a record against a schema."""
    
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_record: dict[str, Any] = Field(default_factory=dict)


class SchemaValidator:
    """Validates parsed log records against schemas.
    
    Features:
    - Validates required fields are present
    - Checks field types match expectations
    - Supports field name alternatives (aliases)
    - Normalizes field names to canonical form
    - Provides detailed validation errors
    
    Usage:
        validator = SchemaValidator(NETWORK_FLOW_SCHEMA)
        result = validator.validate(record.raw)
        if result.valid:
            # Use result.normalized_record
    """
    
    def __init__(self, schema: LogSchema):
        """Initialize validator with a schema.
        
        Args:
            schema: Schema to validate against
        """
        self.schema = schema
        
        # Build field lookup including alternatives
        self._field_map: dict[str, str] = {}
        for field in schema.fields:
            self._field_map[field.name.lower()] = field.name
            for alt in field.alternatives:
                self._field_map[alt.lower()] = field.name
    
    def validate(self, record: dict[str, Any]) -> ValidationResult:
        """Validate a record against the schema.
        
        Args:
            record: Record dict to validate
            
        Returns:
            ValidationResult with validation status and normalized record
        """
        errors: list[str] = []
        warnings: list[str] = []
        normalized: dict[str, Any] = {}
        
        # Check timestamp if required
        if self.schema.require_timestamp:
            timestamp = record.get("timestamp", "")
            if not timestamp:
                # Check common timestamp field names
                ts_fields = ["timestamp", "@timestamp", "time", "TimeCreated", "datetime"]
                found = False
                for tf in ts_fields:
                    if tf in record and record[tf]:
                        normalized["timestamp"] = record[tf]
                        found = True
                        break
                if not found:
                    errors.append("Missing required timestamp field")
        
        # Validate each required field
        for field in self.schema.fields:
            value = self._find_field(record, field)
            
            if value is None:
                if field.required:
                    errors.append(f"Missing required field: {field.name}")
                continue
            
            # Type validation
            if field.field_type != "any":
                type_valid, type_error = self._validate_type(value, field.field_type)
                if not type_valid:
                    warnings.append(
                        f"Field {field.name}: expected {field.field_type}, got {type(value).__name__}"
                    )
            
            # Add to normalized record using canonical name
            normalized[field.name] = value
        
        # Copy remaining fields
        for key, value in record.items():
            if key.lower() not in self._field_map and key not in normalized:
                normalized[key] = value
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_record=normalized,
        )
    
    def _find_field(
        self,
        record: dict[str, Any],
        field: FieldRequirement,
    ) -> Any | None:
        """Find a field in the record, checking alternatives.
        
        Args:
            record: Record to search
            field: Field requirement with alternatives
            
        Returns:
            Field value if found, None otherwise
        """
        # Check primary name
        if field.name in record:
            return record[field.name]
        
        # Check case-insensitive primary name
        for key in record:
            if key.lower() == field.name.lower():
                return record[key]
        
        # Check alternatives
        for alt in field.alternatives:
            if alt in record:
                return record[alt]
            for key in record:
                if key.lower() == alt.lower():
                    return record[key]
        
        return None
    
    def _validate_type(self, value: Any, expected_type: str) -> tuple[bool, str | None]:
        """Validate that a value matches the expected type.
        
        Args:
            value: Value to check
            expected_type: Expected type name
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
        }
        
        expected = type_map.get(expected_type)
        if expected is None:
            return True, None
        
        if isinstance(value, expected):
            return True, None
        
        # Try to coerce string to expected type
        if isinstance(value, str):
            if expected_type == "int":
                try:
                    int(value)
                    return True, None
                except ValueError:
                    pass
            elif expected_type == "float":
                try:
                    float(value)
                    return True, None
                except ValueError:
                    pass
            elif expected_type == "bool":
                if value.lower() in ("true", "false", "yes", "no", "1", "0"):
                    return True, None
        
        return False, f"Expected {expected_type}, got {type(value).__name__}"


def get_schema_for_format(format_name: str) -> LogSchema:
    """Get appropriate schema for a log format.
    
    Args:
        format_name: Format name from parser (JSON, CSV, Syslog, EVTX)
        
    Returns:
        Appropriate LogSchema for validation
    """
    schemas = {
        "EVTX": WINDOWS_EVENT_SCHEMA,
        "Syslog": SYSLOG_SCHEMA,
    }
    return schemas.get(format_name, GENERIC_SCHEMA)
