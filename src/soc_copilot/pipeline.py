"""End-to-end SOC Copilot pipeline.

Integrates all components from log ingestion to alert generation
into a unified, production-ready pipeline.
"""

from pathlib import Path
from typing import Any, Iterator
import pandas as pd
import numpy as np

from soc_copilot.data.log_ingestion import (
    parse_log_file,
    parse_log_directory,
    ParsedRecord,
)
from soc_copilot.data.preprocessing import (
    PreprocessingPipeline,
    PipelineConfig,
)
from soc_copilot.data.feature_engineering import (
    FeatureEngineeringPipeline,
    FeaturePipelineConfig,
)
from soc_copilot.models.ensemble import (
    AnalysisPipeline,
    AnalysisPipelineConfig,
    AnalysisResult,
    Alert,
    format_alert_summary,
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


class SOCCopilotConfig:
    """Configuration for the complete SOC Copilot pipeline."""
    
    def __init__(
        self,
        models_dir: str = "data/models",
        preprocessing_config: PipelineConfig | None = None,
        feature_config: FeaturePipelineConfig | None = None,
        analysis_config: AnalysisPipelineConfig | None = None,
    ):
        self.models_dir = models_dir
        self.preprocessing_config = preprocessing_config or PipelineConfig()
        self.feature_config = feature_config or FeaturePipelineConfig()
        self.analysis_config = analysis_config or AnalysisPipelineConfig(
            models_dir=models_dir
        )


class AnalysisStats:
    """Statistics from a batch analysis run."""
    
    def __init__(self):
        self.total_records = 0
        self.processed_records = 0
        self.alerts_generated = 0
        self.risk_distribution: dict[str, int] = {
            "Low": 0, "Medium": 0, "High": 0, "Critical": 0
        }
        self.classification_distribution: dict[str, int] = {}
        self.parse_errors = 0
        self.preprocessing_errors = 0
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "processed_records": self.processed_records,
            "alerts_generated": self.alerts_generated,
            "risk_distribution": self.risk_distribution,
            "classification_distribution": self.classification_distribution,
            "parse_errors": self.parse_errors,
            "preprocessing_errors": self.preprocessing_errors,
        }


