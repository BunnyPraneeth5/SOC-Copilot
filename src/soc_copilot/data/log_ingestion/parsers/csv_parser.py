"""CSV log parser for SOC Copilot.

Supports:
- Standard CSV with headers
- Auto-detection of delimiters (comma, semicolon, tab, pipe)
- Type inference for numeric and boolean values
- Handling of quoted fields and escapes
"""

import csv
from io import StringIO
from pathlib import Path
from typing import Any

from soc_copilot.core.base import BaseParser, ParsedRecord, ParseError


def infer_type(value: str) -> Any:
    """Infer the Python type of a string value.
    
    Args:
        value: String value to convert
        
    Returns:
        Converted value (int, float, bool, None, or str)
    """
    value = value.strip()
    
    # Empty or null
    if not value or value.lower() in ("null", "none", "na", "n/a", ""):
        return None
    
    # Boolean
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        # Note: "0" could be numeric, but in boolean context treat as False
        # We'll try numeric first
        pass
    
    # Integer
    try:
        # Handle negative numbers and numbers with leading zeros
        if value.lstrip("-").isdigit():
            return int(value)
    except (ValueError, OverflowError):
        pass
    
    # Float
    try:
        float_val = float(value)
        # Check it's not inf or nan from weird strings
        if float_val != float("inf") and float_val != float("-inf"):
            return float_val
    except ValueError:
        pass
    
    # Boolean (second pass after numeric)
    if value.lower() == "false":
        return False
    
    # Return as string
    return value


def detect_delimiter(sample: str) -> str:
    """Detect the delimiter used in CSV content.
    
    Args:
        sample: Sample of CSV content (first few lines)
        
    Returns:
        Detected delimiter character
    """
    # Common delimiters in order of preference
    delimiters = [",", ";", "\t", "|"]
    
    # Count occurrences in first line (header)
    first_line = sample.split("\n")[0]
    
    counts = {d: first_line.count(d) for d in delimiters}
    
    # Return delimiter with highest count, defaulting to comma
    best = max(counts, key=lambda x: counts[x])
    return best if counts[best] > 0 else ","


def extract_timestamp_csv(record: dict[str, Any]) -> str | None:
    """Extract timestamp from common CSV field names.
    
    Args:
        record: Log record as dict
        
    Returns:
        Timestamp string if found, None otherwise
    """
    timestamp_fields = [
        "timestamp",
        "time",
        "datetime",
        "date",
        "created",
        "created_at",
        "event_time",
        "eventTime",
        "log_time",
        "logTime",
        "_time",
        "ts",
        "Timestamp",
        "Time",
        "DateTime",
        "Date",
    ]
    
    # Check exact matches first (case-insensitive)
    record_lower = {k.lower(): v for k, v in record.items()}
    for field in timestamp_fields:
        if field.lower() in record_lower and record_lower[field.lower()]:
            return str(record_lower[field.lower()])
    
    return None


class CSVParser(BaseParser):
    """Parser for CSV log files.
    
    Features:
    - Auto-detects delimiter (comma, semicolon, tab, pipe)
    - Requires header row (first row is field names)
    - Performs type inference (int, float, bool, null)
    - Handles quoted fields and embedded delimiters
    
    Edge Cases:
    - Empty files: Returns empty list
    - Missing header: Raises ParseError
    - Inconsistent column counts: Uses available columns, logs warning
    - Quoted fields with embedded newlines: Handled by csv module
    - BOM markers: Stripped during parsing
    """
    
    def __init__(
        self,
        delimiter: str | None = None,
        infer_types: bool = True,
        skip_invalid: bool = True,
    ):
        """Initialize CSV parser.
        
        Args:
            delimiter: Field delimiter (auto-detect if None)
            infer_types: If True, convert values to appropriate Python types
            skip_invalid: If True, skip malformed rows instead of raising
        """
        self._delimiter = delimiter
        self._infer_types = infer_types
        self._skip_invalid = skip_invalid
        self._parse_errors: list[tuple[int, str]] = []
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".csv", ".tsv"]
    
    @property
    def format_name(self) -> str:
        return "CSV"
    
    @property
    def parse_errors(self) -> list[tuple[int, str]]:
        """Get list of (line_number, error_message) for skipped rows."""
        return self._parse_errors.copy()
    
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        """Parse a CSV file.
        
        Args:
            filepath: Path to the CSV file
            
        Returns:
            List of parsed records
            
        Raises:
            ParseError: If file cannot be parsed
            FileNotFoundError: If file does not exist
        """
        self._parse_errors = []
        
        if not filepath.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        
        # Read content, handling BOM
        content = filepath.read_text(encoding="utf-8-sig")
        
        if not content.strip():
            return []
        
        # Detect delimiter if not specified
        delimiter = self._delimiter or detect_delimiter(content)
        
        # Parse using csv module
        reader = csv.DictReader(StringIO(content), delimiter=delimiter)
        
        if not reader.fieldnames:
            raise ParseError(
                "CSV file has no header row",
                raw_data=content[:200],
            )
        
        results: list[ParsedRecord] = []
        
        for row_num, row in enumerate(reader, start=2):  # +2 for 1-indexed + header
            try:
                record = self._process_row(row)
                if record:
                    parsed = self._to_parsed_record(record, filepath)
                    results.append(parsed)
            except Exception as e:
                if self._skip_invalid:
                    self._parse_errors.append((row_num, str(e)))
                else:
                    raise ParseError(
                        f"Error parsing row {row_num}: {e}",
                        line_number=row_num,
                    ) from e
        
        return results
    
    def parse_line(self, line: str) -> ParsedRecord | None:
        """Parse a single CSV line.
        
        Note: This requires knowing the header, so it's less useful
        for CSV than for other formats. Returns None for header lines.
        
        Args:
            line: Single CSV line
            
        Returns:
            None (CSV requires header context for meaningful parsing)
        """
        # Single line parsing isn't meaningful for CSV without header context
        # This method is included for interface compliance
        return None
    
    def _process_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Process a single CSV row.
        
        Args:
            row: Row dict from csv.DictReader
            
        Returns:
            Processed row with type inference applied
        """
        if not any(row.values()):
            return None
        
        result: dict[str, Any] = {}
        
        for key, value in row.items():
            if key is None:
                continue
            
            # Clean key (remove BOM, whitespace)
            clean_key = key.strip().lstrip("\ufeff")
            
            if value is None:
                result[clean_key] = None
            elif self._infer_types:
                result[clean_key] = infer_type(str(value))
            else:
                result[clean_key] = str(value).strip()
        
        return result
    
    def _to_parsed_record(
        self,
        raw: dict[str, Any],
        filepath: Path,
    ) -> ParsedRecord:
        """Convert processed row to ParsedRecord."""
        timestamp = extract_timestamp_csv(raw) or ""
        
        return ParsedRecord(
            timestamp=timestamp,
            raw=raw,
            source_file=str(filepath),
            source_format=self.format_name,
        )
