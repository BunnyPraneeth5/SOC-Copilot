# AGENTS.md

## Environment
- Python 3.12 virtualenv at `venv/` (use `venv/Scripts/python.exe` on Windows).
- Install: `pip install -e ".[dev]"` (all runtime deps are declared in `pyproject.toml`; keep `requirements.txt` in sync).

## Tests
- Full suite (~2 min): `QT_QPA_PLATFORM=offscreen venv/Scripts/python.exe -m pytest tests/ -q -o addopts=""`
- `tests/conftest.py` strips `SOC_COPILOT_*` env vars per test; don't rely on `.env` in tests.
- Integration tests in `tests/integration/test_pipeline.py` use the local trained models in `data/models/` (gitignored); they need a valid `data/models/model_hashes.json`.

## Conventions
- Alert priority labels everywhere use the ML enum values: `P0-Critical`, `P1-High`, `P2-Medium`, `P3-Low`, `P4-Info`.
- `phase4/controller/app_controller.py` must not import from `soc_copilot.models` (enforced by `test_no_phase_coupling`).
- Training scripts update `data/models/model_hashes.json` via `update_manifest`; the manifest is generated locally, not committed.
