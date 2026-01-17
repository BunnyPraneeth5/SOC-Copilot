# -*- mode: python ; coding: utf-8 -*-
"""
SOC Copilot PyInstaller Specification
=====================================

This spec file configures PyInstaller to create a standalone Windows executable
for SOC Copilot. The application is bundled as a folder (not single-file) for
faster startup and easier debugging.

Usage:
    pyinstaller soc_copilot.spec

Output:
    dist/SOC Copilot/SOC Copilot.exe
"""

# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

project_root = Path(SPECPATH)
src_path = project_root / 'src'
config_path = project_root / 'config'
models_path = project_root / 'data' / 'models'
assets_path = project_root / 'assets'

a = Analysis(
    ['launch_ui.py'],
    pathex=[str(project_root)],  # FIXED
    binaries=[],
    datas=[
        (str(config_path), 'config'),
        (str(models_path), 'data/models'),
        (str(assets_path), 'assets'),
    ],
    hiddenimports=[
        # PyQt6
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',

        # ML stack
        'sklearn',
        'sklearn.ensemble',
        'sklearn.tree',
        'sklearn.neighbors',
        'sklearn.preprocessing',
        'sklearn.utils',
        'numpy',
        'pandas',
        'joblib',

        # Config & logging
        'yaml',
        'pydantic',
        'pydantic_settings',
        'structlog',

        # Windows Event Logs
        'Evtx',

        # SOC Copilot
        'soc_copilot',
        'soc_copilot.pipeline',
        'soc_copilot.phase2',
        'soc_copilot.phase3',
        'soc_copilot.phase4',
        'soc_copilot.phase4.ui',
        'soc_copilot.phase4.controller',
        'soc_copilot.phase4.ingestion',
    ],
    excludes=[
        'pytest',
        'black',
        'ruff',
        'mypy',
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SOC Copilot',
    console=False,
    icon=str(assets_path / 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='SOC Copilot',
)
