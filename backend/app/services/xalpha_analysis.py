# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 18:34
# File : xalpha_analysis.py
"""基于 xalpha 的专业分析功能（保留特色分析，不依赖数据获取）"""

import xalpha as xa
from loguru import logger


class XAAnalysis:
    @staticmethod
    def analyze_convertible_bond(cb_code: str) -> dict:
        """可转债深度分析"""
        try:
            cb = xa.cb.CBCalculator(cb_code)
            return {
                '纯债价值': cb.df.iloc[-1]['纯债价值'],
                '转股溢价率': cb.df.iloc[-1]['转股溢价率'],
                '到期税前收益率': cb.df.iloc[-1]['到期税前收益率'],
            }
        except Exception as e:
            logger.error(f'Convertible bond analysis {cb_code} failed: {e}')
            return {}

    @staticmethod
    def predict_qdii_net_value(fund_code: str) -> float:
        """QDII 净值预测"""
        try:
            qdii = xa.qdii.QDIIPredict(fund_code)
            return qdii.predict()
        except Exception as e:
            logger.error(f'QDII predict {fund_code} failed: {e}')
            return 0.0

    @staticmethod
    def calculate_portfolio_xirr(trades: list) -> float:
        """组合年化收益率，trades 格式依 xalpha mul 要求"""
        try:
            p = xa.mul(trades)
            return p.xirr()
        except Exception as e:
            logger.error(f'Portfolio XIRR failed: {e}')
            return 0.0
