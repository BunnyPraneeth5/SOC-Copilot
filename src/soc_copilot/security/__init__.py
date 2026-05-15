"""Security module for SOC Copilot

Provides:
- File permission enforcement (permissions)
- Input validation and path traversal prevention (input_validator)
- ML model integrity verification (model_integrity)
"""

from .permissions import (
    set_secure_file_permissions,
    set_secure_directory_permissions,
    validate_permissions,
    PermissionStatus,
)

from .input_validator import (
    validate_path,
    validate_log_file,
    validate_model_file,
    sanitize_log_line,
    sanitize_filename,
    ValidationResult,
)

from .network import (
    env_flag,
    is_external_ip,
    online_enrichment_enabled,
)

from .model_integrity import (
    verify_models,
    verify_model_file,
    generate_manifest,
    save_manifest,
    IntegrityResult,
)

__all__ = [
    # Permissions
    "set_secure_file_permissions",
    "set_secure_directory_permissions",
    "validate_permissions",
    "PermissionStatus",
    # Input validation
    "validate_path",
    "validate_log_file",
    "validate_model_file",
    "sanitize_log_line",
    "sanitize_filename",
    "ValidationResult",
    "env_flag",
    "is_external_ip",
    "online_enrichment_enabled",
    # Model integrity
    "verify_models",
    "verify_model_file",
    "generate_manifest",
    "save_manifest",
    "IntegrityResult",
]
