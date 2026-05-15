"""Read-only bridge between UI and AppController"""

from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import threading
from ..controller import AppController, AnalysisResult
from soc_copilot.security.input_validator import validate_log_file


class ControllerBridge:
    """Adapter for UI to access AppController with file upload support and status reporting"""
    
    def __init__(self, controller: AppController):
        self._controller = controller
        self._permission_status = None
        self._sources_added = 0
        self._process_lock = threading.Lock()  # Serialize pipeline access
        self._check_permissions()
    
    def _check_permissions(self):
        """Check system permissions on init"""
        import ctypes
        import sys
        
        self._permission_status = {
            "has_permission": False,
            "elevation_required": True,
            "reason": "Administrator rights required",
            "checked_at": datetime.now().isoformat()
        }
        
        # Check if running as admin on Windows
        if sys.platform == 'win32':
            try:
                self._permission_status["has_permission"] = ctypes.windll.shell32.IsUserAnAdmin()
                if self._permission_status["has_permission"]:
                    self._permission_status["reason"] = "Full access"
                    self._permission_status["elevation_required"] = False
            except Exception:
                pass
    
    def get_latest_alerts(self, limit: int = 50) -> List[AnalysisResult]:
        """Get latest analysis results (read-only)"""
        return self._controller.get_results(limit=limit)
    
    def get_alert_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get specific result by ID (read-only)"""
        return self._controller.get_result_by_id(batch_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive controller statistics (read-only)"""
        base_stats = self._controller.get_stats()
        
        # Enhance with additional status info
        enhanced_stats = {
            **base_stats,
            "permission_check": self._permission_status,
            "shutdown_flag": base_stats.get("shutdown_flag", False),
        }
        
        # Check kill switch if available
        killswitch_check = getattr(self._controller, "__dict__", {}).get("killswitch_check")
        if callable(killswitch_check):
            try:
                enhanced_stats["shutdown_flag"] = bool(killswitch_check())
            except Exception:
                pass
        
        return enhanced_stats
    
    def get_kill_switch_status(self) -> Dict[str, Any]:
        """Get kill switch state (read-only)"""
        is_active = False
        reason = "Normal operation"
        
        killswitch_check = getattr(self._controller, "__dict__", {}).get("killswitch_check")
        if callable(killswitch_check):
            try:
                is_active = bool(killswitch_check())
                if is_active:
                    reason = "Kill switch engaged - processing halted"
            except Exception as e:
                reason = f"Check failed: {str(e)}"
        
        return {
            "active": is_active,
            "reason": reason,
            "checked_at": datetime.now().isoformat()
        }
    
    def get_permission_status(self) -> Dict[str, Any]:
        """Get permission check results (read-only)"""
        return self._permission_status
    
    def get_total_alert_count(self) -> int:
        """Get total stored alert count"""
        return self._controller.result_store.count()
    
    def add_file_source(self, filepath: str) -> bool:
        """Add a file for analysis. Process immediately (thread-safe)."""
        try:
            validation = validate_log_file(filepath, must_exist=True)
            if not validation.is_valid:
                return False
            path = validation.sanitized_path or Path(filepath)
            
            # Read and parse file content
            records = self._parse_file(path)
            if records:
                with self._process_lock:
                    self._controller.process_batch(records)
                    self._sources_added += 1
                    self._controller._sources_count = self._sources_added
            return True
        except Exception:
            return False
    
    def _parse_file(self, path: Path) -> List[dict]:
        """Parse log file and return records"""
        records = []
        suffix = path.suffix.lower()
        
        if suffix in ('.csv', '.tsv'):
            records = self._parse_csv(path, delimiter="\t" if suffix == ".tsv" else ",")
        elif suffix == '.json':
            records = self._parse_json(path)
        elif suffix == '.jsonl':
            records = self._parse_jsonl(path)
        elif suffix == '.evtx':
            records = self._parse_evtx(path)
        else:
            # Plain text - treat each line as a log
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append({"raw_line": line})
        
        return records
    
    def _parse_csv(self, path: Path, delimiter: str = ",") -> List[dict]:
        """Parse CSV file"""
        import csv
        records = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            for row in reader:
                # Create raw_line from the CSV row
                raw_line = ','.join(f"{k}={v}" for k, v in row.items())
                records.append({"raw_line": raw_line, **row})
        return records

    def _parse_jsonl(self, path: Path) -> List[dict]:
        """Parse JSON Lines file"""
        import json
        records = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    raw_line = json.dumps(item)
                    records.append({"raw_line": raw_line, **item})
        return records
    
    def _parse_json(self, path: Path) -> List[dict]:
        """Parse JSON file"""
        import json
        records = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    raw_line = json.dumps(item)
                    records.append({"raw_line": raw_line, **item})
            elif isinstance(data, dict):
                raw_line = json.dumps(data)
                records.append({"raw_line": raw_line, **data})
        return records
    
    def _parse_evtx(self, path: Path) -> List[dict]:
        """Parse Windows Event Log (EVTX) file"""
        try:
            from Evtx.Evtx import Evtx
            records = []
            with Evtx(str(path)) as log:
                for record in log.records():
                    xml = record.xml()
                    records.append({"raw_line": xml})
            return records
        except Exception:
            return []
    
    def start_ingestion(self):
        """Placeholder for ingestion start (files are processed immediately)"""
        pass

