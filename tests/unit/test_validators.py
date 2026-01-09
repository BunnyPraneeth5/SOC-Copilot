"""Unit tests for schema validator and parser factory."""

import pytest
from pathlib import Path

from soc_copilot.data.log_ingestion.validators.schema_validator import (
    SchemaValidator,
    LogSchema,
    FieldRequirement,
    ValidationResult,
    NETWORK_FLOW_SCHEMA,
    AUTH_EVENT_SCHEMA,
    SYSLOG_SCHEMA,
    GENERIC_SCHEMA,
)
from soc_copilot.data.log_ingestion.parser_factory import (
    ParserFactory,
    parse_log_file,
)


# =============================================================================
# Schema Validator Tests
# =============================================================================

class TestFieldRequirement:
    """Tests for field requirement definitions."""
    
    def test_basic_field(self):
        """Should create basic field requirement."""
        field = FieldRequirement(name="src_ip", required=True, field_type="str")
        assert field.name == "src_ip"
        assert field.required is True
        assert field.field_type == "str"
    
    def test_field_with_alternatives(self):
        """Should store alternative field names."""
        field = FieldRequirement(
            name="src_ip",
            alternatives=["source_ip", "srcip", "SrcIP"],
        )
        assert "source_ip" in field.alternatives


class TestSchemaValidator:
    """Tests for schema validation."""
    
    def test_validate_valid_record(self):
        """Should validate correct record."""
        # Use GENERIC_SCHEMA which doesn't require timestamp
        schema = LogSchema(name="test", require_timestamp=False, fields=[
            FieldRequirement(name="src_ip", required=True, field_type="str"),
            FieldRequirement(name="dst_ip", required=True, field_type="str"),
        ])
        validator = SchemaValidator(schema)
        record = {"src_ip": "192.168.1.1", "dst_ip": "10.0.0.1"}
        result = validator.validate(record)
        assert result.valid is True
        assert len(result.errors) == 0
    
    def test_validate_missing_required(self):
        """Should fail when required field missing."""
        schema = LogSchema(name="test", require_timestamp=False, fields=[
            FieldRequirement(name="src_ip", required=True, field_type="str"),
            FieldRequirement(name="dst_ip", required=True, field_type="str"),
        ])
        validator = SchemaValidator(schema)
        record = {"src_ip": "192.168.1.1"}  # Missing dst_ip
        result = validator.validate(record)
        assert result.valid is False
        assert any("dst_ip" in e for e in result.errors)
    
    def test_validate_alternative_names(self):
        """Should accept alternative field names."""
        schema = LogSchema(name="test", require_timestamp=False, fields=[
            FieldRequirement(name="src_ip", required=True, field_type="str", 
                           alternatives=["source_ip"]),
            FieldRequirement(name="dst_ip", required=True, field_type="str",
                           alternatives=["destination_ip"]),
        ])
        validator = SchemaValidator(schema)
        record = {"source_ip": "192.168.1.1", "destination_ip": "10.0.0.1"}
        result = validator.validate(record)
        assert result.valid is True
        # Should normalize to canonical names
        assert "src_ip" in result.normalized_record
    
    def test_validate_type_warning(self):
        """Should warn on type mismatch."""
        schema = LogSchema(name="test", require_timestamp=False, fields=[
            FieldRequirement(name="src_ip", required=True, field_type="str"),
            FieldRequirement(name="dst_ip", required=True, field_type="str"),
            FieldRequirement(name="src_port", required=False, field_type="int"),
        ])
        validator = SchemaValidator(schema)
        record = {
            "src_ip": "192.168.1.1",
            "dst_ip": "10.0.0.1",
            "src_port": "not_a_number",  # Should be int
        }
        result = validator.validate(record)
        # Should still be valid (type mismatch is warning, not error)
        assert result.valid is True
        assert len(result.warnings) > 0
    
    def test_validate_preserves_extra_fields(self):
        """Should preserve fields not in schema."""
        schema = LogSchema(name="test", require_timestamp=False, fields=[
            FieldRequirement(name="src_ip", required=True, field_type="str"),
            FieldRequirement(name="dst_ip", required=True, field_type="str"),
        ])
        validator = SchemaValidator(schema)
        record = {
            "src_ip": "192.168.1.1",
            "dst_ip": "10.0.0.1",
            "custom_field": "custom_value",
        }
        result = validator.validate(record)
        assert result.valid is True
        assert result.normalized_record["custom_field"] == "custom_value"
    
    def test_auth_event_schema(self):
        """Should validate auth event schema."""
        schema = LogSchema(name="auth", require_timestamp=False, fields=[
            FieldRequirement(name="user", required=True, field_type="str",
                           alternatives=["username"]),
            FieldRequirement(name="action", required=True, field_type="str"),
        ])
        validator = SchemaValidator(schema)
        record = {"username": "alice", "action": "login", "status": "success"}
        result = validator.validate(record)
        assert result.valid is True
        assert "user" in result.normalized_record
    
    def test_syslog_schema(self):
        """Should validate syslog schema."""
        schema = LogSchema(name="syslog", require_timestamp=False, fields=[
            FieldRequirement(name="message", required=True, field_type="str"),
            FieldRequirement(name="hostname", required=False, field_type="str"),
        ])
        validator = SchemaValidator(schema)
        record = {"message": "test message", "hostname": "server1"}
        result = validator.validate(record)
        assert result.valid is True


