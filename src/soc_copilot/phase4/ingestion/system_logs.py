"""System log integration for SOC Copilot

CRITICAL DESIGN PRINCIPLE:
SOC Copilot NEVER reads OS logs directly.
External exporters write to files; SOC Copilot reads files.

This follows industry-standard decoupled architecture:
OS Logs → External Exporter → Files → SOC Copilot
"""

from pathlib import Path
from typing import Optional, Callable
import yaml

from soc_copilot.phase4.ingestion import IngestionController


class SystemLogConfig:
    """System log configuration"""
    
    def __init__(self, config_path: str = "config/ingestion/system_logs.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load configuration"""
        if not self.config_path.exists():
            return self._default_config()
        
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f) or self._default_config()
        except Exception:
            return self._default_config()
    
    def _default_config(self) -> dict:
        """Default configuration"""
        return {
            "enabled": False,
            "export_interval": 5,
            "log_types": ["windows_security", "windows_system"],
            "file_paths": {
                "windows_security": "logs/system/windows_security.log",
                "windows_system": "logs/system/windows_system.log"
            },
            "max_batch_size": 100,
            "batch_interval": 5.0,
            "enforce_killswitch": True
        }
    
    @property
    def enabled(self) -> bool:
        return self._config.get("enabled", False)
    
    @property
    def file_paths(self) -> dict:
        return self._config.get("file_paths", {})
    
    @property
    def batch_interval(self) -> float:
        return self._config.get("batch_interval", 5.0)
    
    @property
    def enforce_killswitch(self) -> bool:
        return self._config.get("enforce_killswitch", True)
    
    def to_dict(self) -> dict:
        return self._config.copy()


class SystemLogIntegration:
    """System log integration controller
    
    Manages ingestion of system logs exported by external tools.
    DOES NOT access OS logs directly.
    """
    
    def __init__(self, config_path: str = "config/ingestion/system_logs.yaml",
                 killswitch_check: Optional[Callable[[], bool]] = None):
        self.config = SystemLogConfig(config_path)
        self.killswitch_check = killswitch_check
        self._controller: Optional[IngestionController] = None
    
    def initialize(self, batch_callback: Callable):
        """Initialize ingestion controller"""
        if not self.config.enabled:
            return
        
        # Create controller with killswitch enforcement
        self._controller = IngestionController(
            batch_interval=self.config.batch_interval,
            killswitch_check=self._get_killswitch_check()
        )
        
        # Register file sources
        for log_type, filepath in self.config.file_paths.items():
            file_path = Path(filepath)
            if file_path.exists():
                self._controller.add_file_source(str(file_path))
        
        # Set batch callback
        self._controller.set_batch_callback(batch_callback)
    
    def start(self):
        """Start system log ingestion"""
        if not self.config.enabled:
            raise RuntimeError("System log ingestion is disabled in config")
        
        if not self._controller:
            raise RuntimeError("Controller not initialized. Call initialize() first.")
        
        # Check killswitch before starting
        if self._check_killswitch():
            raise RuntimeError("Cannot start: governance kill switch is enabled")
        
        self._controller.start()
    
    def stop(self):
        """Stop system log ingestion"""
        if self._controller:
            self._controller.stop()
    
    def is_running(self) -> bool:
        """Check if ingestion is running"""
        if not self._controller:
            return False
        return self._controller.is_running()
    
    def get_status(self) -> dict:
        """Get system log ingestion status"""
        status = {
            "enabled": self.config.enabled,
            "running": self.is_running(),
            "killswitch_active": self._check_killswitch(),
            "registered_sources": list(self.config.file_paths.keys())
        }
        
        if self._controller:
            status.update(self._controller.get_stats())
        
        return status
    
    def _get_killswitch_check(self) -> Optional[Callable[[], bool]]:
        """Get killswitch check function"""
        if not self.config.enforce_killswitch:
            return None
        return self.killswitch_check
    
    def _check_killswitch(self) -> bool:
        """Check if killswitch is active"""
        if self.killswitch_check:
            return self.killswitch_check()
        return False
