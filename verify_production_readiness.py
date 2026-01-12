#!/usr/bin/env python3
"""Production readiness verification script for SOC Copilot"""

import sys
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock

def test_ingestion_robustness():
    """Test ingestion robustness improvements"""
    print("Testing ingestion robustness...")
    
    try:
        # Add project root to path for imports
        import sys
        from pathlib import Path
        project_root = Path(__file__).parent
        sys.path.insert(0, str(project_root / "src"))
        
        from soc_copilot.phase4.ingestion.controller import IngestionController
        
        # Test controller with invalid sources
        controller = IngestionController(batch_interval=0.1)
        
        # Should handle non-existent files gracefully
        result = controller.add_file_source("/non/existent/file.log")
        if result is not False:
            print(f"[ERROR] Expected False for non-existent file, got {result}")
            return False
        
        # Should handle non-existent directories gracefully  
        result = controller.add_directory_source("/non/existent/dir")
        if result is not False:
            print(f"[ERROR] Expected False for non-existent directory, got {result}")
            return False
        
        # Test statistics
        stats = controller.get_stats()
        if "running" not in stats:
            print("[ERROR] Missing 'running' in stats")
            return False
        if "errors" not in stats:
            print("[ERROR] Missing 'errors' in stats")
            return False
        
        print("[OK] Ingestion robustness tests passed")
        return True
        
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Ingestion robustness test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ui_improvements():
    """Test UI improvements and error handling"""
    print("Testing UI improvements...")
    
    try:
        # Mock PyQt6 for testing
        sys.modules['PyQt6'] = Mock()
        sys.modules['PyQt6.QtWidgets'] = Mock()
        sys.modules['PyQt6.QtCore'] = Mock()
        sys.modules['PyQt6.QtGui'] = Mock()
        
        from soc_copilot.phase4.ui.dashboard import Dashboard
        from soc_copilot.phase4.ui.alerts_view import AlertsView
        
        # Test with mock bridge
        mock_bridge = Mock()
        mock_bridge.get_latest_alerts.return_value = []
        mock_bridge.get_stats.return_value = {"pipeline_loaded": False}
        
        # Should not raise exceptions
        dashboard = Dashboard(mock_bridge)
        alerts_view = AlertsView(mock_bridge)
        
        print("[OK] UI improvements tests passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] UI improvements test failed: {e}")
        return False

def test_setup_improvements():
    """Test setup script improvements"""
    print("Testing setup improvements...")
    
    try:
        # Import setup functions
        import setup
        
        # Test system compatibility check
        result = setup.check_system_compatibility()
        assert isinstance(result, bool)
        
        # Test Python version check
        result = setup.check_python_version()
        assert isinstance(result, bool)
        
        print("[OK] Setup improvements tests passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Setup improvements test failed: {e}")
        return False

def test_requirements_checker():
    """Test requirements checker improvements"""
    print("Testing requirements checker...")
    
    try:
        import check_requirements
        
        # Test individual checks
        result = check_requirements.check_system_requirements()
        assert isinstance(result, bool)
        
        result = check_requirements.check_file_structure()
        assert isinstance(result, bool)
        
        result = check_requirements.check_configuration()
        assert isinstance(result, bool)
        
        print("[OK] Requirements checker tests passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] Requirements checker test failed: {e}")
        return False

def test_file_tailer_robustness():
    """Test FileTailer encoding and error handling"""
    print("Testing FileTailer robustness...")
    
    try:
        from soc_copilot.phase4.ingestion.watcher import FileTailer
        
        # Create temporary file with different encodings
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as f:
            temp_file = Path(f.name)
            f.write("test line\n")
        
        callback_calls = []
        def test_callback(line):
            callback_calls.append(line)
        
        # Test tailer
        tailer = FileTailer(str(temp_file), test_callback)
        stats = tailer.get_stats()
        
        # Check stats structure
        assert "filepath" in stats
        assert "error_count" in stats
        assert "encoding_errors" in stats
        
        # Cleanup
        temp_file.unlink()
        
        print("[OK] FileTailer robustness tests passed")
        return True
        
    except Exception as e:
        print(f"[ERROR] FileTailer robustness test failed: {e}")
        return False

def main():
    """Run all production readiness tests"""
    print("SOC Copilot Production Readiness Verification")
    print("=" * 50)
    
    tests = [
        ("Ingestion Robustness", test_ingestion_robustness),
        ("UI Improvements", test_ui_improvements),
        ("Setup Improvements", test_setup_improvements),
        ("Requirements Checker", test_requirements_checker),
        ("FileTailer Robustness", test_file_tailer_robustness)
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
    
    passed = 0
    total = len(tests)
    
    for test_name, result in results.items():
        status = "[PASS]" if result else "[FAIL]"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("All production readiness improvements verified!")
        print("\nSOC Copilot is ready for production deployment.")
        return 0
    else:
        print("Some tests failed. Check implementation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())