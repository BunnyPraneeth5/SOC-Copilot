"""Unit tests for Sprint-17: System Log Ingestion"""

import unittest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, patch

from soc_copilot.phase4.ingestion import SystemLogConfig, SystemLogIntegration


class TestSystemLogConfig(unittest.TestCase):
    """Test system log configuration"""
    
    def test_default_config(self):
        """Test default configuration values"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_path = f.name
        
        try:
            config = SystemLogConfig(config_path)
            
            # Should use defaults when file doesn't exist
            self.assertFalse(config.enabled)
            self.assertEqual(config.batch_interval, 5.0)
            self.assertTrue(config.enforce_killswitch)
            self.assertIn("windows_security", config.file_paths)
            self.assertIn("windows_system", config.file_paths)
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_load_config(self):
        """Test loading configuration from file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "enabled": True,
                "export_interval": 10,
                "batch_interval": 3.0,
                "file_paths": {
                    "windows_security": "custom/path.log"
                },
                "enforce_killswitch": False
            }, f)
            config_path = f.name
        
        try:
            config = SystemLogConfig(config_path)
            
            self.assertTrue(config.enabled)
            self.assertEqual(config.batch_interval, 3.0)
            self.assertFalse(config.enforce_killswitch)
            self.assertEqual(config.file_paths["windows_security"], "custom/path.log")
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_to_dict(self):
        """Test configuration serialization"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_path = f.name
        
        try:
            config = SystemLogConfig(config_path)
            config_dict = config.to_dict()
            
            self.assertIsInstance(config_dict, dict)
            self.assertIn("enabled", config_dict)
            self.assertIn("file_paths", config_dict)
        finally:
            Path(config_path).unlink(missing_ok=True)


class TestSystemLogIntegration(unittest.TestCase):
    """Test system log integration"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False)
        yaml.dump({
            "enabled": True,
            "batch_interval": 1.0,
            "file_paths": {
                "windows_security": "test_security.log"
            },
            "enforce_killswitch": True
        }, self.temp_config)
        self.temp_config.close()
    
    def tearDown(self):
        """Clean up test fixtures"""
        Path(self.temp_config.name).unlink(missing_ok=True)
    
    def test_initialization_disabled(self):
        """Test integration when disabled"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"enabled": False}, f)
            config_path = f.name
        
        try:
            integration = SystemLogIntegration(config_path)
            integration.initialize(lambda x: None)
            
            # Should not create controller when disabled
            self.assertIsNone(integration._controller)
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_killswitch_enforcement(self):
        """Test killswitch enforcement"""
        killswitch_active = Mock(return_value=True)
        
        integration = SystemLogIntegration(
            self.temp_config.name,
            killswitch_check=killswitch_active
        )
        
        # Create temp log file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("test log line\n")
            log_path = f.name
        
        try:
            # Update config to use temp file
            with open(self.temp_config.name, 'w') as f:
                yaml.dump({
                    "enabled": True,
                    "batch_interval": 1.0,
                    "file_paths": {"test": log_path},
                    "enforce_killswitch": True
                }, f)
            
            integration = SystemLogIntegration(
                self.temp_config.name,
                killswitch_check=killswitch_active
            )
            integration.initialize(lambda x: None)
            
            # Should raise error when killswitch is active
            with self.assertRaises(RuntimeError) as ctx:
                integration.start()
            
            self.assertIn("kill switch", str(ctx.exception).lower())
        finally:
            Path(log_path).unlink(missing_ok=True)
    
    def test_status(self):
        """Test status reporting"""
        integration = SystemLogIntegration(self.temp_config.name)
        status = integration.get_status()
        
        self.assertIsInstance(status, dict)
        self.assertIn("enabled", status)
        self.assertIn("running", status)
        self.assertIn("killswitch_active", status)
        self.assertIn("registered_sources", status)
    
    def test_start_without_initialization(self):
        """Test starting without initialization raises error"""
        integration = SystemLogIntegration(self.temp_config.name)
        
        with self.assertRaises(RuntimeError) as ctx:
            integration.start()
        
        self.assertIn("not initialized", str(ctx.exception).lower())
    
    def test_start_when_disabled(self):
        """Test starting when disabled raises error"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({"enabled": False}, f)
            config_path = f.name
        
        try:
            integration = SystemLogIntegration(config_path)
            
            with self.assertRaises(RuntimeError) as ctx:
                integration.start()
            
            self.assertIn("disabled", str(ctx.exception).lower())
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_no_os_imports(self):
        """Test that module does NOT import OS-level log access"""
        import soc_copilot.phase4.ingestion.system_logs as module
        
        # Should NOT have direct OS log access
        self.assertFalse(hasattr(module, 'win32evtlog'))
        self.assertFalse(hasattr(module, 'wmi'))
        self.assertFalse(hasattr(module, 'pywin32'))
    
    def test_no_phase1_imports(self):
        """Test that module does NOT import Phase-1 components"""
        import soc_copilot.phase4.ingestion.system_logs as module
        import sys
        
        # Check no Phase-1 model imports
        phase1_modules = [m for m in sys.modules if 'isolation_forest' in m or 'random_forest' in m]
        
        # Module should not trigger Phase-1 imports
        self.assertEqual(len(phase1_modules), 0)


class TestGovernanceIntegration(unittest.TestCase):
    """Test governance integration"""
    
    def test_killswitch_blocks_ingestion(self):
        """Test that killswitch blocks ingestion"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "enabled": True,
                "enforce_killswitch": True,
                "batch_interval": 1.0,
                "file_paths": {}
            }, f)
            config_path = f.name
        
        try:
            # Killswitch active
            killswitch = Mock(return_value=True)
            
            integration = SystemLogIntegration(config_path, killswitch_check=killswitch)
            integration.initialize(lambda x: None)
            
            # Should not be able to start
            with self.assertRaises(RuntimeError):
                integration.start()
        finally:
            Path(config_path).unlink(missing_ok=True)
    
    def test_killswitch_check_called(self):
        """Test that killswitch is checked"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump({
                "enabled": True,
                "enforce_killswitch": True,
                "batch_interval": 1.0,
                "file_paths": {}
            }, f)
            config_path = f.name
        
        try:
            killswitch = Mock(return_value=False)
            
            integration = SystemLogIntegration(config_path, killswitch_check=killswitch)
            status = integration.get_status()
            
            # Killswitch should be checked
            killswitch.assert_called()
        finally:
            Path(config_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
