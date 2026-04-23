from __future__ import annotations

import atexit
import sys
import logging

from streamseeker.api.core.logger import Logger


def _cleanup_terminal() -> None:
    """Ensure terminal is in a usable state on exit."""
    try:
        sys.stderr.write("\033[?25h\033[0m")  # Show cursor, reset attributes
        sys.stderr.flush()
    except Exception:
        pass


if __name__ == "__main__":
    from streamseeker.console.application import main

    atexit.register(_cleanup_terminal)
    logger = Logger(logging.DEBUG).instance()

    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _cleanup_terminal()
        sys.exit(0)
