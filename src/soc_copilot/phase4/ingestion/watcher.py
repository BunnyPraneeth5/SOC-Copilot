"""File tailing and directory watching for real-time log ingestion"""

import os
import time
from pathlib import Path
from typing import Optional, Callable
from threading import Thread, Event


class FileTailer:
    """Tail a log file and emit new lines with robust error handling"""
    
    def __init__(self, filepath: str, callback: Callable[[str], None]):
        self.filepath = Path(filepath)
        self.callback = callback
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._position = 0
        self._error_count = 0
        self._max_errors = 10
    
    def start(self):
        """Start tailing file"""
        if self._thread and self._thread.is_alive():
            return
        
        # Seek to end of file if it exists
        try:
            if self.filepath.exists():
                self._position = self.filepath.stat().st_size
        except (OSError, PermissionError):
            self._position = 0
        
        self._stop_event.clear()
        self._error_count = 0
        self._thread = Thread(target=self._tail_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop tailing file"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _tail_loop(self):
        """Main tailing loop with robust error handling"""
        while not self._stop_event.is_set():
            try:
                # Check if file exists
                if not self.filepath.exists():
                    time.sleep(1.0)  # Wait longer for missing files
                    continue
                
                # Get current file size
                try:
                    current_size = self.filepath.stat().st_size
                except (OSError, PermissionError):
                    time.sleep(1.0)
                    continue
                
                # Handle file truncation or rotation
                if current_size < self._position:
                    self._position = 0
                
                # Read new content
                if current_size > self._position:
                    try:
                        with open(self.filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            f.seek(self._position)
                            for line in f:
                                if self._stop_event.is_set():
                                    break
                                line = line.rstrip('\n\r')
                                if line.strip():  # Skip empty lines
                                    try:
                                        self.callback(line)
                                    except Exception:
                                        pass  # Don't let callback errors stop tailing
                            self._position = f.tell()
                        
                        # Reset error count on successful read
                        self._error_count = 0
                        
                    except (OSError, PermissionError, UnicodeDecodeError):
                        self._error_count += 1
                        if self._error_count >= self._max_errors:
                            break  # Stop after too many errors
                        time.sleep(2.0)  # Wait longer after errors
                        continue
                
                time.sleep(0.1)
                
            except Exception:
                self._error_count += 1
                if self._error_count >= self._max_errors:
                    break
                time.sleep(1.0)


class DirectoryWatcher:
    """Watch directory for new log files with robust error handling"""
    
    def __init__(self, directory: str, callback: Callable[[str], None], 
                 pattern: str = "*.log"):
        self.directory = Path(directory)
        self.callback = callback
        self.pattern = pattern
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._known_files = set()
        self._tailers = {}
        self._error_count = 0
        self._max_errors = 5
    
    def start(self):
        """Start watching directory"""
        if self._thread and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._error_count = 0
        self._thread = Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop watching directory"""
        self._stop_event.set()
        
        # Stop all tailers gracefully
        for tailer in list(self._tailers.values()):
            try:
                tailer.stop()
            except Exception:
                pass
        self._tailers.clear()
        
        if self._thread:
            self._thread.join(timeout=3.0)
    
    def _watch_loop(self):
        """Main watching loop with robust error handling"""
        while not self._stop_event.is_set():
            try:
                # Check if directory exists
                if not self.directory.exists():
                    time.sleep(2.0)  # Wait longer for missing directories
                    continue
                
                # Find matching files
                try:
                    current_files = set(self.directory.glob(self.pattern))
                except (OSError, PermissionError):
                    self._error_count += 1
                    if self._error_count >= self._max_errors:
                        break
                    time.sleep(5.0)
                    continue
                
                # Start tailers for new files
                new_files = current_files - self._known_files
                for filepath in new_files:
                    filepath_str = str(filepath)
                    if filepath_str not in self._tailers:
                        try:
                            tailer = FileTailer(filepath_str, self.callback)
                            tailer.start()
                            self._tailers[filepath_str] = tailer
                        except Exception:
                            pass  # Skip files that can't be tailed
                
                # Remove tailers for deleted files
                deleted_files = self._known_files - current_files
                for filepath in deleted_files:
                    filepath_str = str(filepath)
                    if filepath_str in self._tailers:
                        try:
                            self._tailers[filepath_str].stop()
                            del self._tailers[filepath_str]
                        except Exception:
                            pass
                
                self._known_files = current_files
                self._error_count = 0  # Reset on successful iteration
                time.sleep(2.0)  # Check less frequently
                
            except Exception:
                self._error_count += 1
                if self._error_count >= self._max_errors:
                    break
                time.sleep(5.0)
    
    def get_stats(self) -> dict:
        """Get watcher statistics"""
        return {
            "directory": str(self.directory),
            "pattern": self.pattern,
            "known_files": len(self._known_files),
            "active_tailers": len(self._tailers),
            "error_count": self._error_count,
            "running": self._thread is not None and self._thread.is_alive()
        }