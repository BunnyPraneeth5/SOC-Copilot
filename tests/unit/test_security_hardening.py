"""Security hardening tests for SOC Copilot.

Tests:
- Path traversal prevention
- Input validation (file extensions, sizes)
- Model integrity (hash generation, verification, tamper detection)
- String sanitization
"""

import json
import tempfile
from pathlib import Path

import pytest


# =========================================================================
# Path Validation Tests
# =========================================================================

class TestPathValidation:
    """Test input_validator.validate_path()"""
    
    def test_normal_path_is_valid(self, tmp_path):
        from soc_copilot.security.input_validator import validate_path
        
        test_file = tmp_path / "test.log"
        test_file.touch()
        
        result = validate_path(str(test_file))
        assert result.is_valid is True
        assert result.sanitized_path is not None
    
    def test_empty_path_rejected(self):
        from soc_copilot.security.input_validator import validate_path
        
        result = validate_path("")
        assert result.is_valid is False
        assert "Empty" in result.error
    
    def test_path_traversal_dot_dot_rejected(self):
        from soc_copilot.security.input_validator import validate_path
        
        result = validate_path("../../etc/passwd")
        assert result.is_valid is False
        assert "traversal" in result.error.lower()
    
    def test_path_traversal_backslash_rejected(self):
        from soc_copilot.security.input_validator import validate_path
        
        result = validate_path("..\\..\\windows\\system32")
        assert result.is_valid is False
        assert "traversal" in result.error.lower()
    
    def test_null_byte_rejected(self):
        from soc_copilot.security.input_validator import validate_path
        
        result = validate_path("test\x00.log")
        assert result.is_valid is False
        assert "Null" in result.error
    
    def test_allowed_base_dir_enforced(self, tmp_path):
        from soc_copilot.security.input_validator import validate_path
        
        allowed = tmp_path / "safe"
        allowed.mkdir()
        test_file = allowed / "test.log"
        test_file.touch()
        
        # Inside allowed dir — should pass
        result = validate_path(str(test_file), allowed_base_dirs=[allowed])
        assert result.is_valid is True
    
    def test_outside_allowed_base_dir_rejected(self, tmp_path):
        from soc_copilot.security.input_validator import validate_path
        
        allowed = tmp_path / "safe"
        allowed.mkdir()
        outside = tmp_path / "unsafe" / "test.log"
        outside.parent.mkdir()
        outside.touch()
        
        result = validate_path(str(outside), allowed_base_dirs=[allowed])
        assert result.is_valid is False
        assert "outside" in result.error.lower()
    
    def test_must_exist_nonexistent(self, tmp_path):
        from soc_copilot.security.input_validator import validate_path
        
        result = validate_path(str(tmp_path / "nonexistent.log"), must_exist=True)
        assert result.is_valid is False


# =========================================================================
# Log File Validation Tests
# =========================================================================

class TestLogFileValidation:
    """Test input_validator.validate_log_file()"""
    
    def test_valid_log_extension(self, tmp_path):
        from soc_copilot.security.input_validator import validate_log_file
        
        for ext in [".log", ".syslog", ".jsonl", ".json", ".evtx", ".csv", ".tsv", ".txt"]:
            test_file = tmp_path / f"test{ext}"
            test_file.write_text("test content")
            
            result = validate_log_file(str(test_file))
            assert result.is_valid is True, f"Extension {ext} should be valid"
    
    def test_invalid_extension_rejected(self, tmp_path):
        from soc_copilot.security.input_validator import validate_log_file
        
        for ext in [".exe", ".bat", ".py", ".ps1", ".sh"]:
            test_file = tmp_path / f"test{ext}"
            test_file.write_text("test content")
            
            result = validate_log_file(str(test_file))
            assert result.is_valid is False, f"Extension {ext} should be rejected"

    def test_must_exist_rejected_for_missing_log(self, tmp_path):
        from soc_copilot.security.input_validator import validate_log_file

        result = validate_log_file(str(tmp_path / "missing.log"), must_exist=True)
        assert result.is_valid is False


