"""SOC Copilot UI Launcher"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from PyQt6.QtWidgets import QApplication
from soc_copilot.phase4.controller import AppController
from soc_copilot.phase4.ui import MainWindow


def main():
    """Launch SOC Copilot UI"""
    # Initialize controller
    models_dir = "data/models"
    controller = AppController(models_dir)
    
    try:
        controller.initialize()
    except Exception as e:
        print(f"Warning: Could not initialize pipeline: {e}")
        print("UI will launch but analysis will not be available.")
    
    # Launch UI
    app = QApplication(sys.argv)
    window = MainWindow(controller)
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
