"""File tailing and directory watching for real-time log ingestion"""

import os
import time
from pathlib import Path
from typing import Optional, Callable
from threading import Thread, Event


class FileTailer:
    """Tail a log file and emit new lines"""
    
    def __init__(self, filepath: str, callback: Callable[[str], None]):
        self.filepath = Path(filepath)
        self.callback = callback
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._position = 0
    
    def start(self):
        """Start tailing file"""
        if self._thread and self._thread.is_alive():
            return
        
        # Seek to end of file
        if self.filepath.exists():
            self._position = self.filepath.stat().st_size
        
        self._stop_event.clear()
        self._thread = Thread(target=self._tail_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop tailing file"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _tail_loop(self):
        """Main tailing loop"""
        while not self._stop_event.is_set():
            try:
                if not self.filepath.exists():
                    time.sleep(0.5)
                    continue
                
                current_size = self.filepath.stat().st_size
                
                # File was truncated
                if current_size < self._position:
                    self._position = 0
                
                # Read new content
                if current_size > self._position:
                    with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(self._position)
                        for line in f:
                            if self._stop_event.is_set():
                                break
                            line = line.rstrip('\n\r')
                            if line:
                                self.callback(line)
                        self._position = f.tell()
                
                time.sleep(0.1)
            except Exception:
                time.sleep(0.5)


class DirectoryWatcher:
    """Watch directory for new log files"""
    
    def __init__(self, directory: str, callback: Callable[[str], None], 
                 pattern: str = "*.log"):
        self.directory = Path(directory)
        self.callback = callback
        self.pattern = pattern
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._known_files = set()
        self._tailers = {}
    
    def start(self):
        """Start watching directory"""
        if self._thread and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching directory"""
        self._stop_event.set()
        
        # Stop all tailers
        for tailer in self._tailers.values():
            tailer.stop()
        self._tailers.clear()
        
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _watch_loop(self):
        """Main watching loop"""
        while not self._stop_event.is_set():
            try:
                if not self.directory.exists():
                    time.sleep(1.0)
                    continue
                
                # Find matching files
                current_files = set(self.directory.glob(self.pattern))
                
                # Start tailers for new files
                new_files = current_files - self._known_files
                for filepath in new_files:
                    if str(filepath) not in self._tailers:
                        tailer = FileTailer(str(filepath), self.callback)
                        tailer.start()
                        self._tailers[str(filepath)] = tailer
                
                self._known_files = current_files
                time.sleep(1.0)
            except Exception:
                time.sleep(1.0)
