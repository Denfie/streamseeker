from __future__ import annotations

import sys
import logging

from streamseeker.api.core.logger import Logger

if __name__ == "__main__":
    from streamseeker.api.handler import StreamseekerHandler
    from streamseeker.constants import (DOWNLOAD_MODE, NAME, PREF_PROVIDER, LINK_URL, LANGUAGE, SHOW_TYPE, SHOW_NUMBER, EPISODE_NUMBER)
    logger = Logger(logging.DEBUG).instance()

    try:
        handler = StreamseekerHandler()

        handler.download(DOWNLOAD_MODE, NAME, PREF_PROVIDER, LINK_URL, LANGUAGE, SHOW_TYPE, SHOW_NUMBER, EPISODE_NUMBER)     
    except KeyboardInterrupt:
        logger.info(
f"""\
----------------------------------------------------------
--------- Downloads may still be running. ----------------
----------------------------------------------------------

Please don't close this terminal window until it's done.
"""
)

    except Exception as e:
        logger.info(
f"""\
----------------------------------------------------------
Exception: {e}
----------------------------------------------------------

Please don't close this terminal window until it's done.
"""
)
