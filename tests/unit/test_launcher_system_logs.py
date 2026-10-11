"""Launcher: system log exporters follow config/ingestion/system_logs.yaml.

The exporters used to start whenever the app had admin rights, even with
ingestion disabled in config, so nothing read what they wrote.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from launch_ui import system_log_ingestion_enabled  # noqa: E402


def _project(tmp_path, text=None):
    if text is not None:
        cfg = tmp_path / "config" / "ingestion"
        cfg.mkdir(parents=True)
        (cfg / "system_logs.yaml").write_text(text, encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("text,expected", [
    ("enabled: true\nexport_interval: 5\n", True),
    ("enabled: false\nexport_interval: 5\n", False),
    ("export_interval: 5\n", False),  # not set -> off
    ("", False),
    ("enabled: [unclosed\n", False),  # unreadable -> off
])
def test_reads_enabled_flag(tmp_path, text, expected):
    assert system_log_ingestion_enabled(_project(tmp_path, text)) is expected


def test_missing_config_means_disabled(tmp_path):
    assert system_log_ingestion_enabled(_project(tmp_path)) is False


def test_repo_config_is_readable():
    root = Path(__file__).resolve().parents[2]
    assert isinstance(system_log_ingestion_enabled(root), bool)
