"""Preprocessing pipeline orchestrator.

Chains multiple preprocessors together with configurable flow
and handles the transformation from parsed records to clean DataFrames.
"""

from typing import Any, Protocol, runtime_checkable
from pathlib import Path
import json

import pandas as pd
from pydantic import BaseModel, Field

from soc_copilot.core.logging import get_logger
from soc_copilot.data.preprocessing.missing_values import (
    MissingValueHandler,
    MissingValueConfig,
)
from soc_copilot.data.preprocessing.timestamp_normalizer import (
    TimestampNormalizer,
    TimestampConfig,
)
from soc_copilot.data.preprocessing.field_standardizer import (
    FieldStandardizer,
    FieldStandardizerConfig,
)
from soc_copilot.data.preprocessing.categorical_encoder import (
    CategoricalEncoder,
    CategoricalEncoderConfig,
)

logger = get_logger(__name__)


@runtime_checkable
class Preprocessor(Protocol):
    """Protocol for preprocessing components."""
    
    def process(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process records and return transformed records."""
        ...
    
    def get_stats(self) -> dict[str, int]:
        """Get processing statistics."""
        ...


class PipelineStep(BaseModel):
    """Configuration for a single pipeline step."""
    
    name: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class PipelineConfig(BaseModel):
    """Configuration for the preprocessing pipeline."""
    
    # Pipeline steps in order
    steps: list[PipelineStep] = Field(default_factory=lambda: [
        PipelineStep(name="timestamp_normalizer"),
        PipelineStep(name="field_standardizer"),
        PipelineStep(name="missing_values"),
        PipelineStep(name="categorical_encoder"),
    ])
    
    # Whether to convert final output to DataFrame
    output_dataframe: bool = True
    
    # Fields required in final output (records missing these are dropped)
    required_output_fields: list[str] = Field(
        default_factory=lambda: ["timestamp_normalized"]
    )
    
    # Whether to log detailed stats after each step
    log_step_stats: bool = True
    
    # Save intermediate results for debugging
    save_intermediates: bool = False
    intermediate_dir: str = "data/preprocessing_debug"


class PreprocessingPipeline:
    """Orchestrates the preprocessing pipeline.
    
    Chains multiple preprocessors together in a configurable order:
    1. Timestamp normalization (to UTC ISO 8601)
    2. Field standardization (canonical names)
    3. Missing value handling
    4. Categorical encoding
    
    Features:
    - Configurable step ordering and enabling
    - Per-step configuration
    - DataFrame output option
    - Required field validation
    - Intermediate result saving for debugging
    - Comprehensive statistics tracking
    
    Usage:
        pipeline = PreprocessingPipeline(config)
        
        # Fit on training data (for encoder)
        pipeline.fit(training_records)
        
        # Transform data
        df = pipeline.transform(records)
    """
    
    def __init__(self, config: PipelineConfig | None = None):
        """Initialize pipeline with configuration.
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or PipelineConfig()
        
        # Initialize preprocessors
        self._preprocessors: dict[str, Any] = {}
        self._init_preprocessors()
        
        # Track if fitted
        self._fitted = False
        
        # Aggregate statistics
        self._stats: dict[str, dict[str, int]] = {}
    
    def _init_preprocessors(self) -> None:
        """Initialize all preprocessor instances."""
        for step in self.config.steps:
            if not step.enabled:
                continue
            
            if step.name == "timestamp_normalizer":
                ts_config = TimestampConfig(**step.config) if step.config else None
                self._preprocessors[step.name] = TimestampNormalizer(ts_config)
            
            elif step.name == "field_standardizer":
                fs_config = FieldStandardizerConfig(**step.config) if step.config else None
                self._preprocessors[step.name] = FieldStandardizer(fs_config)
            
            elif step.name == "missing_values":
                mv_config = MissingValueConfig(**step.config) if step.config else None
                self._preprocessors[step.name] = MissingValueHandler(mv_config)
            
            elif step.name == "categorical_encoder":
                ce_config = CategoricalEncoderConfig(**step.config) if step.config else None
                self._preprocessors[step.name] = CategoricalEncoder(ce_config)
            
            else:
                logger.warning(
                    "unknown_pipeline_step",
                    step_name=step.name,
                )
    
    @property
    def is_fitted(self) -> bool:
        """Whether the pipeline has been fitted."""
        return self._fitted
    
    def fit(self, records: list[dict[str, Any]]) -> None:
        """Fit the pipeline on training data.
        
        Currently only the categorical encoder needs fitting.
        Other preprocessors are stateless or self-fitting.
        
        Args:
            records: Training records
        """
        # Run through non-fitting steps first to prepare data for encoder
        processed = records
        
        for step in self.config.steps:
            if not step.enabled or step.name not in self._preprocessors:
                continue
            
            preprocessor = self._preprocessors[step.name]
            
            # Fit components that need it
            if step.name == "missing_values":
                preprocessor.fit(processed)
                processed = preprocessor.process(processed)
            
            elif step.name == "categorical_encoder":
                # Fit encoder on processed data
                preprocessor.fit(processed)
            
            elif hasattr(preprocessor, "process"):
                processed = preprocessor.process(processed)
        
        self._fitted = True
        
        logger.info(
            "pipeline_fit_complete",
            record_count=len(records),
            steps=len(self._preprocessors),
        )
    
    def transform(self, records: list[dict[str, Any]]) -> pd.DataFrame | list[dict[str, Any]]:
        """Transform records through the pipeline.
        
        Args:
            records: Records to transform
            
        Returns:
            DataFrame or list of dicts depending on config
        """
        if not self._fitted:
            logger.warning("pipeline_not_fitted", message="Fitting on input data")
            self.fit(records)
        
        self._stats = {}
        processed = records
        
        for step in self.config.steps:
            if not step.enabled or step.name not in self._preprocessors:
                continue
            
            preprocessor = self._preprocessors[step.name]
            
            # For categorical encoder, use transform (not fit_transform)
            if step.name == "categorical_encoder":
                processed = preprocessor.transform(processed)
            else:
                processed = preprocessor.process(processed)
            
            # Collect stats
            if hasattr(preprocessor, "get_stats"):
                self._stats[step.name] = preprocessor.get_stats()
                
                if self.config.log_step_stats:
                    logger.debug(
                        "pipeline_step_complete",
                        step=step.name,
                        **self._stats[step.name],
                    )
            
            # Save intermediate results if configured
            if self.config.save_intermediates:
                self._save_intermediate(step.name, processed)
        
        # Filter by required output fields
        if self.config.required_output_fields:
            processed = self._filter_required_fields(processed)
        
        # Convert to DataFrame if configured
        if self.config.output_dataframe:
            return self._to_dataframe(processed)
        
        return processed
    
    def fit_transform(self, records: list[dict[str, Any]]) -> pd.DataFrame | list[dict[str, Any]]:
        """Fit and transform in one step.
        
        Args:
            records: Records to fit and transform
            
        Returns:
            Transformed output
        """
        self.fit(records)
        return self.transform(records)
    
    def _filter_required_fields(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filter out records missing required output fields.
        
        Args:
            records: Records to filter
            
        Returns:
            Filtered records
        """
        results: list[dict[str, Any]] = []
        dropped = 0
        
        for record in records:
            has_all_required = all(
                field in record and record[field] not in (None, "")
                for field in self.config.required_output_fields
            )
            
            if has_all_required:
                results.append(record)
            else:
                dropped += 1
        
        if dropped > 0:
            logger.info(
                "records_dropped_missing_required",
                dropped=dropped,
                required_fields=self.config.required_output_fields,
            )
        
        return results
    
    def _to_dataframe(self, records: list[dict[str, Any]]) -> pd.DataFrame:
        """Convert records to DataFrame.
        
        Args:
            records: Records to convert
            
        Returns:
            pandas DataFrame
        """
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        
        logger.info(
            "pipeline_output_dataframe",
            rows=len(df),
            columns=len(df.columns),
        )
        
        return df
    
    def _save_intermediate(self, step_name: str, records: list[dict[str, Any]]) -> None:
        """Save intermediate results for debugging.
        
        Args:
            step_name: Name of the step
            records: Records after this step
        """
        output_dir = Path(self.config.intermediate_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / f"after_{step_name}.json"
        
        # Convert to JSON-serializable format
        serializable = []
        for record in records[:100]:  # Limit to first 100 for debugging
            serializable.append({
                k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                for k, v in record.items()
            })
        
        with open(output_file, "w") as f:
            json.dump(serializable, f, indent=2)
    
    def get_stats(self) -> dict[str, dict[str, int]]:
        """Get aggregate statistics from all steps.
        
        Returns:
            Dict mapping step name to step stats
        """
        return self._stats.copy()
    
    def get_encoder(self) -> CategoricalEncoder | None:
        """Get the categorical encoder for inference.
        
        Returns:
            CategoricalEncoder instance or None
        """
        return self._preprocessors.get("categorical_encoder")


def create_default_pipeline() -> PreprocessingPipeline:
    """Create a pipeline with default configuration.
    
    Returns:
        Configured PreprocessingPipeline
    """
    return PreprocessingPipeline(PipelineConfig())
