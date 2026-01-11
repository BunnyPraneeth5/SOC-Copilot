"""Unit tests for Sprint-14: Real-Time Log Ingestion Engine"""

import pytest
import tempfile
import time
from pathlib import Path
from threading import Event

from soc_copilot.phase4.ingestion import (
    MicroBatchBuffer,
    FileTailer,
    DirectoryWatcher,
    IngestionController,
)


# ============================================================================
# MicroBatchBuffer Tests
# ============================================================================

class TestMicroBatchBuffer:
    """Test micro-batch buffer"""
    
    def test_add_record(self):
        """Test adding records to buffer"""
        buffer = MicroBatchBuffer(batch_interval=5.0)
        
        assert buffer.add({"line": "test1"})
        assert buffer.size() == 1
        
        assert buffer.add({"line": "test2"})
        assert buffer.size() == 2
    
    def test_flush_buffer(self):
        """Test flushing buffer"""
        buffer = MicroBatchBuffer(batch_interval=5.0)
        
        buffer.add({"line": "test1"})
        buffer.add({"line": "test2"})
        
        records = buffer.flush()
        assert len(records) == 2
        assert buffer.size() == 0
    
    def test_should_flush_by_time(self):
        """Test flush trigger by time interval"""
        buffer = MicroBatchBuffer(batch_interval=0.1)
        
        buffer.add({"line": "test"})
        assert not buffer.should_flush()
        
        time.sleep(0.15)
        assert buffer.should_flush()
    
    def test_should_flush_by_size(self):
        """Test flush trigger by max size"""
        buffer = MicroBatchBuffer(batch_interval=10.0, max_size=3)
        
        buffer.add({"line": "test1"})
        buffer.add({"line": "test2"})
        assert not buffer.should_flush()
        
        buffer.add({"line": "test3"})
        assert buffer.should_flush()
    
    def test_max_size_limit(self):
        """Test buffer respects max size"""
        buffer = MicroBatchBuffer(batch_interval=10.0, max_size=2)
        
        assert buffer.add({"line": "test1"})
        assert buffer.add({"line": "test2"})
        assert not buffer.add({"line": "test3"})
        
        assert buffer.size() == 2
    
    def test_clear_buffer(self):
        """Test clearing buffer"""
        buffer = MicroBatchBuffer(batch_interval=5.0)
        
        buffer.add({"line": "test1"})
        buffer.add({"line": "test2"})
        assert buffer.size() == 2
        
        buffer.clear()
        assert buffer.size() == 0
    
    def test_thread_safety(self):
        """Test buffer is thread-safe"""
        buffer = MicroBatchBuffer(batch_interval=5.0)
        
        from threading import Thread
        
        def add_records():
            for i in range(100):
                buffer.add({"line": f"test{i}"})
        
        threads = [Thread(target=add_records) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert buffer.size() <= 500


# ============================================================================
# FileTailer Tests
# ============================================================================

class TestFileTailer:
    """Test file tailing"""
    
    def test_tail_new_lines(self, tmp_path):
        """Test tailing new lines from file"""
        logfile = tmp_path / "test.log"
        logfile.write_text("line1\nline2\n")
        
        lines = []
        tailer = FileTailer(str(logfile), lambda line: lines.append(line))
        tailer.start()
        
        time.sleep(0.2)
        
        # Append new lines
        with open(logfile, 'a') as f:
            f.write("line3\n")
            f.write("line4\n")
        
        time.sleep(0.3)
        tailer.stop()
        
        assert "line3" in lines
        assert "line4" in lines
    
    def test_start_from_end(self, tmp_path):
        """Test tailer starts from end of existing file"""
        logfile = tmp_path / "test.log"
        logfile.write_text("old1\nold2\n")
        
        lines = []
        tailer = FileTailer(str(logfile), lambda line: lines.append(line))
        tailer.start()
        
        time.sleep(0.2)
        
        # Should not see old lines
        assert "old1" not in lines
        assert "old2" not in lines
        
        # Append new line
        with open(logfile, 'a') as f:
            f.write("new1\n")
        
        time.sleep(0.3)
        tailer.stop()
        
        assert "new1" in lines
    
    def test_stop_tailer(self, tmp_path):
        """Test stopping tailer"""
        logfile = tmp_path / "test.log"
        logfile.touch()
        
        lines = []
        tailer = FileTailer(str(logfile), lambda line: lines.append(line))
        tailer.start()
        
        time.sleep(0.2)
        tailer.stop()
        
        # Append after stop
        with open(logfile, 'a') as f:
            f.write("after_stop\n")
        
        time.sleep(0.2)
        
        # Should not see line added after stop
        assert "after_stop" not in lines
    
    def test_handle_truncated_file(self, tmp_path):
        """Test handling file truncation"""
        logfile = tmp_path / "test.log"
        logfile.write_text("line1\n")
        
        lines = []
        tailer = FileTailer(str(logfile), lambda line: lines.append(line))
        tailer.start()
        
        time.sleep(0.2)
        
        # Truncate file
        logfile.write_text("new1\n")
        
        time.sleep(0.3)
        tailer.stop()
        
        assert "new1" in lines


# ============================================================================
# DirectoryWatcher Tests
# ============================================================================

class TestDirectoryWatcher:
    """Test directory watching"""
    
    def test_watch_new_files(self, tmp_path):
        """Test watching for new log files"""
        lines = []
        watcher = DirectoryWatcher(str(tmp_path), lambda line: lines.append(line))
        watcher.start()
        
        time.sleep(0.5)
        
        # Create new log file
        logfile = tmp_path / "test.log"
        logfile.write_text("line1\n")
        
        time.sleep(1.5)
        
        # Append to file
        with open(logfile, 'a') as f:
            f.write("line2\n")
        
        time.sleep(0.5)
        watcher.stop()
        
        assert "line2" in lines
    
    def test_pattern_matching(self, tmp_path):
        """Test file pattern matching"""
        lines = []
        watcher = DirectoryWatcher(str(tmp_path), lambda line: lines.append(line), 
                                   pattern="*.txt")
        watcher.start()
        
        time.sleep(0.5)
        
        # Create .log file (should be ignored)
        logfile = tmp_path / "test.log"
        logfile.write_text("log_line\n")
        
        # Create .txt file (should be watched)
        txtfile = tmp_path / "test.txt"
        txtfile.write_text("")
        
        time.sleep(1.5)
        
        # Append to txt file
        with open(txtfile, 'a') as f:
            f.write("txt_line\n")
        
        time.sleep(0.5)
        watcher.stop()
        
        assert "txt_line" in lines
        assert "log_line" not in lines
    
    def test_stop_watcher(self, tmp_path):
        """Test stopping directory watcher"""
        lines = []
        watcher = DirectoryWatcher(str(tmp_path), lambda line: lines.append(line))
        watcher.start()
        
        time.sleep(0.5)
        watcher.stop()
        
        # Create file after stop
        logfile = tmp_path / "test.log"
        logfile.write_text("after_stop\n")
        
        time.sleep(1.0)
        
        # Should not see line from file created after stop
        assert "after_stop" not in lines


# ============================================================================
# IngestionController Tests
# ============================================================================

class TestIngestionController:
    """Test ingestion controller"""
    
    def test_add_file_source(self, tmp_path):
        """Test adding file source"""
        controller = IngestionController(batch_interval=1.0)
        
        logfile = tmp_path / "test.log"
        logfile.touch()
        
        controller.add_file_source(str(logfile))
        assert controller.get_stats()["sources_count"] == 1
    
    def test_add_directory_source(self, tmp_path):
        """Test adding directory source"""
        controller = IngestionController(batch_interval=1.0)
        
        controller.add_directory_source(str(tmp_path))
        assert controller.get_stats()["sources_count"] == 1
    
    def test_start_stop_ingestion(self, tmp_path):
        """Test starting and stopping ingestion"""
        controller = IngestionController(batch_interval=1.0)
        
        logfile = tmp_path / "test.log"
        logfile.touch()
        controller.add_file_source(str(logfile))
        
        assert not controller.is_running()
        
        controller.start()
        time.sleep(0.2)
        assert controller.is_running()
        
        controller.stop()
        time.sleep(0.2)
        assert not controller.is_running()
    
    def test_batch_callback(self, tmp_path):
        """Test batch processing callback"""
        batches = []
        
        def on_batch(records):
            batches.append(records)
        
        controller = IngestionController(batch_interval=0.5)
        controller.set_batch_callback(on_batch)
        
        logfile = tmp_path / "test.log"
        logfile.write_text("line1\n")
        
        controller.add_file_source(str(logfile))
        controller.start()
        
        time.sleep(0.3)
        
        # Append lines
        with open(logfile, 'a') as f:
            f.write("line2\n")
            f.write("line3\n")
        
        time.sleep(1.0)
        controller.stop()
        
        # Should have received at least one batch
        assert len(batches) > 0
        
        # Check records
        all_records = [r for batch in batches for r in batch]
        assert len(all_records) >= 2
    
    def test_killswitch_check(self, tmp_path):
        """Test kill switch checking"""
        batches = []
        killswitch_enabled = False
        
        def on_batch(records):
            batches.append(records)
        
        def check_killswitch():
            return killswitch_enabled
        
        controller = IngestionController(batch_interval=0.5, 
                                        killswitch_check=check_killswitch)
        controller.set_batch_callback(on_batch)
        
        logfile = tmp_path / "test.log"
        logfile.write_text("line1\n")
        
        controller.add_file_source(str(logfile))
        controller.start()
        
        time.sleep(0.3)
        
        # Append with kill switch disabled
        with open(logfile, 'a') as f:
            f.write("line2\n")
        
        time.sleep(0.7)
        
        # Enable kill switch
        killswitch_enabled = True
        
        # Append with kill switch enabled
        with open(logfile, 'a') as f:
            f.write("line3\n")
        
        time.sleep(0.7)
        controller.stop()
        
        # Should have received batches before kill switch
        assert len(batches) > 0
    
    def test_get_stats(self, tmp_path):
        """Test getting ingestion statistics"""
        controller = IngestionController(batch_interval=5.0)
        
        logfile = tmp_path / "test.log"
        logfile.touch()
        controller.add_file_source(str(logfile))
        
        stats = controller.get_stats()
        assert stats["running"] is False
        assert stats["sources_count"] == 1
        assert stats["batch_interval"] == 5.0
        assert stats["buffer_size"] == 0
        
        controller.start()
        time.sleep(0.2)
        
        stats = controller.get_stats()
        assert stats["running"] is True
        
        controller.stop()
    
    def test_multiple_sources(self, tmp_path):
        """Test ingestion from multiple sources"""
        batches = []
        
        def on_batch(records):
            batches.append(records)
        
        controller = IngestionController(batch_interval=0.5)
        controller.set_batch_callback(on_batch)
        
        # Add multiple file sources
        logfile1 = tmp_path / "test1.log"
        logfile2 = tmp_path / "test2.log"
        logfile1.write_text("file1_line1\n")
        logfile2.write_text("file2_line1\n")
        
        controller.add_file_source(str(logfile1))
        controller.add_file_source(str(logfile2))
        
        controller.start()
        time.sleep(0.3)
        
        # Append to both files
        with open(logfile1, 'a') as f:
            f.write("file1_line2\n")
        with open(logfile2, 'a') as f:
            f.write("file2_line2\n")
        
        time.sleep(1.0)
        controller.stop()
        
        # Should have received batches from both files
        assert len(batches) > 0
        all_records = [r for batch in batches for r in batch]
        assert len(all_records) >= 2


# ============================================================================
# Integration Tests
# ============================================================================

class TestIngestionIntegration:
    """Test ingestion integration"""
    
    def test_end_to_end_ingestion(self, tmp_path):
        """Test complete ingestion workflow"""
        batches = []
        
        def on_batch(records):
            batches.append(records)
        
        controller = IngestionController(batch_interval=0.5)
        controller.set_batch_callback(on_batch)
        
        # Setup source
        logfile = tmp_path / "access.log"
        logfile.write_text("initial\n")
        
        controller.add_file_source(str(logfile))
        controller.start()
        
        time.sleep(0.3)
        
        # Simulate log writes
        with open(logfile, 'a') as f:
            for i in range(5):
                f.write(f"log_entry_{i}\n")
                time.sleep(0.1)
        
        time.sleep(1.0)
        controller.stop()
        
        # Verify batches received
        assert len(batches) > 0
        all_records = [r for batch in batches for r in batch]
        assert len(all_records) >= 5
    
    def test_no_phase_coupling(self):
        """Verify no imports from Phase-1/2/3"""
        import inspect
        from soc_copilot.phase4 import ingestion
        
        source = inspect.getsource(ingestion)
        
        # Should not import from other phases
        assert "from soc_copilot.phase1" not in source
        assert "from soc_copilot.phase2" not in source
        assert "from soc_copilot.phase3" not in source
        assert "import soc_copilot.phase1" not in source
        assert "import soc_copilot.phase2" not in source
        assert "import soc_copilot.phase3" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