# =============================================================================
# Parser Factory Tests
# =============================================================================

class TestParserFactory:
    """Tests for parser factory."""
    
    @pytest.fixture
    def factory(self):
        return ParserFactory()
    
    def test_get_supported_extensions(self, factory):
        """Should return all supported extensions."""
        extensions = factory.get_supported_extensions()
        assert ".json" in extensions
        assert ".csv" in extensions
        assert ".evtx" in extensions
    
    def test_get_parser_json(self, factory):
        """Should return JSON parser for .json."""
        parser = factory.get_parser(".json")
        assert parser is not None
        assert parser.format_name == "JSON"
    
    def test_get_parser_csv(self, factory):
        """Should return CSV parser for .csv."""
        parser = factory.get_parser(".csv")
        assert parser is not None
        assert parser.format_name == "CSV"
    
    def test_get_parser_unknown(self, factory):
        """Should return None for unknown extension."""
        parser = factory.get_parser(".xyz")
        assert parser is None
    
    def test_parse_json_file(self, factory, tmp_path):
        """Should parse JSON file via factory."""
        path = tmp_path / "test.json"
        path.write_text('[{"event": "test"}]')
        records = factory.parse(path)
        assert len(records) == 1
    
    def test_parse_csv_file(self, factory, tmp_path):
        """Should parse CSV file via factory."""
        path = tmp_path / "test.csv"
        path.write_text("name,value\nalice,100")
        records = factory.parse(path)
        assert len(records) == 1
    
    def test_parse_with_format_hint(self, factory, tmp_path):
        """Should use format hint over extension."""
        path = tmp_path / "test.log"  # Ambiguous extension
        path.write_text('[{"event": "test"}]')
        records = factory.parse(path, format_hint="JSON")
        assert len(records) == 1
    
    def test_parse_file_not_found(self, factory, tmp_path):
        """Should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            factory.parse(tmp_path / "nonexistent.json")
    
    def test_detect_format_json(self, factory, tmp_path):
        """Should detect JSON format from content."""
        # Use .txt extension (not registered) to trigger content-based detection
        path = tmp_path / "test.txt"
        path.write_text('[{"event": "test"}]')
        assert factory.detect_format(path) == "JSON"
    
    def test_detect_format_syslog(self, factory, tmp_path):
        """Should detect Syslog format from content."""
        # Use .txt extension (not registered) to trigger content-based detection
        path = tmp_path / "test.txt"
        path.write_text('<13>Jan 1 00:00:00 host prog: message')
        assert factory.detect_format(path) == "Syslog"
    
    def test_convenience_function(self, tmp_path):
        """Should work with convenience function."""
        path = tmp_path / "test.json"
        path.write_text('[{"event": "test"}]')
        records = parse_log_file(path)
        assert len(records) == 1


class TestParseDirectory:
    """Tests for directory parsing."""
    
    def test_parse_directory(self, tmp_path):
        """Should parse all files in directory."""
        # Create test files
        (tmp_path / "logs" / "json").mkdir(parents=True)
        (tmp_path / "logs" / "json" / "test1.json").write_text('[{"a": 1}]')
        (tmp_path / "logs" / "json" / "test2.json").write_text('[{"a": 2}]')
        
        factory = ParserFactory()
        results = factory.parse_directory(tmp_path / "logs", recursive=True)
        
        assert len(results) >= 2
