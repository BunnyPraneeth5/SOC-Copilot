"""Integration tests for kill switch with controller"""

import pytest
from pathlib import Path
import tempfile
import shutil

from soc_copilot.phase4.kill_switch import KillSwitch
from soc_copilot.phase4.controller import AppController


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


@pytest.fixture
def models_dir(temp_dir):
    """Create models directory"""
    models = temp_dir / "models"
    models.mkdir()
    return str(models)


def test_controller_respects_kill_switch(temp_dir, models_dir):
    """Controller should respect kill switch"""
    ks = KillSwitch(temp_dir)
    controller = AppController(models_dir, killswitch_check=ks.is_active)
    
    # Activate kill switch
    ks.activate()
    
    # Process should return None when kill switch active
    result = controller.process_batch([{"raw_line": "test log"}])
    assert result is None


def test_controller_works_without_kill_switch(models_dir):
    """Controller should work without kill switch"""
    controller = AppController(models_dir, killswitch_check=None)
    
    # Should not error when no kill switch provided
    # (will fail for other reasons without models, but not kill switch)
    try:
        controller.process_batch([{"raw_line": "test log"}])
    except RuntimeError:
        pass  # Expected without initialized pipeline
