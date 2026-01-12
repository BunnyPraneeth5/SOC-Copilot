"""Unit tests for system log reader"""

import pytest
import platform
from pathlib import Path
import tempfile
import os

from soc_copilot.phase4.ingestion.system_log_reader import (
    SystemLogReader,
    PermissionCheckResult
)


@pytest.fixture
def reader():
    """Create system log reader"""
    return SystemLogReader()


def test_reader_detects_os(reader):
    """Reader should detect current OS"""
    assert reader.os_type in ["Windows", "Linux", "Darwin"]
    assert reader.os_type == platform.system()


def test_windows_permission_check_on_windows(reader):
    """Windows permission check should work on Windows"""
    result = reader.check_windows_event_log_permission()
    
    if platform.system() == "Windows":
        assert isinstance(result, PermissionCheckResult)
        assert isinstance(result.has_permission, bool)
    else:
        assert not result.has_permission
        assert "Not a Windows system" in result.error_message


def test_linux_permission_check_on_linux(reader):
    """Linux permission check should work on Linux"""
    result = reader.check_linux_syslog_permission("/var/log/syslog")
    
    if platform.system() == "Linux":
        assert isinstance(result, PermissionCheckResult)
        assert isinstance(result.has_permission, bool)
    else:
        assert not result.has_permission
        assert "Not a Linux system" in result.error_message


def test_linux_permission_check_nonexistent_file(reader):
    """Linux permission check should fail for nonexistent file"""
    result = reader.check_linux_syslog_permission("/nonexistent/log/file.log")
    
    if platform.system() == "Linux":
        assert not result.has_permission
        assert "does not exist" in result.error_message


def test_linux_permission_check_with_temp_file(reader):
    """Linux permission check should succeed for readable temp file"""
    if platform.system() != "Linux":
        pytest.skip("Linux-only test")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test log")
        temp_path = f.name
    
    try:
        result = reader.check_linux_syslog_permission(temp_path)
        assert result.has_permission
        assert result.error_message is None
    finally:
        os.unlink(temp_path)


def test_linux_permission_check_unreadable_file(reader):
    """Linux permission check should fail for unreadable file"""
    if platform.system() != "Linux":
        pytest.skip("Linux-only test")
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test log")
        temp_path = f.name
    
    try:
        # Remove read permission
        os.chmod(temp_path, 0o000)
        
        result = reader.check_linux_syslog_permission(temp_path)
        assert not result.has_permission
        assert "No read permission" in result.error_message
        assert result.requires_elevation
    finally:
        os.chmod(temp_path, 0o644)
        os.unlink(temp_path)


def test_get_accessible_linux_logs(reader):
    """Get accessible Linux logs should return list"""
    logs = reader.get_accessible_linux_logs()
    
    if platform.system() == "Linux":
        assert isinstance(logs, list)
        for log_path, result in logs:
            assert isinstance(log_path, str)
            assert isinstance(result, PermissionCheckResult)
    else:
        assert logs == []


def test_validate_system_log_access(reader):
    """Validate system log access should check current OS"""
    result = reader.validate_system_log_access()
    
    assert isinstance(result, PermissionCheckResult)
    assert isinstance(result.has_permission, bool)


def test_get_system_info(reader):
    """Get system info should return dict with OS details"""
    info = reader.get_system_info()
    
    assert "os_type" in info
    assert "os_release" in info
    assert "os_version" in info
    assert "python_version" in info
    assert info["os_type"] == platform.system()


def test_permission_check_result_dataclass():
    """PermissionCheckResult should work as dataclass"""
    result = PermissionCheckResult(
        has_permission=False,
        error_message="Test error",
        requires_elevation=True
    )
    
    assert not result.has_permission
    assert result.error_message == "Test error"
    assert result.requires_elevation


def test_permission_check_result_defaults():
    """PermissionCheckResult should have default values"""
    result = PermissionCheckResult(has_permission=True)
    
    assert result.has_permission
    assert result.error_message is None
    assert not result.requires_elevation
