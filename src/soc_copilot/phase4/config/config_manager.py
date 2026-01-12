"""Configuration manager for YAML-based settings

This module provides clean read/write access to configuration files
without modifying ML models, pipeline logic, or triggering ingestion.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml


class ConfigManager:
    """Manages YAML configuration for SOC Copilot
    
    Handles read/write to config/ingestion/system_logs.yaml.
    Changes require application restart to take effect.
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            # Navigate from phase4/config to project root
            project_root = Path(__file__).parent.parent.parent.parent.parent
        self.project_root = Path(project_root)
        self._ingestion_config_path = self.project_root / "config" / "ingestion" / "system_logs.yaml"
    
    @property
    def ingestion_config_path(self) -> Path:
        """Path to ingestion config file"""
        return self._ingestion_config_path
    
    def load_ingestion_config(self) -> Dict[str, Any]:
        """Load ingestion configuration from YAML
        
        Returns:
            Configuration dictionary, or empty dict if file not found
        """
        if not self._ingestion_config_path.exists():
            return {}
        
        try:
            with open(self._ingestion_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config if config else {}
        except (yaml.YAMLError, OSError):
            return {}
    
    def save_ingestion_config(self, config: Dict[str, Any]) -> bool:
        """Save ingestion configuration to YAML
        
        Args:
            config: Configuration dictionary to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Ensure directory exists
            self._ingestion_config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._ingestion_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            return True
        except (yaml.YAMLError, OSError):
            return False
    
    def get_system_logs_enabled(self) -> bool:
        """Get current system logs enabled state
        
        Returns:
            True if system logs are enabled, False otherwise
        """
        config = self.load_ingestion_config()
        return config.get('enabled', False)
    
    def set_system_logs_enabled(self, enabled: bool) -> bool:
        """Set system logs enabled state
        
        This only writes to YAML config. Application restart required
        for changes to take effect. Does NOT start ingestion.
        
        Args:
            enabled: Whether system logs should be enabled
            
        Returns:
            True if saved successfully, False otherwise
        """
        config = self.load_ingestion_config()
        config['enabled'] = enabled
        return self.save_ingestion_config(config)
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get summary of current configuration state
        
        Returns:
            Dictionary with configuration summary for UI display
        """
        config = self.load_ingestion_config()
        return {
            'system_logs_enabled': config.get('enabled', False),
            'export_interval': config.get('export_interval', 5),
            'log_types': config.get('log_types', []),
            'max_batch_size': config.get('max_batch_size', 100),
            'enforce_killswitch': config.get('enforce_killswitch', True)
        }
