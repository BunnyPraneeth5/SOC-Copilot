"""Unit tests for log parsers."""

import pytest
from pathlib import Path

from soc_copilot.data.log_ingestion.parsers.json_parser import (
    JSONParser,
    flatten_dict,
    extract_timestamp,
)
from soc_copilot.data.log_ingestion.parsers.csv_parser import (
    CSVParser,
    infer_type,
    detect_delimiter,
)
from soc_copilot.data.log_ingestion.parsers.syslog_parser import (
    SyslogParser,
    parse_priority,
    parse_rfc3164_timestamp,
)
from soc_copilot.core.base import ParseError


# =============================================================================
# JSON Parser Tests
# =============================================================================

class TestFlattenDict:
    """Tests for nested dict flattening."""
    
    def test_simple_dict(self):
        """Simple dict should remain unchanged."""
        d = {"a": 1, "b": 2}
        result = flatten_dict(d)
        assert result == {"a": 1, "b": 2}
    
    def test_nested_dict(self):
        """Nested dicts should be flattened with dots."""
        d = {"user": {"name": "alice", "id": 1}}
        result = flatten_dict(d)
        assert result["user.name"] == "alice"
        assert result["user.id"] == 1
    
    def test_deeply_nested(self):
        """Deeply nested dicts should flatten correctly."""
        d = {"a": {"b": {"c": {"d": "value"}}}}
        result = flatten_dict(d)
        assert result["a.b.c.d"] == "value"
    
    def test_list_values(self):
        """Lists should be preserved and indexed."""
        d = {"tags": ["a", "b", "c"]}
        result = flatten_dict(d)
        assert result["tags"] == ["a", "b", "c"]
        assert result["tags[0]"] == "a"
        assert result["tags[1]"] == "b"


class TestExtractTimestamp:
    """Tests for timestamp extraction."""
    
    def test_standard_timestamp_field(self):
        """Should find 'timestamp' field."""
        record = {"timestamp": "2026-01-07T10:00:00Z", "data": "test"}
        assert extract_timestamp(record) == "2026-01-07T10:00:00Z"
    
    def test_at_timestamp_field(self):
        """Should find '@timestamp' field (Elasticsearch format)."""
        record = {"@timestamp": "2026-01-07T10:00:00Z"}
        assert extract_timestamp(record) == "2026-01-07T10:00:00Z"
    
    def test_nested_timestamp(self):
        """Should find nested timestamp fields."""
        record = {"event.timestamp": "2026-01-07T10:00:00Z"}
        assert extract_timestamp(record) == "2026-01-07T10:00:00Z"
    
    def test_no_timestamp(self):
        """Should return None if no timestamp found."""
        record = {"data": "test", "value": 123}
        assert extract_timestamp(record) is None