# =========================================================================
# Model File Validation Tests
# =========================================================================

class TestModelFileValidation:
    """Test input_validator.validate_model_file()"""
    
    def test_valid_model_extension(self, tmp_path):
        from soc_copilot.security.input_validator import validate_model_file
        
        model_file = tmp_path / "model.joblib"
        model_file.write_bytes(b"model data")
        
        result = validate_model_file(str(model_file))
        assert result.is_valid is True
    
    def test_invalid_model_extension_rejected(self, tmp_path):
        from soc_copilot.security.input_validator import validate_model_file
        
        bad_file = tmp_path / "model.exe"
        bad_file.write_bytes(b"not a model")
        
        result = validate_model_file(str(bad_file))
        assert result.is_valid is False


# =========================================================================
# String Sanitization Tests
# =========================================================================

class TestStringSanitization:
    """Test input_validator sanitization functions"""
    
    def test_sanitize_log_line_removes_control_chars(self):
        from soc_copilot.security.input_validator import sanitize_log_line
        
        dirty = "2026-01-01 Normal log\x00\x01\x02 entry"
        clean = sanitize_log_line(dirty)
        assert "\x00" not in clean
        assert "\x01" not in clean
        assert "\x02" not in clean
        assert "Normal log" in clean
    
    def test_sanitize_log_line_preserves_tabs(self):
        from soc_copilot.security.input_validator import sanitize_log_line
        
        line = "field1\tfield2\tfield3"
        clean = sanitize_log_line(line)
        assert "\t" in clean
    
    def test_sanitize_log_line_truncates(self):
        from soc_copilot.security.input_validator import sanitize_log_line
        
        long_line = "x" * 20_000
        clean = sanitize_log_line(long_line, max_length=100)
        assert len(clean) == 100
    
    def test_sanitize_filename_removes_path_separators(self):
        from soc_copilot.security.input_validator import sanitize_filename
        
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
    
    def test_sanitize_filename_removes_null_bytes(self):
        from soc_copilot.security.input_validator import sanitize_filename
        
        result = sanitize_filename("test\x00.log")
        assert "\x00" not in result


# =========================================================================
# Model Integrity Tests
# =========================================================================

