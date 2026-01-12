"""Unit tests for secure permissions module"""

import pytest
import tempfile
import shutil
from pathlib import Path
import os
import sys
import platform

from soc_copilot.security.permissions import (
    set_secure_file_permissions,
    set_secure_directory_permissions,
    validate_permissions,
    PermissionStatus
)


@pytest.fixture
def temp_dir():
    """Create temporary directory"""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


def test_set_secure_file_permissions_db(temp_dir):
    """Set secure permissions on database file"""
    db_file = temp_dir / "test.db"
    db_file.write_text("test")
    
    result = set_secure_file_permissions(db_file, "db")
    assert result is True
    
    if platform.system() != "Windows":
        stat_info = db_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o600


def test_set_secure_file_permissions_model(temp_dir):
    """Set secure permissions on model file"""
    model_file = temp_dir / "model.joblib"
    model_file.write_text("test")
    
    result = set_secure_file_permissions(model_file, "model")
    assert result is True
    
    if platform.system() != "Windows":
        stat_info = model_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o600


def test_set_secure_file_permissions_log(temp_dir):
    """Set secure permissions on log file"""
    log_file = temp_dir / "test.log"
    log_file.write_text("test")
    
    result = set_secure_file_permissions(log_file, "log")
    assert result is True
    
    if platform.system() != "Windows":
        stat_info = log_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o640


def test_set_secure_file_permissions_nonexistent(temp_dir):
    """Set permissions on nonexistent file should fail"""
    nonexistent = temp_dir / "nonexistent.db"
    
    result = set_secure_file_permissions(nonexistent, "db")
    assert result is False


def test_set_secure_file_permissions_invalid_type(temp_dir):
    """Set permissions with invalid type should fail"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    
    result = set_secure_file_permissions(test_file, "invalid")
    assert result is False


def test_set_secure_directory_permissions(temp_dir):
    """Set secure permissions on directory"""
    test_subdir = temp_dir / "subdir"
    test_subdir.mkdir()
    
    result = set_secure_directory_permissions(test_subdir)
    assert result is True
    
    if platform.system() != "Windows":
        stat_info = test_subdir.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o700


def test_set_secure_directory_permissions_nonexistent(temp_dir):
    """Set directory permissions on nonexistent should fail"""
    nonexistent = temp_dir / "nonexistent"
    
    result = set_secure_directory_permissions(nonexistent)
    assert result is False


def test_set_secure_directory_permissions_on_file(temp_dir):
    """Set directory permissions on file should fail"""
    test_file = temp_dir / "test.txt"
    test_file.write_text("test")
    
    result = set_secure_directory_permissions(test_file)
    assert result is False


def test_validate_permissions_secure_db(temp_dir):
    """Validate permissions on secure database file"""
    db_file = temp_dir / "test.db"
    db_file.write_text("test")
    
    if platform.system() != "Windows":
        os.chmod(db_file, 0o600)
    
    status = validate_permissions(db_file)
    
    assert isinstance(status, PermissionStatus)
    assert status.path == str(db_file)
    assert status.expected_mode == 0o600
    
    if platform.system() != "Windows":
        assert status.is_secure is True
        assert status.current_mode == 0o600


def test_validate_permissions_insecure_db(temp_dir):
    """Validate permissions on insecure database file"""
    if platform.system() == "Windows":
        pytest.skip("Permission validation not strict on Windows")
    
    db_file = temp_dir / "test.db"
    db_file.write_text("test")
    os.chmod(db_file, 0o644)
    
    status = validate_permissions(db_file)
    
    assert status.is_secure is False
    assert status.current_mode == 0o644
    assert status.expected_mode == 0o600


def test_validate_permissions_secure_log(temp_dir):
    """Validate permissions on secure log file"""
    log_file = temp_dir / "test.log"
    log_file.write_text("test")
    
    if platform.system() != "Windows":
        os.chmod(log_file, 0o640)
    
    status = validate_permissions(log_file)
    
    assert status.expected_mode == 0o640
    
    if platform.system() != "Windows":
        assert status.is_secure is True
        assert status.current_mode == 0o640


def test_validate_permissions_secure_directory(temp_dir):
    """Validate permissions on secure directory"""
    test_subdir = temp_dir / "subdir"
    test_subdir.mkdir()
    
    if platform.system() != "Windows":
        os.chmod(test_subdir, 0o700)
    
    status = validate_permissions(test_subdir)
    
    assert status.expected_mode == 0o700
    
    if platform.system() != "Windows":
        assert status.is_secure is True
        assert status.current_mode == 0o700


def test_validate_permissions_nonexistent(temp_dir):
    """Validate permissions on nonexistent path"""
    nonexistent = temp_dir / "nonexistent"
    
    status = validate_permissions(nonexistent)
    
    assert status.is_secure is False
    assert status.error == "Path does not exist"


def test_validate_permissions_model_file(temp_dir):
    """Validate permissions on model file"""
    model_file = temp_dir / "model.joblib"
    model_file.write_text("test")
    
    if platform.system() != "Windows":
        os.chmod(model_file, 0o600)
    
    status = validate_permissions(model_file)
    
    assert status.expected_mode == 0o600


def test_validate_permissions_json_file(temp_dir):
    """Validate permissions on JSON file"""
    json_file = temp_dir / "config.json"
    json_file.write_text("{}")
    
    if platform.system() != "Windows":
        os.chmod(json_file, 0o600)
    
    status = validate_permissions(json_file)
    
    assert status.expected_mode == 0o600


def test_windows_best_effort_behavior(temp_dir):
    """Test Windows best-effort permission behavior"""
    if platform.system() != "Windows":
        pytest.skip("Windows-only test")
    
    test_file = temp_dir / "test.db"
    test_file.write_text("test")
    
    # Should succeed even if chmod doesn't work
    result = set_secure_file_permissions(test_file, "db")
    assert result is True
    
    # Validation should be lenient on Windows
    status = validate_permissions(test_file)
    assert status.is_secure is True


def test_unix_strict_enforcement(temp_dir):
    """Test Unix strict permission enforcement"""
    if platform.system() == "Windows":
        pytest.skip("Unix-only test")
    
    test_file = temp_dir / "test.db"
    test_file.write_text("test")
    
    # Set insecure permissions
    os.chmod(test_file, 0o644)
    
    # Validation should detect insecurity
    status = validate_permissions(test_file)
    assert status.is_secure is False
    assert status.current_mode == 0o644
    assert status.expected_mode == 0o600


def test_permission_status_dataclass():
    """Test PermissionStatus dataclass"""
    status = PermissionStatus(
        path="/test/path",
        is_secure=True,
        current_mode=0o600,
        expected_mode=0o600
    )
    
    assert status.path == "/test/path"
    assert status.is_secure is True
    assert status.current_mode == 0o600
    assert status.expected_mode == 0o600
    assert status.error is None


def test_permission_status_with_error():
    """Test PermissionStatus with error"""
    status = PermissionStatus(
        path="/test/path",
        is_secure=False,
        current_mode=0,
        expected_mode=0o600,
        error="Test error"
    )
    
    assert status.error == "Test error"
