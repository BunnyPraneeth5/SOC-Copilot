"""Centralized UI state definitions for consistent display across all components.

This module provides a single source of truth for:
- Pipeline states (Active, Loading, Inactive)
- Ingestion states (Active, Idle, Configured, Not Started, Stopped)
- Governance states (OK, Limited, Halted)
"""

from dataclasses import dataclass
from typing import Dict

from .theme import color


@dataclass
class StateConfig:
    """Configuration for a UI state display.

    ``color`` holds a palette *token name*; it is resolved to the
    current palette's hex value when read through ``_StateMap``.
    """
    label: str
    color: str
    icon: str = "●"


class _StateMap(dict):
    """State map whose entries resolve token names to live palette colors."""

    def __getitem__(self, key):
        cfg = super().__getitem__(key)
        return StateConfig(label=cfg.label, color=color(cfg.color), icon=cfg.icon)

    def get(self, key, default=None):
        return self[key] if key in self else default

    def items(self):
        return ((k, self[k]) for k in self.keys())

    def values(self):
        return (self[k] for k in self.keys())


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE STATES
# ─────────────────────────────────────────────────────────────────────────────
class PipelineState:
    ACTIVE = "active"
    LOADING = "loading"
    INACTIVE = "inactive"


PIPELINE_STATES: Dict[str, StateConfig] = _StateMap({
    PipelineState.ACTIVE: StateConfig(label="Active", color="success", icon="●"),
    PipelineState.LOADING: StateConfig(label="Loading...", color="sev_medium", icon="○"),
    PipelineState.INACTIVE: StateConfig(label="Inactive", color="sev_high", icon="○"),
})


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


INGESTION_STATES: Dict[str, StateConfig] = _StateMap({
    IngestionState.ACTIVE: StateConfig(label="Active", color="info", icon="●"),
    IngestionState.IDLE: StateConfig(label="Idle", color="text_muted", icon="○"),
    IngestionState.CONFIGURED: StateConfig(label="Configured", color="info", icon="○"),
    IngestionState.NOT_STARTED: StateConfig(label="Not Started", color="text_muted", icon="○"),
    IngestionState.STOPPED: StateConfig(label="Stopped", color="warning", icon="○"),
})


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


GOVERNANCE_STATES: Dict[str, StateConfig] = _StateMap({
    GovernanceState.OK: StateConfig(label="OK", color="success", icon="✓"),
    GovernanceState.LIMITED: StateConfig(label="Limited", color="warning", icon="⚠"),
    GovernanceState.HALTED: StateConfig(label="Halted", color="sev_critical", icon="🛑"),
})


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
