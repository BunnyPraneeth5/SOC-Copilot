"""Ingestion controller for starting/stopping real-time log ingestion"""

from typing import Optional, Callable, List
from pathlib import Path
from threading import Thread, Event
import time

from .buffer import MicroBatchBuffer
from .watcher import FileTailer, DirectoryWatcher


class IngestionController:
    """Controls real-time log ingestion with micro-batching and robust error handling"""
    
    def __init__(self, batch_interval: float = 5.0, 
                 killswitch_check: Optional[Callable[[], bool]] = None):
        self.batch_interval = batch_interval
        self.killswitch_check = killswitch_check
        self.buffer = MicroBatchBuffer(batch_interval=batch_interval)
        
        self._sources = []
        self._flush_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._shutdown_flag = False
        self._batch_callback: Optional[Callable[[List[dict]], None]] = None
        self._stats = {
            "lines_processed": 0,
            "batches_sent": 0,
            "errors": 0,
            "last_activity": None
        }
    
    def add_file_source(self, filepath: str) -> bool:
        """Add file to tail. Returns True if successful."""
        try:
            if not Path(filepath).exists():
                return False
            tailer = FileTailer(filepath, self._on_line)
            self._sources.append(tailer)
            return True
        except Exception:
            return False
    
    def add_directory_source(self, directory: str, pattern: str = "*.log") -> bool:
        """Add directory to watch. Returns True if successful."""
        try:
            if not Path(directory).exists():
                return False
            watcher = DirectoryWatcher(directory, self._on_line, pattern)
            self._sources.append(watcher)
            return True
        except Exception:
            return False
    
    def set_batch_callback(self, callback: Callable[[List[dict]], None]):
        """Set callback for processing batches"""
        self._batch_callback = callback
    
    def start(self) -> bool:
        """Start ingestion. Returns True if successful."""
        if self._flush_thread and self._flush_thread.is_alive():
            return True
        
        try:
            # Start all sources
            for source in self._sources:
                source.start()
            
            # Start flush thread
            self._stop_event.clear()
            self._flush_thread = Thread(target=self._flush_loop, daemon=True)
            self._flush_thread.start()
            return True
        except Exception:
            self._stats["errors"] += 1
            return False
    
    def stop(self):
        """Stop ingestion gracefully"""
        self._shutdown_flag = True
        self._stop_event.set()
        
        # Stop all sources
        for source in self._sources:
            try:
                source.stop()
            except Exception:
                pass
        
        # Stop flush thread
        if self._flush_thread:
            self._flush_thread.join(timeout=3.0)
        
        # Final flush
        try:
            self._flush_buffer()
        except Exception:
            pass
    
    def is_running(self) -> bool:
        """Check if ingestion is running"""
        return self._flush_thread is not None and self._flush_thread.is_alive()
    
    def _on_line(self, line: str):
        """Handle new log line with error tracking"""
        # Check shutdown flag first
        if self._shutdown_flag:
            return
        
        try:
            # Check kill switch
            if self.killswitch_check and self.killswitch_check():
                return
            
            # Add to buffer
            record = {"raw_line": line, "timestamp": time.time()}
            if self.buffer.add(record):
                self._stats["lines_processed"] += 1
                self._stats["last_activity"] = time.time()
        except Exception:
            self._stats["errors"] += 1
    
    def _flush_loop(self):
        """Periodic buffer flush loop with error handling"""
        while not self._stop_event.is_set() and not self._shutdown_flag:
            try:
                # Check kill switch
                if self.killswitch_check and self.killswitch_check():
                    time.sleep(0.5)
                    continue
                
                # Check if should flush
                if self.buffer.should_flush():
                    self._flush_buffer()
                
                time.sleep(0.5)
            except Exception:
                self._stats["errors"] += 1
                time.sleep(1.0)
    
    def _flush_buffer(self):
        """Flush buffer and process batch with error handling"""
        try:
            records = self.buffer.flush()
            if records and self._batch_callback:
                self._batch_callback(records)
                self._stats["batches_sent"] += 1
        except Exception:
            self._stats["errors"] += 1
    
    def get_stats(self) -> dict:
        """Get comprehensive ingestion statistics"""
        base_stats = {
            "running": self.is_running(),
            "shutdown_flag": self._shutdown_flag,
            "sources_count": len(self._sources),
            "batch_interval": self.batch_interval,
            **self._stats,
            **self.buffer.get_stats()
        }
        
        # Add source-specific stats
        for i, source in enumerate(self._sources):
            if hasattr(source, 'get_stats'):
                base_stats[f"source_{i}"] = source.get_stats()
        
        return base_stats
