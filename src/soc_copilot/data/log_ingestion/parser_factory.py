"""Parser factory for automatic format detection and parser selection.

Provides a unified interface for parsing log files regardless of format.
"""

from pathlib import Path

from soc_copilot.core.base import BaseParser, ParsedRecord, ParseError
from soc_copilot.data.log_ingestion.parsers.json_parser import JSONParser
from soc_copilot.data.log_ingestion.parsers.csv_parser import CSVParser
from soc_copilot.data.log_ingestion.parsers.syslog_parser import SyslogParser
from soc_copilot.data.log_ingestion.parsers.evtx_parser import EVTXParser


class ParserFactory:
    """Factory for creating appropriate parsers based on file type.
    
    Features:
    - Auto-detection of log format from file extension
    - Content-based format detection as fallback
    - Registry of available parsers
    - Unified interface for all log formats
    
    Usage:
        factory = ParserFactory()
        records = factory.parse("logs/access.json")
        # or
        parser = factory.get_parser(".json")
        records = parser.parse(filepath)
    """
    
    def __init__(self):
        """Initialize the parser factory with default parsers."""
        self._parsers: dict[str, BaseParser] = {}
        self._register_defaults()
    
    def _register_defaults(self) -> None:
        """Register default parsers for common formats."""
        # JSON parser
        json_parser = JSONParser()
        for ext in json_parser.supported_extensions:
            self._parsers[ext.lower()] = json_parser
        
        # CSV parser
        csv_parser = CSVParser()
        for ext in csv_parser.supported_extensions:
            self._parsers[ext.lower()] = csv_parser
        
        # Syslog parser
        syslog_parser = SyslogParser()
        for ext in syslog_parser.supported_extensions:
            self._parsers[ext.lower()] = syslog_parser
        
        # EVTX parser
        evtx_parser = EVTXParser()
        for ext in evtx_parser.supported_extensions:
            self._parsers[ext.lower()] = evtx_parser
    
    def register_parser(self, extension: str, parser: BaseParser) -> None:
        """Register a custom parser for an extension.
        
        Args:
            extension: File extension (with dot, e.g., ".mylog")
            parser: Parser instance to use for this extension
        """
        self._parsers[extension.lower()] = parser
    
    def get_parser(self, extension: str) -> BaseParser | None:
        """Get a parser for the specified extension.
        
        Args:
            extension: File extension (with dot)
            
        Returns:
            Parser instance or None if not found
        """
        return self._parsers.get(extension.lower())
    
    def get_supported_extensions(self) -> list[str]:
        """Get list of all supported file extensions.
        
        Returns:
            List of extensions (with dots)
        """
        return list(self._parsers.keys())
    
    def detect_format(self, filepath: Path) -> str | None:
        """Detect the format of a log file.
        
        Uses extension first, then content-based detection.
        
        Args:
            filepath: Path to the log file
            
        Returns:
            Format name or None if unknown
        """
        ext = filepath.suffix.lower()
        
        # Extension-based detection
        if ext in self._parsers:
            return self._parsers[ext].format_name
        
        # Content-based detection for .log and unknown extensions
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")[:1000]
                
                # Check for JSON
                content_stripped = content.strip()
                if content_stripped.startswith("{") or content_stripped.startswith("["):
                    return "JSON"
                
                # Check for syslog (starts with <PRI>)
                if content_stripped.startswith("<") and ">" in content_stripped[:10]:
                    return "Syslog"
                
                # Check for CSV (has consistent delimiters on first lines)
                lines = content_stripped.split("\n")
                if len(lines) >= 2:
                    first_line = lines[0]
                    for delim in [",", ";", "\t", "|"]:
                        if first_line.count(delim) > 0:
                            # Check if second line has similar structure
                            if lines[1].count(delim) == first_line.count(delim):
                                return "CSV"
            except Exception:
                pass
        
        return None
    
    def parse(
        self,
        filepath: str | Path,
        format_hint: str | None = None,
    ) -> list[ParsedRecord]:
        """Parse a log file using the appropriate parser.
        
        Args:
            filepath: Path to the log file
            format_hint: Optional format hint to override auto-detection
            
        Returns:
            List of parsed records
            
        Raises:
            ParseError: If parsing fails
            ValueError: If format cannot be detected
        """
        filepath = Path(filepath)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Log file not found: {filepath}")
        
        # Determine parser to use
        if format_hint:
            # Find parser by format name
            for parser in self._parsers.values():
                if parser.format_name.lower() == format_hint.lower():
                    return parser.parse(filepath)
            raise ValueError(f"Unknown format: {format_hint}")
        
        # Try extension-based lookup
        ext = filepath.suffix.lower()
        if ext in self._parsers:
            return self._parsers[ext].parse(filepath)
        
        # Try content-based detection
        detected_format = self.detect_format(filepath)
        if detected_format:
            for parser in self._parsers.values():
                if parser.format_name == detected_format:
                    return parser.parse(filepath)
        
        raise ValueError(
            f"Cannot determine log format for: {filepath}. "
            f"Supported extensions: {', '.join(self.get_supported_extensions())}"
        )
    
    def parse_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
        format_hint: str | None = None,
    ) -> dict[str, list[ParsedRecord]]:
        """Parse all log files in a directory.
        
        Args:
            directory: Path to directory containing log files
            recursive: If True, search subdirectories
            format_hint: Optional format hint for all files
            
        Returns:
            Dict mapping filepath to parsed records
        """
        directory = Path(directory)
        
        if not directory.is_dir():
            raise ValueError(f"Not a directory: {directory}")
        
        results: dict[str, list[ParsedRecord]] = {}
        
        # Get all files with supported extensions
        pattern = "**/*" if recursive else "*"
        
        for ext in self.get_supported_extensions():
            for filepath in directory.glob(f"{pattern}{ext}"):
                try:
                    records = self.parse(filepath, format_hint)
                    results[str(filepath)] = records
                except Exception as e:
                    # Store empty list with error info
                    results[str(filepath)] = []
        
        return results


# Global factory instance for convenience
_default_factory: ParserFactory | None = None


def get_parser_factory() -> ParserFactory:
    """Get the default global parser factory.
    
    Returns:
        Default ParserFactory instance
    """
    global _default_factory
    if _default_factory is None:
        _default_factory = ParserFactory()
    return _default_factory


def parse_log_file(
    filepath: str | Path,
    format_hint: str | None = None,
) -> list[ParsedRecord]:
    """Convenience function to parse a log file.
    
    Args:
        filepath: Path to the log file
        format_hint: Optional format hint
        
    Returns:
        List of parsed records
    """
    return get_parser_factory().parse(filepath, format_hint)


def parse_log_directory(
    dirpath: str | Path,
    recursive: bool = True,
    format_hint: str | None = None,
) -> list[ParsedRecord]:
    """Convenience function to parse all log files in a directory.
    
    Args:
        dirpath: Path to the directory
        recursive: Whether to search recursively
        format_hint: Optional format hint
        
    Returns:
        List of all parsed records from all files
    """
    results = get_parser_factory().parse_directory(dirpath, recursive, format_hint)
    all_records = []
    for records in results.values():
        all_records.extend(records)
    return all_records
