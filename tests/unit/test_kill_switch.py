"""Unit tests for kill switch"""

import pytest
from pathlib import Path
import tempfile
import shutil

from soc_copilot.phase4.kill_switch import KillSwitch


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    temp = Path(tempfile.mkdtemp())
    yield temp
    shutil.rmtree(temp)


def test_kill_switch_inactive_by_default(temp_dir):
    """Kill switch should be inactive by default"""
    ks = KillSwitch(temp_dir)
    assert not ks.is_active()


def test_kill_switch_activate(temp_dir):
    """Kill switch should activate"""
    ks = KillSwitch(temp_dir)
    ks.activate()
    assert ks.is_active()
    assert ks.kill_file.exists()


def test_kill_switch_deactivate(temp_dir):
    """Kill switch should deactivate"""
    ks = KillSwitch(temp_dir)
    ks.activate()
    ks.deactivate()
    assert not ks.is_active()
    assert not ks.kill_file.exists()


def test_kill_switch_deactivate_when_inactive(temp_dir):
    """Deactivating inactive kill switch should not error"""
    ks = KillSwitch(temp_dir)
    ks.deactivate()
    assert not ks.is_active()


def test_kill_switch_persistence(temp_dir):
    """Kill switch state should persist across instances"""
    ks1 = KillSwitch(temp_dir)
    ks1.activate()
    
    ks2 = KillSwitch(temp_dir)
    assert ks2.is_active()
    
    ks2.deactivate()
    
    ks3 = KillSwitch(temp_dir)
    assert not ks3.is_active()
