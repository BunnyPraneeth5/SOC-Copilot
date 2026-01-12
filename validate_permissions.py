#!/usr/bin/env python3
"""Validate file permissions in SOC Copilot installation"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from soc_copilot.security import validate_permissions


def main():
    """Validate permissions on critical files"""
    print("SOC Copilot Permission Validation")
    print("=" * 50)
    
    # Define critical paths to check
    paths_to_check = [
        ("data", True),
        ("data/models", True),
        ("logs", True),
        ("data/models/isolation_forest_v1.joblib", False),
        ("data/models/random_forest_v1.joblib", False),
        ("data/models/feature_order.json", False),
        ("data/models/label_map.json", False),
    ]
    
    issues = []
    
    for path_str, is_dir in paths_to_check:
        path = project_root / path_str
        
        if not path.exists():
            print(f"[SKIP] {path_str} - does not exist")
            continue
        
        status = validate_permissions(path)
        
        if status.error:
            print(f"[ERROR] {path_str} - {status.error}")
            issues.append(path_str)
        elif status.is_secure:
            mode_str = oct(status.current_mode)
            print(f"[OK] {path_str} - {mode_str}")
        else:
            current = oct(status.current_mode)
            expected = oct(status.expected_mode)
            print(f"[WARN] {path_str} - {current} (expected {expected})")
            issues.append(path_str)
    
    print("\n" + "=" * 50)
    
    if issues:
        print(f"Found {len(issues)} permission issues")
        print("\nTo fix permissions on Unix-like systems:")
        print("  chmod 700 data/ data/models/ logs/")
        print("  chmod 600 data/models/*.joblib data/models/*.json")
        print("\nNote: Windows uses best-effort permissions")
        return 1
    else:
        print("All checked paths have secure permissions")
        return 0


if __name__ == "__main__":
    sys.exit(main())
