"""Alert export helpers (UX-6) — pure formatting, no Qt."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Iterable

EXPORT_FIELDS = [
    "timestamp", "priority", "status", "classification",
    "source_ip", "destination_ip", "confidence", "risk_score",
    "anomaly_score", "alert_id", "batch_id", "reasoning",
    "suggested_action",
]

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _csv_safe(value) -> str:
    """Stringify and neutralise spreadsheet formula injection."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.isoformat()
    else:
        value = str(value)
    if value and value[0] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


def alerts_to_csv(rows: Iterable[dict]) -> str:
    """Render alert row dicts as CSV (utf-8 text, header first)."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(
        buf, fieldnames=EXPORT_FIELDS, extrasaction="ignore",
        lineterminator="\r\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({f: _csv_safe(row.get(f)) for f in EXPORT_FIELDS})
    return buf.getvalue()


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def alerts_to_json(rows: Iterable[dict]) -> str:
    """Render alert row dicts as JSON (list of objects, indent 2)."""
    data = [
        {f: _json_safe(row.get(f)) for f in EXPORT_FIELDS}
        for row in rows
    ]
    return json.dumps(data, indent=2, default=str)
