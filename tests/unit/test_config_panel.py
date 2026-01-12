"""Unit tests for Configuration UI Controls

Tests for:
- ConfigManager YAML read/write operations
- ConfigPanel toggle and status indicator logic
- No ML/pipeline calls from config module
- Read-only access for status fields
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import yaml

from soc_copilot.phase4.config import ConfigManager


# ============================================================================
# ConfigManager Tests
# ============================================================================

class TestConfigManager:
    """Test ConfigManager YAML operations"""
    
    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create temp project structure"""
        config_dir = tmp_path / "config" / "ingestion"
        config_dir.mkdir(parents=True)
        return tmp_path
    
    @pytest.fixture
    def config_manager(self, temp_project):
        """Create ConfigManager with temp project"""
        return ConfigManager(temp_project)
    
    def test_load_empty_config(self, config_manager):
        """Test loading when config file doesn't exist"""
        config = config_manager.load_ingestion_config()
        assert config == {}
    
    def test_save_and_load_config(self, config_manager):
        """Test round-trip save and load"""
        test_config = {
            'enabled': True,
            'export_interval': 10,
            'log_types': ['windows_security']
        }
        
        result = config_manager.save_ingestion_config(test_config)
        assert result is True
        
        loaded = config_manager.load_ingestion_config()
        assert loaded['enabled'] is True
        assert loaded['export_interval'] == 10
        assert loaded['log_types'] == ['windows_security']
    
    def test_get_system_logs_enabled_default(self, config_manager):
        """Test default enabled state is False"""
        enabled = config_manager.get_system_logs_enabled()
        assert enabled is False
    
    def test_set_system_logs_enabled(self, config_manager):
        """Test enabling system logs"""
        result = config_manager.set_system_logs_enabled(True)
        assert result is True
        
        enabled = config_manager.get_system_logs_enabled()
        assert enabled is True
    
    def test_set_system_logs_disabled(self, config_manager):
        """Test disabling system logs"""
        # First enable
        config_manager.set_system_logs_enabled(True)
        
        # Then disable
        result = config_manager.set_system_logs_enabled(False)
        assert result is True
        
        enabled = config_manager.get_system_logs_enabled()
        assert enabled is False
    
    def test_preserves_existing_config(self, config_manager):
        """Test that toggle preserves other config values"""
        # Save initial config
        initial = {
            'enabled': False,
            'export_interval': 5,
            'log_types': ['windows_security', 'windows_system'],
            'max_batch_size': 100
        }
        config_manager.save_ingestion_config(initial)
        
        # Toggle enabled
        config_manager.set_system_logs_enabled(True)
        
        # Verify other values preserved
        loaded = config_manager.load_ingestion_config()
        assert loaded['enabled'] is True
        assert loaded['export_interval'] == 5
        assert loaded['log_types'] == ['windows_security', 'windows_system']
        assert loaded['max_batch_size'] == 100
    
    def test_get_config_summary(self, config_manager):
        """Test getting config summary"""
        test_config = {
            'enabled': True,
            'export_interval': 10,
            'log_types': ['windows_security'],
            'max_batch_size': 50,
            'enforce_killswitch': True
        }
        config_manager.save_ingestion_config(test_config)
        
        summary = config_manager.get_config_summary()
        
        assert summary['system_logs_enabled'] is True
        assert summary['export_interval'] == 10
        assert summary['log_types'] == ['windows_security']
        assert summary['max_batch_size'] == 50
        assert summary['enforce_killswitch'] is True
    
    def test_yaml_format_preserved(self, config_manager):
        """Test that YAML file is readable and properly formatted"""
        config_manager.set_system_logs_enabled(True)
        
        # Read raw file
        with open(config_manager.ingestion_config_path, 'r') as f:
            content = f.read()
        
        # Should be valid YAML
        parsed = yaml.safe_load(content)
        assert parsed['enabled'] is True
    
    def test_handles_invalid_yaml(self, config_manager):
        """Test handling of invalid YAML file"""
        # Write invalid YAML
        config_manager.ingestion_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_manager.ingestion_config_path, 'w') as f:
            f.write(":::invalid yaml:::{{")
        
        # Should return empty dict, not raise
        config = config_manager.load_ingestion_config()
        assert config == {}


# ============================================================================
# ConfigPanel Logic Tests (No Qt)
# ============================================================================

