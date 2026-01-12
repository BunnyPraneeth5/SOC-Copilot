"""SOC Copilot UI Launcher"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))


def main():
    """Launch SOC Copilot UI with robust error handling and graceful degradation"""
    try:
        # Check if we're in the right directory
        project_root = Path(__file__).parent
        if not (project_root / "src" / "soc_copilot").exists():
            print("Error: SOC Copilot source code not found.")
            print(f"Expected: {project_root / 'src' / 'soc_copilot'}")
            print("Please run from the SOC Copilot project directory.")
            sys.exit(1)
        
        # Import PyQt6 with helpful error message
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
        except ImportError as e:
            print("Error: PyQt6 not installed or not working.")
            print(f"Details: {e}")
            print("\nInstallation steps:")
            print("1. pip install PyQt6")
            print("2. Or run: python setup.py")
            sys.exit(1)
        
        # Import SOC Copilot modules
        try:
            from soc_copilot.phase4.controller import AppController
            from soc_copilot.phase4.ui import MainWindow
        except ImportError as e:
            print("Error: SOC Copilot modules not found.")
            print(f"Details: {e}")
            print("\nTry:")
            print("1. python setup.py")
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
        controller = AppController(str(models_dir))
        
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
        
        # Create and configure QApplication
        app = QApplication(sys.argv)
        
        # Set application properties
        app.setApplicationName("SOC Copilot")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("SOC Copilot Team")
        
        # Handle high DPI displays
        try:
            app.setAttribute(app.ApplicationAttribute.AA_EnableHighDpiScaling, True)
            app.setAttribute(app.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
        except AttributeError:
            pass  # Older Qt versions
        
        # Create main window
        try:
            window = MainWindow(controller)
            window.show()
            
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
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error launching SOC Copilot: {e}")
        print("\nTroubleshooting steps:")
        print("1. Check installation: python check_requirements.py")
        print("2. Reinstall: python setup.py")
        print("3. Check logs in logs/ directory")
        sys.exit(1)


if __name__ == "__main__":
    main()
