"""SOC Copilot - Offline Security Operations Center Assistant."""

__version__ = "1.0.0b1"

from soc_copilot.pipeline import (
    SOCCopilot,
    SOCCopilotConfig,
    AnalysisStats,
    create_soc_copilot,
)

__all__ = [
    "__version__",
    "SOCCopilot",
    "SOCCopilotConfig",
    "AnalysisStats",
    "create_soc_copilot",
]
