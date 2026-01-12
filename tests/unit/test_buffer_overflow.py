"""Unit tests for buffer overflow tracking"""

import pytest
import time
from datetime import datetime

from soc_copilot.phase4.ingestion.buffer import MicroBatchBuffer


def test_buffer_tracks_dropped_records():
    """Buffer should track dropped records when full"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=3)
    
    # Add records up to max
    assert buffer.add({"line": "1"})
    assert buffer.add({"line": "2"})
    assert buffer.add({"line": "3"})
    
    # Next add should fail and increment dropped count
    assert not buffer.add({"line": "4"})
    
    stats = buffer.get_stats()
    assert stats["dropped_count"] == 1
    assert stats["overflow_warnings"] == 1


def test_buffer_tracks_multiple_overflows():
    """Buffer should track multiple overflow events"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=2)
    
    buffer.add({"line": "1"})
    buffer.add({"line": "2"})
    
    # Multiple overflow attempts
    assert not buffer.add({"line": "3"})
    assert not buffer.add({"line": "4"})
    assert not buffer.add({"line": "5"})
    
    stats = buffer.get_stats()
    assert stats["dropped_count"] == 3
    assert stats["overflow_warnings"] == 3


def test_buffer_stats_include_size():
    """Buffer stats should include current size"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=10)
    
    buffer.add({"line": "1"})
    buffer.add({"line": "2"})
    
    stats = buffer.get_stats()
    assert stats["size"] == 2
    assert stats["max_size"] == 10


def test_buffer_stats_after_flush():
    """Buffer stats should reset size after flush"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=10)
    
    buffer.add({"line": "1"})
    buffer.add({"line": "2"})
    
    records = buffer.flush()
    assert len(records) == 2
    
    stats = buffer.get_stats()
    assert stats["size"] == 0
    assert stats["dropped_count"] == 0


def test_buffer_dropped_count_persists_after_flush():
    """Dropped count should persist after flush"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=2)
    
    buffer.add({"line": "1"})
    buffer.add({"line": "2"})
    assert not buffer.add({"line": "3"})
    
    buffer.flush()
    
    stats = buffer.get_stats()
    assert stats["size"] == 0
    assert stats["dropped_count"] == 1


def test_buffer_clear_resets_counters():
    """Clear should reset buffer but not counters"""
    buffer = MicroBatchBuffer(batch_interval=5.0, max_size=2)
    
    buffer.add({"line": "1"})
    buffer.add({"line": "2"})
    assert not buffer.add({"line": "3"})
    
    buffer.clear()
    
    stats = buffer.get_stats()
    assert stats["size"] == 0
    # Counters persist
    assert stats["dropped_count"] == 1
