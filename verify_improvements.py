#!/usr/bin/env python3
"""Verification script for SOC Copilot production readiness improvements"""

import sys
import tempfile
import time
from pathlib import Path

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    try:
        from soc_copilot.phase4.ingestion.controller import IngestionController
        from soc_copilot.phase4.ingestion.watcher import FileTailer, DirectoryWatcher
        from soc_copilot.phase4.controller.app_controller import AppController
        print("[OK] All ingestion modules imported successfully")
        return True
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        return False

def test_ingestion_robustness():
    """Test ingestion robustness improvements"""
    print("Testing ingestion robustness...")
    
    try:
        from soc_copilot.phase4.ingestion.controller import IngestionController
        
        # Test IngestionController validation
        controller = IngestionController(batch_interval=0.1)
        
        # Test file validation
        result = controller.add_file_source("/non/existent/file.log")
        if result:
            print("[ERROR] Should reject non-existent file")
            return False
        
        # Test directory validation  
        result = controller.add_directory_source("/non/existent/dir")
        if result:
            print("[ERROR] Should reject non-existent directory")
            return False
        
        # Test with valid directory
        with tempfile.TemporaryDirectory() as temp_dir:
            result = controller.add_directory_source(temp_dir)
            if not result:
                print("[ERROR] Should accept existing directory")
                return False
        
        print("[OK] Ingestion validation works correctly")
        return True
        
    except Exception as e:
        print(f"[ERROR] Ingestion test failed: {e}")
        return False

def test_watcher_stats():
    """Test watcher statistics functionality"""
    print("Testing watcher statistics...")
    
    try:
        from soc_copilot.phase4.ingestion.watcher import DirectoryWatcher
        
        with tempfile.TemporaryDirectory() as temp_dir:
            watcher = DirectoryWatcher(temp_dir, lambda x: None)
            stats = watcher.get_stats()
            
            expected_keys = ["directory", "pattern", "known_files", "active_tailers", "error_count", "running"]
            for key in expected_keys:
                if key not in stats:
                    print(f"[ERROR] Missing stat key: {key}")
                    return False
            
            print("[OK] Watcher statistics working correctly")
            return True
            
    except Exception as e:
        print(f"[ERROR] Watcher stats test failed: {e}")
        return False

def test_ui_imports():
    """Test UI module imports"""
    print("Testing UI imports...")
    
    try:
        # Mock PyQt6 for testing
        import sys
        from unittest.mock import Mock
        
        # Only mock if not already available
        if 'PyQt6' not in sys.modules:
            sys.modules['PyQt6'] = Mock()
            sys.modules['PyQt6.QtWidgets'] = Mock()
            sys.modules['PyQt6.QtCore'] = Mock()
            sys.modules['PyQt6.QtGui'] = Mock()
        
        from soc_copilot.phase4.ui.dashboard import Dashboard
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        
        print("[OK] UI modules imported successfully")
        return True
        
    except ImportError as e:
        print(f"[ERROR] UI import failed: {e}")
        return False

def test_main_entry_point():
    """Test main entry point"""
    print("Testing main entry point...")
    
    try:
        from soc_copilot.main import main
        print("[OK] Main entry point accessible")
        return True
        
    except ImportError as e:
        print(f"[ERROR] Main entry point failed: {e}")
        return False

def main():
    """Run all verification tests"""
    print("SOC Copilot Production Readiness Verification")
    print("=" * 50)
    
    tests = [
        ("Module Imports", test_imports),
        ("Ingestion Robustness", test_ingestion_robustness),
        ("Watcher Statistics", test_watcher_stats),
        ("UI Imports", test_ui_imports),
        ("Main Entry Point", test_main_entry_point)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"[ERROR] {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 50)
    print("VERIFICATION SUMMARY")
    print("=" * 50)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\nAll verification tests passed!")
        print("Production readiness improvements are working correctly.")
    else:
        print("\nSome verification tests failed.")
        print("Please check the implementation.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())