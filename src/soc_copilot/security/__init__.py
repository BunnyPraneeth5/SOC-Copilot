"""Security module for SOC Copilot"""

from .permissions import (
    set_secure_file_permissions,
    set_secure_directory_permissions,
    validate_permissions,
    PermissionStatus
)

__all__ = [
    "set_secure_file_permissions",
    "set_secure_directory_permissions",
    "validate_permissions",
    "PermissionStatus"
]
