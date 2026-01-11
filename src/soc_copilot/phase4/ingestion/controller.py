"""Ingestion controller for starting/stopping real-time log ingestion"""

from typing import Optional, Callable, List
from pathlib import Path
from threading import Thread, Event
import time

from .buffer import MicroBatchBuffer
from .watcher import FileTailer, DirectoryWatcher


class IngestionController:
    """Controls real-time log ingestion with micro-batching"""
    
    def __init__(self, batch_interval: float = 5.0, 
                 killswitch_check: Optional[Callable[[], bool]] = None):
        self.batch_interval = batch_interval
        self.killswitch_check = killswitch_check
        self.buffer = MicroBatchBuffer(batch_interval=batch_interval)
        
        self._sources = []
        self._flush_thread: Optional[Thread] = None
        self._stop_event = Event()
        self._batch_callback: Optional[Callable[[List[dict]], None]] = None
    
    def add_file_source(self, filepath: str):
        """Add file to tail"""
        tailer = FileTailer(filepath, self._on_line)
        self._sources.append(tailer)
    
    def add_directory_source(self, directory: str, pattern: str = "*.log"):
        """Add directory to watch"""
        watcher = DirectoryWatcher(directory, self._on_line, pattern)
        self._sources.append(watcher)
    
    def set_batch_callback(self, callback: Callable[[List[dict]], None]):
        """Set callback for processing batches"""
        self._batch_callback = callback
    
    def start(self):
        """Start ingestion"""
        if self._flush_thread and self._flush_thread.is_alive():
            return
        
        # Start all sources
        for source in self._sources:
            source.start()
        
        # Start flush thread
        self._stop_event.clear()
        self._flush_thread = Thread(target=self._flush_loop, daemon=True)
        self._flush_thread.start()
    
    def stop(self):
        """Stop ingestion"""
        self._stop_event.set()
        
        # Stop all sources
        for source in self._sources:
            source.stop()
        
        # Stop flush thread
        if self._flush_thread:
            self._flush_thread.join(timeout=2.0)
        
        # Final flush
        self._flush_buffer()
    
    def is_running(self) -> bool:
        """Check if ingestion is running"""
        return self._flush_thread is not None and self._flush_thread.is_alive()
    
    def _on_line(self, line: str):
        """Handle new log line"""
        # Check kill switch
        if self.killswitch_check and self.killswitch_check():
            return
        
        # Add to buffer
        record = {"raw_line": line, "timestamp": time.time()}
        self.buffer.add(record)
    
    def _flush_loop(self):
        """Periodic buffer flush loop"""
        while not self._stop_event.is_set():
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
                time.sleep(0.5)
    
    def _flush_buffer(self):
        """Flush buffer and process batch"""
        records = self.buffer.flush()
        if records and self._batch_callback:
            try:
                self._batch_callback(records)
            except Exception:
                pass
    
    def get_stats(self) -> dict:
        """Get ingestion statistics"""
        return {
            "running": self.is_running(),
            "buffer_size": self.buffer.size(),
            "sources_count": len(self._sources),
            "batch_interval": self.batch_interval
        }