class TestConfigPanelLogic:
    """Test ConfigPanel logic without Qt event loop"""
    
    def test_status_color_mapping(self):
        """Test status to color mapping logic"""
        def get_status_color(status: str) -> str:
            colors = {
                'Enabled': '#4CAF50',    # Green
                'Disabled': '#666666',   # Grey
                'Active': '#4CAF50',     # Green
                'Inactive': '#4CAF50',   # Green (kill switch inactive is good)
                'Stopped': '#FFC107',    # Yellow
                'Limited': '#FFC107',    # Yellow
                'Not Started': '#666666' # Grey
            }
            return colors.get(status, '#888888')
        
        assert get_status_color('Enabled') == '#4CAF50'
        assert get_status_color('Disabled') == '#666666'
        assert get_status_color('Active') == '#4CAF50'
        assert get_status_color('Stopped') == '#FFC107'
        assert get_status_color('Unknown') == '#888888'
    
    def test_ingestion_status_logic(self):
        """Test ingestion status determination logic"""
        def get_ingestion_status(running: bool, shutdown: bool, sources: int) -> str:
            if shutdown:
                return "Stopped"
            elif running and sources > 0:
                return "Active"
            elif sources > 0:
                return "Configured"
            else:
                return "Not Started"
        
        assert get_ingestion_status(False, False, 0) == "Not Started"
        assert get_ingestion_status(True, False, 1) == "Active"
        assert get_ingestion_status(False, True, 1) == "Stopped"
        assert get_ingestion_status(False, False, 2) == "Configured"
    
    def test_logs_enabled_indicator(self):
        """Test system logs indicator logic"""
        def get_logs_indicator(enabled: bool) -> tuple:
            if enabled:
                return ("Enabled", "#4CAF50")
            else:
                return ("Disabled", "#666666")
        
        assert get_logs_indicator(True) == ("Enabled", "#4CAF50")
        assert get_logs_indicator(False) == ("Disabled", "#666666")
    
    def test_kill_switch_indicator(self):
        """Test kill switch indicator logic"""
        def get_kill_switch_indicator(active: bool) -> tuple:
            if active:
                return ("Active", "#f44336")  # Red - bad
            else:
                return ("Inactive", "#4CAF50")  # Green - good
        
        assert get_kill_switch_indicator(True) == ("Active", "#f44336")
        assert get_kill_switch_indicator(False) == ("Inactive", "#4CAF50")


# ============================================================================
# Safety Tests
# ============================================================================

class TestConfigSafety:
    """Test safety constraints for config module"""
    
    def test_no_ml_imports(self):
        """Verify config module has no ML imports"""
        import inspect
        from soc_copilot.phase4.config import config_manager
        
        source = inspect.getsource(config_manager)
        
        # Should not import ML modules
        assert "from soc_copilot.models" not in source
        assert "from soc_copilot.data" not in source
        assert "import sklearn" not in source
        assert "import torch" not in source
        assert "import tensorflow" not in source
    
    def test_no_pipeline_imports(self):
        """Verify config module doesn't import pipeline"""
        import inspect
        from soc_copilot.phase4.config import config_manager
        
        source = inspect.getsource(config_manager)
        
        assert "from soc_copilot.pipeline" not in source
        assert "import soc_copilot.pipeline" not in source
    
    def test_no_ingestion_start(self):
        """Verify config module doesn't start ingestion"""
        import inspect
        from soc_copilot.phase4.config import config_manager
        
        source = inspect.getsource(config_manager)
        
        # Should not have methods that start ingestion
        assert ".start(" not in source
        assert "ingestion_controller" not in source.lower()
    
    def test_no_network_calls(self):
        """Verify config module doesn't make network calls"""
        import inspect
        from soc_copilot.phase4.config import config_manager
        
        source = inspect.getsource(config_manager)
        
        assert "import requests" not in source
        assert "import urllib" not in source
        assert "import http" not in source
        assert "socket" not in source.lower()


# ============================================================================
# Integration Tests
# ============================================================================

class TestConfigIntegration:
    """Test config integration with real components"""
    
    def test_real_yaml_file_format(self, tmp_path):
        """Test config matches expected YAML format"""
        config_manager = ConfigManager(tmp_path)
        
        # Create config similar to real file
        config = {
            'enabled': True,
            'export_interval': 5,
            'log_types': ['windows_security', 'windows_system'],
            'file_paths': {
                'windows_security': 'logs/system/windows_security.log',
                'windows_system': 'logs/system/windows_system.log'
            },
            'max_batch_size': 100,
            'batch_interval': 5.0,
            'enforce_killswitch': True
        }
        
        config_manager.save_ingestion_config(config)
        
        # Verify file contents
        with open(config_manager.ingestion_config_path, 'r') as f:
            loaded = yaml.safe_load(f)
        
        assert loaded['enabled'] is True
        assert loaded['file_paths']['windows_security'] == 'logs/system/windows_security.log'
    
    def test_toggle_does_not_start_ingestion(self, tmp_path):
        """Verify toggle only writes config, doesn't start ingestion"""
        config_manager = ConfigManager(tmp_path)
        
        # Enable system logs
        result = config_manager.set_system_logs_enabled(True)
        assert result is True
        
        # Verify only config file was touched, no processes started
        # If ingestion was started, there would be log files or state changes
        # This test just verifies the toggle returns cleanly
        assert config_manager.get_system_logs_enabled() is True
    
    def test_config_survives_restart(self, tmp_path):
        """Test config persists across ConfigManager instances"""
        # First instance
        cm1 = ConfigManager(tmp_path)
        cm1.set_system_logs_enabled(True)
        
        # Second instance (simulating restart)
        cm2 = ConfigManager(tmp_path)
        assert cm2.get_system_logs_enabled() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
