"""
Standard logging configuration for DKIST micro services
which intercepts standard logger messages from imported
libraries to emit through the loguru handler.  Must be the
first import on the entry point to ensure the first execution
of the standard library logger basicConfig method
"""
import logging
from os import environ
from sys import stderr

from loguru import logger

__all__ = ["logger"]

LOG_LEVEL_TO_NAME = {
    5: "TRACE",
    10: "DEBUG",
    20: "INFO",
    25: "SUCCESS",
    30: "WARNING",
    40: "ERROR",
    50: "CRITICAL",
}
LOG_NAME_TO_LEVEL = {v: k for k, v in LOG_LEVEL_TO_NAME.items()}

# Retrieve default log level from same environment variable as loguru
LOG_LEVEL = LOG_NAME_TO_LEVEL.get(environ.get("LOGURU_LEVEL", "DEBUG"))

# Turn off better exceptions for log levels above debug to prevent secret leaking
IS_BETTER_EXCEPTIONS_ACTIVE = LOG_LEVEL <= 10

# Remove the default stderr handler
logger.remove()

# Add back the stderr handler with the diagnose flag set
logger.add(stderr, diagnose=IS_BETTER_EXCEPTIONS_ACTIVE)


class InterceptHandler(logging.Handler):
    """
    Handler to route stdlib logs to loguru
    """
    def emit(self, record):
        # Retrieve context where the logging call occurred, this happens to be in the 6th frame upward
        logger_opt = logger.opt(depth=6, exception=record.exc_info)
        # Log with name to support formatting if known, otherwise use the level number
        logger_opt.log(LOG_LEVEL_TO_NAME.get(record.levelno, record.levelno),
                       record.getMessage())


# Configuration for stdlib logger to route messages to loguru; must be run before other imports
logging.basicConfig(handlers=[InterceptHandler()], level=LOG_LEVEL)
