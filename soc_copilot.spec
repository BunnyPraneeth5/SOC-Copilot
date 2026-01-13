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

import os
from pathlib import Path

# Get project root directory
project_root = Path(SPECPATH)

# Define paths
src_path = project_root / 'src'
config_path = project_root / 'config'
models_path = project_root / 'data' / 'models'
assets_path = project_root / 'assets'

# Analysis configuration
a = Analysis(
    ['launch_ui.py'],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        # Configuration files (read-only, bundled)
        (str(config_path), 'config'),
        
        # Pre-trained ML models
        (str(models_path), 'data/models'),
        
        # Assets (icons, etc.) - if directory exists
        (str(assets_path), 'assets') if assets_path.exists() else None,
    ],
    hiddenimports=[
        # PyQt6 modules
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        
        # ML/Data science
        'sklearn',
        'sklearn.ensemble',
        'sklearn.neighbors',
        'sklearn.tree',
        'sklearn.utils',
        'sklearn.preprocessing',
        'numpy',
        'pandas',
        'joblib',
        
        # Configuration
        'pydantic',
        'pydantic_settings',
        'yaml',
        'pyyaml',
        
        # Logging
        'structlog',
        
        # Windows event log parsing
        'Evtx',
        
        # SOC Copilot modules
        'soc_copilot',
        'soc_copilot.core',
        'soc_copilot.core.config',
        'soc_copilot.core.logging',
        'soc_copilot.data',
        'soc_copilot.models',
        'soc_copilot.phase2',
        'soc_copilot.phase3',
        'soc_copilot.phase4',
        'soc_copilot.phase4.ui',
        'soc_copilot.phase4.controller',
        'soc_copilot.phase4.ingestion',
        'soc_copilot.pipeline',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude dev dependencies
        'pytest',
        'black',
        'ruff',
        'mypy',
        'pre_commit',
        
        # Exclude unnecessary modules
        'tkinter',
        'matplotlib',
        'IPython',
        'jupyter',
    ],
    noarchive=False,
    optimize=0,
)

# Filter out None entries from datas
a.datas = [d for d in a.datas if d is not None]

# Create PYZ archive
pyz = PYZ(a.pure)

# Create executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SOC Copilot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI application, no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(assets_path / 'icon.ico') if (assets_path / 'icon.ico').exists() else None,
    version_file=None,  # Can add version info later
)

# Collect all files into distribution folder
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SOC Copilot',
)
