"""SOC Copilot entry point."""

import sys
import os
from pathlib import Path
from soc_copilot.core.logging import setup_logging, get_logger


def main() -> int:
    """Main entry point for SOC Copilot."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("soc_copilot_started", version="0.1.0")
    
    try:
        # Check if models exist
        models_dir = Path("data/models")
        if not models_dir.exists():
            print("Warning: Models directory not found. Please run training first.")
            print("See README.md for setup instructions.")
        
        # Launch UI
        from PyQt6.QtWidgets import QApplication
        from soc_copilot.phase4.controller import AppController
        from soc_copilot.phase4.ui import MainWindow
        
        # Initialize controller
        controller = AppController(str(models_dir))
        
        try:
            controller.initialize()
            logger.info("pipeline_initialized")
        except Exception as e:
            logger.warning("pipeline_init_failed", error=str(e))
            print(f"Warning: Could not initialize pipeline: {e}")
            print("UI will launch but analysis will not be available.")
        
        # Launch UI
        app = QApplication(sys.argv)
        window = MainWindow(controller)
        window.show()
        
        logger.info("soc_copilot_ready")
        return app.exec()
        
    except ImportError as e:
        print(f"Error: Missing dependencies - {e}")
        print("Please install SOC Copilot: pip install -e .")
        return 1
    except Exception as e:
        logger.error("startup_failed", error=str(e))
        print(f"Error starting SOC Copilot: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
