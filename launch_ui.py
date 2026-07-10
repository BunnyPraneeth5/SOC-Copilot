"""SOC Copilot UI Launcher"""

import sys
import os
import ctypes
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent

# Load environment variables from .env
load_dotenv(project_root / ".env")

sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))


def check_required_permissions(project_root: Path) -> bool:
    """Check required directory permissions before startup"""
    required_dirs = [
        project_root / "data",
        project_root / "logs"
    ]
    
    for dir_path in required_dirs:
        try:
            # Create if doesn't exist
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_file = dir_path / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            print(f"Error: No write access to {dir_path}")
            print(f"Details: {e}")
            print("\nRemediation:")
            if sys.platform == "win32":
                print("  - Run as Administrator, or")
                print("  - Change directory permissions")
            else:
                print(f"  - Run: chmod -R u+w {dir_path}")
            return False
    
    return True


def check_optional_permissions(project_root: Path) -> dict:
    """Check optional system log permissions"""
    result = {"has_system_log_access": False, "message": None}
    
    try:
        from soc_copilot.phase4.ingestion.system_log_reader import SystemLogReader
        
        reader = SystemLogReader()
        perm_check = reader.validate_system_log_access()
        
        result["has_system_log_access"] = perm_check.has_permission
        
        if not perm_check.has_permission:
            result["message"] = perm_check.error_message
            if perm_check.requires_elevation:
                print("\nNote: System log access limited")
                print(f"Reason: {perm_check.error_message}")
                print("Impact: System log ingestion unavailable (file-based ingestion still works)")
    except Exception:
        pass  # Optional check, don't fail
    
    return result


