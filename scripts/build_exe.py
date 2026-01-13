#!/usr/bin/env python3
"""
SOC Copilot Build Script
========================

Builds the SOC Copilot desktop application using PyInstaller.

Usage:
    python scripts/build_exe.py           # Full build
    python scripts/build_exe.py --clean   # Clean build (removes previous)
    python scripts/build_exe.py --dry-run # Validate only, no build

Output:
    dist/SOC Copilot/SOC Copilot.exe

Requirements:
    pip install pyinstaller>=6.0.0
"""

import os
import sys
import shutil
import subprocess
import argparse
from pathlib import Path


def get_project_root() -> Path:
    """Get project root directory"""
    return Path(__file__).parent.parent


def check_requirements(project_root: Path) -> bool:
    """Verify build requirements are met"""
    print("Checking build requirements...")
    
    errors = []
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"  ✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        errors.append("PyInstaller not installed. Run: pip install pyinstaller>=6.0.0")
    
    # Check spec file
    spec_file = project_root / "soc_copilot.spec"
    if spec_file.exists():
        print(f"  ✓ Spec file found: {spec_file.name}")
    else:
        errors.append(f"Spec file not found: {spec_file}")
    
    # Check source
    src_dir = project_root / "src" / "soc_copilot"
    if src_dir.exists():
        print(f"  ✓ Source directory found")
    else:
        errors.append(f"Source not found: {src_dir}")
    
    # Check models
    models_dir = project_root / "data" / "models"
    required_models = [
        "isolation_forest_v1.joblib",
        "random_forest_v1.joblib",
        "feature_order.json",
        "label_map.json"
    ]
    
    if models_dir.exists():
        missing = [m for m in required_models if not (models_dir / m).exists()]
        if missing:
            errors.append(f"Missing models: {', '.join(missing)}")
        else:
            print(f"  ✓ All required models found")
    else:
        errors.append(f"Models directory not found: {models_dir}")
    
    # Check config
    config_dir = project_root / "config"
    if config_dir.exists():
        print(f"  ✓ Config directory found")
    else:
        errors.append(f"Config not found: {config_dir}")
    
    if errors:
        print("\n❌ Build requirements not met:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("\n✓ All requirements satisfied")
    return True


def clean_build(project_root: Path):
    """Remove previous build artifacts"""
    print("Cleaning previous build...")
    
    dirs_to_remove = [
        project_root / "build",
        project_root / "dist",
    ]
    
    for dir_path in dirs_to_remove:
        if dir_path.exists():
            print(f"  Removing {dir_path}")
            shutil.rmtree(dir_path)
    
    print("  ✓ Clean complete")


def run_pyinstaller(project_root: Path) -> bool:
    """Run PyInstaller with spec file"""
    print("\nBuilding executable...")
    
    spec_file = project_root / "soc_copilot.spec"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file)
    ]
    
    print(f"  Command: {' '.join(cmd)}")
    print("-" * 60)
    
    result = subprocess.run(
        cmd,
        cwd=str(project_root),
        capture_output=False
    )
    
    print("-" * 60)
    
    if result.returncode != 0:
        print(f"\n❌ Build failed with exit code {result.returncode}")
        return False
    
    return True


def verify_build(project_root: Path) -> bool:
    """Verify the build output"""
    print("\nVerifying build output...")
    
    dist_dir = project_root / "dist" / "SOC Copilot"
    exe_path = dist_dir / "SOC Copilot.exe"
    
    if not dist_dir.exists():
        print(f"  ❌ Distribution directory not found: {dist_dir}")
        return False
    
    if not exe_path.exists():
        print(f"  ❌ Executable not found: {exe_path}")
        return False
    
    # Check file size
    exe_size = exe_path.stat().st_size / (1024 * 1024)  # MB
    print(f"  ✓ Executable: {exe_path.name} ({exe_size:.1f} MB)")
    
    # Check bundled files
    config_bundled = (dist_dir / "config").exists()
    models_bundled = (dist_dir / "data" / "models").exists()
    
    print(f"  ✓ Config bundled: {config_bundled}")
    print(f"  ✓ Models bundled: {models_bundled}")
    
    # Calculate total distribution size
    total_size = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file())
    total_size_mb = total_size / (1024 * 1024)
    print(f"  ✓ Total distribution size: {total_size_mb:.1f} MB")
    
    return True


def create_version_file(project_root: Path):
    """Create a version info file in the dist"""
    print("\nCreating version file...")
    
    version_content = """SOC Copilot Desktop Application
Version: 0.1.0
Build Date: {date}
Platform: Windows x64

Features:
- Hybrid ML Detection (Isolation Forest + Random Forest)
- Real-time Log Ingestion
- Offline Operation
- Governance Controls

© 2026 SOC Copilot Team
MIT License
"""
    
    from datetime import datetime
    content = version_content.format(date=datetime.now().strftime("%Y-%m-%d"))
    
    dist_dir = project_root / "dist" / "SOC Copilot"
    version_file = dist_dir / "VERSION.txt"
    
    if dist_dir.exists():
        version_file.write_text(content)
        print(f"  ✓ Created {version_file.name}")


def main():
    parser = argparse.ArgumentParser(description="Build SOC Copilot executable")
    parser.add_argument("--clean", action="store_true", help="Clean build (remove previous)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no build")
    args = parser.parse_args()
    
    project_root = get_project_root()
    print(f"SOC Copilot Build Script")
    print(f"Project root: {project_root}")
    print("=" * 60)
    
    # Check requirements
    if not check_requirements(project_root):
        sys.exit(1)
    
    if args.dry_run:
        print("\n✓ Dry run complete - all requirements satisfied")
        sys.exit(0)
    
    # Clean if requested
    if args.clean:
        clean_build(project_root)
    
    # Build
    if not run_pyinstaller(project_root):
        sys.exit(1)
    
    # Verify
    if not verify_build(project_root):
        sys.exit(1)
    
    # Create version file
    create_version_file(project_root)
    
    print("\n" + "=" * 60)
    print("✓ BUILD SUCCESSFUL")
    print("=" * 60)
    print(f"\nExecutable: {project_root / 'dist' / 'SOC Copilot' / 'SOC Copilot.exe'}")
    print("\nTo test: Run the executable directly")
    print("To package: Run scripts/build_installer.py (if available)")


if __name__ == "__main__":
    main()
