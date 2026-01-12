"""Integration tests for system log integration with permission checks"""

import pytest
from pathlib import Path
import tempfile
import shutil

from soc_copilot.phase4.ingestion.system_logs import SystemLogIntegration


@pytest.fixture
def temp_dir():
    """Create temporary directory"""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def config_file(temp_dir):
    """Create test config file"""
    config_dir = temp_dir / "config" / "ingestion"
    config_dir.mkdir(parents=True)
    
    config_path = config_dir / "system_logs.yaml"
    config_path.write_text("""
enabled: false
export_interval: 5
log_types: ["test"]
file_paths:
  test: "logs/test.log"
max_batch_size: 100
batch_interval: 5.0
enforce_killswitch: true
""")
    
    return str(config_path)


def test_system_log_integration_init(config_file):
    """System log integration should initialize"""
    integration = SystemLogIntegration(config_file)
    
    assert integration.config is not None
    assert integration._log_reader is not None
    assert integration._permission_check is None


def test_system_log_integration_status_includes_permissions(config_file):
    """Status should include permission check results after initialize"""
    integration = SystemLogIntegration(config_file)
    
    # Enable config for testing
    integration.config._config["enabled"] = True
    
    # Initialize (will check permissions)
    integration.initialize(lambda x: None)
    
    status = integration.get_status()
    
    assert "os_type" in status
    assert "permission_check" in status


def test_system_log_integration_disabled_by_default(config_file):
    """System log integration should be disabled by default"""
    integration = SystemLogIntegration(config_file)
    
    assert not integration.config.enabled
    
    # Initialize should do nothing when disabled
    integration.initialize(lambda x: None)
    
    assert integration._controller is None


def test_system_log_integration_respects_killswitch(config_file):
    """System log integration should respect killswitch"""
    kill_active = False
    
    def killswitch_check():
        return kill_active
    
    integration = SystemLogIntegration(config_file, killswitch_check=killswitch_check)
    
    status = integration.get_status()
    assert not status["killswitch_active"]
    
    kill_active = True
    status = integration.get_status()
    assert status["killswitch_active"]
