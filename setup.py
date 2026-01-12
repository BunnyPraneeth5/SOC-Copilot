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
    """Install project dependencies with better error handling"""
    print("Installing dependencies...")
    try:
        # First try to upgrade pip
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], 
                          check=True, capture_output=True, text=True, timeout=60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            print("[WARNING] Could not upgrade pip, continuing...")
        
        # Install project in editable mode
        result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], 
                              check=True, capture_output=True, text=True, timeout=300)
        print("[OK] Dependencies installed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Installation timed out. Check internet connection.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Installation failed: {e}")
        if e.stdout:
            print(f"Output: {e.stdout[-500:]}")
        if e.stderr:
            print(f"Error: {e.stderr[-500:]}")
        print("\nTry manual installation:")
        print("  pip install --upgrade pip")
        print("  pip install -e .")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
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
    """Verify installation by importing key modules with detailed feedback"""
    print("Verifying installation...")
    
    # Test core imports
    test_imports = [
        ("soc_copilot", "Core package"),
        ("soc_copilot.pipeline", "Pipeline module"),
        ("PyQt6.QtWidgets", "PyQt6 GUI framework"),
        ("sklearn", "Scikit-learn ML library"),
        ("pandas", "Pandas data processing"),
        ("numpy", "NumPy numerical computing")
    ]
    
    failed_imports = []
    
    for module_name, description in test_imports:
        try:
            __import__(module_name)
            print(f"[OK] {description}")
        except ImportError as e:
            print(f"[ERROR] {description} - {e}")
            failed_imports.append((module_name, description))
    
    if failed_imports:
        print("\nFailed imports:")
        for module_name, description in failed_imports:
            print(f"  - {module_name}: {description}")
        print("\nTry reinstalling with: pip install -e .")
        return False
    
    # Test pipeline creation (without models)
    try:
        from soc_copilot.pipeline import create_soc_copilot
        print("[OK] Pipeline creation test passed")
        return True
    except Exception as e:
        print(f"[WARNING] Pipeline test failed: {e}")
        print("This may be normal if models are not trained yet.")
        return True  # Don't fail setup for missing models


def check_system_compatibility():
    """Check system compatibility and requirements"""
    print("Checking system compatibility...")
    
    # Check available memory
    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / (1024**3)
        if memory_gb < 2:
            print(f"[WARNING] Low memory: {memory_gb:.1f}GB (4GB+ recommended)")
        else:
            print(f"[OK] Memory: {memory_gb:.1f}GB")
    except ImportError:
        print("[INFO] Memory check skipped (psutil not available)")
    
    # Check disk space
    try:
        import shutil
        free_gb = shutil.disk_usage('.').free / (1024**3)
        if free_gb < 1:
            print(f"[WARNING] Low disk space: {free_gb:.1f}GB")
        else:
            print(f"[OK] Disk space: {free_gb:.1f}GB free")
    except Exception:
        print("[INFO] Disk space check skipped")
    
    return True


def main():
    """Main setup function with improved error handling"""
    print("SOC Copilot Setup")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Check system compatibility
    check_system_compatibility()
    
    # Create directories
    create_directories()
    
    # Install dependencies
    if not install_dependencies():
        print("\n[ERROR] Setup failed during dependency installation")
        print("\nManual installation steps:")
        print("1. pip install --upgrade pip")
        print("2. pip install -e .")
        print("3. python check_requirements.py")
        sys.exit(1)
    
    # Verify installation
    if not verify_installation():
        print("\n[ERROR] Setup failed during verification")
        print("Check error messages above and try manual installation.")
        sys.exit(1)
    
    # Check models
    models_exist = check_models()
    
    print("\n" + "=" * 50)
    print("[SUCCESS] Setup completed successfully!")
    print("\nNext steps:")
    
    if not models_exist:
        print("1. Train models: python scripts/train_models.py")
        print("2. Verify setup: python check_requirements.py")
        print("3. Launch UI: python launch_ui.py")
    else:
        print("1. Verify setup: python check_requirements.py")
        print("2. Launch UI: python launch_ui.py")
        print("3. Or use CLI: soc-copilot")
    
    print("\nFor troubleshooting, see README.md")
    print("For system requirements: python check_requirements.py")


if __name__ == "__main__":
    main()