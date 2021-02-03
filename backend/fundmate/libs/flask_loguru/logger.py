"""
Standard logging configuration for DKIST micro services
which intercepts standard logger messages from imported
libraries to emit through the loguru handler.  Must be the
first import on the entry point to ensure the first execution
of the standard library logger basicConfig method
"""
import logging
import os
import time
import zipfile
from os import environ
from sys import stderr
import datetime
from loguru import logger


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


class Logger(object):
    """This class is used to config loguru
    """

    def __init__(self, app=None, config=None):
        if not (config is None or isinstance(config, dict)):
            raise ValueError("`config` must be an instance of dict or None")

        self.config = config

        if app is not None:
            self.init_app(app, config)

    def init_app(self, app, config=None):
        """This is used to initialize logger with your app object
        """
        if not (config is None or isinstance(config, dict)):
            raise ValueError("`config` must be an instance of dict or None")

        base_config = app.config.copy()
        if self.config:
            base_config.update(self.config)
        if config:
            base_config.update(config)

        config = base_config

        config.setdefault("LOG_PATH", None)
        config.setdefault("LOG_NAME", "")
        config.setdefault("LOG_ROTATION", 60 * 60)
        config.setdefault("LOG_FORMAT", "")
        config.setdefault("LOG_ENQUEUE", True)
        config.setdefault("LOG_SERIALIZE", True)

        self._set_loguru(app, config)

    def _set_loguru(self, app, config):
        """ Config logru
        """
        path = config["LOG_NAME"]
        logger.info(path)
        if config["LOG_PATH"] is not None:
            path = os.path.join(config["LOG_PATH"], config["LOG_NAME"])

        def should_rotate(message, file):
            filepath = os.path.abspath(file.name)
            creation = os.path.getctime(filepath)
            now = message.record["time"].timestamp()
            return now - creation > config["LOG_ROTATION"]

        def should_retention(logs):
            """ 检查是否需要进行压缩
            """
            # 依次查找写入
            file_list = list()
            for log in logs:
                file_path = os.path.abspath(log)

                if file_path.endswith(".zip"):
                    continue

                if time.gmtime(time.time() - os.path.getctime(file_path)).tm_mday == 7:
                    file_list.append(file_path)

            if file_list:
                zip_logs(config, file_list)

        logger.add(path, format=config["LOG_FORMAT"], rotation=should_rotate,
                   enqueue=config["LOG_ENQUEUE"], serialize=config["LOG_SERIALIZE"],
                   retention=should_retention)

        if not hasattr(app, "extensions"):
            app.extensions = {}

        app.extensions.setdefault("loguru", {})
        app.extensions["loguru"][self] = logger


def zip_logs(config, file_list):
    """ 超过7天的文件按天打成zip包
    """
    day = datetime.datetime.today().date() - datetime.timedelta(days=7)

    # 设置zip位置
    zip_name = config['LOG_NAME'] + str(day) + ".zip"

    # 启动zip写入对象
    zp = zipfile.ZipFile(os.path.join(config["LOG_PATH"], zip_name), "w")
    for tar in file_list:
        zp.write(tar, os.path.basename(tar))

    zp.close()

    for tar in file_list:
        os.remove(tar)
