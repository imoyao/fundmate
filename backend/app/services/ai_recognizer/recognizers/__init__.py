# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : recognizers/__init__.py
"""AI 识别器实现。导入本包即完成注册（见 ai_recognizer/__init__.py）。"""

from app.services.ai_recognizer.recognizers.txn_recognizer import TxnRecognizer
from app.services.ai_recognizer.recognizers.watchlist_recognizer import WatchlistRecognizer

__all__ = ['WatchlistRecognizer', 'TxnRecognizer']
