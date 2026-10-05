"""Application controller orchestrating ingestion → analysis → results"""

import time
import uuid
from datetime import datetime
from typing import Optional, Callable, List
from pathlib import Path

from soc_copilot.pipeline import AnalysisStats, create_soc_copilot
from .schemas import AnalysisResult, AlertSummary, PipelineStats, LogSummary
from .result_store import ResultStore

from soc_copilot.core.logging import get_logger
from soc_copilot.security.model_integrity import strict_model_integrity_enabled
from soc_copilot.security.network import is_external_ip, online_enrichment_enabled

logger = get_logger(__name__)


# Priority labels for rule/text-log alerts. Kept identical to
# soc_copilot.models.ensemble.coordinator.AlertPriority values (not imported,
# to keep the controller decoupled from the models package).
PRIORITY_CRITICAL = "P0-Critical"
PRIORITY_HIGH = "P1-High"
PRIORITY_MEDIUM = "P2-Medium"


class AppController:
    """Main application controller for real-time analysis"""
    
    def __init__(
        self,
        models_dir: str,
        killswitch_check: Optional[Callable[[], bool]] = None,
        results_db=None,
    ):
        self.models_dir = models_dir
        self.killswitch_check = killswitch_check
        self.result_store = ResultStore(max_results=1000, db_path=results_db)
        self._pipeline = None
        self._text_log_classifier = None
        self._text_log_model_status = {
            "loaded": False,
            "path": "",
            "error": None,
        }
        self._running = False
        self._sources_count = 0
        self._dropped_count = 0
        self._batches_processed = 0
    
    def initialize(self):
        """Initialize analysis pipelines (network-flow ML + text log ML)"""
        self._pipeline = create_soc_copilot(self.models_dir)
        
        # Load text log classifier (optional — falls back to rules)
        text_log_model_path = Path(self.models_dir) / "text_log_rf_v1.joblib"
        try:
            from models.text_log_classifier.text_log_classifier import TextLogClassifier
            clf = TextLogClassifier()
            clf.load(text_log_model_path)
            self._text_log_classifier = clf
            self._text_log_model_status = {
                "loaded": True,
                "path": str(text_log_model_path),
                "error": None,
            }
            logger.info("text_log_classifier_loaded", path=str(text_log_model_path))
        except (FileNotFoundError, ImportError) as e:
            logger.warning(
                "text_log_classifier_not_available",
                error=str(e),
                fallback="rule-based detection",
            )
            self._text_log_classifier = None
            self._text_log_model_status = {
                "loaded": False,
                "path": str(text_log_model_path),
                "error": str(e),
            }
    
    def process_batch(self, records: List[dict]) -> Optional[AnalysisResult]:
        """Process batch of raw log records"""
        # Check kill switch
        if self.killswitch_check and self.killswitch_check():
            return None
        
        if not self._pipeline:
            raise RuntimeError("Pipeline not initialized. Call initialize() first.")
        
        # Extract raw lines
        raw_lines = [r.get("raw_line", "") for r in records if r.get("raw_line")]
        if not raw_lines:
            return None
        
        # Measure processing time
        start_time = time.time()
        
        # Run text log ML detection (falls back to rules if model unavailable)
        text_log_alerts = self._text_log_ml_detect(raw_lines)
        
        # Analyze batch (using existing ML pipeline). If it fails, keep the
        # text-log/rule alerts instead of discarding the whole batch.
        try:
            results, alerts, stats = self._analyze_lines(raw_lines)
        except Exception as e:
            logger.error("ml_pipeline_batch_failed", lines=len(raw_lines), error=str(e))
            self._dropped_count += len(raw_lines)
            if not text_log_alerts:
                return None
            results, alerts, stats = [], [], AnalysisStats()
            stats.total_records = len(raw_lines)
        
        # Mark as active after first processed batch
        self._running = True
        self._sources_count = max(self._sources_count, 1)
        self._batches_processed += 1
        
        processing_time = time.time() - start_time
        
        # Convert ML alerts to view models
        alert_summaries = self._convert_alerts(alerts)
        
        # Merge text log alerts with network-flow ML alerts
        alert_summaries.extend(text_log_alerts)
        
        pipeline_stats = self._convert_stats(stats, processing_time)
        pipeline_stats.alerts_generated = len(alert_summaries)
        for ta in text_log_alerts:
            cls = ta.classification
            pipeline_stats.classification_distribution[cls] = (
                pipeline_stats.classification_distribution.get(cls, 0) + 1
            )
            
        # Build generic log summaries for ALL logs. Results are matched to
        # their originating line by index, since failed records are skipped.
        results_by_line = {
            r.source_context["line_index"]: r
            for r in results
            if "line_index" in r.source_context
        }
        log_summaries = []
        for i, line in enumerate(raw_lines):
            cls = "Benign"
            conf = 1.0
            risk = "Low"
            is_alert = False
            src_ip = None
            dst_ip = None
            
            r = results_by_line.get(i)
            if r is not None:
                cls = r.ensemble_result.classification
                conf = r.ensemble_result.class_confidence
                risk = r.ensemble_result.risk_level.value
                is_alert = r.requires_alert
                src_ip = r.source_context.get("src_ip")
                dst_ip = r.source_context.get("dst_ip")
                
            log_id = f"LOG-{uuid.uuid4().hex[:8]}"
            log_summaries.append(LogSummary(
                log_id=log_id,
                timestamp=datetime.now(),
                classification=cls,
                confidence=conf,
                risk_level=risk,
                source_ip=src_ip,
                destination_ip=dst_ip,
                raw_log=line,
                is_alert=is_alert
            ))
        
        # Create result
        result = AnalysisResult(
            batch_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            alerts=alert_summaries,
            logs=log_summaries,
            stats=pipeline_stats,
            raw_count=len(raw_lines)
        )
        
        # Store result
        self.result_store.add(result)
        
        return result
    
    # ------------------------------------------------------------------
    # Text Log ML Detection
    # ------------------------------------------------------------------
    
    # Priority and action mappings for text log classifications
    _CLASSIFICATION_CONFIG = {
        "BruteForce": {
            "priority_high": PRIORITY_CRITICAL,
            "priority_low": PRIORITY_HIGH,
            "prefix": "ML-BF",
            "action": "Block source IP and investigate compromised credentials",
        },
        "Malware": {
            "priority_high": PRIORITY_CRITICAL,
            "priority_low": PRIORITY_CRITICAL,
            "prefix": "ML-MAL",
            "action": "Isolate host immediately, run malware scan, check for lateral movement",
        },
        "Exfiltration": {
            "priority_high": PRIORITY_CRITICAL,
            "priority_low": PRIORITY_HIGH,
            "prefix": "ML-EXFIL",
            "action": "Block outbound connection, investigate data contents and authorization",
        },
        "Suspicious": {
            "priority_high": PRIORITY_HIGH,
            "priority_low": PRIORITY_MEDIUM,
            "prefix": "ML-SUSP",
            "action": "Investigate the activity and correlate with other events",
        },
    }
    
    def _text_log_ml_detect(self, lines: List[str]) -> List[AlertSummary]:
        """ML-based threat detection for text log lines.
        
        Uses the text log Random Forest classifier. Falls back to
        rule-based detection if the model is not loaded.
        
        Args:
            lines: Raw log lines
            
        Returns:
            List of AlertSummary objects for detected threats
        """
        # Fall back to rules if ML model not available
        if self._text_log_classifier is None:
            return self._rule_based_detect(lines)
        
        alerts: List[AlertSummary] = []
        
        for line in lines:
            parsed = self._parse_raw_log(line)
            
            try:
                classification, confidence, class_probas = (
                    self._text_log_classifier.classify(parsed)
                )
            except Exception as e:
                logger.warning("text_log_classify_failed", line=line[:80], error=str(e))
                continue
            
            # Skip benign events
            if classification == "Benign":
                continue
            
            # Only alert if confidence is above threshold
            if confidence < 0.70:
                continue
            
            config = self._CLASSIFICATION_CONFIG.get(classification, {})
            if not config:
                continue
            
            # Determine priority based on confidence
            if confidence >= 0.85:
                priority = config["priority_high"]
                risk = min(confidence, 0.95)
            else:
                priority = config["priority_low"]
                risk = confidence
            
            # Build human-readable reasoning
            src_ip = parsed.get("src_ip", "")
            dst_ip = parsed.get("dst_ip", "")
            user = parsed.get("user", "")
            event_type = parsed.get("event_type", "")
            
            reasoning_parts = [
                f"ML classification: {classification} ({confidence:.0%} confidence).",
            ]
            if event_type:
                reasoning_parts.append(f"Event: {event_type}.")
            if user:
                reasoning_parts.append(f"User: {user}.")
            if src_ip and self._is_external_ip(src_ip):
                reasoning_parts.append(f"External source IP: {src_ip}.")
            if dst_ip and self._is_external_ip(dst_ip):
                reasoning_parts.append(f"External destination IP: {dst_ip}.")
            if parsed.get("login_attempts", 0) > 0:
                reasoning_parts.append(f"Failed login attempts: {parsed['login_attempts']}.")
            if parsed.get("data_size_mb", 0) > 0:
                reasoning_parts.append(f"Data transfer: {parsed['data_size_mb']}MB.")
            
            # Top class probabilities for context
            top_3 = sorted(class_probas.items(), key=lambda x: -x[1])[:3]
            prob_str = ", ".join(f"{c}: {p:.0%}" for c, p in top_3)
            reasoning_parts.append(f"Class probabilities: [{prob_str}]")
            
            alerts.append(AlertSummary(
                alert_id=f"{config['prefix']}-{uuid.uuid4().hex[:8]}",
                priority=priority,
                classification=classification,
                confidence=confidence,
                anomaly_score=risk,
                risk_score=risk,
                source_ip=src_ip or None,
                destination_ip=dst_ip or None,
                timestamp=datetime.now(),
                reasoning=" ".join(reasoning_parts),
                suggested_action=config["action"],
            ))
        
        return alerts
    
    @staticmethod
    def _is_external_ip(ip: str) -> bool:
        """Check if an IP address is external (non-RFC1918)."""
        return is_external_ip(ip)
    
    def _rule_based_detect(self, lines: List[str]) -> List[AlertSummary]:
        """Rule-based threat detection for custom text log formats.
        
        Detects:
        - Brute force: LoginAttempt with attempts >= 5
        - Malware execution: FileExecution with suspicious files (.exe, payload)
        - Data exfiltration: DataTransfer > 500MB to external IPs
        - External brute force: LoginAttempt from external IPs
        
        Returns:
            List of AlertSummary objects for detected threats
        """
        alerts = []
        
        for line in lines:
            parsed = self._parse_raw_log(line)
            event_type = parsed.get("event_type", "")
            
            # Rule 1: Brute Force Detection
            if event_type == "LoginAttempt":
                attempts = parsed.get("login_attempts", 0)
                src_ip = parsed.get("src_ip", "")
                user = parsed.get("user", "unknown")
                is_external = self._is_external_ip(src_ip)
                
                if attempts >= 10 and is_external:
                    # Critical: high-volume brute force from external IP
                    alerts.append(AlertSummary(
                        alert_id=f"RULE-BF-{uuid.uuid4().hex[:8]}",
                        priority=PRIORITY_CRITICAL,
                        classification="BruteForce",
                        confidence=0.95,
                        anomaly_score=0.95,
                        risk_score=0.95,
                        source_ip=src_ip,
                        destination_ip=None,
                        timestamp=datetime.now(),
                        reasoning=(
                            f"Brute force attack detected: {attempts} failed login attempts "
                            f"for user '{user}' from external IP {src_ip}"
                        ),
                        suggested_action="Block source IP immediately and investigate compromised credentials",
                    ))
                elif attempts >= 5:
                    # High: moderate brute force
                    priority = PRIORITY_CRITICAL if is_external else PRIORITY_HIGH
                    risk = 0.90 if is_external else 0.75
                    alerts.append(AlertSummary(
                        alert_id=f"RULE-BF-{uuid.uuid4().hex[:8]}",
                        priority=priority,
                        classification="BruteForce",
                        confidence=0.85,
                        anomaly_score=risk,
                        risk_score=risk,
                        source_ip=src_ip,
                        destination_ip=None,
                        timestamp=datetime.now(),
                        reasoning=(
                            f"Brute force attempt: {attempts} failed logins "
                            f"for user '{user}' from {'external' if is_external else 'internal'} IP {src_ip}"
                        ),
                        suggested_action="Investigate account and consider temporary lockout",
                    ))
            
            # Rule 2: Malware Execution Detection
            elif event_type == "FileExecution":
                host = parsed.get("host", "unknown")
                filename = parsed.get("file", "")
                
                if filename and (".exe" in filename.lower() or "payload" in filename.lower()):
                    alerts.append(AlertSummary(
                        alert_id=f"RULE-MAL-{uuid.uuid4().hex[:8]}",
                        priority=PRIORITY_CRITICAL,
                        classification="Malware",
                        confidence=0.90,
                        anomaly_score=0.92,
                        risk_score=0.92,
                        source_ip=None,
                        destination_ip=None,
                        timestamp=datetime.now(),
                        reasoning=(
                            f"Suspicious executable detected: '{filename}' executed on {host}"
                        ),
                        suggested_action="Isolate host immediately, run malware scan, check for lateral movement",
                    ))
            
            # Rule 3: Data Exfiltration Detection
            elif event_type == "DataTransfer":
                size_mb = parsed.get("data_size_mb", 0)
                dst_ip = parsed.get("dst_ip", "")
                host = parsed.get("host", "unknown")
                is_external = self._is_external_ip(dst_ip)
                
                if size_mb > 500 and is_external:
                    if size_mb > 2000:
                        priority = PRIORITY_CRITICAL
                        risk = 0.95
                    else:
                        priority = PRIORITY_HIGH
                        risk = 0.80
                    
                    alerts.append(AlertSummary(
                        alert_id=f"RULE-EXFIL-{uuid.uuid4().hex[:8]}",
                        priority=priority,
                        classification="Exfiltration",
                        confidence=0.88,
                        anomaly_score=risk,
                        risk_score=risk,
                        source_ip=None,
                        destination_ip=dst_ip,
                        timestamp=datetime.now(),
                        reasoning=(
                            f"Potential data exfiltration: {size_mb}MB transferred "
                            f"from {host} to external IP {dst_ip}"
                        ),
                        suggested_action="Block outbound connection, investigate data contents and authorization",
                    ))
            # Rule 4: Privilege Escalation Detection
            elif event_type == "PrivilegeEscalation":
                user = parsed.get("user", "unknown")
                new_role = parsed.get("new_role", "")

                if new_role.lower() in ("admin", "root"):
                    alerts.append(AlertSummary(
                        alert_id=f"RULE-PRIV-{uuid.uuid4().hex[:8]}",
                        priority=PRIORITY_CRITICAL,
                        classification="PrivilegeEscalation",
                        confidence=0.90,
                        anomaly_score=0.93,
                        risk_score=0.93,
                        source_ip=None,
                        destination_ip=None,
                        timestamp=datetime.now(),
                        reasoning=(
                            f"Privilege escalation detected: user '{user}' "
                            f"was granted '{new_role}' role"
                        ),
                        suggested_action="Verify authorization for this role change and audit account activity immediately",
                    ))
        
        return alerts
    
    def _parse_raw_log(self, line: str) -> dict:
        """Extract security-relevant fields from raw log lines.
        
        Parses log formats like:
        2026-01-18 02:56:01 LoginAttempt user=admin ip=45.67.89.101 success=false attempts=23
        2026-01-18 02:49:12 FileExecution host=server-02 file=payload.exe
        2026-01-18 02:58:11 DataTransfer source=server-02 destination=185.220.101.45 size=3526MB
        """
        import re
        
        entry = {
            "timestamp": "",
            "event_type": "",
            "user": "",
            "src_ip": "",
            "dst_ip": "",
            "host": "",
            "file": "",
            "action": "log_entry",
            "protocol": "TCP",
            "raw_log": line,
            "login_attempts": 0,
            "data_size_mb": 0,
            "new_role": ""
        }
        
        # Extract timestamp (YYYY-MM-DD HH:MM:SS)
        ts_match = re.match(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if ts_match:
            entry["timestamp"] = ts_match.group(1).replace(' ', 'T') + 'Z'
        
        # Extract event type
        event_match = re.search(r'\b(UserLogin|LoginAttempt|LoginFailure|BruteForceDetected|FileExecution|MalwareDetected|DataTransfer|DataExfiltration|PrivilegeEscalation)\b', line)
        if event_match:
            raw_event = event_match.group(1)
            _EVENT_NORMALIZE = {
                "LoginFailure": "LoginAttempt",
                "BruteForceDetected": "LoginAttempt",
                "MalwareDetected": "FileExecution",
                "DataExfiltration": "DataTransfer",
            }
            entry["event_type"] = _EVENT_NORMALIZE.get(raw_event, raw_event)
        
        # Extract key=value pairs
        for match in re.finditer(r'(\w+)=([^\s]+)', line):
            key, value = match.groups()
            if key == 'ip':
                entry["src_ip"] = value
            elif key == 'source':
                entry["host"] = value
            elif key == 'destination':
                entry["dst_ip"] = value
            elif key == 'host':
                entry["host"] = value
            elif key == 'user':
                entry["user"] = value
            elif key == 'file':
                entry["file"] = value
                entry["action"] = f"execute:{value}"
            elif key == 'attempts':
                try:
                    entry["login_attempts"] = int(value)
                except ValueError:
                    pass
            elif key == 'size':
                try:
                    if 'GB' in value:
                        entry["data_size_mb"] = int(float(value.replace('GB', '')) * 1024)
                    else:
                        entry["data_size_mb"] = int(value.replace('MB', ''))
                except ValueError:
                    pass
            elif key == "new_role":
                entry["new_role"] = value
        
        # Flag suspicious patterns based on thresholds
        if entry["login_attempts"] >= 5:
            entry["action"] = "brute_force"
        if "payload" in line.lower() or ".exe" in line:
            entry["action"] = "malware_execution"
        if entry["data_size_mb"] > 500:
            entry["action"] = "data_exfiltration"
        
        # Mark external IPs as suspicious
        for ip_field in ["src_ip", "dst_ip"]:
            ip = entry.get(ip_field, "")
            if is_external_ip(ip):
                entry["external_ip"] = True
        
        return entry
    
    def _analyze_lines(self, lines: List[str]):
        """Analyze lines using existing pipeline"""
        import tempfile
        import json
        
        # Create temp file in JSONL format for proper parsing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8') as f:
            for index, line in enumerate(lines):
                # Use JSON objects as-is, otherwise extract fields from the raw log
                try:
                    log_entry = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    log_entry = None
                if not isinstance(log_entry, dict):
                    log_entry = self._parse_raw_log(line)
                log_entry["_line_index"] = index
                f.write(json.dumps(log_entry) + '\n')
            temp_path = f.name
        
        try:
            results, alerts, stats = self._pipeline.analyze_file(Path(temp_path))
            return results, alerts, stats
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    def _convert_alerts(self, alerts) -> List[AlertSummary]:
        """Convert pipeline alerts to view models"""
        summaries = []
        for alert in alerts:
            summaries.append(AlertSummary(
                alert_id=alert.alert_id,
                priority=alert.priority.value,
                classification=alert.classification,
                confidence=alert.classification_confidence,
                anomaly_score=alert.anomaly_score,
                risk_score=alert.combined_risk_score,
                source_ip=alert.source_ip,
                destination_ip=alert.destination_ip,
                timestamp=datetime.now(),
                reasoning=alert.reasoning,
                suggested_action=alert.suggested_action
            ))
        return summaries
    
    def _convert_stats(self, stats, processing_time: float) -> PipelineStats:
        """Convert pipeline stats to view model"""
        return PipelineStats(
            total_records=stats.total_records,
            processed_records=stats.processed_records,
            alerts_generated=0,
            risk_distribution=dict(stats.risk_distribution),
            classification_distribution=dict(stats.classification_distribution),
            processing_time=processing_time
        )
    
    def set_sources_count(self, count: int) -> None:
        """Record how many log sources are feeding this controller."""
        self._sources_count = max(0, count)
    
    def get_results(self, limit: int = 10) -> List[AnalysisResult]:
        """Get latest analysis results"""
        return self.result_store.get_latest(limit)
    
    def get_result_by_id(self, batch_id: str) -> Optional[AnalysisResult]:
        """Get specific result by ID"""
        return self.result_store.get_by_id(batch_id)
    
    def get_stats(self) -> dict:
        """Get controller statistics"""
        deduplication = {}
        model_integrity = {}
        if self._pipeline and hasattr(self._pipeline, "_analysis"):
            analysis = getattr(self._pipeline, "_analysis", None)
            if analysis and hasattr(analysis, "get_deduplication_stats"):
                deduplication = analysis.get_deduplication_stats()
        if self._pipeline and hasattr(self._pipeline, "get_security_status"):
            model_integrity = self._pipeline.get_security_status().get("model_integrity", {})

        return {
            "pipeline_loaded": self._pipeline is not None,
            "results_stored": self.result_store.count(),
            "models_dir": self.models_dir,
            "running": self._running,
            "sources_count": self._sources_count,
            "dropped_count": self._dropped_count,
            "batches_processed": self._batches_processed,
            "deduplication": deduplication,
            "security": {
                "strict_model_integrity": strict_model_integrity_enabled(),
                "online_enrichment_enabled": online_enrichment_enabled(),
                "model_integrity": model_integrity,
                "text_log_model": dict(self._text_log_model_status),
            },
        }
    
    def clear_results(self):
        """Clear stored results"""
        self.result_store.clear()
