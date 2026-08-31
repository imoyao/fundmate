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

import json
import random
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

# 全局请求补丁：确保即使本模块被单独 import（如单测）也自动启用东财友好会话；
# 正常由 app/__init__ 安装，此处为幂等兜底，避免遗漏调用点。
from app.core.requests_patch import install_requests_patch
from app.services.bias.constants import (
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
from app.services.bias.direct_feeds import (
    _eastmoney_secid,
    fetch_close_eastmoney,
    fetch_close_tencent,
)
from app.services.bias.schemas import BiasResult

# 幂等安装请求补丁（置于 import 之后，避免 E402）
install_requests_patch()


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
    import numpy as np
    import pandas as pd

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


# 价格持久化缓存目录：遵循项目 data/ 约定（与 xalpha_cache 同级）
_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[3] / 'data' / 'bias_price_cache'


class PriceFetcher:
    """
    价格数据获取器（与品种类型解耦）
    支持：指数、ETF、场外基金、股票

    缓存策略（缓解东财限流 + 断网可降级）：
      - 进程内 dict 去重（同进程秒级复用）
      - 文件缓存（backend/data/bias_price_cache/*.json）：按 (symbol, item_type) 存
        最近 N 日收盘价序列 + 数据最后交易日；当日已抓过则直接复用，避免每天冷启动全量重抓。
      - 实时抓取失败且本地有旧缓存时，回退旧数据并标记 stale=True（前端可感知数据滞后）。
    """

    def __init__(
        self,
        days: int = DEFAULT_HISTORY_DAYS,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
        cache_dir: Optional[Path] = None,
    ):
        self.days = days
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        # 统一转为 pathlib.Path，避免传入 str/py.path.local 时 "/" 运算符抛 TypeError（被 _save_cache 吞掉，导致文件缓存永不写入）
        self.cache_dir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE_DIR
        # 同一进程内去重缓存，避免重复请求同一品种
        self._cache: dict = {}
        # (symbol, item_type) -> 是否滞后（实时抓取失败回退旧数据时为 True）
        self._stale: dict = {}

    # ---------- 持久化缓存 ----------
    def _file_path(self, symbol: str, item_type: str) -> Path:
        safe = f'{item_type}__{symbol.replace(".", "_")}.json'
        return self.cache_dir / safe

    def _load_cache(self, symbol: str, item_type: str) -> Optional[dict]:
        try:
            p = self._file_path(symbol, item_type)
            if p.exists():
                with open(p, 'r', encoding='utf-8') as fh:
                    return json.load(fh)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _save_cache(self, symbol: str, item_type: str, values: List[float], data_last_date: str) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                'symbol': symbol,
                'item_type': item_type,
                'values': values,
                'data_last_date': data_last_date,
                'fetched_at': datetime.now().isoformat(timespec='seconds'),
            }
            with open(self._file_path(symbol, item_type), 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logger.warning(f'乖离度价格缓存写入失败 {symbol} ({item_type}): {e}')

    @staticmethod
    def _is_fresh(date_str: str) -> bool:
        """数据最后交易日（或抓取日）是否在过去 2 天内（容忍周末/周一盘前）。"""
        if not date_str:
            return False
        try:
            d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
        except Exception:  # noqa: BLE001
            return False
        return d >= (datetime.now().date() - timedelta(days=2))

    def fetch(self, symbol: str, item_type: str) -> Optional[List[float]]:
        """
        获取品种的日线收盘价/净值序列（最新在末位）。

        优先级：进程内缓存 → 文件缓存(当日新鲜) → 实时抓取 → 回退旧文件缓存(标 stale)。
        最终仍失败且无任何缓存返回 None，真实异常类型已在日志透出。

        Args:
            symbol: 代码
            item_type: 品种类型 (index/etf/fund/stock)

        Returns:
            收盘价列表，失败返回 None
        """
        cache_key = (symbol, item_type)
        if cache_key in self._cache:
            return self._cache[cache_key]

        cached = self._load_cache(symbol, item_type)
        fresh_date = (cached.get('data_last_date') or cached.get('fetched_at', '')) if cached else ''
        if cached and self._is_fresh(fresh_date):
            values = cached['values']
            self._cache[cache_key] = values
            self._stale[cache_key] = False
            return values

        values, data_last_date = self._fetch_live(symbol, item_type)
        if values is not None:
            self._cache[cache_key] = values
            self._save_cache(symbol, item_type, values, data_last_date)
            self._stale[cache_key] = False
            return values

        # 实时失败 → 回退任何本地缓存（旧数据也好过无数据）
        if cached:
            logger.warning(f'获取 {symbol} ({item_type}) 实时失败，回退本地缓存（数据可能滞后）')
            self._cache[cache_key] = cached['values']
            self._stale[cache_key] = True
            return cached['values']

        return None

    # ── 数据源优先级（直连绕开 akshare/东财限流）：腾讯 > 东财 > akshare 兜底 ──
    def _fetch_direct(self, symbol: str, item_type: str):
        """直连行情：申万行业走东财(90.x)，股票/ETF/宽基走腾讯；返回 (values, data_last_date)。"""
        try:
            if item_type == ITEM_TYPE_INDUSTRY:
                secid = _eastmoney_secid(symbol)
                if secid:
                    res = fetch_close_eastmoney(secid, self.days)
                    if res:
                        return res
                return None, None

            # 股票 / ETF / 宽基：腾讯优先
            res = fetch_close_tencent(symbol, self.days)
            if res:
                return res
            # 宽基指数腾讯兜底到东财
            if item_type == ITEM_TYPE_INDEX:
                secid = _eastmoney_secid(symbol)
                if secid:
                    res = fetch_close_eastmoney(secid, self.days)
                    if res:
                        return res
            return None, None
        except Exception as e:  # noqa: BLE001
            logger.debug(f'直连抓取 {symbol} ({item_type}) 异常: {e}')
            return None, None

    def _fetch_live(self, symbol: str, item_type: str):
        """实时抓取：直连优先，失败回退 akshare（最后手段）。"""
        values, data_last_date = self._fetch_direct(symbol, item_type)
        if values is not None:
            return values, data_last_date
        return self._fetch_akshare(symbol, item_type)

    def _fetch_akshare(self, symbol: str, item_type: str):
        """akshare 兜底（东财后端）：场外基金/直连失败时使用，保留重试退避。"""
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=self.days + 10)).strftime('%Y%m%d')

        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
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
                    last_err = RuntimeError('返回空数据')
                    break  # 空数据不可重试

                # 确保数据按日期升序
                df = df.sort_values(df.columns[0]) if '日期' in df.columns else df
                values = df[col].astype(float).tolist()
                if len(values) < BIAS_PERIOD:
                    last_err = RuntimeError(f'数据不足{BIAS_PERIOD}日(仅{len(values)}日)')
                    break  # 数据不足不可重试

                data_last_date = str(df['日期'].iloc[-1]) if '日期' in df.columns else ''
                return values, data_last_date

            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    wait = self.retry_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        f'获取 {symbol} ({item_type}) 第{attempt}次失败: {type(e).__name__}: {e}，{wait:.1f}s 后重试'
                    )
                    time.sleep(wait)
                else:
                    logger.error(f'获取 {symbol} ({item_type}) 重试{self.max_retries}次仍失败: {type(e).__name__}: {e}')

        return None, None


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
        import numpy as np
        import pandas as pd

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
            stale=self.fetcher._stale.get((symbol, item_type), False),
        )

    def calculate_batch(
        self,
        products: List[Tuple[str, str, str]],  # (symbol, item_type, name)
        data_date: Optional[date] = None,
        max_workers: int = 4,
        request_interval: float = 3.0,
    ) -> List[BiasResult]:
        """
        批量计算乖离率

        Args:
            products: 品种列表 [(symbol, item_type, name), ...]
            data_date: 数据日期（默认今天）
            max_workers: 预留并发参数（当前顺序执行，避免并发触发东财限流）
            request_interval: 相邻请求间隔（秒），限速用，缓解连续请求断连

        Returns:
            BiasResult 列表（失败的品种被过滤，并在日志汇总透出）
        """
        results: List[BiasResult] = []
        failures: List[Tuple[str, str, str]] = []
        total = len(products)

        for idx, (symbol, item_type, name) in enumerate(products, 1):
            if idx % 10 == 0:
                logger.debug(f'乖离率计算进度: {idx}/{total}')

            result = self.calculate_item(symbol, item_type, name, data_date)
            if result:
                results.append(result)
            else:
                failures.append((symbol, item_type, name))

            # 限速：相邻请求随机间隔，缓解东方财富连续请求断连(RemoteDisconnected)
            if idx < total and request_interval > 0:
                time.sleep(request_interval + random.uniform(-0.5, 0.5))

        logger.info(f'乖离率计算完成: 成功 {len(results)}/{total}，失败 {len(failures)}')
        if failures:
            detail = ', '.join(f'{s}({t})' for s, t, _ in failures)
            logger.warning(f'乖离率失败品种({len(failures)}): {detail}')
        return results
