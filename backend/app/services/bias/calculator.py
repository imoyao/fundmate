# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/31 23:23
# File : calculator.py
# -*- coding: utf-8 -*-
"""
乖离率计算核心引擎

纯函数 + 类设计，与数据源解耦。

bias.py · 市场乖离率（刘晨明"均线偏离度"）灵活计算引擎

核心结论：乖离率不限于指数——**任何能拿到日线/净值序列的品种都能算**：
  - 指数(index)   ：akshare.index_zh_a_hist        → 收盘价
  - ETF(etf)      ：akshare.fund_etf_hist_em        → 收盘价(市价)
  - 场外基金(fund)：akshare.fund_open_fund_info_em  → 单位净值(或累计净值)
  - 股票(stock)   ：akshare.stock_zh_a_hist         → 收盘价
所以"我们持有的基金"完全能算：ETF 用市价、场外基金用单位净值。

方法（减法版，刘晨明）：  LOGBIAS = ( ln(close) − EMA20(ln(close)) ) × 100
  · 自然对数 np.log（非 log10）
  · EMA 非 SMA，alpha = 2/(span+1)，span=20，adjust=False
阈值(红绿区话术)：+15 极度高位(止盈) / +5 高位区(绿卖) / −5 中性区 / <−5 低位区(红买)
等价覆盖：爱基金「净值波动/趋势强弱/低位区/波段掘金」(同宗 NAV 位置振荡器)
派生：bias_to_position() 把 LOGBIAS(±15) 线性映射为 0-100 波段位置(红区低位·绿区高位)

设计：把"算什么品种"与"怎么算"解耦——
  - logbias(close)        纯函数，给定序列算一个值（易单测、易复用）
  - fetch_close(sym,kind) 按品种取序列
  - compute_bias(...)     单品种 → 统一 item
  - load_products()       从 bias_products.json 读"要算哪些品种"（用户可随时增删持有的基金）
  - compute_all()         批量 → item 列表，直接并入 aggregate()

用法：
    from bias import compute_all
    items = compute_all()                 # 读 bias_products.json（缺省回落内置默认）
    # 或在 market_thermometer.fetch_bias() 中调用

ref:[微信公众平台](https://mp.weixin.qq.com/s/yoDNm2TSrWCvvedu_Xozgw)

"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.bias.schemas import BiasResult

from .constants import (
    BIAS_PERIOD,
    BIAS_THRESHOLD_HIGH,
    BIAS_THRESHOLD_LOW,
    BIAS_THRESHOLD_MID,
    DEFAULT_HISTORY_DAYS,
    ITEM_TYPE_ETF,
    ITEM_TYPE_FUND,
    ITEM_TYPE_INDEX,
    ITEM_TYPE_INDUSTRY,
    ITEM_TYPE_STOCK,
)

logger = logging.getLogger(__name__)


def logbias(close: List[float]) -> float:
    """
    计算乖离率（减法版刘晨明方法）
    BIAS = (ln(close) - EMA20(ln(close))) × 100

    Args:
        close: 收盘价/净值序列（最新在末位）

    Returns:
        乖离率值 (%)

    Raises:
        RuntimeError: 数据不足时抛出
    """
    arr = np.asarray(close, dtype=float)
    if len(arr) < BIAS_PERIOD:
        raise RuntimeError(f'数据不足{BIAS_PERIOD}日(仅{len(arr)}日)')

    ln_close = np.log(arr)
    ema = pd.Series(ln_close).ewm(alpha=2 / (BIAS_PERIOD + 1), adjust=False).mean().values
    return float((ln_close - ema)[-1] * 100)


def bias_label(bias: float) -> str:
    """根据乖离率值返回信号标签"""
    if bias >= BIAS_THRESHOLD_HIGH:
        return '极度高位(止盈)'
    elif bias >= BIAS_THRESHOLD_MID:
        return '高位区(绿卖)'
    elif bias >= BIAS_THRESHOLD_LOW:
        return '中性区'
    else:
        return '低位区(红买)'


def bias_to_position(bias: float) -> float:
    """
    将乖离率映射到 0-100 波段位置
    映射公式: pos = (bias + 15) / 30 * 100
    范围: [-15, 15] → [0, 100]
    """
    return round(max(0.0, min(100.0, (bias + 15.0) / 30.0 * 100.0)), 1)


def position_label(pos: float) -> str:
    """波段位置标签"""
    if pos >= 90:
        return '极度高位(止盈)'
    elif pos >= 67:
        return '高位区(绿卖)'
    elif pos >= 33:
        return '中性区'
    else:
        return '低位区(红买)'


class PriceFetcher:
    """
    价格数据获取器（与品种类型解耦）
    支持：指数、ETF、场外基金、股票
    """

    def __init__(self, days: int = DEFAULT_HISTORY_DAYS):
        self.days = days

    def fetch(self, symbol: str, item_type: str) -> Optional[List[float]]:
        """
        获取品种的日线收盘价/净值序列（最新在末位）

        Args:
            symbol: 代码
            item_type: 品种类型 (index/etf/fund/stock)

        Returns:
            收盘价列表，失败返回 None
        """
        from datetime import datetime, timedelta

        import akshare as ak

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=self.days + 10)).strftime('%Y%m%d')

        try:
            if item_type in (ITEM_TYPE_INDEX, ITEM_TYPE_INDUSTRY):
                df = ak.index_zh_a_hist(symbol=symbol, period='daily', start_date=start_date, end_date=end_date)
                col = '收盘'
            elif item_type == ITEM_TYPE_ETF:
                df = ak.fund_etf_hist_em(symbol=symbol, period='daily', start_date=start_date, end_date=end_date)
                col = '收盘'
            elif item_type == ITEM_TYPE_STOCK:
                df = ak.stock_zh_a_hist(symbol=symbol, period='daily', start_date=start_date, end_date=end_date)
                col = '收盘'
            elif item_type in (ITEM_TYPE_FUND, 'fund_cum'):
                indicator = '累计净值走势' if item_type == 'fund_cum' else '单位净值走势'
                df = ak.fund_open_fund_info_em(symbol=symbol, indicator=indicator)
                col = '累计净值' if item_type == 'fund_cum' else '单位净值'
            else:
                raise ValueError(f'不支持的品种类型: {item_type}')

            if df is None or df.empty:
                return None

            # 确保数据按日期升序
            df = df.sort_values(df.columns[0]) if '日期' in df.columns else df
            values = df[col].astype(float).tolist()
            return values if len(values) >= BIAS_PERIOD else None

        except Exception as e:
            logger.warning(f'获取 {symbol} ({item_type}) 失败: {e}')
            return None


class BiasCalculator:
    """
    乖离率计算器（核心类）

    职责：
      1. 接收品种列表和价格获取器
      2. 计算每个品种的乖离率
      3. 返回 BiasResult 列表
    """

    def __init__(self, fetcher: Optional[PriceFetcher] = None):
        self.fetcher = fetcher or PriceFetcher()

    def calculate_item(
        self,
        symbol: str,
        item_type: str,
        name: str,
        data_date: Optional[date] = None,
    ) -> Optional[BiasResult]:
        """
        计算单个品种的乖离率

        Returns:
            BiasResult 或 None（计算失败时）
        """
        close = self.fetcher.fetch(symbol, item_type)
        if close is None:
            return None

        try:
            bias = logbias(close)
        except RuntimeError as e:
            logger.warning(f'计算乖离率失败 {symbol}: {e}')
            return None

        # 计算 EMA20 对数值（用于展示）
        arr = np.asarray(close, dtype=float)
        ln_close = np.log(arr)
        ema = pd.Series(ln_close).ewm(alpha=2 / (BIAS_PERIOD + 1), adjust=False).mean().values
        ema20 = float(ema[-1])

        pos = bias_to_position(bias)

        return BiasResult(
            item_type=item_type,
            item_code=symbol,
            item_name=name,
            close=float(close[-1]),
            bias=round(bias, 2),
            ema20=round(ema20, 4),
            label=bias_label(bias),
            position=pos,
            position_label=position_label(pos),
            data_date=data_date or date.today(),
            calculated_at=datetime.now(),
            stale=False,
        )

    def calculate_batch(
        self,
        products: List[Tuple[str, str, str]],  # (symbol, item_type, name)
        data_date: Optional[date] = None,
        max_workers: int = 4,
    ) -> List[BiasResult]:
        """
        批量计算乖离率

        Args:
            products: 品种列表 [(symbol, item_type, name), ...]
            data_date: 数据日期（默认今天）
            max_workers: 并发数（暂未实现并发，顺序执行）

        Returns:
            BiasResult 列表（失败的品种被过滤掉）
        """
        results: List[BiasResult] = []
        total = len(products)

        for idx, (symbol, item_type, name) in enumerate(products, 1):
            if idx % 10 == 0:
                logger.debug(f'乖离率计算进度: {idx}/{total}')

            result = self.calculate_item(symbol, item_type, name, data_date)
            if result:
                results.append(result)

        logger.info(f'乖离率计算完成: 成功 {len(results)}/{total}')
        return results
