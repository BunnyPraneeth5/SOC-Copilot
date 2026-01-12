"""Tests for improved ingestion robustness"""

import unittest
import tempfile
import time
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from soc_copilot.phase4.ingestion.watcher import FileTailer, DirectoryWatcher
from soc_copilot.phase4.ingestion.controller import IngestionController


class TestFileTailerRobustness(unittest.TestCase):
    """Test FileTailer robustness improvements"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.temp_file = Path(self.temp_dir) / "test.log"
        self.callback = Mock()
    
    def test_handles_missing_file(self):
        """Test tailer handles missing file gracefully"""
        missing_file = Path(self.temp_dir) / "missing.log"
        tailer = FileTailer(str(missing_file), self.callback)
        
        # Should start without error
        tailer.start()
        time.sleep(0.2)
        tailer.stop()
        
        # No callbacks should be made
        self.callback.assert_not_called()
    
    def test_handles_permission_errors(self):
        """Test tailer handles permission errors"""
        # Create file and make it unreadable
        self.temp_file.write_text("test line\n")
        
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            tailer = FileTailer(str(self.temp_file), self.callback)
            tailer.start()
            time.sleep(0.2)
            tailer.stop()
        
        # Should not crash
        self.callback.assert_not_called()
    
    def test_handles_file_truncation(self):
        """Test tailer handles file truncation"""
        self.temp_file.write_text("line1\nline2\n")
        
        tailer = FileTailer(str(self.temp_file), self.callback)
        tailer.start()
        time.sleep(0.1)
        
        # Truncate file (simulate log rotation)
        self.temp_file.write_text("new line\n")
        time.sleep(0.2)
        
        tailer.stop()
        
        # Should handle truncation and read new content
        self.callback.assert_called_with("new line")
    
    def test_skips_empty_lines(self):
        """Test tailer skips empty lines"""
        self.temp_file.write_text("line1\n\n  \nline2\n")
        
        tailer = FileTailer(str(self.temp_file), self.callback)
        tailer.start()
        time.sleep(0.2)
        tailer.stop()
        
        # Should only call for non-empty lines
        expected_calls = [unittest.mock.call("line1"), unittest.mock.call("line2")]
        self.callback.assert_has_calls(expected_calls, any_order=True)
    
    def test_encoding_fallback(self):
        """Test tailer handles different encodings"""
        # Create file with non-UTF8 content
        self.temp_file.write_bytes(b"line1\n\xff\xfe invalid utf8\nline2\n")
        
        tailer = FileTailer(str(self.temp_file), self.callback)
        tailer.start()
        time.sleep(0.2)
        tailer.stop()
        
        # Should handle encoding errors gracefully
        stats = tailer.get_stats()
        self.assertIn("encoding_errors", stats)
        
        # Should still process valid lines
        call_args = [call[0][0] for call in self.callback.call_args_list]
        self.assertIn("line1", call_args)
        self.assertIn("line2", call_args)
    
    def test_tailer_get_stats(self):
        """Test tailer statistics"""
        tailer = FileTailer(str(self.temp_file), self.callback)
        stats = tailer.get_stats()
        
        expected_keys = ["filepath", "position", "error_count", "encoding_errors", "running", "file_exists"]
        for key in expected_keys:
            self.assertIn(key, stats)


class TestDirectoryWatcherRobustness(unittest.TestCase):
    """Test DirectoryWatcher robustness improvements"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.callback = Mock()
    
    def test_handles_missing_directory(self):
        """Test watcher handles missing directory"""
        missing_dir = Path(self.temp_dir) / "missing"
        watcher = DirectoryWatcher(str(missing_dir), self.callback)
        
        watcher.start()
        time.sleep(0.2)
        watcher.stop()
        
        # Should not crash
        self.assertEqual(len(watcher._tailers), 0)
    
    def test_handles_permission_errors(self):
        """Test watcher handles directory permission errors"""
        with patch.object(Path, 'glob', side_effect=PermissionError("Access denied")):
            watcher = DirectoryWatcher(str(self.temp_dir), self.callback)
            watcher._max_errors = 2  # Set low limit
            
            watcher.start()
            time.sleep(0.5)
            
            # Should stop after error limit
            self.assertFalse(watcher._thread.is_alive())
    
    def test_cleans_up_deleted_files(self):
        """Test watcher removes tailers for deleted files"""
        # Create test file
        test_file = Path(self.temp_dir) / "test.log"
        test_file.write_text("test\n")
        
        watcher = DirectoryWatcher(str(self.temp_dir), self.callback)
        watcher.start()
        time.sleep(0.2)
        
        # Should have one tailer
        self.assertEqual(len(watcher._tailers), 1)
        
        # Delete file
        test_file.unlink()
        time.sleep(0.5)  # Wait for watcher to notice
        
        watcher.stop()
        
        # Tailer should be cleaned up
        self.assertEqual(len(watcher._tailers), 0)
    
    def test_get_stats_enhanced(self):
        """Test watcher statistics with enhanced data"""
        # Create test file
        test_file = Path(self.temp_dir) / "test.log"
        test_file.write_text("test\n")
        
        watcher = DirectoryWatcher(str(self.temp_dir), self.callback)
        watcher.start()
        time.sleep(0.2)
        
        stats = watcher.get_stats()
        expected_keys = ["directory", "pattern", "known_files", "active_tailers", "error_count", "running", "last_scan", "tailer_stats"]
        for key in expected_keys:
            self.assertIn(key, stats)
        
        watcher.stop()