class TestModelIntegrity:
    """Test model_integrity hash generation and verification"""
    
    def test_compute_file_hash_deterministic(self, tmp_path):
        from soc_copilot.security.model_integrity import compute_file_hash
        
        test_file = tmp_path / "test.joblib"
        test_file.write_bytes(b"model content 12345")
        
        hash1 = compute_file_hash(test_file)
        hash2 = compute_file_hash(test_file)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
    
    def test_generate_manifest(self, tmp_path):
        from soc_copilot.security.model_integrity import (
            generate_manifest,
            REQUIRED_MODEL_FILES,
        )
        
        # Create fake model files
        for name in REQUIRED_MODEL_FILES:
            (tmp_path / name).write_bytes(f"content of {name}".encode())
        
        manifest = generate_manifest(tmp_path)
        
        assert len(manifest) == len(REQUIRED_MODEL_FILES)
        for name in REQUIRED_MODEL_FILES:
            assert name in manifest
            assert len(manifest[name]) == 64
    
    def test_save_and_load_manifest(self, tmp_path):
        from soc_copilot.security.model_integrity import (
            save_manifest, load_manifest, REQUIRED_MODEL_FILES,
        )
        
        for name in REQUIRED_MODEL_FILES:
            (tmp_path / name).write_bytes(f"content of {name}".encode())
        
        save_manifest(tmp_path)
        
        loaded = load_manifest(tmp_path)
        assert loaded is not None
        assert len(loaded) == len(REQUIRED_MODEL_FILES)
    
    def test_verify_models_passes_with_valid_files(self, tmp_path):
        from soc_copilot.security.model_integrity import (
            save_manifest, verify_models, REQUIRED_MODEL_FILES,
        )
        
        for name in REQUIRED_MODEL_FILES:
            (tmp_path / name).write_bytes(f"content of {name}".encode())
        
        save_manifest(tmp_path)
        
        result = verify_models(tmp_path)
        assert result.is_valid is True
        assert len(result.verified_files) == len(REQUIRED_MODEL_FILES)
    
    def test_verify_models_detects_tampering(self, tmp_path):
        from soc_copilot.security.model_integrity import (
            save_manifest, verify_models, REQUIRED_MODEL_FILES,
        )
        
        for name in REQUIRED_MODEL_FILES:
            (tmp_path / name).write_bytes(f"content of {name}".encode())
        
        save_manifest(tmp_path)
        
        # Tamper with a model file
        tampered = tmp_path / REQUIRED_MODEL_FILES[0]
        tampered.write_bytes(b"TAMPERED CONTENT")
        
        result = verify_models(tmp_path)
        assert result.is_valid is False
        assert REQUIRED_MODEL_FILES[0] in result.failed_files
    
    def test_verify_models_detects_missing_files(self, tmp_path):
        from soc_copilot.security.model_integrity import (
            save_manifest, verify_models, REQUIRED_MODEL_FILES,
        )
        
        for name in REQUIRED_MODEL_FILES:
            (tmp_path / name).write_bytes(f"content of {name}".encode())
        
        save_manifest(tmp_path)
        
        # Delete a model file
        (tmp_path / REQUIRED_MODEL_FILES[0]).unlink()
        
        result = verify_models(tmp_path)
        assert result.is_valid is False
        assert REQUIRED_MODEL_FILES[0] in result.missing_files
    
    def test_verify_models_no_manifest_skips(self, tmp_path):
        from soc_copilot.security.model_integrity import verify_models
        
        # No manifest — should pass with warning
        result = verify_models(tmp_path)
        assert result.is_valid is True
        assert "skipped" in (result.error or "").lower()

    def test_verify_models_no_manifest_fails_in_strict_mode(self, tmp_path):
        from soc_copilot.security.model_integrity import verify_models

        result = verify_models(tmp_path, strict=True)
        assert result.is_valid is False
        assert "strict" in (result.error or "").lower()

    def test_verify_model_file_detects_single_file_tampering(self, tmp_path):
        from soc_copilot.security.model_integrity import save_manifest, verify_model_file

        model_file = tmp_path / "text_log_rf_v1.joblib"
        model_file.write_bytes(b"trusted model")
        save_manifest(tmp_path, {"text_log_rf_v1.joblib": "bad-hash"})

        result = verify_model_file(model_file)
        assert result.is_valid is False
        assert "text_log_rf_v1.joblib" in result.failed_files

    def test_verify_model_file_missing_manifest_dev_vs_strict(self, tmp_path):
        from soc_copilot.security.model_integrity import verify_model_file

        model_file = tmp_path / "text_log_rf_v1.joblib"
        model_file.write_bytes(b"model")

        assert verify_model_file(model_file, strict=False).is_valid is True
        assert verify_model_file(model_file, strict=True).is_valid is False


class TestNetworkHelpers:
    """Test shared network policy helpers."""

    def test_external_ip_public_ipv4(self):
        from soc_copilot.security.network import is_external_ip

        assert is_external_ip("8.8.8.8") is True

    def test_external_ip_private_ranges(self):
        from soc_copilot.security.network import is_external_ip

        for ip in ["10.1.2.3", "172.16.0.1", "172.31.255.255", "192.168.1.10"]:
            assert is_external_ip(ip) is False

    def test_external_ip_reserved_loopback_invalid(self):
        from soc_copilot.security.network import is_external_ip

        for ip in ["127.0.0.1", "169.254.1.1", "224.0.0.1", "198.51.100.42", "", "nope"]:
            assert is_external_ip(ip) is False

    def test_external_ip_ipv6(self):
        from soc_copilot.security.network import is_external_ip

        assert is_external_ip("2001:4860:4860::8888") is True
        assert is_external_ip("::1") is False
