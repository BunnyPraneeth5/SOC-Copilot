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
    """Check if all dependencies can be imported with detailed feedback"""
    print("\nDependency Check")
    print("=" * 40)
    
    required_packages = [
        ("scikit-learn", "sklearn", "Machine learning library"),
        ("numpy", "numpy", "Numerical computing"),
        ("pandas", "pandas", "Data processing"),
        ("PyQt6", "PyQt6.QtWidgets", "GUI framework"),
        ("pydantic", "pydantic", "Data validation"),
        ("pyyaml", "yaml", "YAML configuration"),
        ("structlog", "structlog", "Structured logging"),
        ("joblib", "joblib", "Model serialization"),
        ("python-dateutil", "dateutil", "Date parsing"),
        ("python-evtx", "Evtx", "Windows event log parsing")
    ]
    
    missing_packages = []
    optional_missing = []
    
    for package_name, import_name, description in required_packages:
        try:
            __import__(import_name)
            print(f"[OK] {package_name} - {description}")
        except ImportError:
            if package_name in ["python-evtx"]:
                print(f"[OPTIONAL] {package_name} - {description} (Windows only)")
                optional_missing.append(package_name)
            else:
                print(f"[ERROR] {package_name} - {description} - Missing")
                missing_packages.append(package_name)
    
    # Check optional system packages
    try:
        import psutil
        print("[OK] psutil - System monitoring (optional)")
    except ImportError:
        print("[OPTIONAL] psutil - System monitoring (recommended)")
        optional_missing.append("psutil")
    
    if missing_packages:
        print(f"\nCritical missing packages: {', '.join(missing_packages)}")
        print("Run: pip install -e .")
        return False
    
    if optional_missing:
        print(f"\nOptional packages missing: {', '.join(optional_missing)}")
        print("These are not required but may improve functionality.")
    
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
    """Check if trained models are available with detailed status"""
    print("\nModel Check")
    print("=" * 40)
    
    models_dir = Path("data/models")
    if not models_dir.exists():
        print("[ERROR] Models directory missing")
        print(f"Expected: {models_dir.absolute()}")
        print("Run: mkdir -p data/models")
        return False
    
    required_models = [
        ("isolation_forest_v1.joblib", "Isolation Forest anomaly detection model"),
        ("random_forest_v1.joblib", "Random Forest classification model"),
        ("feature_order.json", "Feature ordering configuration"),
        ("label_map.json", "Attack type label mapping")
    ]
    
    missing_models = []
    
    for model_file, description in required_models:
        model_path = models_dir / model_file
        if model_path.exists():
            # Check file size
            size_mb = model_path.stat().st_size / (1024 * 1024)
            print(f"[OK] {model_file} - {description} ({size_mb:.1f}MB)")
        else:
            print(f"[ERROR] {model_file} - {description} - Missing")
            missing_models.append(model_file)
    
    if missing_models:
        print("\nTo train models:")
        print("1. python scripts/train_models.py")
        print("2. Wait for training to complete (may take several minutes)")
        print("3. Re-run this check")
        return False
    
    print("\n[SUCCESS] All models are available and ready!")
    return True


def check_configuration():
    """Check configuration files and settings"""
    print("\nConfiguration Check")
    print("=" * 40)
    
    config_files = [
        ("config/thresholds.yaml", "Alert thresholds"),
        ("config/features.yaml", "Feature definitions"),
        ("config/model_config.yaml", "Model parameters"),
        ("config/ingestion/system_logs.yaml", "Log ingestion settings"),
        ("config/governance/policy.yaml", "Governance policies")
    ]
    
    missing_configs = []
    
    for config_path, description in config_files:
        path = Path(config_path)
        if path.exists():
            print(f"[OK] {description}: {config_path}")
        else:
            print(f"[ERROR] {description}: {config_path} - Missing")
            missing_configs.append(config_path)
    
    return len(missing_configs) == 0


def check_system_log_permissions():
    """Check system log access permissions"""
    print("\nSystem Log Permissions Check")
    print("=" * 40)
    
    try:
        from soc_copilot.phase4.ingestion.system_log_reader import SystemLogReader
        
        reader = SystemLogReader()
        result = reader.validate_system_log_access()
        
        if result.has_permission:
            print("[OK] System log access available")
            return True
        else:
            print(f"[OPTIONAL] System log access limited: {result.error_message}")
            if result.requires_elevation:
                if reader.os_type == "Windows":
                    print("  To enable: Run as Administrator")
                elif reader.os_type == "Linux":
                    print("  To enable: Run with sudo or add user to appropriate group")
            print("  Impact: System log ingestion will not be available")
            print("  Note: Application can still run with file-based log ingestion")
            return False
    
    except ImportError:
        print("[SKIP] System log reader not available")
        return False
    except Exception as e:
        print(f"[ERROR] Permission check failed: {e}")
        return False


def check_permissions():
    """Check file permissions and write access"""
    print("\nPermissions Check")
    print("=" * 40)
    
    test_paths = [
        ("data", "Data directory write access"),
        ("logs", "Logs directory write access"),
        (".", "Current directory write access")
    ]
    
    permission_issues = []
    
    for path_str, description in test_paths:
        path = Path(path_str)
        try:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_file = path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            
            print(f"[OK] {description}")
        except (OSError, PermissionError) as e:
            print(f"[ERROR] {description} - {e}")
            permission_issues.append(path_str)
    
    return len(permission_issues) == 0


def main():
    """Main check function with comprehensive validation"""
    print("SOC Copilot Production Readiness Check")
    print("=" * 50)
    
    checks = [
        ("System Requirements", check_system_requirements),
        ("Dependencies", check_dependencies),
        ("File Structure", check_file_structure),
        ("Configuration", check_configuration),
        ("Permissions", check_permissions),
        ("System Log Permissions", check_system_log_permissions),
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
    
    critical_checks = ["System Requirements", "Dependencies", "File Structure", "Permissions"]
    optional_checks = ["Configuration", "Models", "System Log Permissions"]
    
    critical_passed = all(results.get(check, False) for check in critical_checks)
    optional_passed = all(results.get(check, False) for check in optional_checks)
    
    for check_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        check_type = "[CRITICAL]" if check_name in critical_checks else "[OPTIONAL]"
        print(f"{check_name}: {status} {check_type}")
    
    print("\n" + "=" * 50)
    
    if critical_passed and optional_passed:
        print("ALL CHECKS PASSED! SOC Copilot is ready for production use.")
        print("\nLaunch with: python launch_ui.py")
        return 0
    elif critical_passed:
        print("CRITICAL CHECKS PASSED. SOC Copilot can run with limited functionality.")
        print("\nTo enable full functionality:")
        if not results.get("Models", False):
            print("- Train models: python scripts/train_models.py")
        if not results.get("Configuration", False):
            print("- Check configuration files in config/ directory")
        print("\nLaunch with: python launch_ui.py")
        return 0
    else:
        print("CRITICAL CHECKS FAILED. Please address the issues above.")
        print("\nFor help:")
        print("- Run setup: python setup.py")
        print("- See README.md for troubleshooting")
        return 1


if __name__ == "__main__":
    import os
    sys.exit(main())