"""EVTX (Windows Event Log) parser for SOC Copilot.

Supports:
- Windows Event Log XML format (.evtx)
- Extraction of System, EventData, and UserData sections
- Security, Application, System, and custom event logs
"""

from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from soc_copilot.core.base import BaseParser, ParsedRecord, ParseError


# Windows Event Log XML namespaces
EVTX_NS = {
    "evt": "http://schemas.microsoft.com/win/2004/08/events/event",
}


def safe_get_text(element: ET.Element | None, default: str = "") -> str:
    """Safely get text content from an XML element.
    
    Args:
        element: XML element or None
        default: Default value if element is None or has no text
        
    Returns:
        Text content or default
    """
    if element is None:
        return default
    return element.text or default


def parse_event_data(
    event_data: ET.Element | None,
    ns: dict[str, str],
) -> dict[str, Any]:
    """Parse EventData section of Windows Event Log.
    
    Args:
        event_data: EventData XML element
        ns: XML namespaces
        
    Returns:
        Dict of event data fields
    """
    if event_data is None:
        return {}
    
    result: dict[str, Any] = {}
    
    # Named data items: <Data Name="XXX">value</Data>
    for data in event_data.findall("evt:Data", ns):
        name = data.get("Name")
        value = data.text or ""
        
        if name:
            result[name] = value
        else:
            # Unnamed data (positional)
            idx = len([k for k in result if k.startswith("Data")])
            result[f"Data{idx}"] = value
    
    # Binary data
    binary = event_data.find("evt:Binary", ns)
    if binary is not None and binary.text:
        result["Binary"] = binary.text
    
    return result


def parse_user_data(
    user_data: ET.Element | None,
    ns: dict[str, str],
) -> dict[str, Any]:
    """Parse UserData section of Windows Event Log.
    
    Args:
        user_data: UserData XML element
        ns: XML namespaces
        
    Returns:
        Dict of user data fields
    """
    if user_data is None:
        return {}
    
    result: dict[str, Any] = {}
    
    # UserData can contain arbitrary nested structure
    def recurse(elem: ET.Element, prefix: str = "") -> None:
        # Get local name without namespace
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        key = f"{prefix}.{tag}" if prefix else tag
        
        if elem.text and elem.text.strip():
            result[key] = elem.text.strip()
        
        for attr_name, attr_value in elem.attrib.items():
            result[f"{key}.@{attr_name}"] = attr_value
        
        for child in elem:
            recurse(child, key)
    
    for child in user_data:
        recurse(child)
    
    return result


