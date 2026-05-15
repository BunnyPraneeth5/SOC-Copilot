"""Network safety helpers for SOC Copilot."""

from __future__ import annotations

import os
from ipaddress import ip_address


TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment flag with conservative defaults."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def is_external_ip(value: str | None) -> bool:
    """Return True only for valid, globally routable IP addresses.

    Private, loopback, link-local, multicast, reserved, documentation, and
    malformed addresses are treated as non-external.
    """
    if not value:
        return False

    try:
        addr = ip_address(value.strip())
    except ValueError:
        return False

    return addr.is_global and not addr.is_multicast


def online_enrichment_enabled() -> bool:
    """Whether optional online threat-intelligence enrichment may run."""
    return env_flag("SOC_COPILOT_ENABLE_ONLINE_ENRICHMENT", default=False)
