import logging
import os

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

class Logger(metaclass=Singleton):
    _active = False

    def __init__(self, level=logging.NOTSET, name: str = "streamseeker") -> None:
        self._name = name
        self._logLevel = level
        self._active = True
    
    def deactivate(self):
        self._active = False
        self._logLevel = logging.CRITICAL

    def activate(self):
        self._active = True
        self._logLevel = logging.INFO
    
    def instance(self) -> logging.Logger:    
        logger = logging.getLogger(self._name)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(BaseFormatter().setup())
        logger.addHandler(handler)
        logger.setLevel(self._logLevel)
        return logger
