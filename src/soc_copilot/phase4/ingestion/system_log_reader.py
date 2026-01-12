"""OS-aware system log reader with explicit permission checks"""

import platform
import os
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class PermissionCheckResult:
    """Result of permission check"""
    has_permission: bool
    error_message: Optional[str] = None
    requires_elevation: bool = False


class SystemLogReader:
    """OS-aware system log reader with explicit permission validation"""
    
    def __init__(self):
        self.os_type = platform.system()
    
    def check_windows_event_log_permission(self) -> PermissionCheckResult:
        """Check if user has permission to read Windows Event Logs"""
        if self.os_type != "Windows":
            return PermissionCheckResult(
                has_permission=False,
                error_message="Not a Windows system"
            )
        
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            
            if not is_admin:
                return PermissionCheckResult(
                    has_permission=False,
                    error_message="Administrator rights required to access Windows Event Logs",
                    requires_elevation=True
                )
            
            return PermissionCheckResult(has_permission=True)
            
        except Exception as e:
            return PermissionCheckResult(
                has_permission=False,
                error_message=f"Failed to check permissions: {e}"
            )
    
    def check_linux_syslog_permission(self, log_path: str = "/var/log/syslog") -> PermissionCheckResult:
        """Check if user has permission to read Linux system logs"""
        if self.os_type != "Linux":
            return PermissionCheckResult(
                has_permission=False,
                error_message="Not a Linux system"
            )
        
        path = Path(log_path)
        
        if not path.exists():
            return PermissionCheckResult(
                has_permission=False,
                error_message=f"Log file does not exist: {log_path}"
            )
        
        if not os.access(path, os.R_OK):
            return PermissionCheckResult(
                has_permission=False,
                error_message=f"No read permission for {log_path}",
                requires_elevation=True
            )
        
        return PermissionCheckResult(has_permission=True)
    
    def get_accessible_linux_logs(self) -> List[Tuple[str, PermissionCheckResult]]:
        """Get list of accessible Linux log files with permission status"""
        if self.os_type != "Linux":
            return []
        
        common_logs = [
            "/var/log/syslog",
            "/var/log/auth.log",
            "/var/log/kern.log",
            "/var/log/messages"
        ]
        
        results = []
        for log_path in common_logs:
            result = self.check_linux_syslog_permission(log_path)
            results.append((log_path, result))
        
        return results
    
    def validate_system_log_access(self) -> PermissionCheckResult:
        """Validate system log access for current OS"""
        if self.os_type == "Windows":
            return self.check_windows_event_log_permission()
        elif self.os_type == "Linux":
            # Check if any common log is accessible
            accessible_logs = self.get_accessible_linux_logs()
            
            if not accessible_logs:
                return PermissionCheckResult(
                    has_permission=False,
                    error_message="No system logs found"
                )
            
            # Check if at least one log is accessible
            has_any_access = any(result.has_permission for _, result in accessible_logs)
            
            if not has_any_access:
                return PermissionCheckResult(
                    has_permission=False,
                    error_message="No read permission for any system logs",
                    requires_elevation=True
                )
            
            return PermissionCheckResult(has_permission=True)
        else:
            return PermissionCheckResult(
                has_permission=False,
                error_message=f"Unsupported OS: {self.os_type}"
            )
    
    def get_system_info(self) -> dict:
        """Get system information for diagnostics"""
        return {
            "os_type": self.os_type,
            "os_release": platform.release(),
            "os_version": platform.version(),
            "python_version": platform.python_version()
        }