class TestJSONParser:
    """Tests for JSON parser."""
    
    @pytest.fixture
    def parser(self):
        return JSONParser()
    
    @pytest.fixture
    def sample_json_path(self, tmp_path):
        content = '[{"timestamp": "2026-01-07T10:00:00Z", "event": "test"}]'
        path = tmp_path / "test.json"
        path.write_text(content)
        return path
    
    def test_parse_array(self, parser, sample_json_path):
        """Should parse JSON array."""
        records = parser.parse(sample_json_path)
        assert len(records) == 1
        assert records[0].raw["event"] == "test"
    
    def test_parse_single_object(self, parser, tmp_path):
        """Should parse single JSON object."""
        path = tmp_path / "single.json"
        path.write_text('{"event": "single"}')
        records = parser.parse(path)
        assert len(records) == 1
    
    def test_parse_jsonl(self, parser, tmp_path):
        """Should parse JSON Lines format."""
        path = tmp_path / "test.jsonl"
        path.write_text('{"a": 1}\n{"a": 2}\n{"a": 3}')
        records = parser.parse(path)
        assert len(records) == 3
    
    def test_empty_file(self, parser, tmp_path):
        """Should return empty list for empty file."""
        path = tmp_path / "empty.json"
        path.write_text("")
        records = parser.parse(path)
        assert records == []
    
    def test_invalid_json_raises(self, tmp_path):
        """Should raise ParseError for invalid JSON."""
        parser = JSONParser(skip_invalid=False)
        path = tmp_path / "invalid.json"
        path.write_text('{"broken":')
        with pytest.raises(ParseError):
            parser.parse(path)
    
    def test_file_not_found(self, parser, tmp_path):
        """Should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parser.parse(tmp_path / "nonexistent.json")
    
    def test_nested_flattening(self, parser, tmp_path):
        """Should flatten nested objects."""
        path = tmp_path / "nested.json"
        path.write_text('[{"user": {"name": "alice"}}]')
        records = parser.parse(path)
        assert records[0].raw["user.name"] == "alice"


# =============================================================================
# CSV Parser Tests
# =============================================================================

class TestInferType:
    """Tests for CSV type inference."""
    
    def test_integer(self):
        assert infer_type("123") == 123
        assert infer_type("-456") == -456
    
    def test_float(self):
        assert infer_type("123.45") == 123.45
        assert infer_type("-0.5") == -0.5
    
    def test_boolean(self):
        assert infer_type("true") is True
        assert infer_type("FALSE") is False
        assert infer_type("yes") is True
    
    def test_null_values(self):
        assert infer_type("") is None
        assert infer_type("null") is None
        assert infer_type("N/A") is None
    
    def test_string(self):
        assert infer_type("hello") == "hello"
        assert infer_type("192.168.1.1") == "192.168.1.1"


class TestDetectDelimiter:
    """Tests for delimiter detection."""
    
    def test_comma(self):
        assert detect_delimiter("a,b,c\n1,2,3") == ","
    
    def test_semicolon(self):
        assert detect_delimiter("a;b;c\n1;2;3") == ";"
    
    def test_tab(self):
        assert detect_delimiter("a\tb\tc\n1\t2\t3") == "\t"
    
    def test_pipe(self):
        assert detect_delimiter("a|b|c\n1|2|3") == "|"


class TestCSVParser:
    """Tests for CSV parser."""
    
    @pytest.fixture
    def parser(self):
        return CSVParser()
    
    def test_parse_basic(self, parser, tmp_path):
        """Should parse basic CSV."""
        path = tmp_path / "test.csv"
        path.write_text("name,value\nalice,100\nbob,200")
        records = parser.parse(path)
        assert len(records) == 2
        assert records[0].raw["name"] == "alice"
        assert records[0].raw["value"] == 100  # Type inferred
    
    def test_type_inference(self, parser, tmp_path):
        """Should infer types correctly."""
        path = tmp_path / "types.csv"
        path.write_text("str,int,float,bool\nhello,42,3.14,true")
        records = parser.parse(path)
        assert records[0].raw["str"] == "hello"
        assert records[0].raw["int"] == 42
        assert records[0].raw["float"] == 3.14
        assert records[0].raw["bool"] is True
    
    def test_auto_detect_semicolon(self, tmp_path):
        """Should auto-detect semicolon delimiter."""
        parser = CSVParser()
        path = tmp_path / "semi.csv"
        path.write_text("a;b;c\n1;2;3")
        records = parser.parse(path)
        assert len(records) == 1
        assert records[0].raw["a"] == 1
    
    def test_empty_file(self, parser, tmp_path):
        """Should return empty list for empty file."""
        path = tmp_path / "empty.csv"
        path.write_text("")
        records = parser.parse(path)
        assert records == []


# =============================================================================
# Syslog Parser Tests
# =============================================================================

class TestParsePriority:
    """Tests for syslog priority parsing."""
    
    def test_user_notice(self):
        """Priority 13 = user.notice."""
        result = parse_priority(13)
        assert result["facility"] == 1
        assert result["facility_name"] == "user"
        assert result["severity"] == 5
        assert result["severity_name"] == "notice"
    
    def test_kern_emerg(self):
        """Priority 0 = kern.emerg."""
        result = parse_priority(0)
        assert result["facility"] == 0
        assert result["severity"] == 0
    
    def test_local7_debug(self):
        """Priority 191 = local7.debug."""
        result = parse_priority(191)
        assert result["facility"] == 23
        assert result["severity"] == 7


class TestSyslogParser:
    """Tests for Syslog parser."""
    
    @pytest.fixture
    def parser(self):
        return SyslogParser()
    
    def test_parse_rfc3164(self, parser):
        """Should parse RFC 3164 format."""
        line = "<34>Jan  7 10:00:00 webserver nginx: test message"
        record = parser.parse_line(line)
        assert record is not None
        assert record.raw["hostname"] == "webserver"
        assert record.raw["tag"] == "nginx"
        assert record.raw["message"] == "test message"
        assert record.raw["format"] == "RFC3164"
    
    def test_parse_rfc5424(self, parser):
        """Should parse RFC 5424 format."""
        line = '<165>1 2026-01-07T10:00:00.000Z host app - - - Test message'
        record = parser.parse_line(line)
        assert record is not None
        assert record.raw["hostname"] == "host"
        assert record.raw["app_name"] == "app"
        assert record.raw["format"] == "RFC5424"
    
    def test_parse_rfc5424_with_sd(self, parser):
        """Should parse RFC 5424 with structured data."""
        line = '<165>1 2026-01-07T10:00:00Z host app - - [meta key="value"] msg'
        record = parser.parse_line(line)
        assert record is not None
        assert record.raw["sd.meta.key"] == "value"
    
    def test_invalid_line(self, parser):
        """Should return None for invalid syslog."""
        record = parser.parse_line("This is not syslog format")
        assert record is None
    
    def test_parse_file(self, parser, tmp_path):
        """Should parse syslog file."""
        path = tmp_path / "test.syslog"
        path.write_text("<13>Jan  7 10:00:00 host prog: msg1\n<13>Jan  7 10:00:01 host prog: msg2")
        records = parser.parse(path)
        assert len(records) == 2
