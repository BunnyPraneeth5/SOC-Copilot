"""Unit tests for permission checks"""

import pytest
import tempfile
import shutil
from pathlib import Path
import os
import sys

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def temp_project_root():
    """Create temporary project root"""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp, ignore_errors=True)


def test_check_required_permissions_success(temp_project_root):
    """Required permission check should succeed with writable directories"""
    # Import after path setup
    from launch_ui import check_required_permissions
    
    result = check_required_permissions(temp_project_root)
    assert result is True
    assert (temp_project_root / "data").exists()
    assert (temp_project_root / "logs").exists()


def test_check_required_permissions_creates_dirs(temp_project_root):
    """Required permission check should create missing directories"""
    from launch_ui import check_required_permissions
    
    data_dir = temp_project_root / "data"
    logs_dir = temp_project_root / "logs"
    
    assert not data_dir.exists()
    assert not logs_dir.exists()
    
    result = check_required_permissions(temp_project_root)
    
    assert result is True
    assert data_dir.exists()
    assert logs_dir.exists()


def test_check_required_permissions_fails_readonly(temp_project_root):
    """Required permission check should fail with readonly directory"""
    if sys.platform == "win32":
        pytest.skip("Readonly test not reliable on Windows")
    
    from launch_ui import check_required_permissions
    
    data_dir = temp_project_root / "data"
    data_dir.mkdir()
    
    # Make readonly
    os.chmod(data_dir, 0o444)
    
    try:
        result = check_required_permissions(temp_project_root)
        assert result is False
    finally:
        # Restore permissions for cleanup
        os.chmod(data_dir, 0o755)


def test_check_optional_permissions_returns_dict(temp_project_root):
    """Optional permission check should return dict"""
    from launch_ui import check_optional_permissions
    
    result = check_optional_permissions(temp_project_root)
    
    assert isinstance(result, dict)
    assert "has_system_log_access" in result
    assert "message" in result


def test_check_optional_permissions_non_blocking(temp_project_root):
    """Optional permission check should not raise exceptions"""
    from launch_ui import check_optional_permissions
    
    # Should not raise even if system log reader unavailable
    result = check_optional_permissions(temp_project_root)
    
    assert isinstance(result, dict)


def test_setup_check_permissions_success(temp_project_root, monkeypatch):
    """Setup permission check should succeed"""
    # Change to temp directory
    monkeypatch.chdir(temp_project_root)
    
    # Import setup module
    import setup
    
    result = setup.check_permissions()
    assert result is True


def test_setup_check_permissions_creates_dirs(temp_project_root, monkeypatch):
    """Setup should create required directories"""
    monkeypatch.chdir(temp_project_root)
    
    import setup
    
    setup.check_permissions()
    
    assert (temp_project_root / "data").exists()
    assert (temp_project_root / "data" / "models").exists()
    assert (temp_project_root / "logs").exists()


def test_check_requirements_system_log_permissions():
    """Check requirements should validate system log permissions"""
    import check_requirements
    
    # Should not raise exception
    result = check_requirements.check_system_log_permissions()
    
    # Result is boolean
    assert isinstance(result, bool)
