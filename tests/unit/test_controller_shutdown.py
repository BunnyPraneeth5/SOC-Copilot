"""Unit tests for controller graceful shutdown"""

import pytest
import time
from threading import Event

from soc_copilot.phase4.ingestion.controller import IngestionController


def test_controller_shutdown_flag_set_on_stop():
    """Controller should set shutdown flag on stop"""
    controller = IngestionController(batch_interval=5.0)
    
    assert not controller._shutdown_flag
    
    controller.stop()
    
    assert controller._shutdown_flag


def test_controller_rejects_lines_after_shutdown():
    """Controller should reject lines after shutdown"""
    controller = IngestionController(batch_interval=5.0)
    
    # Add line before shutdown
    controller._on_line("test line 1")
    assert controller._stats["lines_processed"] == 1
    
    # Stop controller
    controller.stop()
    
    # Try to add line after shutdown
    controller._on_line("test line 2")
    
    # Should still be 1
    assert controller._stats["lines_processed"] == 1


def test_controller_flush_loop_respects_shutdown():
    """Flush loop should exit when shutdown flag set"""
    controller = IngestionController(batch_interval=5.0)
    
    # Start controller
    controller.start()
    assert controller.is_running()
    
    # Stop controller
    controller.stop()
    
    # Wait for thread to terminate
    time.sleep(1.0)
    
    assert not controller.is_running()
    assert controller._shutdown_flag


def test_controller_stats_include_shutdown_flag():
    """Stats should include shutdown flag"""
    controller = IngestionController(batch_interval=5.0)
    
    stats = controller.get_stats()
    assert "shutdown_flag" in stats
    assert not stats["shutdown_flag"]
    
    controller.stop()
    
    stats = controller.get_stats()
    assert stats["shutdown_flag"]


def test_controller_stats_include_buffer_stats():
    """Stats should include buffer statistics"""
    controller = IngestionController(batch_interval=5.0)
    
    controller._on_line("test line")
    
    stats = controller.get_stats()
    assert "size" in stats
    assert "max_size" in stats
    assert "dropped_count" in stats
    assert "overflow_warnings" in stats


def test_controller_respects_killswitch_in_on_line():
    """Controller should respect killswitch in _on_line"""
    kill_active = False
    
    def killswitch_check():
        return kill_active
    
    controller = IngestionController(batch_interval=5.0, killswitch_check=killswitch_check)
    
    # Add line with killswitch inactive
    controller._on_line("test line 1")
    assert controller._stats["lines_processed"] == 1
    
    # Activate killswitch
    kill_active = True
    
    # Try to add line with killswitch active
    controller._on_line("test line 2")
    
    # Should still be 1
    assert controller._stats["lines_processed"] == 1


def test_controller_no_processing_after_stop():
    """Controller should not process after stop called"""
    controller = IngestionController(batch_interval=5.0)
    
    lines_received = []
    
    def callback(records):
        lines_received.extend(records)
    
    controller.set_batch_callback(callback)
    
    # Add lines
    controller._on_line("line 1")
    controller._on_line("line 2")
    
    # Stop immediately
    controller.stop()
    
    # Try to add more lines
    controller._on_line("line 3")
    controller._on_line("line 4")
    
    # Only first 2 should be processed
    assert controller._stats["lines_processed"] == 2
