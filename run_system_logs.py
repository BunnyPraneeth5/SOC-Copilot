#!/usr/bin/env python3
"""System log ingestion runner for SOC Copilot."""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

from soc_copilot.phase4.ingestion import IngestionController
from soc_copilot.phase4.controller import AppController
from soc_copilot.phase3.governance import KillSwitch
from soc_copilot.phase4.ingestion.system_logs import SystemLogIntegration

Path('logs/system').mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/system/system_logs.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

DEFAULT_BATCH_INTERVAL = 5.0
MODELS_DIR = Path("data/models")
GOVERNANCE_DB = Path("data/governance/governance.db")


def main() -> int:
    """Run system log ingestion with proper error handling and cleanup."""
    print("SOC Copilot — System Log Ingestion Mode")
    logger.info("Starting system log ingestion")

    ingestion: Optional[SystemLogIntegration] = None

    try:
        killswitch = KillSwitch(str(GOVERNANCE_DB))
        if killswitch.is_enabled():
            logger.warning("Kill switch is enabled")
            print("❌ Kill switch enabled. Aborting.")
            return 1

        if not MODELS_DIR.exists():
            logger.error(f"Models directory not found: {MODELS_DIR}")
            print(f"❌ Models directory not found. Run 'python scripts/train_models.py' first.")
            return 1

        controller = AppController(models_dir=str(MODELS_DIR))
        controller.initialize()
        logger.info("AppController initialized")

        system_logs = SystemLogIntegration(
            config_path="config/ingestion/system_logs.yaml",
            killswitch_check=lambda: killswitch.is_enabled()
        )
        system_logs.initialize(controller.process_batch)

        print("✅ System logs enabled")
        logger.info("System logs enabled successfully")

        system_logs.start()
        print("▶ Monitoring system logs. Press Ctrl+C to stop.")
        logger.info("Ingestion started")

        ingestion = system_logs

        while system_logs.is_running() and not killswitch.is_enabled():
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
        print("\n🛑 Stopping...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        print(f"❌ Fatal error: {e}")
        return 1
    finally:
        if ingestion:
            try:
                ingestion.stop()
                logger.info("Ingestion stopped cleanly")
            except Exception as e:
                logger.error(f"Error stopping ingestion: {e}")
        print("🛑 Stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
