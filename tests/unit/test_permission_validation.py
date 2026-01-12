"""Simple permission validation tests"""

import pytest
import tempfile
from pathlib import Path
import shutil


def test_directory_write_permission_check():
    """Test basic directory write permission check"""
    temp = Path(tempfile.mkdtemp())
    
    try:
        # Should be able to write
        test_file = temp / ".write_test"
        test_file.write_text("test")
        assert test_file.exists()
        
        # Should be able to delete
        test_file.unlink()
        assert not test_file.exists()
        
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_permission_check_creates_missing_directory():
    """Permission check should create missing directory"""
    temp = Path(tempfile.mkdtemp())
    
    try:
        test_dir = temp / "new_dir"
        assert not test_dir.exists()
        
        # Create directory
        test_dir.mkdir(parents=True, exist_ok=True)
        assert test_dir.exists()
        
        # Test write
        test_file = test_dir / ".write_test"
        test_file.write_text("test")
        assert test_file.exists()
        
        test_file.unlink()
        
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_permission_check_handles_nested_directories():
    """Permission check should handle nested directories"""
    temp = Path(tempfile.mkdtemp())
    
    try:
        nested_dir = temp / "data" / "models"
        nested_dir.mkdir(parents=True, exist_ok=True)
        
        assert nested_dir.exists()
        assert (temp / "data").exists()
        
        # Test write in nested dir
        test_file = nested_dir / ".write_test"
        test_file.write_text("test")
        assert test_file.exists()
        
        test_file.unlink()
        
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def test_permission_error_detection():
    """Test detection of permission errors"""
    import os
    import sys
    
    if sys.platform == "win32":
        pytest.skip("Readonly test not reliable on Windows")
    
    temp = Path(tempfile.mkdtemp())
    
    try:
        # Make directory readonly
        os.chmod(temp, 0o444)
        
        # Try to write - should fail
        test_file = temp / ".write_test"
        
        with pytest.raises((OSError, PermissionError)):
            test_file.write_text("test")
        
    finally:
        # Restore permissions for cleanup
        os.chmod(temp, 0o755)
        shutil.rmtree(temp, ignore_errors=True)
