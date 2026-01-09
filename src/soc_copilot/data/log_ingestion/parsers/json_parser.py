"""JSON log parser for SOC Copilot.

Supports:
- Standard JSON files (array of objects)
- JSON Lines format (one JSON object per line, .jsonl)
- Nested JSON with automatic flattening
"""

import json
from pathlib import Path
from typing import Any

from soc_copilot.core.base import BaseParser, ParsedRecord, ParseError


def flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Flatten a nested dictionary using dot notation.
    
    Args:
        d: Dictionary to flatten
        parent_key: Prefix for keys (used in recursion)
        sep: Separator between nested keys
        
    Returns:
        Flattened dictionary with dot-notation keys
        
    Example:
        {"user": {"name": "alice", "id": 1}} -> {"user.name": "alice", "user.id": 1}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            # For lists, store as-is but also create indexed entries for simple values
            items.append((new_key, v))
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    items.extend(flatten_dict(item, f"{new_key}[{i}]", sep).items())
                else:
                    items.append((f"{new_key}[{i}]", item))
        else:
            items.append((new_key, v))
    return dict(items)


def extract_timestamp(record: dict[str, Any]) -> str | None:
    """Extract timestamp from common field names.
    
    Searches for timestamp in common field names used by various log sources.
    
    Args:
        record: Flattened log record
        
    Returns:
        Timestamp string if found, None otherwise
    """
    timestamp_fields = [
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
    
    for field in timestamp_fields:
        if field in record and record[field]:
            return str(record[field])
        # Also check flattened nested fields
        for key in record:
            if key.endswith(f".{field}") and record[key]:
                return str(record[key])
    
    return None


class JSONParser(BaseParser):
    """Parser for JSON and JSON Lines log files.
    
    Handles:
    - .json files containing an array of log objects
    - .json files containing a single log object
    - .jsonl files with one JSON object per line
    - Nested JSON structures (automatically flattened)
    
    Edge Cases:
    - Empty files: Returns empty list
    - Invalid JSON: Raises ParseError with line context
    - Mixed valid/invalid lines in JSONL: Skips invalid, logs warning
    - Deeply nested objects: Flattened with dot notation
    - Arrays: Preserved but also indexed for access
    """
    
    def __init__(self, flatten: bool = True, skip_invalid: bool = True):
        """Initialize JSON parser.
        
        Args:
            flatten: If True, flatten nested dicts to dot notation
            skip_invalid: If True, skip invalid lines in JSONL instead of raising
        """
        self._flatten = flatten
        self._skip_invalid = skip_invalid
        self._parse_errors: list[tuple[int, str]] = []
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".json", ".jsonl"]
    
    @property
    def format_name(self) -> str:
        return "JSON"
    
    @property
    def parse_errors(self) -> list[tuple[int, str]]:
        """Get list of (line_number, error_message) for skipped lines."""
        return self._parse_errors.copy()
    
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        """Parse a JSON or JSONL file.
        
        Args:
            filepath: Path to the log file
            
        Returns:
            List of parsed records
            
        Raises:
            ParseError: If file cannot be parsed and skip_invalid is False
            FileNotFoundError: If file does not exist
        """
        self._parse_errors = []
        
        if not filepath.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        
        content = filepath.read_text(encoding="utf-8")
        
        if not content.strip():
            return []
        
        # Determine if JSONL or regular JSON
        if filepath.suffix.lower() == ".jsonl":
            return self._parse_jsonl(content, filepath)
        
        # Try to parse as JSON
        return self._parse_json(content, filepath)
    
    def _parse_json(self, content: str, filepath: Path) -> list[ParsedRecord]:
        """Parse standard JSON content."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            raise ParseError(
                f"Invalid JSON: {e.msg}",
                line_number=e.lineno,
                raw_data=content[:200] if len(content) > 200 else content,
            ) from e
        
        # Handle single object vs array
        if isinstance(data, dict):
            records = [data]
        elif isinstance(data, list):
            records = [r for r in data if isinstance(r, dict)]
        else:
            raise ParseError(
                f"Expected JSON object or array, got {type(data).__name__}",
                raw_data=content[:200],
            )
        
        return [
            self._to_parsed_record(record, filepath)
            for record in records
        ]
    
    def _parse_jsonl(self, content: str, filepath: Path) -> list[ParsedRecord]:
        """Parse JSON Lines content (one JSON object per line)."""
        results: list[ParsedRecord] = []
        
        for line_num, line in enumerate(content.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            
            parsed = self.parse_line(line)
            if parsed:
                parsed.source_file = str(filepath)
                results.append(parsed)
            elif not self._skip_invalid:
                raise ParseError(
                    f"Invalid JSON on line {line_num}",
                    line_number=line_num,
                    raw_data=line[:200],
                )
        
        return results
    
    def parse_line(self, line: str) -> ParsedRecord | None:
        """Parse a single line of JSON.
        
        Args:
            line: Single line containing JSON object
            
        Returns:
            ParsedRecord if valid, None if invalid and skip_invalid is True
        """
        line = line.strip()
        if not line:
            return None
        
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                return None
            return self._to_parsed_record(data, filepath=None)
        except json.JSONDecodeError as e:
            self._parse_errors.append((0, str(e)))
            return None
    
    def _to_parsed_record(
        self,
        raw: dict[str, Any],
        filepath: Path | None,
    ) -> ParsedRecord:
        """Convert raw dict to ParsedRecord."""
        if self._flatten:
            flattened = flatten_dict(raw)
        else:
            flattened = raw
        
        timestamp = extract_timestamp(flattened) or ""
        
        return ParsedRecord(
            timestamp=timestamp,
            raw=flattened,
            source_file=str(filepath) if filepath else None,
            source_format=self.format_name,
        )
