"""Training label mapping: CICIDS2017 web-attack labels with broken dashes.

The raw labels read "Web Attack \\ufffd Brute Force" (or with 0x96); before
the fix they matched no mapping and were trained as an "Unknown" class.
"""

import pandas as pd
import pytest

from soc_copilot.models.training.data_loader import (
    SOC_LABELS,
    TrainingDataLoader,
    normalize_label,
)

# Every label in the CICIDS2017 MachineLearningCSV files, as stored
CICIDS2017_LABELS = [
    "BENIGN", "Bot", "DDoS", "DoS GoldenEye", "DoS Hulk", "DoS Slowhttptest",
    "DoS slowloris", "FTP-Patator", "Heartbleed", "Infiltration", "PortScan",
    "SSH-Patator", "Web Attack � Brute Force", "Web Attack � XSS",
    "Web Attack � Sql Injection",
]


def _map(labels):
    df = pd.DataFrame({"label_raw": labels})
    df = df.rename(columns={"label_raw": "Label"})
    df.columns = df.columns.str.lower()
    return list(TrainingDataLoader()._map_labels(df)["label"])


@pytest.mark.parametrize("raw", [
    "Web Attack � Brute Force",
    "Web Attack \x96 Brute Force",
    "Web Attack – Brute Force",
    " Web Attack  -  Brute Force ",
])
def test_broken_dashes_normalize(raw):
    assert normalize_label(raw) == "Web Attack - Brute Force"


def test_plain_labels_unchanged():
    assert normalize_label("  DoS Hulk ") == "DoS Hulk"
    assert normalize_label("SSH-Patator") == "SSH-Patator"


def test_web_attacks_map_to_bruteforce():
    mapped = _map(["Web Attack � Brute Force", "Web Attack � XSS",
                   "Web Attack � Sql Injection"])
    assert mapped == ["BruteForce"] * 3


def test_every_cicids2017_label_maps_into_taxonomy():
    mapped = _map(CICIDS2017_LABELS)
    assert "Unknown" not in mapped
    assert set(mapped) <= set(SOC_LABELS)


def test_unmapped_label_still_unknown():
    assert _map(["Something New"]) == ["Unknown"]
