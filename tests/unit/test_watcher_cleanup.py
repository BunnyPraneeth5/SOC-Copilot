"""Unit tests for watcher file handle cleanup"""

import pytest
import tempfile
import time
from pathlib import Path

from soc_copilot.phase4.ingestion.watcher import FileTailer, DirectoryWatcher


@pytest.fixture
def temp_log_file():
    """Create temporary log file"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        f.write("initial line\n")
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    try:
        Path(temp_path).unlink()
    except Exception:
        pass


def test_tailer_cleans_up_file_handle_on_stop(temp_log_file):
    """Tailer should clean up file handle on stop"""
    lines = []
    
    def callback(line):
        lines.append(line)
    
    tailer = FileTailer(temp_log_file, callback)
    tailer.start()
    
    # Wait for tailer to start
    time.sleep(0.5)
    
    # Stop tailer
    tailer.stop()
    
    # File handle should be None
    assert tailer._file_handle is None


def test_tailer_stops_cleanly_on_error():
    """Tailer should stop cleanly after max errors"""
    lines = []
    
    def callback(line):
        lines.append(line)
    
    # Use non-existent file
    tailer = FileTailer("/nonexistent/file.log", callback)
    tailer._max_errors = 3
    tailer.start()
    
    # Wait for errors to accumulate
    time.sleep(2.0)
    
    # Thread should have stopped
    assert not tailer._thread.is_alive()


def test_tailer_handles_file_deletion(temp_log_file):
    """Tailer should handle file deletion gracefully"""
    lines = []
    
    def callback(line):
        lines.append(line)
    
    tailer = FileTailer(temp_log_file, callback)
    tailer.start()
    
    time.sleep(0.5)
    
    # Delete file
    Path(temp_log_file).unlink()
    
    # Wait a bit
    time.sleep(1.0)
    
    # Stop should work cleanly
    tailer.stop()
    
    assert tailer._file_handle is None


def test_directory_watcher_stops_all_tailers():
    """Directory watcher should stop all tailers on stop"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test files
        log1 = Path(temp_dir) / "test1.log"
        log2 = Path(temp_dir) / "test2.log"
        log1.write_text("line 1\n")
        log2.write_text("line 2\n")
        
        lines = []
        
        def callback(line):
            lines.append(line)
        
        watcher = DirectoryWatcher(temp_dir, callback, "*.log")
        watcher.start()
        
        # Wait for watcher to find files
        time.sleep(2.0)
        
        # Should have created tailers
        assert len(watcher._tailers) > 0
        
        # Stop watcher
        watcher.stop()
        
        # All tailers should be stopped
        assert len(watcher._tailers) == 0


def test_directory_watcher_handles_missing_directory():
    """Directory watcher should handle missing directory"""
    lines = []
    
    def callback(line):
        lines.append(line)
    
    watcher = DirectoryWatcher("/nonexistent/directory", callback)
    watcher._max_errors = 3
    watcher.start()
    
    # Wait for errors
    time.sleep(2.0)
    
    # Stop should work cleanly
    watcher.stop()
    
    assert not watcher._thread.is_alive()


def test_tailer_stats_show_file_exists():
    """Tailer stats should show if file exists"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
        temp_path = f.name
    
    try:
        tailer = FileTailer(temp_path, lambda x: None)
        
        stats = tailer.get_stats()
        assert stats["file_exists"]
        
        # Delete file
        Path(temp_path).unlink()
        
        stats = tailer.get_stats()
        assert not stats["file_exists"]
    finally:
        try:
            Path(temp_path).unlink()
        except Exception:
            pass
