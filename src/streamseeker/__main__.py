from __future__ import annotations

import sys
import logging

# from streamseeker.streamseeker import Streamseeker
from streamseeker.api.core.logger import Logger

if __name__ == "__main__":
    from streamseeker.console.application import main

    logger = Logger(logging.INFO).instance()

    sys.exit(main())

    # loggerClass = Logger()
    # loggerClass.activate()
    # loggerClass.log_level(logging.INFO)
    # logger = loggerClass.setup(__name__)
    # try:
    #     if __name__ == "__main__":

    # except KeyboardInterrupt:
    #     logger.warning("----------------------------------------------------------")
    #     logger.warning("                  Stream Download Helper                  ")
    #     logger.warning("----------------------------------------------------------")
    #     logger.warning("Downloads may still be running. Please don't close this")
    #     logger.warning("terminal window until it's done.")
    #     logger.warning("...Running in background...")

    # except Exception as e:
    #     logger.error("----------------------------------------------------------")
    #     logger.error(f"Exception: {e}")
    #     logger.error("----------------------------------------------------------")