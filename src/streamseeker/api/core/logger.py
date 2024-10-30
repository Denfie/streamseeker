import logging
import os

from streamseeker.api.core.helpers import Singleton

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

class CustomFormatter(logging.Formatter):
    green = "\033[1;92m"
    yellow = "\033[1;93m"
    red = "\033[1;31m"
    purple = "\033[1;35m"
    blue = "\033[1;94m"
    white = "\033[1;37m"
    reset = "\033[0m"
    format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s "

    FORMATS = {
        logging.DEBUG: white + format + reset,
        logging.INFO: blue + format + reset,
        logging.WARNING: yellow + format + reset,
        logging.ERROR: red + format + reset,
        logging.CRITICAL: red + format + reset,
        LOADING: purple + format + reset,
        SUCCESS: green + format + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

class Logger(metaclass=Singleton):
    _active = False
    _logLevel = logging.INFO

    def setup(self, name: str) -> logging.Logger:
        return self.setup_logger(name)
    
    def log_level(self, level: int):
        self._logLevel = level
    
    def deactivate(self):
        self._active = False
        self._logLevel = logging.CRITICAL

    def activate(self):
        self._active = True
        self._logLevel = logging.INFO
    
    def setup_logger(self, name: str) -> logging.Logger:    
        logger = logging.getLogger(name)
        logger.propagate = False
        handler = logging.StreamHandler()
        handler.setFormatter(CustomFormatter())
        logger.addHandler(handler)
        logger.setLevel(self._logLevel)
        return logger
