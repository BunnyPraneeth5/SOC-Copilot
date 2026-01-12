"""
Integration Guide: Secure File Permissions

This module provides secure file permission management for SOC Copilot.
Apply permissions ONLY at file creation time.

USAGE EXAMPLES:
===============

1. When creating a SQLite database:
   
   from soc_copilot.security import set_secure_file_permissions
   
   db_path = Path("data/alerts.db")
   # Create database
   conn = sqlite3.connect(db_path)
   # ... initialize schema ...
   conn.close()
   
   # Apply secure permissions immediately after creation
   set_secure_file_permissions(db_path, "db")


2. When saving model files:
   
   from soc_copilot.security import set_secure_file_permissions
   
   model_path = Path("data/models/isolation_forest_v1.joblib")
   # Save model
   joblib.dump(model, model_path)
   
   # Apply secure permissions immediately after save
   set_secure_file_permissions(model_path, "model")


3. When creating log files:
   
   from soc_copilot.security import set_secure_file_permissions
   
   log_path = Path("logs/system.log")
   # Create log file
   with open(log_path, 'w') as f:
       f.write("Log started\n")
   
   # Apply secure permissions immediately after creation
   set_secure_file_permissions(log_path, "log")


4. When creating directories:
   
   from soc_copilot.security import set_secure_directory_permissions
   
   data_dir = Path("data/models")
   data_dir.mkdir(parents=True, exist_ok=True)
   
   # Apply secure permissions
   set_secure_directory_permissions(data_dir)


5. Validating permissions:
   
   from soc_copilot.security import validate_permissions
   
   status = validate_permissions(Path("data/alerts.db"))
   if not status.is_secure:
       print(f"Warning: Insecure permissions on {status.path}")
       print(f"Current: {oct(status.current_mode)}, Expected: {oct(status.expected_mode)}")


PERMISSION RULES:
=================

File Type       | Permission | Octal | Description
----------------|------------|-------|----------------------------------
SQLite DB       | 600        | rw--- | Owner read/write only
Model files     | 600        | rw--- | Owner read/write only
Log files       | 640        | rw-r- | Owner read/write, group read
Directories     | 700        | rwx-- | Owner read/write/execute only


PLATFORM BEHAVIOR:
==================

Linux/macOS:
- Strict enforcement using os.chmod
- Validation checks exact permission bits
- Insecure permissions detected and reported

Windows:
- Best-effort using os.chmod
- May not support full Unix permission model
- Validation is lenient (assumes secure)
- No installation failures due to chmod


ERROR HANDLING:
===============

- Permission failures are explicit (return False)
- No silent failures
- No automatic retries
- No privilege escalation
- Clear error messages in PermissionStatus


INTEGRATION POINTS:
===================

DO apply permissions:
- When creating new SQLite databases
- When saving model files (joblib.dump)
- When creating log files
- When creating data directories

DO NOT apply permissions:
- Retroactively to existing files
- During file reads
- During directory scans
- To system files


TESTING:
========

Run unit tests:
    pytest tests/unit/test_secure_permissions.py

Run integration tests:
    pytest tests/integration/test_permission_application.py

Platform-specific tests:
    pytest tests/unit/test_secure_permissions.py -k windows
    pytest tests/unit/test_secure_permissions.py -k unix
"""
