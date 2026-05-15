"""Centralized input validation and sanitization for SOC Copilot.

Security hardening module that prevents:
- Path traversal attacks
- Loading of unsafe file types
- Processing of excessively large files
- Control character injection in log inputs
"""

import os
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Allowed file extensions for log ingestion
ALLOWED_LOG_EXTENSIONS = frozenset({
    ".log", ".syslog", ".jsonl", ".json", ".evtx", ".csv", ".tsv", ".txt",
})

# Allowed file extensions for model loading
ALLOWED_MODEL_EXTENSIONS = frozenset({
    ".joblib", ".json",
})

# Allowed file extensions for config loading
ALLOWED_CONFIG_EXTENSIONS = frozenset({
    ".yaml", ".yml",
})

# Maximum file sizes (bytes)
MAX_LOG_FILE_SIZE = 500 * 1024 * 1024       # 500 MB
MAX_MODEL_FILE_SIZE = 200 * 1024 * 1024     # 200 MB
MAX_CONFIG_FILE_SIZE = 1 * 1024 * 1024      # 1 MB

# Control character pattern (ASCII 0-31 except \t \n \r)
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of an input validation check."""
    is_valid: bool
    error: Optional[str] = None
    sanitized_path: Optional[Path] = None


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def validate_path(
    path: str | Path,
    allowed_base_dirs: Optional[list[Path]] = None,
    must_exist: bool = False,
) -> ValidationResult:
    """Validate a file path against traversal attacks.
    
    Args:
        path: The path to validate
        allowed_base_dirs: If provided, the resolved path must be under one of these
        must_exist: If True, the path must exist on disk
    
    Returns:
        ValidationResult with is_valid and optional error message
    """
    if not path:
        return ValidationResult(is_valid=False, error="Empty path provided")
    
    path_str = str(path)
    
    # Block null bytes
    if "\x00" in path_str:
        return ValidationResult(is_valid=False, error="Null byte in path")
    
    try:
        resolved = Path(path).resolve()
    except (OSError, ValueError) as e:
        return ValidationResult(is_valid=False, error=f"Invalid path: {e}")
    
    # Check for path traversal patterns in the original input
    normalized = path_str.replace("\\", "/")
    if "/.." in normalized or "../" in normalized or normalized == "..":
        return ValidationResult(
            is_valid=False,
            error="Path traversal detected: '..' components not allowed",
        )
    
    # If allowed_base_dirs specified, ensure path is within one of them
    if allowed_base_dirs:
        in_allowed = False
        for base_dir in allowed_base_dirs:
            try:
                resolved_base = base_dir.resolve()
                resolved.relative_to(resolved_base)
                in_allowed = True
                break
            except (OSError, ValueError):
                continue
        
        if not in_allowed:
            return ValidationResult(
                is_valid=False,
                error=f"Path '{resolved}' is outside allowed directories",
            )
    
    # Existence check
    if must_exist and not resolved.exists():
        return ValidationResult(
            is_valid=False,
            error=f"Path does not exist: {resolved}",
        )
    
    return ValidationResult(is_valid=True, sanitized_path=resolved)


def validate_log_file(
    path: str | Path,
    allowed_base_dirs: Optional[list[Path]] = None,
    must_exist: bool = False,
) -> ValidationResult:
    """Validate a log file path for safe ingestion.
    
    Checks:
    - Path traversal safety
    - File extension is allowed
    - File size does not exceed limit
    
    Args:
        path: Log file path to validate
        allowed_base_dirs: Optional base directory restrictions
    
    Returns:
        ValidationResult
    """
    # Base path validation
    result = validate_path(path, allowed_base_dirs=allowed_base_dirs, must_exist=must_exist)
    if not result.is_valid:
        return result
    
    resolved = result.sanitized_path
    
    # Extension check
    ext = resolved.suffix.lower()
    if ext not in ALLOWED_LOG_EXTENSIONS:
        return ValidationResult(
            is_valid=False,
            error=f"Unsafe file extension '{ext}'. Allowed: {sorted(ALLOWED_LOG_EXTENSIONS)}",
        )
    
    # Size check (only if file exists)
    if resolved.exists():
        try:
            size = resolved.stat().st_size
            if size > MAX_LOG_FILE_SIZE:
                size_mb = size / (1024 * 1024)
                limit_mb = MAX_LOG_FILE_SIZE / (1024 * 1024)
                return ValidationResult(
                    is_valid=False,
                    error=f"File too large: {size_mb:.0f}MB (limit: {limit_mb:.0f}MB)",
                )
        except OSError as e:
            return ValidationResult(is_valid=False, error=f"Cannot stat file: {e}")
    
    return ValidationResult(is_valid=True, sanitized_path=resolved)


def validate_model_file(path: str | Path) -> ValidationResult:
    """Validate a model file path.
    
    Checks extension and file size.
    
    Args:
        path: Model file path to validate
    
    Returns:
        ValidationResult
    """
    result = validate_path(path, must_exist=True)
    if not result.is_valid:
        return result
    
    resolved = result.sanitized_path
    
    ext = resolved.suffix.lower()
    if ext not in ALLOWED_MODEL_EXTENSIONS:
        return ValidationResult(
            is_valid=False,
            error=f"Unsafe model file extension '{ext}'. Allowed: {sorted(ALLOWED_MODEL_EXTENSIONS)}",
        )
    
    try:
        size = resolved.stat().st_size
        if size > MAX_MODEL_FILE_SIZE:
            size_mb = size / (1024 * 1024)
            limit_mb = MAX_MODEL_FILE_SIZE / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error=f"Model file too large: {size_mb:.0f}MB (limit: {limit_mb:.0f}MB)",
            )
    except OSError as e:
        return ValidationResult(is_valid=False, error=f"Cannot stat model file: {e}")
    
    return ValidationResult(is_valid=True, sanitized_path=resolved)


# ---------------------------------------------------------------------------
# String sanitization
# ---------------------------------------------------------------------------

def sanitize_log_line(line: str, max_length: int = 10_000) -> str:
    """Sanitize a raw log line before processing.
    
    - Strips control characters (keeps tabs, newlines, carriage returns)
    - Truncates to max_length
    - Strips leading/trailing whitespace
    
    Args:
        line: Raw log line
        max_length: Maximum allowed length
    
    Returns:
        Sanitized log line
    """
    if not line:
        return ""
    
    # Remove control characters
    cleaned = _CONTROL_CHARS.sub("", line)
    
    # Truncate
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    
    return cleaned.strip()


def sanitize_filename(name: str) -> str:
    """Sanitize a filename to prevent path injection.
    
    Removes directory separators, null bytes, and other dangerous characters.
    
    Args:
        name: Filename to sanitize
    
    Returns:
        Safe filename string
    """
    if not name:
        return ""
    
    # Remove path separators and null bytes
    sanitized = name.replace("/", "_").replace("\\", "_").replace("\x00", "")
    
    # Remove other potentially dangerous characters
    sanitized = re.sub(r'[<>:"|?*]', "_", sanitized)
    
    # Prevent empty result
    sanitized = sanitized.strip(". ")
    if not sanitized:
        return "unnamed"
    
    return sanitized
