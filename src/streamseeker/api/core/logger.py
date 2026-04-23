import logging
import os

from tqdm.auto import tqdm

from streamseeker.api.core.helpers import Singleton
from streamseeker.api.core.formatters.base_fomatter import BaseFormatter

LOADING = 24
SUCCESS = 25

logging.addLevelName(LOADING, "LOADING")
logging.addLevelName(SUCCESS, "SUCCESS")

def loading(self, message, *args, **kwargs):
    if self.isEnabledFor(LOADING):
        self._log(LOADING, message, args, **kwargs)

def success(self, message, *args, **kwargs):
    if self.isEnabledFor(SUCCESS):
        self._log(SUCCESS, message, args, **kwargs)

logging.Logger.loading = loading
logging.Logger.success = success

loglevel = logging.INFO


class TqdmLoggingHandler(logging.StreamHandler):
    """Logging handler that routes output through tqdm.write()
    so log messages don't collide with active progress bars."""

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
        except Exception:
            self.handleError(record)


class Logger(metaclass=Singleton):

    def __init__(self, level=logging.INFO, name: str = "streamseeker") -> None:
        self._name = name
        self._initLogLevel = level if not logging.NOTSET else loglevel
        self._active = True
        self._logger = None

    def deactivate(self):
        self._logger.setLevel(logging.CRITICAL)

    def activate(self):
        self._logger.setLevel(self._initLogLevel)

    def instance(self) -> logging.Logger:
        if self._logger:
            return self._logger

        self._logger = logging.getLogger(self._name)

        self._logger.propagate = False
        handler = TqdmLoggingHandler()
        handler.setFormatter(BaseFormatter().setup())
        self._logger.addHandler(handler)
        self._logger.setLevel(self._initLogLevel)

        return self._logger
