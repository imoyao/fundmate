# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/8 21:08
# File : __init__.py.py

import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        logger.opt(depth=6, exception=record.exc_info).log(record.levelname, record.getMessage())


logging.basicConfig(handlers=[InterceptHandler()], level=0)
