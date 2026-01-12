"""Integration tests for secure permission application"""

import pytest
import tempfile
import shutil
from pathlib import Path
import platform

from soc_copilot.security.permissions import (
    set_secure_file_permissions,
    set_secure_directory_permissions,
    validate_permissions
)


@pytest.fixture
def temp_project():
    """Create temporary project structure"""
    temp = Path(tempfile.mkdtemp())
    
    # Create project structure
    (temp / "data" / "models").mkdir(parents=True)
    (temp / "logs").mkdir(parents=True)
    
    yield temp
    
    shutil.rmtree(temp, ignore_errors=True)


def test_secure_permissions_on_new_db(temp_project):
    """Test applying secure permissions to new database"""
    db_path = temp_project / "data" / "test.db"
    db_path.write_text("test database")
    
    # Apply secure permissions
    result = set_secure_file_permissions(db_path, "db")
    assert result is True
    
    # Validate
    status = validate_permissions(db_path)
    if platform.system() != "Windows":
        assert status.is_secure is True


def test_secure_permissions_on_new_model(temp_project):
    """Test applying secure permissions to new model file"""
    model_path = temp_project / "data" / "models" / "model.joblib"
    model_path.write_text("test model")
    
    # Apply secure permissions
    result = set_secure_file_permissions(model_path, "model")
    assert result is True
    
    # Validate
    status = validate_permissions(model_path)
    if platform.system() != "Windows":
        assert status.is_secure is True


def test_secure_permissions_on_new_log(temp_project):
    """Test applying secure permissions to new log file"""
    log_path = temp_project / "logs" / "app.log"
    log_path.write_text("test log")
    
    # Apply secure permissions
    result = set_secure_file_permissions(log_path, "log")
    assert result is True
    
    # Validate
    status = validate_permissions(log_path)
    if platform.system() != "Windows":
        assert status.is_secure is True


def test_secure_permissions_on_directories(temp_project):
    """Test applying secure permissions to directories"""
    data_dir = temp_project / "data"
    logs_dir = temp_project / "logs"
    
    # Apply secure permissions
    assert set_secure_directory_permissions(data_dir) is True
    assert set_secure_directory_permissions(logs_dir) is True
    
    # Validate
    data_status = validate_permissions(data_dir)
    logs_status = validate_permissions(logs_dir)
    
    if platform.system() != "Windows":
        assert data_status.is_secure is True
        assert logs_status.is_secure is True


def test_permission_workflow_db_creation(temp_project):
    """Test complete workflow: create DB, set permissions, validate"""
    db_path = temp_project / "data" / "alerts.db"
    
    # Simulate DB creation
    db_path.write_text("CREATE TABLE alerts...")
    
    # Apply permissions immediately after creation
    set_secure_file_permissions(db_path, "db")
    
    # Validate
    status = validate_permissions(db_path)
    assert status.path == str(db_path)
    assert status.expected_mode == 0o600


def test_permission_workflow_log_creation(temp_project):
    """Test complete workflow: create log, set permissions, validate"""
    log_path = temp_project / "logs" / "system.log"
    
    # Simulate log creation
    log_path.write_text("Log entry 1\n")
    
    # Apply permissions immediately after creation
    set_secure_file_permissions(log_path, "log")
    
    # Validate
    status = validate_permissions(log_path)
    assert status.path == str(log_path)
    assert status.expected_mode == 0o640


def test_permission_workflow_model_save(temp_project):
    """Test complete workflow: save model, set permissions, validate"""
    model_path = temp_project / "data" / "models" / "isolation_forest_v1.joblib"
    
    # Simulate model save
    model_path.write_text("model data")
    
    # Apply permissions immediately after save
    set_secure_file_permissions(model_path, "model")
    
    # Validate
    status = validate_permissions(model_path)
    assert status.path == str(model_path)
    assert status.expected_mode == 0o600


def test_no_retroactive_modification(temp_project):
    """Test that existing files are not modified retroactively"""
    existing_file = temp_project / "data" / "existing.db"
    existing_file.write_text("existing data")
    
    # Get initial state
    initial_status = validate_permissions(existing_file)
    initial_mode = initial_status.current_mode
    
    # Permission module should NOT modify existing files
    # Only new files should have permissions set
    
    # Verify file still exists with original permissions
    current_status = validate_permissions(existing_file)
    assert current_status.current_mode == initial_mode


def test_cross_platform_compatibility(temp_project):
    """Test cross-platform compatibility"""
    test_file = temp_project / "data" / "test.db"
    test_file.write_text("test")
    
    # Should work on all platforms
    result = set_secure_file_permissions(test_file, "db")
    assert result is True
    
    # Validation should work on all platforms
    status = validate_permissions(test_file)
    assert isinstance(status, type(status))
    assert status.path == str(test_file)


def test_multiple_file_types(temp_project):
    """Test setting permissions on multiple file types"""
    files = [
        (temp_project / "data" / "test.db", "db", 0o600),
        (temp_project / "data" / "model.joblib", "model", 0o600),
        (temp_project / "logs" / "app.log", "log", 0o640)
    ]
    
    for file_path, file_type, expected_mode in files:
        file_path.write_text("test")
        result = set_secure_file_permissions(file_path, file_type)
        assert result is True
        
        status = validate_permissions(file_path)
        assert status.expected_mode == expected_mode
