#!/usr/bin/env python3
"""Setup script for SOC Copilot installation and verification"""

import os
import sys
import subprocess
from pathlib import Path


def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 10):
        print("Error: Python 3.10 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"[OK] Python version: {sys.version.split()[0]}")
    return True


def install_dependencies():
    """Install project dependencies"""
    print("Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], 
                      check=True, capture_output=True, text=True)
        print("[OK] Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        print(f"Output: {e.stdout}")
        print(f"Error: {e.stderr}")
        return False


def create_directories():
    """Create necessary directories"""
    dirs = [
        "data/models",
        "data/logs", 
        "logs/system",
        "data/drift",
        "data/feedback",
        "data/governance"
    ]
    
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"[OK] Created directory: {dir_path}")


def check_models():
    """Check if trained models exist"""
    models_dir = Path("data/models")
    required_files = [
        "isolation_forest_v1.joblib",
        "random_forest_v1.joblib", 
        "feature_order.json",
        "label_map.json"
    ]
    
    missing_files = []
    for file in required_files:
        if not (models_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("[WARNING] Missing trained models:")
        for file in missing_files:
            print(f"  - {file}")
        print("Run 'python scripts/train_models.py' to train models")
        return False
    else:
        print("[OK] All trained models found")
        return True


def verify_installation():
    """Verify installation by importing key modules"""
    print("Verifying installation...")
    try:
        import soc_copilot
        from soc_copilot.pipeline import create_soc_copilot
        from PyQt6.QtWidgets import QApplication
        print("[OK] All modules imported successfully")
        return True
    except ImportError as e:
        print(f"Error importing modules: {e}")
        return False


def main():
    """Main setup function"""
    print("SOC Copilot Setup")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Install dependencies
    if not install_dependencies():
        print("Setup failed during dependency installation")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        print("Setup failed during verification")
        sys.exit(1)
    
    # Check models
    models_exist = check_models()
    
    print("\n" + "=" * 50)
    print("Setup completed successfully!")
    print("\nNext steps:")
    
    if not models_exist:
        print("1. Train models: python scripts/train_models.py")
        print("2. Launch UI: python launch_ui.py")
    else:
        print("1. Launch UI: python launch_ui.py")
        print("2. Or use CLI: soc-copilot")
    
    print("\nFor more information, see README.md")


if __name__ == "__main__":
    main()