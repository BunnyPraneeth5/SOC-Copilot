"""SOC Copilot entry point."""

import sys
from soc_copilot.core.logging import setup_logging, get_logger


def main() -> int:
    """Main entry point for SOC Copilot."""
    setup_logging()
    logger = get_logger(__name__)
    
    logger.info("soc_copilot_started", version="0.1.0")
    
    # TODO: Initialize UI and start application
    logger.info("soc_copilot_ready")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
