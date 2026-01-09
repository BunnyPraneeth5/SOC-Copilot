"""Syslog parser for SOC Copilot.

Supports:
- RFC 3164 (BSD syslog format)
- RFC 5424 (modern syslog format)
- Auto-detection between formats
- Structured data parsing for RFC 5424
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from soc_copilot.core.base import BaseParser, ParsedRecord, ParseError


# =============================================================================
# RFC 3164 (BSD Syslog)
# =============================================================================
# Format: <PRI>TIMESTAMP HOSTNAME TAG: MESSAGE
# Example: <34>Oct 11 22:14:15 mymachine su: 'su root' failed for lonvick

# Priority = Facility * 8 + Severity
FACILITY_NAMES = {
    0: "kern", 1: "user", 2: "mail", 3: "daemon",
    4: "auth", 5: "syslog", 6: "lpr", 7: "news",
    8: "uucp", 9: "cron", 10: "authpriv", 11: "ftp",
    12: "ntp", 13: "security", 14: "console", 15: "solaris-cron",
    16: "local0", 17: "local1", 18: "local2", 19: "local3",
    20: "local4", 21: "local5", 22: "local6", 23: "local7",
}

SEVERITY_NAMES = {
    0: "emerg", 1: "alert", 2: "crit", 3: "err",
    4: "warning", 5: "notice", 6: "info", 7: "debug",
}

# RFC 3164 timestamp pattern: "Oct 11 22:14:15" or "Oct  1 22:14:15"
# Use non-capturing groups for internal parts to simplify extraction
RFC3164_TIMESTAMP = r"(?:[A-Z][a-z]{2})\s+(?:\d{1,2})\s+(?:\d{2}):(?:\d{2}):(?:\d{2})"

# RFC 3164 full pattern
RFC3164_PATTERN = re.compile(
    r"^<(\d{1,3})>"  # Group 1: Priority
    rf"({RFC3164_TIMESTAMP})\s+"  # Group 2: Timestamp (full)
    r"(\S+)\s+"  # Group 3: Hostname
    r"(\S+?):\s*"  # Group 4: Tag (program name)
    r"(.*)$",  # Group 5: Message
    re.DOTALL,
)

# Simplified RFC 3164 (no tag)
RFC3164_SIMPLE = re.compile(
    r"^<(\d{1,3})>"  # Group 1: Priority
    rf"({RFC3164_TIMESTAMP})\s+"  # Group 2: Timestamp (full)
    r"(\S+)\s+"  # Group 3: Hostname
    r"(.*)$",  # Group 4: Message
    re.DOTALL,
)


# =============================================================================
# RFC 5424 (Modern Syslog)
# =============================================================================
# Format: <PRI>VERSION TIMESTAMP HOSTNAME APP-NAME PROCID MSGID STRUCTURED-DATA MSG
# Example: <165>1 2003-10-11T22:14:15.003Z mymachine.example.com evntslog - ID47 
#          [exampleSDID@32473 eventSource="Application" eventID="1011"] An application event

RFC5424_PATTERN = re.compile(
    r"^<(\d{1,3})>"  # Priority
    r"(\d+)\s+"  # Version
    r"(\S+)\s+"  # Timestamp (ISO 8601)
    r"(\S+)\s+"  # Hostname
    r"(\S+)\s+"  # App-Name
    r"(\S+)\s+"  # ProcID
    r"(\S+)\s+"  # MsgID
    r"(\[.*?\]|-)\s*"  # Structured Data or NILVALUE
    r"(.*)$",  # Message
    re.DOTALL,
)

# Pattern to parse structured data elements
SD_ELEMENT = re.compile(r"\[(\S+?)(?:\s+([^\]]+))?\]")
SD_PARAM = re.compile(r'(\S+?)="([^"]*)"')


def parse_priority(pri: int) -> dict[str, Any]:
    """Parse syslog priority into facility and severity.
    
    Args:
        pri: Priority value (0-191)
        
    Returns:
        Dict with facility, severity, and their names
    """
    facility = pri // 8
    severity = pri % 8
    
    return {
        "facility": facility,
        "facility_name": FACILITY_NAMES.get(facility, f"unknown({facility})"),
        "severity": severity,
        "severity_name": SEVERITY_NAMES.get(severity, f"unknown({severity})"),
    }


def parse_rfc3164_timestamp(ts_str: str) -> str:
    """Parse RFC 3164 timestamp and convert to ISO format.
    
    Args:
        ts_str: Timestamp like "Oct 11 22:14:15"
        
    Returns:
        ISO 8601 formatted timestamp (with current year assumed)
    """
    try:
        # Add current year since RFC 3164 doesn't include year
        current_year = datetime.now().year
        dt = datetime.strptime(f"{current_year} {ts_str}", "%Y %b %d %H:%M:%S")
        return dt.isoformat()
    except ValueError:
        return ts_str


def parse_structured_data(sd_str: str) -> dict[str, Any]:
    """Parse RFC 5424 structured data.
    
    Args:
        sd_str: Structured data string like "[id@123 key1="val1" key2="val2"]"
        
    Returns:
        Dict with parsed structured data
    """
    if sd_str == "-":
        return {}
    
    result: dict[str, Any] = {}
    
    for match in SD_ELEMENT.finditer(sd_str):
        sd_id = match.group(1)
        params_str = match.group(2) or ""
        
        params: dict[str, str] = {}
        for param_match in SD_PARAM.finditer(params_str):
            params[param_match.group(1)] = param_match.group(2)
        
        result[sd_id] = params
    
    return result


class SyslogParser(BaseParser):
    """Parser for Syslog format log files.
    
    Supports:
    - RFC 3164 (BSD syslog): <PRI>TIMESTAMP HOSTNAME TAG: MESSAGE
    - RFC 5424 (modern): <PRI>VERSION TIMESTAMP HOSTNAME APP PROCID MSGID [SD] MSG
    - Auto-detection between formats based on content
    
    Edge Cases:
    - Missing priority: Assumes priority 13 (user.notice)
    - Malformed timestamps: Preserves raw value
    - RFC 3164 without year: Current year assumed
    - Structured data in RFC 5424: Parsed into nested dict
    - Multi-line messages: Each line parsed separately
    - Non-syslog lines: Skipped with warning
    """
    
    def __init__(self, skip_invalid: bool = True):
        """Initialize Syslog parser.
        
        Args:
            skip_invalid: If True, skip unparseable lines
        """
        self._skip_invalid = skip_invalid
        self._parse_errors: list[tuple[int, str]] = []
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".log", ".syslog"]
    
    @property
    def format_name(self) -> str:
        return "Syslog"
    
    @property
    def parse_errors(self) -> list[tuple[int, str]]:
        """Get list of (line_number, error_message) for skipped lines."""
        return self._parse_errors.copy()
    
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        """Parse a syslog file.
        
        Args:
            filepath: Path to the syslog file
            
        Returns:
            List of parsed records
            
        Raises:
            ParseError: If file cannot be parsed and skip_invalid is False
            FileNotFoundError: If file does not exist
        """
        self._parse_errors = []
        
        if not filepath.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        
        content = filepath.read_text(encoding="utf-8", errors="replace")
        
        if not content.strip():
            return []
        
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
                    f"Invalid syslog format on line {line_num}",
                    line_number=line_num,
                    raw_data=line[:200],
                )
            else:
                self._parse_errors.append((line_num, "Invalid syslog format"))
        
        return results
    
    def parse_line(self, line: str) -> ParsedRecord | None:
        """Parse a single syslog line.
        
        Auto-detects RFC 3164 vs RFC 5424 format.
        
        Args:
            line: Single syslog line
            
        Returns:
            ParsedRecord if valid, None otherwise
        """
        line = line.strip()
        if not line:
            return None
        
        # Try RFC 5424 first (has version number after priority)
        result = self._parse_rfc5424(line)
        if result:
            return result
        
        # Try RFC 3164
        result = self._parse_rfc3164(line)
        if result:
            return result
        
        return None
    
    def _parse_rfc3164(self, line: str) -> ParsedRecord | None:
        """Parse RFC 3164 (BSD) syslog format."""
        match = RFC3164_PATTERN.match(line)
        
        if not match:
            # Try simplified pattern without tag
            match = RFC3164_SIMPLE.match(line)
            if not match:
                return None
            
            pri_str, ts_full, hostname, message = match.groups()
            tag = None
        else:
            pri_str, ts_full, hostname, tag, message = match.groups()
        
        try:
            pri = int(pri_str)
        except ValueError:
            pri = 13  # Default: user.notice
        
        priority_info = parse_priority(pri)
        timestamp = parse_rfc3164_timestamp(ts_full.strip())
        
        raw: dict[str, Any] = {
            "priority": pri,
            **priority_info,
            "timestamp_raw": ts_full.strip(),
            "hostname": hostname,
            "message": message.strip() if message else "",
            "format": "RFC3164",
        }
        
        if tag:
            raw["tag"] = tag
            raw["program"] = tag.rstrip("[]").split("[")[0]
        
        return ParsedRecord(
            timestamp=timestamp,
            raw=raw,
            source_format=self.format_name,
        )
    
    def _parse_rfc5424(self, line: str) -> ParsedRecord | None:
        """Parse RFC 5424 (modern) syslog format."""
        match = RFC5424_PATTERN.match(line)
        if not match:
            return None
        
        (
            pri_str, version, timestamp, hostname,
            app_name, proc_id, msg_id, sd_str, message
        ) = match.groups()
        
        try:
            pri = int(pri_str)
        except ValueError:
            pri = 13
        
        priority_info = parse_priority(pri)
        structured_data = parse_structured_data(sd_str)
        
        raw: dict[str, Any] = {
            "priority": pri,
            **priority_info,
            "version": int(version) if version.isdigit() else version,
            "hostname": hostname if hostname != "-" else None,
            "app_name": app_name if app_name != "-" else None,
            "proc_id": proc_id if proc_id != "-" else None,
            "msg_id": msg_id if msg_id != "-" else None,
            "structured_data": structured_data,
            "message": message.strip() if message else "",
            "format": "RFC5424",
        }
        
        # Flatten structured data for easier feature extraction
        for sd_id, params in structured_data.items():
            for key, value in params.items():
                raw[f"sd.{sd_id}.{key}"] = value
        
        return ParsedRecord(
            timestamp=timestamp if timestamp != "-" else "",
            raw=raw,
            source_format=self.format_name,
        )