def main():
    """Launch SOC Copilot UI with robust error handling and graceful degradation"""
    # Track background exporter processes for cleanup
    exporter_processes = []
    
    try:
        # Check if we're in the right directory
        project_root = Path(__file__).parent
        if not (project_root / "src" / "soc_copilot").exists():
            print("Error: SOC Copilot source code not found.")
            print(f"Expected: {project_root / 'src' / 'soc_copilot'}")
            print("Please run from the SOC Copilot project directory.")
            sys.exit(1)
        
        # Check kill switch
        from soc_copilot.phase4.kill_switch import KillSwitch
        kill_switch = KillSwitch(project_root)
        if kill_switch.is_active():
            print("Kill switch is active. Application disabled.")
            print(f"Remove {kill_switch.kill_file} to re-enable.")
            sys.exit(1)
        
        # Check required permissions
        if not check_required_permissions(project_root):
            print("\nCannot start: Required permissions missing.")
            print("Run 'python setup_project.py' to fix permissions.")
            sys.exit(1)
        
        # Check optional permissions (non-blocking)
        optional_perms = check_optional_permissions(project_root)
        
        # If running as admin, start system log exporters
        if optional_perms.get("has_system_log_access"):
            exporter_processes = start_system_log_exporters(project_root)
            if exporter_processes:
                print(f"Started {len(exporter_processes)} system log exporter(s).")
        
        # Import PyQt6 with helpful error message
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
        except ImportError as e:
            print("Error: PyQt6 not installed or not working.")
            print(f"Details: {e}")
            print("\nInstallation steps:")
            print("1. pip install PyQt6")
            print("2. Or run: python setup_project.py")
            sys.exit(1)
        
        # Import SOC Copilot modules
        try:
            from soc_copilot.phase4.controller import AppController
            from soc_copilot.phase4.ui import MainWindow
            from soc_copilot.phase4.ui.splash_screen import create_splash
        except ImportError as e:
            print("Error: SOC Copilot modules not found.")
            print(f"Details: {e}")
            print("\nTry:")
            print("1. python setup_project.py")
            print("2. pip install -e .")
            sys.exit(1)
        
        # Check and prepare models directory
        models_dir = project_root / "data" / "models"
        models_available = False
        
        if not models_dir.exists():
            print(f"Warning: Models directory not found: {models_dir}")
            models_dir.mkdir(parents=True, exist_ok=True)
            print("Created models directory.")
        else:
            # Check for required model files
            required_models = [
                "isolation_forest_v1.joblib",
                "random_forest_v1.joblib",
                "feature_order.json",
                "label_map.json"
            ]
            
            missing_models = []
            for model_file in required_models:
                if not (models_dir / model_file).exists():
                    missing_models.append(model_file)
            
            if missing_models:
                print("Warning: Missing trained models:")
                for model in missing_models:
                    print(f"  - {model}")
                print("\nTo train models: python scripts/train_models.py")
                print("UI will launch but analysis will be limited.")
            else:
                models_available = True
                print("All required models found.")
        
        # Initialize controller with error handling
        controller = AppController(str(models_dir), killswitch_check=kill_switch.is_active)
        
        try:
            controller.initialize()
            print("Pipeline initialized successfully.")
        except Exception as e:
            print(f"Warning: Could not initialize pipeline: {e}")
            if models_available:
                print("This is unexpected. Check logs for details.")
            else:
                print("This is expected without trained models.")
            print("UI will launch but analysis will not be available.")
        
        # Start system log ingestion if running as admin
        system_log_integration = None
        if optional_perms.get("has_system_log_access"):
            system_log_integration = start_system_log_ingestion(
                controller, kill_switch, project_root
            )
        
        # Create and configure QApplication
        app = QApplication(sys.argv)
        
        # Set application properties
        app.setApplicationName("SOC Copilot")
        app.setApplicationVersion("1.0.0-beta.1")
        app.setOrganizationName("SOC Copilot Team")
        
        # Handle high DPI displays
        try:
            app.setAttribute(app.ApplicationAttribute.AA_EnableHighDpiScaling, True)
            app.setAttribute(app.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        except AttributeError:
            pass  # Older Qt versions
        
        # Show splash screen
        splash = create_splash()
        splash.show_message("Loading models...")
        
        # Create main window
        try:
            splash.show_message("Initializing UI...")
            window = MainWindow(controller)
            window.show()
            
            # Close splash screen
            splash.finish(window)
            
            # Show status message
            if models_available:
                print("SOC Copilot UI launched successfully with full functionality.")
            else:
                print("SOC Copilot UI launched with limited functionality.")
                print("Train models to enable threat detection.")
            
            # Start event loop
            sys.exit(app.exec())
            
        except Exception as e:
            print(f"Error creating main window: {e}")
            # Show error dialog if possible
            try:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("SOC Copilot Error")
                msg.setText(f"Failed to create main window:\n{str(e)}")
                msg.setInformativeText("Check console output for details.")
                msg.exec()
            except Exception:
                pass
            sys.exit(1)
        
    except KeyboardInterrupt:
        print("\nShutdown requested by user.")
    except Exception as e:
        print(f"Unexpected error launching SOC Copilot: {e}")
        print("\nTroubleshooting steps:")
        print("1. Check installation: python check_requirements.py")
        print("2. Reinstall: python setup_project.py")
        print("3. Check logs in logs/ directory")
        sys.exit(1)
    finally:
        # Cleanup: stop system log exporters
        for proc in exporter_processes:
            try:
                proc.terminate()
            except Exception:
                pass


def is_admin() -> bool:
    """Check if running with administrator privileges."""
    if sys.platform != "win32":
        return os.geteuid() == 0
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin_elevation():
    """Re-launch the current script with UAC elevation (Windows).
    
    If on Windows and not admin, triggers the UAC prompt.
    If accepted, the current process exits and a new elevated process starts.
    """
    if sys.platform != "win32":
        print("On Linux/macOS, re-run with: sudo python launch_ui.py")
        return
    
    print("\nRequesting administrator privileges for system log access...")
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        sys.exit(0)  # Exit current non-elevated process
    except Exception as e:
        print(f"Elevation failed: {e}")
        print("Continuing without system log access.")


def start_system_log_exporters(project_root: Path) -> list:
    """Start PowerShell exporter scripts as hidden background processes.
    
    These export Windows Security and System event logs to files
    that SOC Copilot can then ingest.
    
    Returns:
        List of subprocess.Popen objects for cleanup
    """
    processes = []
    exporters = [
        ("Security", project_root / "scripts" / "exporters" / "export_windows_security.ps1"),
        ("System", project_root / "scripts" / "exporters" / "export_windows_system.ps1"),
    ]
    
    # Ensure output directory exists
    log_dir = project_root / "logs" / "system"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    for name, script_path in exporters:
        if not script_path.exists():
            print(f"Warning: Exporter script not found: {script_path}")
            continue
        
        try:
            # Create empty log file so the tailer can start watching it
            if name == "Security":
                log_file = log_dir / "windows_security.log"
            else:
                log_file = log_dir / "windows_system.log"
            log_file.touch(exist_ok=True)
            
            # Launch PowerShell exporter as a hidden background process
            proc = subprocess.Popen(
                [
                    "powershell.exe",
                    "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden",
                    "-File", str(script_path),
                ],
                cwd=str(project_root),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            processes.append(proc)
            print(f"  ▶ Windows {name} log exporter started (PID {proc.pid})")
        except Exception as e:
            print(f"  ✗ Failed to start {name} exporter: {e}")
    
    return processes


def start_system_log_ingestion(controller, kill_switch, project_root: Path):
    """Wire SystemLogIntegration to the controller for live system log analysis.
    
    Args:
        controller: AppController instance
        kill_switch: KillSwitch instance
        project_root: Project root path
        
    Returns:
        SystemLogIntegration instance (or None if failed)
    """
    try:
        from soc_copilot.phase4.ingestion.system_logs import SystemLogIntegration
        
        config_path = str(project_root / "config" / "ingestion" / "system_logs.yaml")
        integration = SystemLogIntegration(
            config_path=config_path,
            killswitch_check=kill_switch.is_active,
        )
        integration.initialize(controller.process_batch)
        integration.start()
        
        print("  ▶ System log ingestion started — analyzing live Windows events")
        return integration
    except Exception as e:
        print(f"  ✗ System log ingestion failed: {e}")
        return None


if __name__ == "__main__":
    # Auto-request admin if not elevated — needed for Windows Event Log access
    if sys.platform == "win32" and not is_admin():
        print("SOC Copilot needs administrator rights to read Windows Event Logs.")
        print("Requesting elevation...")
        request_admin_elevation()
        # If we reach here, elevation was declined — continue without system log access
        print("Continuing without system log access (file-based analysis still works).\n")
    main()
