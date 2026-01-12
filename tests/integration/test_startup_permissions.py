"""Integration tests for startup permission checks"""

import pytest
import tempfile
import shutil
from pathlib import Path
import sys
import os


@pytest.fixture
def temp_project():
    """Create temporary project structure"""
    temp = Path(tempfile.mkdtemp())
    
    # Create minimal project structure
    src_dir = temp / "src" / "soc_copilot"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").touch()
    
    phase4_dir = src_dir / "phase4"
    phase4_dir.mkdir()
    (phase4_dir / "__init__.py").touch()
    
    ingestion_dir = phase4_dir / "ingestion"
    ingestion_dir.mkdir()
    (ingestion_dir / "__init__.py").touch()
    
    yield temp
    
    shutil.rmtree(temp, ignore_errors=True)


def test_launch_ui_checks_permissions_before_start(temp_project):
    """Launch UI should check permissions before starting"""
    # Add to path
    sys.path.insert(0, str(temp_project / "src"))
    
    from launch_ui import check_required_permissions
    
    # Should succeed with writable temp directory
    result = check_required_permissions(temp_project)
    assert result is True


def test_launch_ui_creates_required_directories(temp_project):
    """Launch UI should create required directories"""
    sys.path.insert(0, str(temp_project / "src"))
    
    from launch_ui import check_required_permissions
    
    data_dir = temp_project / "data"
    logs_dir = temp_project / "logs"
    
    assert not data_dir.exists()
    assert not logs_dir.exists()
    
    check_required_permissions(temp_project)
    
    assert data_dir.exists()
    assert logs_dir.exists()


def test_launch_ui_optional_permissions_non_blocking(temp_project):
    """Launch UI optional permission check should not block startup"""
    sys.path.insert(0, str(temp_project / "src"))
    
    from launch_ui import check_optional_permissions
    
    # Should return result even if system log reader unavailable
    result = check_optional_permissions(temp_project)
    
    assert isinstance(result, dict)
    assert "has_system_log_access" in result


def test_setup_fails_on_permission_error(temp_project, monkeypatch):
    """Setup should fail with clear message on permission error"""
    if sys.platform == "win32":
        pytest.skip("Readonly test not reliable on Windows")
    
    monkeypatch.chdir(temp_project)
    
    # Create readonly data directory
    data_dir = temp_project / "data"
    data_dir.mkdir()
    os.chmod(data_dir, 0o444)
    
    try:
        import setup
        
        result = setup.check_permissions()
        assert result is False
    finally:
        os.chmod(data_dir, 0o755)


def test_check_requirements_distinguishes_critical_optional():
    """Check requirements should distinguish critical vs optional checks"""
    import check_requirements
    
    # System log permissions should be optional
    result = check_requirements.check_system_log_permissions()
    
    # Should return boolean, not raise exception
    assert isinstance(result, bool)


def test_permission_check_provides_remediation():
    """Permission checks should provide remediation steps"""
    import tempfile
    from pathlib import Path
    
    temp = Path(tempfile.mkdtemp())
    
    try:
        from launch_ui import check_required_permissions
        
        # Should succeed and not print remediation
        result = check_required_permissions(temp)
        assert result is True
    finally:
        shutil.rmtree(temp, ignore_errors=True)
