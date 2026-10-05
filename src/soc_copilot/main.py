"""SOC Copilot entry point."""

import sys
import os
from pathlib import Path
from soc_copilot.core.logging import setup_logging, get_logger


def main() -> int:
    """Main entry point for SOC Copilot."""
    from dotenv import load_dotenv
    load_dotenv(Path.cwd() / ".env")

    setup_logging()
    logger = get_logger(__name__)
    
    from soc_copilot import __version__
    logger.info("soc_copilot_started", version=__version__)
    
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
        
        # Phase-2/3 subsystems (drift, feedback, audit) — optional; a
        # failure must not prevent the app from launching.
        drift_monitor = None
        try:
            from soc_copilot.phase2.drift.monitor import DriftMonitor
            drift_monitor = DriftMonitor("data/drift/drift.db")
            drift_monitor.initialize()
        except Exception as e:
            logger.warning("drift_monitor_unavailable", error=str(e))

        feedback_store = None
        try:
            from soc_copilot.phase2.feedback.store import FeedbackStore
            feedback_store = FeedbackStore("data/feedback/feedback.db")
            feedback_store.initialize()
        except Exception as e:
            logger.warning("feedback_store_unavailable", error=str(e))

        audit_logger = None
        try:
            from soc_copilot.phase3.governance import AuditLogger
            Path("data/governance").mkdir(parents=True, exist_ok=True)
            audit_logger = AuditLogger("data/governance/governance.db")
        except Exception as e:
            logger.warning("audit_logger_unavailable", error=str(e))

        # Initialize controller
        controller = AppController(
            str(models_dir),
            results_db=Path("data/alerts/results.db"),
            drift_monitor=drift_monitor,
            feedback_store=feedback_store,
            audit_logger=audit_logger,
        )
        
        try:
            controller.initialize()
            logger.info("pipeline_initialized")
        except Exception as e:
            logger.warning("pipeline_init_failed", error=str(e))
            print(f"Warning: Could not initialize pipeline: {e}")
            print("UI will launch but analysis will not be available.")
        
        # Launch UI
        app = QApplication(sys.argv)

        # Apply central theme (persisted preference, dark default)
        from soc_copilot.phase4.ui.theme import ThemeManager
        ThemeManager.instance().load_preferences()
        ThemeManager.instance().apply(app)

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
