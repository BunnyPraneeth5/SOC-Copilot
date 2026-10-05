"""Centralized UI state definitions for consistent display across all components.

This module provides a single source of truth for:
- Pipeline states (Active, Loading, Inactive)
- Ingestion states (Active, Idle, Configured, Not Started, Stopped)
- Governance states (OK, Limited, Halted)
"""

from dataclasses import dataclass
from typing import Dict

from .theme import DARK


@dataclass
class StateConfig:
    """Configuration for a UI state display."""
    label: str
    color: str
    icon: str = "●"


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STATES
# ─────────────────────────────────────────────────────────────────────────────
class PipelineState:
    ACTIVE = "active"
    LOADING = "loading"
    INACTIVE = "inactive"


PIPELINE_STATES: Dict[str, StateConfig] = {
    PipelineState.ACTIVE: StateConfig(label="Active", color=DARK.success, icon="●"),
    PipelineState.LOADING: StateConfig(label="Loading...", color=DARK.sev_medium, icon="○"),
    PipelineState.INACTIVE: StateConfig(label="Inactive", color=DARK.sev_high, icon="○"),
}


def get_pipeline_state(pipeline_loaded: bool) -> str:
    """Determine pipeline state from stats."""
    return PipelineState.ACTIVE if pipeline_loaded else PipelineState.LOADING


# ─────────────────────────────────────────────────────────────────────────────
# INGESTION STATES
# ─────────────────────────────────────────────────────────────────────────────
class IngestionState:
    ACTIVE = "active"
    IDLE = "idle"
    CONFIGURED = "configured"
    NOT_STARTED = "not_started"
    STOPPED = "stopped"


INGESTION_STATES: Dict[str, StateConfig] = {
    IngestionState.ACTIVE: StateConfig(label="Active", color=DARK.info, icon="●"),
    IngestionState.IDLE: StateConfig(label="Idle", color=DARK.text_muted, icon="○"),
    IngestionState.CONFIGURED: StateConfig(label="Configured", color=DARK.info, icon="○"),
    IngestionState.NOT_STARTED: StateConfig(label="Not Started", color=DARK.text_muted, icon="○"),
    IngestionState.STOPPED: StateConfig(label="Stopped", color=DARK.warning, icon="○"),
}


def get_ingestion_state(running: bool, sources_count: int, shutdown_flag: bool) -> str:
    """Determine ingestion state from stats."""
    if shutdown_flag:
        return IngestionState.STOPPED
    if running and sources_count > 0:
        return IngestionState.ACTIVE
    if sources_count > 0:
        return IngestionState.CONFIGURED
    return IngestionState.NOT_STARTED


# ─────────────────────────────────────────────────────────────────────────────
# GOVERNANCE STATES
# ─────────────────────────────────────────────────────────────────────────────
class GovernanceState:
    OK = "ok"
    LIMITED = "limited"
    HALTED = "halted"


GOVERNANCE_STATES: Dict[str, StateConfig] = {
    GovernanceState.OK: StateConfig(label="OK", color=DARK.success, icon="✓"),
    GovernanceState.LIMITED: StateConfig(label="Limited", color=DARK.warning, icon="⚠"),
    GovernanceState.HALTED: StateConfig(label="Halted", color=DARK.sev_critical, icon="🛑"),
}


def get_governance_state(shutdown_flag: bool, has_permission: bool) -> str:
    """Determine governance state from stats."""
    if shutdown_flag:
        return GovernanceState.HALTED
    if not has_permission:
        return GovernanceState.LIMITED
    return GovernanceState.OK


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: Format with source count
# ─────────────────────────────────────────────────────────────────────────────
def format_ingestion_label(state: str, sources_count: int) -> str:
    """Format ingestion label with optional source count."""
    config = INGESTION_STATES.get(state, INGESTION_STATES[IngestionState.NOT_STARTED])
    if sources_count > 0 and state in (IngestionState.ACTIVE, IngestionState.IDLE):
        return f"{config.label} ({sources_count})"
    return config.label