class SOCCopilot:
    """Complete SOC Copilot analysis pipeline.
    
    Provides end-to-end processing from raw logs to actionable alerts:
    
    1. Log Ingestion: Parse various log formats (JSON, Syslog, CSV)
    2. Preprocessing: Normalize timestamps, standardize fields, encode categoricals
    3. Feature Engineering: Extract statistical, temporal, behavioral, network features
    4. ML Inference: Anomaly detection (IF) + Classification (RF)
    5. Ensemble Scoring: Combine scores with decision matrix
    6. Alert Generation: Create prioritized alerts with MITRE ATT&CK mapping
    
    Usage:
        copilot = SOCCopilot()
        copilot.load()
        
        # Analyze a single file
        results, alerts = copilot.analyze_file("logs/access.log")
        
        # Analyze a directory
        results, alerts, stats = copilot.analyze_directory("logs/")
    """
    
    def __init__(self, config: SOCCopilotConfig | None = None):
        """Initialize SOC Copilot.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or SOCCopilotConfig()
        
        self._preprocessing = PreprocessingPipeline(self.config.preprocessing_config)
        self._features = FeatureEngineeringPipeline(self.config.feature_config)
        self._analysis = AnalysisPipeline(self.config.analysis_config)
        
        self._loaded = False
        self._feature_order: list[str] = []
    
    @property
    def is_loaded(self) -> bool:
        """Whether models are loaded."""
        return self._loaded
    
    def load(self) -> None:
        """Load ML models."""
        self._analysis.load()
        self._feature_order = self._analysis.feature_order
        self._loaded = True
        
        logger.info(
            "soc_copilot_loaded",
            feature_count=len(self._feature_order),
        )
    
    def analyze_records(
        self,
        records: list[ParsedRecord],
    ) -> tuple[list[AnalysisResult], list[Alert]]:
        """Analyze a batch of parsed records.
        
        Args:
            records: List of ParsedRecord objects
            
        Returns:
            Tuple of (results, alerts)
        """
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")
        
        if not records:
            return [], []
        
        # Convert to DataFrame
        df = pd.DataFrame([r.raw for r in records])
        
        # Add metadata
        for i, record in enumerate(records):
            df.loc[i, "_record_id"] = getattr(record, 'record_id', str(i))
            df.loc[i, "_source_file"] = str(record.source_file) if record.source_file else ""
            df.loc[i, "_line_number"] = getattr(record, 'line_number', i)
        
        # Step 1: Preprocessing
        try:
            df_preprocessed = self._preprocessing.fit_transform(df)
        except Exception as e:
            logger.error("preprocessing_failed", error=str(e))
            df_preprocessed = df.copy()
        
        # Step 2: Feature Engineering
        try:
            self._features.fit(df_preprocessed)
            df_features = self._features.transform(df_preprocessed)
        except Exception as e:
            logger.error("feature_extraction_failed", error=str(e))
            df_features = df_preprocessed.copy()
        
        # Step 3: Prepare feature vectors
        results = []
        alerts = []
        
        for idx in df_features.index:
            try:
                # Build feature vector in correct order
                feature_vector = self._build_feature_vector(df_features.loc[idx])
                
                # Build source context
                context = self._build_context(df_features.loc[idx], records[idx] if idx < len(records) else None)
                
                # Step 4-6: Analysis (inference + ensemble + alert)
                result = self._analysis.analyze(feature_vector, context)
                results.append(result)
                
                if result.alert:
                    alerts.append(result.alert)
                    
            except Exception as e:
                logger.warning(
                    "record_analysis_failed",
                    index=idx,
                    error=str(e),
                )
        
        logger.info(
            "batch_analysis_complete",
            records=len(records),
            results=len(results),
            alerts=len(alerts),
        )
        
        return results, alerts
    
    def _build_feature_vector(self, row: pd.Series) -> np.ndarray:
        """Build feature vector in correct order."""
        vector = np.zeros(len(self._feature_order))
        
        for i, name in enumerate(self._feature_order):
            if name in row.index:
                val = row[name]
                if pd.notna(val):
                    try:
                        vector[i] = float(val)
                    except (ValueError, TypeError):
                        vector[i] = 0.0
        
        return vector
    
    def _build_context(
        self,
        row: pd.Series,
        record: ParsedRecord | None,
    ) -> dict[str, Any]:
        """Build source context for alert."""
        context = {}
        
        # Extract network fields
        for field in ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]:
            if field in row.index and pd.notna(row[field]):
                context[field] = row[field]
        
        # Add record metadata
        if record:
            context["record_id"] = record.record_id
            context["source_file"] = str(record.source_file)
            context["line_number"] = record.line_number
        
        return context
    
    def analyze_file(
        self,
        filepath: str | Path,
    ) -> tuple[list[AnalysisResult], list[Alert], AnalysisStats]:
        """Analyze a single log file.
        
        Args:
            filepath: Path to log file
            
        Returns:
            Tuple of (results, alerts, stats)
        """
        filepath = Path(filepath)
        stats = AnalysisStats()
        
        if not filepath.exists():
            logger.error("file_not_found", path=str(filepath))
            return [], [], stats
        
        logger.info("analyzing_file", path=str(filepath))
        
        # Parse log file
        records = parse_log_file(filepath)
        stats.total_records = len(records)
        
        if not records:
            logger.warning("no_records_parsed", path=str(filepath))
            return [], [], stats
        
        # Analyze records
        results, alerts = self.analyze_records(records)
        
        # Update stats
        stats.processed_records = len(results)
        stats.alerts_generated = len(alerts)
        
        for result in results:
            risk = result.ensemble_result.risk_level.value
            stats.risk_distribution[risk] = stats.risk_distribution.get(risk, 0) + 1
            
            cls = result.ensemble_result.classification
            stats.classification_distribution[cls] = (
                stats.classification_distribution.get(cls, 0) + 1
            )
        
        return results, alerts, stats
    
    def analyze_directory(
        self,
        dirpath: str | Path,
        recursive: bool = True,
    ) -> tuple[list[AnalysisResult], list[Alert], AnalysisStats]:
        """Analyze all log files in a directory.
        
        Args:
            dirpath: Path to directory
            recursive: Whether to search recursively
            
        Returns:
            Tuple of (results, alerts, stats)
        """
        dirpath = Path(dirpath)
        stats = AnalysisStats()
        all_results = []
        all_alerts = []
        
        if not dirpath.exists():
            logger.error("directory_not_found", path=str(dirpath))
            return [], [], stats
        
        logger.info("analyzing_directory", path=str(dirpath), recursive=recursive)
        
        # Parse all files
        all_records = parse_log_directory(dirpath, recursive=recursive)
        stats.total_records = len(all_records)
        
        if not all_records:
            logger.warning("no_records_found", path=str(dirpath))
            return [], [], stats
        
        # Process in batches
        batch_size = 1000
        for i in range(0, len(all_records), batch_size):
            batch = all_records[i:i + batch_size]
            results, alerts = self.analyze_records(batch)
            all_results.extend(results)
            all_alerts.extend(alerts)
        
        # Update stats
        stats.processed_records = len(all_results)
        stats.alerts_generated = len(all_alerts)
        
        for result in all_results:
            risk = result.ensemble_result.risk_level.value
            stats.risk_distribution[risk] = stats.risk_distribution.get(risk, 0) + 1
            
            cls = result.ensemble_result.classification
            stats.classification_distribution[cls] = (
                stats.classification_distribution.get(cls, 0) + 1
            )
        
        logger.info(
            "directory_analysis_complete",
            files_processed=stats.total_records,
            alerts=stats.alerts_generated,
        )
        
        return all_results, all_alerts, stats


def create_soc_copilot(models_dir: str = "data/models") -> SOCCopilot:
    """Create and load SOC Copilot pipeline.
    
    Args:
        models_dir: Path to trained models
        
    Returns:
        Loaded SOCCopilot instance
    """
    config = SOCCopilotConfig(models_dir=models_dir)
    copilot = SOCCopilot(config)
    copilot.load()
    return copilot