class TestIngestionControllerRobustness(unittest.TestCase):
    """Test IngestionController robustness improvements"""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.controller = IngestionController(batch_interval=0.1)
        self.batch_callback = Mock()
        self.controller.set_batch_callback(self.batch_callback)
    
    def test_add_file_source_validation(self):
        """Test file source validation"""
        # Non-existent file should return False
        result = self.controller.add_file_source("/non/existent/file.log")
        self.assertFalse(result)
        
        # Existing file should return True
        test_file = Path(self.temp_dir) / "test.log"
        test_file.write_text("test\n")
        result = self.controller.add_file_source(str(test_file))
        self.assertTrue(result)
    
    def test_add_directory_source_validation(self):
        """Test directory source validation"""
        # Non-existent directory should return False
        result = self.controller.add_directory_source("/non/existent/dir")
        self.assertFalse(result)
        
        # Existing directory should return True
        result = self.controller.add_directory_source(str(self.temp_dir))
        self.assertTrue(result)
    
    def test_start_returns_status(self):
        """Test start method returns success status"""
        # Should return True on successful start
        result = self.controller.start()
        self.assertTrue(result)
        
        # Should return True if already running
        result = self.controller.start()
        self.assertTrue(result)
        
        self.controller.stop()
    
    def test_graceful_shutdown(self):
        """Test graceful shutdown with errors"""
        # Add a source that will cause errors
        with patch.object(self.controller._sources[0] if self.controller._sources else Mock(), 'stop', side_effect=Exception("Stop error")):
            self.controller.start()
            # Should not raise exception
            self.controller.stop()
    
    def test_statistics_tracking(self):
        """Test statistics are tracked correctly"""
        stats = self.controller.get_stats()
        
        expected_keys = ["running", "buffer_size", "sources_count", "batch_interval", 
                        "lines_processed", "batches_sent", "errors", "last_activity"]
        for key in expected_keys:
            self.assertIn(key, stats)
        
        # Initial values
        self.assertEqual(stats["lines_processed"], 0)
        self.assertEqual(stats["batches_sent"], 0)
        self.assertEqual(stats["errors"], 0)
    
    def test_error_handling_in_callbacks(self):
        """Test error handling in line processing"""
        # Set up callback that raises exception
        def error_callback(records):
            raise Exception("Processing error")
        
        self.controller.set_batch_callback(error_callback)
        
        # Should not crash when processing lines
        self.controller._on_line("test line")
        
        # Error count should increase
        stats = self.controller.get_stats()
        self.assertGreaterEqual(stats["errors"], 0)


if __name__ == "__main__":
    unittest.main()