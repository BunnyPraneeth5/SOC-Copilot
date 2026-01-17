"""Read-only bridge between UI and AppController"""

from typing import List, Optional
from pathlib import Path
from ..controller import AppController, AnalysisResult


class ControllerBridge:
    """Adapter for UI to access AppController with file upload support"""
    
    def __init__(self, controller: AppController):
        self._controller = controller
    
    def get_latest_alerts(self, limit: int = 50) -> List[AnalysisResult]:
        """Get latest analysis results (read-only)"""
        return self._controller.get_results(limit=limit)
    
    def get_alert_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get specific result by ID (read-only)"""
        return self._controller.get_result_by_id(batch_id)
    
    def get_stats(self) -> dict:
        """Get controller statistics (read-only)"""
        return self._controller.get_stats()
    
    def get_total_alert_count(self) -> int:
        """Get total stored alert count"""
        return self._controller.result_store.count()
    
    def add_file_source(self, filepath: str) -> bool:
        """Add a file for analysis. Process immediately."""
        try:
            path = Path(filepath)
            if not path.exists():
                return False
            
            # Read and parse file content
            records = self._parse_file(path)
            if records:
                self._controller.process_batch(records)
            return True
        except Exception:
            return False
    
    def _parse_file(self, path: Path) -> List[dict]:
        """Parse log file and return records"""
        records = []
        suffix = path.suffix.lower()
        
        if suffix == '.csv':
            records = self._parse_csv(path)
        elif suffix == '.json':
            records = self._parse_json(path)
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
    
    def _parse_csv(self, path: Path) -> List[dict]:
        """Parse CSV file"""
        import csv
        records = []
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Create raw_line from the CSV row
                raw_line = ','.join(f"{k}={v}" for k, v in row.items())
                records.append({"raw_line": raw_line, **row})
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

