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

loglevel = logging.INFO

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

        # if not self._logger.hasHandlers():
        self._logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(BaseFormatter().setup())
        self._logger.addHandler(handler)
        self._logger.setLevel(self._initLogLevel)

        return self._logger
