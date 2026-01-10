"""Log ingestion module - parsers and validators."""

from soc_copilot.core.base import ParsedRecord

from soc_copilot.data.log_ingestion.parsers import (
    JSONParser,
    CSVParser,
    SyslogParser,
    EVTXParser,
)
from soc_copilot.data.log_ingestion.parser_factory import (
    ParserFactory,
    get_parser_factory,
    parse_log_file,
    parse_log_directory,
)
from soc_copilot.data.log_ingestion.validators import (
    SchemaValidator,
    LogSchema,
    get_schema_for_format,
)

__all__ = [
    # Types
    "ParsedRecord",
    # Parsers
    "JSONParser",
    "CSVParser",
    "SyslogParser",
    "EVTXParser",
    # Factory
    "ParserFactory",
    "get_parser_factory",
    "parse_log_file",
    "parse_log_directory",
    # Validators
    "SchemaValidator",
    "LogSchema",
    "get_schema_for_format",
]
