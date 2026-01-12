"""Secure file permissions management for SOC Copilot"""

import os
import platform
from pathlib import Path
from typing import Literal
from dataclasses import dataclass


@dataclass
class PermissionStatus:
    """Permission validation status"""
    path: str
    is_secure: bool
    current_mode: int
    expected_mode: int
    error: str = None


def set_secure_file_permissions(path: Path, file_type: Literal["db", "model", "log"]) -> bool:
    """Set secure permissions on file at creation time
    
    Args:
        path: File path
        file_type: Type of file (db=600, model=600, log=640)
    
    Returns:
        True if permissions set successfully, False otherwise
    """
    if not path.exists():
        return False
    
    # Define permission modes
    modes = {
        "db": 0o600,      # SQLite: owner read/write only
        "model": 0o600,   # Models: owner read/write only
        "log": 0o640      # Logs: owner read/write, group read
    }
    
    mode = modes.get(file_type)
    if mode is None:
        return False
    
    return _set_permissions(path, mode)


def set_secure_directory_permissions(path: Path) -> bool:
    """Set secure permissions on directory
    
    Args:
        path: Directory path
    
    Returns:
        True if permissions set successfully, False otherwise
    """
    if not path.exists() or not path.is_dir():
        return False
    
    # Directories: owner read/write/execute only
    return _set_permissions(path, 0o700)


def validate_permissions(path: Path) -> PermissionStatus:
    """Validate file/directory permissions
    
    Args:
        path: Path to validate
    
    Returns:
        PermissionStatus with validation results
    """
    if not path.exists():
        return PermissionStatus(
            path=str(path),
            is_secure=False,
            current_mode=0,
            expected_mode=0,
            error="Path does not exist"
        )
    
    try:
        stat_info = path.stat()
        current_mode = stat_info.st_mode & 0o777
        
        # Determine expected mode
        if path.is_dir():
            expected_mode = 0o700
        else:
            # Check file extension for type
            suffix = path.suffix.lower()
            if suffix in [".db", ".sqlite", ".sqlite3"]:
                expected_mode = 0o600
            elif suffix in [".joblib", ".pkl", ".json"]:
                expected_mode = 0o600
            elif suffix in [".log", ".txt"]:
                expected_mode = 0o640
            else:
                expected_mode = 0o600  # Default to most restrictive
        
        # On Windows, chmod may not work as expected
        if platform.system() == "Windows":
            # Best-effort validation on Windows
            is_secure = True  # Assume secure on Windows
        else:
            # Strict validation on Unix-like systems
            is_secure = current_mode == expected_mode
        
        return PermissionStatus(
            path=str(path),
            is_secure=is_secure,
            current_mode=current_mode,
            expected_mode=expected_mode
        )
    
    except Exception as e:
        return PermissionStatus(
            path=str(path),
            is_secure=False,
            current_mode=0,
            expected_mode=0,
            error=str(e)
        )


def _set_permissions(path: Path, mode: int) -> bool:
    """Internal function to set permissions with OS-specific handling
    
    Args:
        path: Path to set permissions on
        mode: Permission mode (octal)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        os.chmod(path, mode)
        return True
    except (OSError, NotImplementedError) as e:
        # Windows may not support chmod fully
        if platform.system() == "Windows":
            # Log warning but don't fail on Windows
            # This is best-effort on Windows
            return True
        else:
            # On Unix-like systems, this is a real error
            return False
    except Exception:
        return False
