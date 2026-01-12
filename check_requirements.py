#!/usr/bin/env python3
"""System requirements checker for SOC Copilot"""

import sys
import platform
import subprocess
from pathlib import Path


def check_system_requirements():
    """Check system requirements"""
    print("System Requirements Check")
    print("=" * 40)
    
    # Operating System
    os_name = platform.system()
    print(f"Operating System: {os_name} {platform.release()}")
    
    if os_name not in ["Windows", "Linux", "Darwin"]:
        print("[WARNING] Untested operating system")
    else:
        print("[OK] Supported operating system")
    
    # Python version
    python_version = sys.version_info
    print(f"Python Version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 10):
        print("[ERROR] Python 3.10+ required")
        return False
    else:
        print("[OK] Python version compatible")
    
    # Memory
    try:
        import psutil
        memory_gb = psutil.virtual_memory().total / (1024**3)
        print(f"Available Memory: {memory_gb:.1f} GB")
        
        if memory_gb < 4:
            print("[WARNING] Less than 4GB RAM may cause performance issues")
        else:
            print("[OK] Sufficient memory")
    except ImportError:
        print("? Memory check skipped (psutil not available)")
    
    return True


def check_dependencies():
    """Check if all dependencies can be imported"""
    print("\nDependency Check")
    print("=" * 40)
    
    required_packages = [
        ("scikit-learn", "sklearn"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("PyQt6", "PyQt6.QtWidgets"),
        ("pydantic", "pydantic"),
        ("pyyaml", "yaml"),
        ("structlog", "structlog"),
        ("joblib", "joblib")
    ]
    
    missing_packages = []
    
    for package_name, import_name in required_packages:
        try:
            __import__(import_name)
            print(f"[OK] {package_name}")
        except ImportError:
            print(f"[ERROR] {package_name} - Missing")
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"\nMissing packages: {', '.join(missing_packages)}")
        print("Run: pip install -e .")
        return False
    
    return True


def check_file_structure():
    """Check if required files and directories exist"""
    print("\nFile Structure Check")
    print("=" * 40)
    
    required_paths = [
        ("src/soc_copilot", "Source code directory"),
        ("config", "Configuration directory"),
        ("data", "Data directory"),
        ("tests", "Tests directory"),
        ("pyproject.toml", "Project configuration"),
        ("launch_ui.py", "UI launcher")
    ]
    
    missing_paths = []
    
    for path_str, description in required_paths:
        path = Path(path_str)
        if path.exists():
            print(f"[OK] {description}: {path_str}")
        else:
            print(f"[ERROR] {description}: {path_str} - Missing")
            missing_paths.append(path_str)
    
    return len(missing_paths) == 0


def check_models():
    """Check if trained models are available"""
    print("\nModel Check")
    print("=" * 40)
    
    models_dir = Path("data/models")
    if not models_dir.exists():
        print("[ERROR] Models directory missing")
        return False
    
    required_models = [
        "isolation_forest_v1.joblib",
        "random_forest_v1.joblib",
        "feature_order.json",
        "label_map.json"
    ]
    
    missing_models = []
    
    for model_file in required_models:
        model_path = models_dir / model_file
        if model_path.exists():
            print(f"[OK] {model_file}")
        else:
            print(f"[ERROR] {model_file} - Missing")
            missing_models.append(model_file)
    
    if missing_models:
        print("\nTo train models, run: python scripts/train_models.py")
        return False
    
    return True


def check_permissions():
    """Check file permissions"""
    print("\nPermissions Check")
    print("=" * 40)
    
    test_paths = [
        ("data", "Data directory write access"),
        ("logs", "Logs directory write access"),
        (".", "Current directory write access")
    ]
    
    for path_str, description in test_paths:
        path = Path(path_str)
        if path.exists() and os.access(path, os.W_OK):
            print(f"[OK] {description}")
        else:
            print(f"[ERROR] {description} - No write permission")
            return False
    
    return True


def main():
    """Main check function"""
    print("SOC Copilot Production Readiness Check")
    print("=" * 50)
    
    checks = [
        ("System Requirements", check_system_requirements),
        ("Dependencies", check_dependencies),
        ("File Structure", check_file_structure),
        ("Permissions", check_permissions),
        ("Models", check_models)
    ]
    
    results = {}
    
    for check_name, check_func in checks:
        try:
            results[check_name] = check_func()
        except Exception as e:
            print(f"Error during {check_name} check: {e}")
            results[check_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    all_passed = True
    for check_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{check_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\nAll checks passed! SOC Copilot is ready to run.")
        print("Launch with: python launch_ui.py")
    else:
        print("\nSome checks failed. Please address the issues above.")
        print("For help, see README.md or run: python setup.py")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    import os
    sys.exit(main())