class EVTXParser(BaseParser):
    """Parser for Windows Event Log (EVTX) files.
    
    Uses python-evtx library to read binary EVTX files and extract
    structured event data from the embedded XML.
    
    Extracted Fields:
    - System: EventID, TimeCreated, Computer, Channel, Provider, etc.
    - EventData: Named and positional data elements
    - UserData: Custom provider-specific data
    
    Edge Cases:
    - Corrupted records: Skipped with warning
    - Missing fields: Set to None or empty
    - Large files: Processed incrementally
    - Non-EVTX files: Raises ParseError
    
    Note:
        Requires python-evtx package: pip install python-evtx
    """
    
    def __init__(self, skip_corrupted: bool = True):
        """Initialize EVTX parser.
        
        Args:
            skip_corrupted: If True, skip corrupted records
        """
        self._skip_corrupted = skip_corrupted
        self._parse_errors: list[tuple[int, str]] = []
    
    @property
    def supported_extensions(self) -> list[str]:
        return [".evtx"]
    
    @property
    def format_name(self) -> str:
        return "EVTX"
    
    @property
    def parse_errors(self) -> list[tuple[int, str]]:
        """Get list of (record_number, error_message) for skipped records."""
        return self._parse_errors.copy()
    
    def parse(self, filepath: Path) -> list[ParsedRecord]:
        """Parse an EVTX file.
        
        Args:
            filepath: Path to the EVTX file
            
        Returns:
            List of parsed records
            
        Raises:
            ParseError: If file cannot be parsed
            FileNotFoundError: If file does not exist
            ImportError: If python-evtx is not installed
        """
        self._parse_errors = []
        
        if not filepath.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        
        try:
            import Evtx.Evtx as evtx
        except ImportError as e:
            raise ImportError(
                "python-evtx package is required for EVTX parsing. "
                "Install it with: pip install python-evtx"
            ) from e
        
        results: list[ParsedRecord] = []
        record_num = 0
        
        try:
            with evtx.Evtx(str(filepath)) as log:
                for record in log.records():
                    record_num += 1
                    try:
                        xml_str = record.xml()
                        parsed = self._parse_xml_record(xml_str, filepath)
                        if parsed:
                            results.append(parsed)
                    except Exception as e:
                        if self._skip_corrupted:
                            self._parse_errors.append((record_num, str(e)))
                        else:
                            raise ParseError(
                                f"Error parsing record {record_num}: {e}",
                                line_number=record_num,
                            ) from e
        except Exception as e:
            if "not a valid EVTX" in str(e).lower() or "invalid" in str(e).lower():
                raise ParseError(
                    f"Invalid EVTX file: {e}",
                    raw_data=str(filepath),
                ) from e
            raise
        
        return results
    
    def parse_line(self, line: str) -> ParsedRecord | None:
        """Parse a single XML event record.
        
        This can be used to parse individual event XML strings.
        
        Args:
            line: XML string of a single event
            
        Returns:
            ParsedRecord if valid, None otherwise
        """
        try:
            return self._parse_xml_record(line, source_file=None)
        except Exception:
            return None
    
    def _parse_xml_record(
        self,
        xml_str: str,
        source_file: Path | None,
    ) -> ParsedRecord | None:
        """Parse XML content of a single event record.
        
        Args:
            xml_str: XML string of the event
            source_file: Source file path
            
        Returns:
            ParsedRecord with extracted fields
        """
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return None
        
        # Handle namespace
        ns = EVTX_NS
        
        # System section
        system = root.find("evt:System", ns)
        if system is None:
            # Try without namespace (some exports don't have it)
            system = root.find("System")
            ns = {}  # No namespace
        
        raw: dict[str, Any] = {"_xml": xml_str}
        timestamp = ""
        
        if system is not None:
            # Provider
            provider = system.find("evt:Provider", ns) if ns else system.find("Provider")
            if provider is not None:
                raw["Provider.Name"] = provider.get("Name", "")
                raw["Provider.Guid"] = provider.get("Guid", "")
                raw["Provider.EventSourceName"] = provider.get("EventSourceName", "")
            
            # EventID
            event_id_elem = system.find("evt:EventID", ns) if ns else system.find("EventID")
            if event_id_elem is not None:
                raw["EventID"] = event_id_elem.text
                raw["EventID.Qualifiers"] = event_id_elem.get("Qualifiers", "")
            
            # Version
            version = system.find("evt:Version", ns) if ns else system.find("Version")
            raw["Version"] = safe_get_text(version)
            
            # Level
            level = system.find("evt:Level", ns) if ns else system.find("Level")
            raw["Level"] = safe_get_text(level)
            
            # Task
            task = system.find("evt:Task", ns) if ns else system.find("Task")
            raw["Task"] = safe_get_text(task)
            
            # Opcode
            opcode = system.find("evt:Opcode", ns) if ns else system.find("Opcode")
            raw["Opcode"] = safe_get_text(opcode)
            
            # Keywords
            keywords = system.find("evt:Keywords", ns) if ns else system.find("Keywords")
            raw["Keywords"] = safe_get_text(keywords)
            
            # TimeCreated
            time_created = system.find("evt:TimeCreated", ns) if ns else system.find("TimeCreated")
            if time_created is not None:
                timestamp = time_created.get("SystemTime", "")
                raw["TimeCreated"] = timestamp
            
            # EventRecordID
            record_id = system.find("evt:EventRecordID", ns) if ns else system.find("EventRecordID")
            raw["EventRecordID"] = safe_get_text(record_id)
            
            # Correlation
            correlation = system.find("evt:Correlation", ns) if ns else system.find("Correlation")
            if correlation is not None:
                raw["Correlation.ActivityID"] = correlation.get("ActivityID", "")
                raw["Correlation.RelatedActivityID"] = correlation.get("RelatedActivityID", "")
            
            # Execution
            execution = system.find("evt:Execution", ns) if ns else system.find("Execution")
            if execution is not None:
                raw["Execution.ProcessID"] = execution.get("ProcessID", "")
                raw["Execution.ThreadID"] = execution.get("ThreadID", "")
            
            # Channel
            channel = system.find("evt:Channel", ns) if ns else system.find("Channel")
            raw["Channel"] = safe_get_text(channel)
            
            # Computer
            computer = system.find("evt:Computer", ns) if ns else system.find("Computer")
            raw["Computer"] = safe_get_text(computer)
            
            # Security
            security = system.find("evt:Security", ns) if ns else system.find("Security")
            if security is not None:
                raw["Security.UserID"] = security.get("UserID", "")
        
        # EventData section
        event_data_elem = root.find("evt:EventData", ns) if ns else root.find("EventData")
        event_data = parse_event_data(event_data_elem, ns if ns else {})
        for key, value in event_data.items():
            raw[f"EventData.{key}"] = value
        
        # UserData section
        user_data_elem = root.find("evt:UserData", ns) if ns else root.find("UserData")
        user_data = parse_user_data(user_data_elem, ns if ns else {})
        for key, value in user_data.items():
            raw[f"UserData.{key}"] = value
        
        return ParsedRecord(
            timestamp=timestamp,
            raw=raw,
            source_file=str(source_file) if source_file else None,
            source_format=self.format_name,
        )
