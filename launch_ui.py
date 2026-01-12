"""SOC Copilot UI Launcher"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))


def main():
    """Launch SOC Copilot UI with robust error handling"""
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        from soc_copilot.phase4.controller import AppController
        from soc_copilot.phase4.ui import MainWindow
        
        # Check models directory
        models_dir = project_root / "data" / "models"
        if not models_dir.exists():
            print("Warning: Models directory not found.")
            print(f"Expected: {models_dir}")
            print("Please run model training first or check installation.")
        
        # Initialize controller
        controller = AppController(str(models_dir))
        
        try:
            controller.initialize()
            print("Pipeline initialized successfully.")
        except Exception as e:
            print(f"Warning: Could not initialize pipeline: {e}")
            print("UI will launch but analysis will not be available.")
        
        # Launch UI
        app = QApplication(sys.argv)
        
        # Set application properties
        app.setApplicationName("SOC Copilot")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("SOC Copilot Team")
        
        window = MainWindow(controller)
        window.show()
        
        print("SOC Copilot UI launched successfully.")
        sys.exit(app.exec())
        
    except ImportError as e:
        print(f"Error: Missing dependencies - {e}")
        print("Please install SOC Copilot dependencies:")
        print("  pip install -e .")
        sys.exit(1)
    except Exception as e:
        print(f"Error launching SOC Copilot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
