"""
End-to-end SOC Copilot pipeline.

Integrates all components from log ingestion to alert generation
into a unified, production-ready pipeline.
"""

from pathlib import Path
from typing import Any
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
)
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

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


# -------------------------------------------------------------------
# Stats container
# -------------------------------------------------------------------

class AnalysisStats:
    """Statistics from a batch analysis run."""

    def __init__(self):
        self.total_records = 0
        self.processed_records = 0
        self.alerts_generated = 0
        self.risk_distribution = {
            "Low": 0,
            "Medium": 0,
            "High": 0,
            "Critical": 0,
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


# -------------------------------------------------------------------
# Main SOC Copilot
# -------------------------------------------------------------------

class SOCCopilot:
    """
    Complete SOC Copilot analysis pipeline.

    Flow:
    1. Log ingestion
    2. Preprocessing
    3. Feature engineering
    4. ML inference
    5. Ensemble scoring
    6. Alert generation (with deduplication)
    """

    def __init__(self, config: SOCCopilotConfig | None = None):
        self.config = config or SOCCopilotConfig()

        self._preprocessing = PreprocessingPipeline(self.config.preprocessing_config)
        self._features = FeatureEngineeringPipeline(self.config.feature_config)
        self._analysis = AnalysisPipeline(self.config.analysis_config)

        self._loaded = False
        self._feature_order: list[str] = []

    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load ML models and pipelines."""
        self._analysis.load()
        self._feature_order = self._analysis.feature_order
        self._loaded = True

        logger.info(
            "soc_copilot_loaded",
            feature_count=len(self._feature_order),
        )

    # ------------------------------------------------------------------

    def analyze_records(
        self,
        records: list[ParsedRecord],
    ) -> tuple[list[AnalysisResult], list[Alert]]:
        """Analyze parsed log records."""
        if not self._loaded:
            raise RuntimeError("Pipeline not loaded. Call load() first.")

        if not records:
            return [], []

        df = pd.DataFrame([r.raw for r in records])

        # Add record metadata
        for i, record in enumerate(records):
            df.loc[i, "_record_id"] = getattr(record, "record_id", str(i))
            df.loc[i, "_source_file"] = str(record.source_file) if record.source_file else ""
            df.loc[i, "_line_number"] = getattr(record, "line_number", i)

        # Preprocessing
        try:
            df_pre = self._preprocessing.fit_transform(df)
        except Exception as e:
            logger.error("preprocessing_failed", error=str(e))
            df_pre = df.copy()

        # Feature engineering
        try:
            self._features.fit(df_pre)
            df_feat = self._features.transform(df_pre)
        except Exception as e:
            logger.error("feature_extraction_failed", error=str(e))
            df_feat = df_pre.copy()

        results: list[AnalysisResult] = []
        alerts: list[Alert] = []

        for idx in df_feat.index:
            try:
                vector = self._build_feature_vector(df_feat.loc[idx])
                context = self._build_context(
                    df_feat.loc[idx],
                    records[idx] if idx < len(records) else None,
                )

                result = self._analysis.analyze(vector, context)

                # 🔑 Deduplicated benign events return None
                if result is None:
                    continue

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

    # ------------------------------------------------------------------

    def _build_feature_vector(self, row: pd.Series) -> np.ndarray:
        """Build feature vector in correct order."""
        vector = np.zeros(len(self._feature_order))

        for i, name in enumerate(self._feature_order):
            if name in row.index and pd.notna(row[name]):
                try:
                    vector[i] = float(row[name])
                except (TypeError, ValueError):
                    vector[i] = 0.0

        return vector

    # ------------------------------------------------------------------

    def _build_context(
        self,
        row: pd.Series,
        record: ParsedRecord | None,
    ) -> dict[str, Any]:
        """Build source context for alerts."""
        context: dict[str, Any] = {}

        for field in ["src_ip", "dst_ip", "src_port", "dst_port", "protocol"]:
            if field in row.index and pd.notna(row[field]):
                context[field] = row[field]

        if record:
            context["record_id"] = getattr(record, "record_id", None) or str(id(record))
            context["source_file"] = str(getattr(record, "source_file", "") or "")
            context["line_number"] = getattr(record, "line_number", 0)

        return context

    # ------------------------------------------------------------------

    def analyze_file(
        self,
        filepath: str | Path,
    ) -> tuple[list[AnalysisResult], list[Alert], AnalysisStats]:
        filepath = Path(filepath)
        stats = AnalysisStats()

        if not filepath.exists():
            logger.error("file_not_found", path=str(filepath))
            return [], [], stats

        logger.info("analyzing_file", path=str(filepath))

        records = parse_log_file(filepath)
        stats.total_records = len(records)

        results, alerts = self.analyze_records(records)

        stats.processed_records = len(results)
        stats.alerts_generated = len(alerts)

        for r in results:
            risk = r.ensemble_result.risk_level.value
            stats.risk_distribution[risk] += 1

            cls = r.ensemble_result.classification
            stats.classification_distribution[cls] = (
                stats.classification_distribution.get(cls, 0) + 1
            )

        return results, alerts, stats

    # ------------------------------------------------------------------

    def analyze_directory(
        self,
        dirpath: str | Path,
        recursive: bool = True,
    ) -> tuple[list[AnalysisResult], list[Alert], AnalysisStats]:
        dirpath = Path(dirpath)
        stats = AnalysisStats()

        if not dirpath.exists():
            logger.error("directory_not_found", path=str(dirpath))
            return [], [], stats

        records = parse_log_directory(dirpath, recursive=recursive)
        stats.total_records = len(records)

        all_results: list[AnalysisResult] = []
        all_alerts: list[Alert] = []

        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            results, alerts = self.analyze_records(batch)
            all_results.extend(results)
            all_alerts.extend(alerts)

        stats.processed_records = len(all_results)
        stats.alerts_generated = len(all_alerts)

        for r in all_results:
            risk = r.ensemble_result.risk_level.value
            stats.risk_distribution[risk] += 1

            cls = r.ensemble_result.classification
            stats.classification_distribution[cls] = (
                stats.classification_distribution.get(cls, 0) + 1
            )

        logger.info(
            "directory_analysis_complete",
            records=stats.total_records,
            alerts=stats.alerts_generated,
        )

        return all_results, all_alerts, stats


# -------------------------------------------------------------------
# Factory
# -------------------------------------------------------------------

def create_soc_copilot(models_dir: str = "data/models") -> SOCCopilot:
    config = SOCCopilotConfig(models_dir=models_dir)
    copilot = SOCCopilot(config)
    copilot.load()
    return copilot
