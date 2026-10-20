# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:24
# File : akshare_adapter.py
# -*- coding: utf-8 -*-
# app/services/adapters/akshare_adapter.py
import json
import math
import re
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from loguru import logger

from app.core.symbol_utils import (
    derive_security_type,
    get_normalizer,
    market_of_cn_a_code,
    split_symbol,
)
from app.services.adapters.base import DataSourceAdapter

# 基金经理全量接口（东财 fund_manager_em）偶发抖动，首次拉取的有限重试策略
_FUND_MANAGER_RETRY = 3
_FUND_MANAGER_RETRY_SLEEP = 3  # 秒

# 日线取数中**不接受日期区间参数**的品类：可转债（bond_zh_hs_cov_daily）与 ETF 的
# 新浪保底源（fund_etf_hist_sina）都会返回全部历史，必须由调用侧本地裁剪（#1104）。
# ETF 主源（腾讯 stock_zh_a_hist_tx）与备源（东财）虽接受日期参数，但保底路径不接受，
# 故 etf 保留在名单里统一裁剪（对接受参数的源只是二次裁剪，无副作用）
_NO_WINDOW_SEC_TYPES = ('bond', 'etf')

# ── 东财 K 线连接级失败熔断器 ────────────────────────────────────────────────
# WHY：2026-10-14 实测 push2his.eastmoney.com 对本机 IP 级拒绝（RemoteDisconnected，
# curl 直连同样失败）。东财挂掉期间每只 ETF 仍白烧 adjust='' 与 adjust='qfq' 两轮、
# 每轮 urllib3 重试 3 次（约 7~10 秒/只）才走到既有回退，8 只持仓 ETF 一轮多耗
# 约 1.5 分钟并刷屏 WARNING（当日实测 16 条）。
# 自 2026-10-14 起东财已降为 ETF 日线**备源**（主源切腾讯，见 _fetch_etf_frame），
# 仅在腾讯失败时才会被尝试；熔断语义不变：
# 连续 2 次连接级失败后 600s 内跳过东财——adjust='' 直切新浪保底、
# adjust='qfq' 直接返回 None（adj_close 由 _fetch_adj_close_map 回退 close）；
# 一次成功即复位；冷却过期后下一次调用即半开试探。仅连接级异常（ConnectionError /
# Timeout）计数，解析错等业务异常不计。数据自愈仍靠 price_history 缺口回补下次运行。
_EM_KLINE_FAILURE_THRESHOLD = 2
_EM_KLINE_BREAKER_COOLDOWN = 600  # 秒


class _EmKlineBreaker:
    """东财 K 线连接级失败熔断器（进程内共享，见模块级常量处的 WHY 说明）。"""

    def __init__(self):
        self._consecutive = 0
        self._open_until = 0.0

    def should_skip(self, now: float) -> bool:
        """熔断是否处于打开期（now 早于冷却截止时间）。"""
        return now < self._open_until

    def record_success(self) -> None:
        """一次成功即完全复位（含关闭熔断）。"""
        self._consecutive = 0
        self._open_until = 0.0

    def record_connection_failure(self, now: float) -> None:
        """记录一次连接级失败；达到阈值时打开熔断并打日志。"""
        self._consecutive += 1
        if self._consecutive >= _EM_KLINE_FAILURE_THRESHOLD:
            self._open_until = now + _EM_KLINE_BREAKER_COOLDOWN
            logger.info(
                f'东财 K 线连接级失败连续 {self._consecutive} 次，熔断打开 '
                f'{_EM_KLINE_BREAKER_COOLDOWN}s：期间 ETF 未复权直切新浪回退、'
                '复权请求直接跳过（adj_close 回退 close）'
            )

    def reset(self) -> None:
        """测试用：清零计数并关闭熔断。"""
        self._consecutive = 0
        self._open_until = 0.0


_em_kline_breaker = _EmKlineBreaker()

# ── 基金持仓明细 / 行业配置（#870）─────────────────────────────────────────────
# 东财基金档案-投资组合有两个端点，取数语义都是「**报告年份**」，不是日期：
#   · 持仓明细：fundf10.eastmoney.com/FundArchivesDatas.aspx?type=jjcc（HTML 片段）
#   · 行业配置：api.fund.eastmoney.com/f10/HYPZ/（``callback({...})`` 包裹的标准 JSON）
# 两者的 year 默认值在上游分别是硬编码的 "2024" / "2023"（长期未更新），**必须显式传当年**，
# 否则静默拿到两年前的旧数据（本仓实测：不传参 → 返回全为 2024 年四个季度）。
_EM_HYPZ_URL = 'https://api.fund.eastmoney.com/f10/HYPZ/'

# 行业分类体系。东财同一端点**混用两套体系且不做任何标记**：
#   · 证监会门类：单字母 A~S（境内股票）
#   · GICS 板块：两位数字 10/15/20/…（港股等）
# 两套体系语义不重叠（GICS 的「非必需消费品」在证监会门类里并入「制造业」），
# **不可合并聚合**，必须分区存储与分区展示。判定靠代码形态而非名称字符串猜测。
_HY_SCHEME_CSRC = 'csrc'
_HY_SCHEME_GICS = 'gics'
_HY_SCHEME_UNKNOWN = 'unknown'

# 披露口径：季报（Q1/Q3）只披露前十大；半年报/年报（Q2/Q4）披露全量（东财服务端上限 100 条）
_BASIS_TOP10 = 'top10'
_BASIS_FULL = 'full'

_QUARTER_END_MONTH_DAY = {1: '-03-31', 2: '-06-30', 3: '-09-30', 4: '-12-31'}
# 实测季度标签形如 '2026年2季度股票投资明细'（前后还有基金简称、来源、截止日等噪声）
_REPORT_PERIOD_RE = re.compile(r'(\d{4})\s*年\s*(\d)\s*季度')


def _to_float(value) -> float:
    """宽松转 float：容忍东财字段里的 ``%``、千分位与 NaN（NaN 归 0，避免污染数值列）。"""
    try:
        num = float(str(value).replace('%', '').replace(',', '').strip())
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(num) else num


def parse_report_period(label) -> Optional[tuple]:
    """从东财季度标签解析 ``(year, quarter)``；解析不出返回 ``None``（调用方丢弃该行）。"""
    match = _REPORT_PERIOD_RE.search(str(label or ''))
    if not match:
        return None
    year, quarter = int(match.group(1)), int(match.group(2))
    return (year, quarter) if 1 <= quarter <= 4 else None


def format_report_period(period: tuple) -> str:
    """``(2026, 2)`` → ``'2026Q2'``（报告期即版本键）。"""
    return f'{period[0]}Q{period[1]}'


def report_period_date(period: tuple) -> date:
    """``(2026, 2)`` → ``date(2026, 6, 30)``（报告期截止日）。"""
    return date.fromisoformat(f'{period[0]}{_QUARTER_END_MONTH_DAY[period[1]]}')


def holding_basis_of(quarter: int) -> str:
    """报告期 → 披露口径：Q2/Q4 全量，Q1/Q3 仅前十大。"""
    return _BASIS_FULL if quarter in (2, 4) else _BASIS_TOP10


def industry_scheme_of(industry_code) -> str:
    """行业代码 → 分类体系（单字母 A~S = 证监会门类；纯数字 = GICS 板块）。"""
    code = str(industry_code or '').strip().upper()
    if len(code) == 1 and 'A' <= code <= 'S':
        return _HY_SCHEME_CSRC
    if code.isdigit():
        return _HY_SCHEME_GICS
    return _HY_SCHEME_UNKNOWN


class AkshareAdapter(DataSourceAdapter):
    def __init__(self):
        self._fund_manager_cache = None
        # 是否已发起过全量拉取（注意：不能用 hasattr(_fund_manager_cache) 判定，
        # 该属性在 __init__ 即存在，会导致「首次拉取」分支永不执行、经理同步恒空转）
        self._fund_manager_fetched = False
        self.logger = logger.bind(adapter='akshare')

    def get_name(self) -> str:
        return 'akshare'

    def get_version(self) -> str:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        return getattr(ak, '__version__', 'unknown')

    # ── 股票列表 ──

    # app/services/adapters/akshare_adapter.py

    def _parse_fund_info_dataframe(self, df, fund_code: str) -> Dict[str, Any]:
        """
        将 ak.fund_info_ths 返回的 DataFrame 解析为结构化字典。
        返回空字典表示解析失败。
        """
        if df is None or df.empty:
            self.logger.warning(f'fund_info_ths 返回空: {fund_code}')
            return {}

        # 列名是 "字段" 和 "值"
        if '字段' not in df.columns or '值' not in df.columns:
            self.logger.warning(f'fund_info_ths 列名异常: {df.columns.tolist()}')
            return {}

        info = dict(zip(df['字段'], df['值']))
        if not info:
            return {}

        result = dict()
        result['fund_type_raw'] = info.get('投资类型', '') or info.get('基金类型', '')
        result['company_name'] = info.get('基金管理人', '')
        result['fund_full_name'] = info.get('基金全称', '')
        raw_date = info.get('成立日期', '')
        if raw_date:
            try:
                result['create_time'] = datetime.strptime(raw_date.strip(), '%Y-%m-%d').date()
            except (ValueError, IndexError):
                self.logger.warning(f'{fund_code} 成立日期解析失败: {raw_date}')
        benchmark = info.get('业绩比较基准', '')
        if benchmark and benchmark != '无':
            result['benchmark'] = benchmark
        manager_names = info.get('基金经理', '')
        if manager_names:
            result['manager_names'] = [n.strip() for n in manager_names.split(',') if n.strip()]
        return result

    def fetch_stock_price(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        """获取场内证券历史日线（按品类分派数据源：股票 / ETF / 可转债）。

        口径（#1104 场内拍板）：`close` 存**未复权**收盘价——最新价展示、持仓盈亏、
        每日收益日历都用它；`adj_close` 存**前复权**收盘价——区间收益 / 回撤 /
        收益率曲线用它。两者不可混用：前复权价在分红除权时会整体重算，若拿它当
        「当日收盘价」写进 `positions.current_price`，历史值与盈亏会随之漂移
        （原实现 `adjust='qfq'` 且 `adj_close` 直接等于 `close`，等于没有区分口径）。

        数据源：
        - 股票：新浪 `stock_zh_a_daily`（沪 `sh600519` / 深 `sz000001`）
        - ETF：腾讯 `stock_zh_a_hist_tx`（主，支持服务端复权）→ 东财 `fund_etf_hist_em`
          （备，带熔断）→ 新浪 `fund_etf_hist_sina`（保底，无复权）——主源切换依据
          见 `_fetch_etf_frame` docstring；`source` 按**实际命中**的源打标
        - 可转债：新浪 `bond_zh_hs_cov_daily`，不做复权（转股 / 强赎不改变历史成交价）

        Returns:
            包含字段: symbol, trade_date, open, high, low, close, volume, adj_close, source
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        market, code = split_symbol(symbol)
        if not market or not code:
            logger.warning(f'无法解析场内代码: {symbol}')
            return []

        # 调用方显式给出窗口时才一律本地裁剪；未给出时沿用「数据源返回即结果」的原契约
        explicit_window = start_date is not None or end_date is not None
        if start_date is None:
            start_date = date.today() - timedelta(days=365)
        if end_date is None:
            end_date = date.today()

        sec_type = derive_security_type(code, market) or 'stock'
        try:
            raw, raw_source = self._fetch_daily_frame(ak, sec_type, market, code, start_date, end_date, adjust='')
            if raw is None or raw.empty:
                logger.info(f'{symbol} 在 {start_date} ~ {end_date} 无行情数据')
                return []

            adj_map = self._fetch_adj_close_map(ak, sec_type, market, code, start_date, end_date)

            records = []
            for _, row in raw.iterrows():
                trade_date = self._to_date(row.get('date'))
                close = self._num(row.get('close'))
                if trade_date is None or close is None:
                    continue
                # 本地区间裁剪：可转债接口（bond_zh_hs_cov_daily）与 ETF 的新浪保底
                # **不接受日期参数**，会一次吐回全部历史（实测 1231 行），不裁就会把
                # 无关历史整段搬去写库；股票与 ETF 的腾讯/东财已由接口按参数过滤。
                if (explicit_window or sec_type in _NO_WINDOW_SEC_TYPES) and (
                    trade_date < start_date or trade_date > end_date
                ):
                    continue
                volume = self._num(row.get('volume'))
                # 东财 ETF K 线的成交量单位是「手」，腾讯/新浪是「股」——统一按「股」
                # 入库，否则备源切换会在同一序列里留下 ~100 倍断崖（2026-10-14 实测
                # 三只 ETF 均为 ×100；库里 SH563530 已存在新浪回退写入的「股」行）
                if volume is not None and sec_type == 'etf' and raw_source == 'akshare_em':
                    volume *= 100
                records.append(
                    {
                        'symbol': symbol,
                        'trade_date': trade_date,
                        'open': self._num(row.get('open')),
                        'high': self._num(row.get('high')),
                        'low': self._num(row.get('low')),
                        'close': close,
                        'volume': volume,
                        # 前复权价缺失时回退未复权价，宁可口径降级也不留空
                        'adj_close': adj_map.get(trade_date, close),
                        # 按实际命中的源打标（此前 ETF 一律硬编码 akshare_em，新浪
                        # 回退写入的行也被错标，产品详情页脚注会指错数据来源）
                        'source': raw_source,
                    }
                )

            logger.debug(f'{symbol}({sec_type}) 获取到 {len(records)} 条行情')
            return records

        except Exception as e:
            logger.error(f'获取 {symbol} 历史行情失败: {e}')
            return []

    # 东财日线中文列 → 统一英文列（新浪两个接口本身已是英文列）
    _EM_DAILY_COLUMN_MAP = {
        '日期': 'date',
        '开盘': 'open',
        '收盘': 'close',
        '最高': 'high',
        '最低': 'low',
        '成交量': 'volume',
    }

    def _fetch_daily_frame(
        self, ak, sec_type: str, market: str, code: str, start_date: date, end_date: date, adjust: str
    ):
        """按品类取日线 DataFrame，列名统一为 date/open/high/low/close/volume（#1104）。

        返回 ``(df, source)``——source 是实际命中的数据源码（`akshare_tx` /
        `akshare_em` / `akshare_sina`），供入库打标；取不到数据时为 ``(None, '')``。
        """
        if sec_type == 'etf':
            df, source = self._fetch_etf_frame(ak, market, code, start_date, end_date, adjust)
        elif sec_type == 'bond':
            # 可转债接口无复权参数
            df = ak.bond_zh_hs_cov_daily(symbol=f'{market.lower()}{code}')
            source = 'akshare_sina'
        else:
            df = ak.stock_zh_a_daily(
                symbol=f'{market.lower()}{code}',
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                adjust=adjust,
            )
            source = 'akshare_sina'
        # rename 对不存在的列无副作用：新浪两接口本身是英文列，东财是中文列
        return (None if df is None else df.rename(columns=self._EM_DAILY_COLUMN_MAP)), source

    def _fetch_etf_frame(self, ak, market: str, code: str, start_date: date, end_date: date, adjust: str):
        """ETF 日线：腾讯优先（支持复权），失败回退东财（备源，带熔断），再退新浪（无复权）。

        为什么主源是腾讯（2026-10-14 拍板）：
        - 东财 push2his 对本机 IP 级封锁反复发作（2026-09-22 时通时断、10-01、
          10-14 全断，akshare 社区同类 issue 2 年 12+ 条），腾讯源社区 3 年 0 封禁投诉；
        - 数据质量实测零差异：3 只 ETF × 252 天重叠，close 与 qfq 均与东财逐位一致
          （2026-10-14 交叉验证）；
        - 腾讯支持服务端 qfq/hfq、接受日期参数、新鲜度到当日盘中，不输东财。

        回退语义：
        - 新浪保底（fund_etf_hist_sina）不支持复权参数，仅 adjust='' 时可用；
          复权请求在腾讯与东财都失败时返回 None，由 `_fetch_adj_close_map` 让
          adj_close 回退 close；
        - 新浪源返回全历史且无日期参数，区间裁剪由 `fetch_stock_price` 统一完成；
        - 东财连续连接级失败会触发模块级熔断（见 `_EmKlineBreaker`）：打开期间
          跳过东财直接走新浪保底，不再白烧重试。

        腾讯源按年份分页、带 tqdm 进度条输出（增量窗口通常只触发 1~2 次请求），量级可接受。
        返回 ``(df, source)``；三源皆空时 adjust='' 返回 (空 df 或 None, '')。
        """
        tx_symbol = f'{market.lower()}{code}'
        # 1) 腾讯主源（支持 adjust='' / 'qfq' / 'hfq'，YYYYMMDD 窗口）
        try:
            df = ak.stock_zh_a_hist_tx(
                symbol=tx_symbol,
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust=adjust,
            )
            if df is not None and not df.empty:
                return df, 'akshare_tx'
        except Exception as e:
            self.logger.warning(f'腾讯 ETF 日线失败（{code} adjust={adjust!r}）: {e}')

        # 2) 东财备源（熔断器管辖）
        now = time.time()
        if _em_kline_breaker.should_skip(now):
            self.logger.debug(f'东财熔断打开中，跳过 {code} adjust={adjust!r} 的东财请求')
        else:
            try:
                df = ak.fund_etf_hist_em(
                    symbol=code,
                    period='daily',
                    start_date=start_date.strftime('%Y%m%d'),
                    end_date=end_date.strftime('%Y%m%d'),
                    adjust=adjust,
                )
                if df is not None and not df.empty:
                    _em_kline_breaker.record_success()
                    return df, 'akshare_em'
            except Exception as e:
                # 仅连接级异常计入熔断；解析错等业务异常不影响熔断状态
                if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
                    _em_kline_breaker.record_connection_failure(now)
                self.logger.warning(f'东财 ETF 日线失败（{code} adjust={adjust!r}）: {e}')

        # 3) 新浪保底（无复权，仅 adjust=''；异常向上抛，由 fetch_stock_price 统一兜底）
        if adjust:
            return None, ''
        df = ak.fund_etf_hist_sina(symbol=tx_symbol)
        return (df, 'akshare_sina') if df is not None else (None, '')

    def _fetch_adj_close_map(self, ak, sec_type: str, market: str, code: str, start_date: date, end_date: date) -> dict:
        """前复权收盘价 {trade_date: close}；取不到返回空 dict，由调用方回退 close。"""
        if sec_type == 'bond':
            return {}
        try:
            df, _source = self._fetch_daily_frame(ak, sec_type, market, code, start_date, end_date, adjust='qfq')
            if df is None or df.empty:
                return {}
            out = {}
            for _, row in df.iterrows():
                d = self._to_date(row.get('date'))
                c = self._num(row.get('close'))
                if d is not None and c is not None:
                    out[d] = c
            return out
        except Exception as e:
            self.logger.warning(f'{code} 前复权价获取失败，adj_close 回退 close: {e}')
            return {}

    @staticmethod
    def _to_date(value) -> Optional[date]:
        """宽松转 date：兼容 datetime / date / 'YYYY-MM-DD' / 'YYYYMMDD'。"""
        if value is None:
            return None
        if isinstance(value, datetime):  # datetime 是 date 的子类，须先判
            return value.date()
        if isinstance(value, date):
            return value
        s = str(value).strip()
        if not s:
            return None
        for fmt in ('%Y-%m-%d', '%Y%m%d'):
            try:
                return datetime.strptime(s[:10], fmt).date()
            except ValueError:
                continue
        return None

    def fetch_stock_list(self, market: Optional[str] = None) -> List[dict]:
        """获取 A 股股票（含沪深北）"""
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        try:
            df = ak.stock_info_a_code_name()
            if df is None or df.empty:
                return []

            normalizer = get_normalizer()
            records = []
            for _, row in df.iterrows():
                raw_code = str(row['code'])
                normalized, mkt, _ = normalizer.normalize(raw_code)
                if normalized:
                    records.append(
                        {
                            'symbol': normalized,
                            'name': str(row['name']),
                            'market': mkt or 'CN_A',
                            'type': 'stock',
                            'currency': 'CNY',
                        }
                    )
            return records
        except Exception as e:
            logger.error(f'获取股票列表失败: {e}')
            return []

    def fetch_security_catalog(self) -> List[dict]:
        """场内证券名录：A 股个股 + ETF + 可转债，三源合并（#1104）。

        为什么需要它：securities 表原先只登记 A 股个股（实测 5525 条全是 type='stock'），
        而 `PriceHistorySyncJob._get_security_map` 按 symbol 查该表，查不到直接 continue
        —— 持仓里的 8 只 ETF、8 只可转债因此**永远拿不到日线**（实测 price_history 0 行），
        自选页「最新价」只能回落到导入当天的快照。本方法是整条场内日线链路的前置。

        symbol 一律归一为「交易所前缀 + 6 位代码」，与持仓/自选的存储规范一致
        （`SZ159857` 而非 `159857`）——否则名录登记了也对不上目标池。
        单个子源失败只告警不抛错，不影响其余两源（名录属于可重建的元数据）。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        records: List[dict] = []
        seen = set()

        def _add(raw_code, raw_name, sec_type: str) -> None:
            code = str(raw_code or '').strip()
            market = market_of_cn_a_code(code)
            if not code or not market:
                return
            symbol = f'{market}{code}'
            if symbol in seen:
                return
            seen.add(symbol)
            records.append(
                {
                    'symbol': symbol,
                    'name': (str(raw_name or '').strip() or symbol)[:100],
                    'market': 'CN_A',
                    'type': sec_type,
                    'currency': 'CNY',
                }
            )

        # 1) A 股个股：沿用既有 normalizer 链路，保证与存量 symbol 规范完全一致
        for item in self.fetch_stock_list():
            sym = item.get('symbol')
            if sym and sym not in seen:
                seen.add(sym)
                records.append(item)

        # 2) ETF 名录：东财 spot 优先，失败回退同花顺 ETF 名录（两源都给裸 6 位代码）。
        # 为什么必须带回退：2026-09-22 实测 fund_etf_spot_em 的 push2delay 域名
        # 直接 RemoteDisconnected，单源会让 8 只 ETF 持仓继续留在名录之外。
        etf_rows: List[tuple] = []
        try:
            df = ak.fund_etf_spot_em()
            if df is not None and not df.empty:
                etf_rows = [(self._cell(row, '代码'), self._cell(row, '名称')) for _, row in df.iterrows()]
        except Exception as e:
            self.logger.warning(f'东财 ETF 名录失败，回退同花顺: {e}')
        if not etf_rows:
            etf_rows = [(item.get('code'), item.get('name')) for item in self.fetch_etf_list_ths()]
        for raw_code, raw_name in etf_rows:
            _add(raw_code, raw_name, 'etf')

        # 3) 可转债名录（bond_zh_cov，代码为裸 6 位）
        try:
            df = ak.bond_zh_cov()
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    _add(
                        self._cell(row, '债券代码', '转债代码', '代码'),
                        self._cell(row, '债券简称', '转债简称', '名称'),
                        'bond',
                    )
        except Exception as e:
            self.logger.warning(f'获取可转债名录失败（不影响个股/ETF）: {e}')

        self.logger.info(f'场内证券名录合并完成：{len(records)} 条（个股 + ETF + 可转债）')
        return records

    def fetch_daily_spot_all(self) -> List[dict]:
        """获取全市场 A 股当日实时行情（作为日线数据），仅用于增量同步"""
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        try:
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return []

            normalizer = get_normalizer()
            records = []
            for _, row in df.iterrows():
                raw_code = str(row['代码'])
                normalized, _, _ = normalizer.normalize(raw_code)
                if not normalized:
                    continue
                records.append(
                    {
                        'symbol': normalized,
                        'trade_date': date.today(),  # 注意：非交易日可能无数据，届时由调用方处理
                        'open': row['今开'],
                        'high': row['最高'],
                        'low': row['最低'],
                        'close': row['最新价'],
                        'volume': row['成交量'],
                        'adj_close': row['最新价'],  # 当日无复权，用最新价代替
                        'source': 'akshare_spot',
                    }
                )
            return records
        except Exception as e:
            logger.error(f'获取实时行情失败: {e}')
            return []

    # ── 基金列表 ──
    def fetch_fund_list(self) -> List[dict]:
        """
        使用 akshare 官方接口获取全市场公募基金基本信息。
        接口：ak.fund_name_em() 返回所有基金的代码、简称、类型。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        try:
            # 使用 fund_name_em 替代 fund_em_fund_name（后者在当前版本中不可用）
            df = ak.fund_name_em()
            if df is None or df.empty:
                self.logger.error('akshare fund_name_em 返回空数据')
                return []

            records = []
            for _, row in df.iterrows():
                code = str(row['基金代码']).strip()
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                records.append(
                    {
                        'fund_code': code,
                        'name': row['基金简称'],
                        'fund_type': row.get('基金类型', ''),
                        'company_name': '',  # 该接口不直接提供公司名
                    }
                )
            self.logger.info(f'获取到 {len(records)} 只基金')
            return records
        except Exception as e:
            self.logger.error(f'获取基金列表失败: {e}')
            return []

    def fetch_fund_nav(
        self,
        fund_code: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[dict]:
        raise NotImplementedError

    def fetch_fund_manager(self, fund_code: str) -> List[dict]:
        """获取指定基金的基金经理，全量数据仅请求一次，失败后静默跳过

        该接口（东财 fund_manager_em）偶发抖动；此前一次失败就把缓存置 None，
        导致本轮后续所有基金都静默返回空（表现为「经理全量同步跑了但一条没进」）。
        故首次拉取做有限重试，只有连续重试均失败才标记为不可用。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        # 已经请求过（成功或失败），直接使用缓存结果
        if self._fund_manager_fetched:
            df = self._fund_manager_cache
            if df is None or df.empty:
                return []
            # 有缓存数据，按基金代码筛选
            return self._filter_managers(df, fund_code)

        # 第一次请求全量数据（带重试，规避偶发抖动）
        df = None
        for attempt in range(_FUND_MANAGER_RETRY):
            try:
                df = ak.fund_manager_em()
                break
            except Exception as e:  # noqa: BLE001
                if attempt == _FUND_MANAGER_RETRY - 1:
                    self.logger.warning(f'基金经理全量接口不可用: {e}，后续将跳过所有经理同步')
                else:
                    self.logger.warning(f'基金经理全量接口第 {attempt + 1}/{_FUND_MANAGER_RETRY} 次失败: {e}，稍后重试')
                    time.sleep(_FUND_MANAGER_RETRY_SLEEP)

        # 无论成败只拉一次：成功则缓存 df，失败则缓存 None 并跳过本轮后续基金。
        # 缺了这一步会退化为「逐基金重复全量请求」（#1286 回填实测踩坑）。
        self._fund_manager_fetched = True

        if df is None or df.empty:
            if df is not None:
                self.logger.warning('基金经理全量数据为空')
            self._fund_manager_cache = None
            return []

        self._fund_manager_cache = df
        self.logger.info(f'获取到 {len(df)} 条基金经理数据')
        return self._filter_managers(df, fund_code)

    @staticmethod
    def _opt_float(row, key: str) -> Optional[float]:
        """安全取 float：缺失 / NaN / 非数字一律 None（不返回 0，避免「没数据」被读成「真的是 0」）。

        `fund_manager_em` 这三列存在空值与 ``'--'`` 占位，故必须逐值判定，
        不能依赖 pandas 的 ``pd.to_numeric`` 批量转换后统一判断。
        """
        try:
            raw = row.get(key)
        except Exception:  # noqa: BLE001
            return None
        if raw is None:
            return None
        text = str(raw).strip()
        if not text or text in {'--', '-', 'nan', 'None'}:
            return None
        try:
            value = float(text)
        except (TypeError, ValueError):
            return None
        # NaN 自身（float('nan')）比较恒 False，须显式判定
        return None if value != value else value

    def _filter_managers(self, df, fund_code: str) -> List[dict]:
        """从全量数据中筛选某基金的经理。

        **除姓名/公司外，透传三列规模类字段**（#1970 扩展）：

        ===========================  ==================================  ==========
        源列                目标字段                实测样本
        ===========================  ==================================  ==========
        现任基金资产总规模            ``sum_scale``（亿元）张坤 307.94
        现任基金最佳回报``best_return``（%）           张坤 297.54
        累计从业时间                ``tenure_days``（**单位：天**）    张坤 5125
        ===========================  ==================================  ==========

        **为什么此前填充率是 0%**：本方法当年只回传 ``name`` / ``company`` /
        ``mgr_code``，这三列虽在 DataFrame 里却在此处被丢弃，下游 ``_save_data``
        无从写入 —— **是写入侧的裁剪决策，不是数据源缺失**。

        **三个口径要点（改动前请读完）**：

        1. **规模与回报是「该经理全部在管基金的合计」，不是逐只基金的数字。**
           实测张坤 3 行（005827/110011/118001）的这两列**完全相同**
           （307.94 / 297.54）。故只写到 ``managers`` 单行，
           **禁止**灌进 ``fund_managers``（会造成同经理每基金一行重复同值）。
        2. **「累计从业时间」单位是天**（值域 1~8145），不是年。展示层须换算，
           且**不可用它反推 ``appointment_date``** —— 那会造出假日期。
           故本方法不产出日期，只产出 ``tenure_days``。
        3. 源列缺失 / 非数字时返回 ``None`` 而非 0，交由下游降级「—」。
        """
        try:
            filtered = df[df['现任基金代码'].str.contains(fund_code, na=False)]
            if filtered.empty:
                return []

            managers = []
            seen = set()
            import hashlib

            for _, row in filtered.iterrows():
                name = str(row['姓名'])
                company = str(row.get('所属公司', ''))
                mgr_code = hashlib.sha256(f'{name}_{company}'.encode()).hexdigest()[:12]
                if mgr_code in seen:
                    continue
                seen.add(mgr_code)
                managers.append(
                    {
                        'fund_code': fund_code,
                        'name': name,
                        'mgr_code': mgr_code,
                        'company': company,
                        'sum_scale': self._opt_float(row, '现任基金资产总规模'),
                        'best_return': self._opt_float(row, '现任基金最佳回报'),
                        'tenure_days': self._opt_float(row, '累计从业时间'),
                    }
                )
            return managers
        except Exception as e:
            self.logger.warning(f'筛选基金经理出错: {e}')
            return []

    def fetch_fund_detail(self, fund_code: str) -> Dict[str, Any]:
        """
        获取单只基金的详细信息 (ak.fund_info_ths)
        返回字典，键为 model 字段名，值为解析后的数据。解析失败返回空字典。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()

        result = {}
        try:
            df = ak.fund_info_ths(symbol=fund_code)
            if df is None or df.empty:
                self.logger.warning(f'fund_info_ths 返回空: {fund_code}')
                return result

            # 将两列 DataFrame 转换为 dict
            info = dict(zip(df['字段'], df['值']))
            if not info:
                return result

            # 基金类型 -> fund_type_id (先存原始字符串，后续由 Job 映射)
            raw_type = info.get('投资类型', '') or info.get('基金类型', '')
            result['fund_type_raw'] = raw_type

            # 基金管理人 -> company_id (Job 中根据名称查找或创建)
            company_name = info.get('基金管理人', '')
            result['company_name'] = company_name

            # 成立日期 -> create_time
            raw_date = info.get('成立日期', '')
            if raw_date:
                try:
                    result['create_time'] = datetime.strptime(raw_date.strip(), '%Y-%m-%d').date()
                except (ValueError, IndexError):
                    self.logger.warning(f'{fund_code} 成立日期解析失败: {raw_date}')

            # 业绩比较基准 -> benchmark
            benchmark = info.get('业绩比较基准', '')
            if benchmark and benchmark != '无':
                result['benchmark'] = benchmark

            # 风险等级 -> risk_level (字符串转数字)
            risk_str = info.get('风险等级', '')
            if risk_str:
                risk_mapping = {
                    '低风险': 1,
                    '中低风险': 2,
                    '中风险': 3,
                    '中高风险': 4,
                    '高风险': 5,
                }
                for key, val in risk_mapping.items():
                    if key in risk_str:
                        result['risk_level'] = val
                        break

            # 基金全称 -> full_name
            result['fund_full_name'] = info.get('基金全称', '')

            # 管理费率、最高申购费、最高赎回费可作为费率参考
            result['management_fee'] = info.get('管理费', '')  # 字符串 "1.20%"
            result['max_purchase_fee'] = info.get('最高申购费', '')
            result['max_redeem_fee'] = info.get('最高赎回费', '')

            # 基金经理姓名 -> managers (仅姓名，无编码)
            manager_names = info.get('基金经理', '')
            if manager_names:
                result['manager_names'] = [n.strip() for n in manager_names.split('、') if n.strip()]

        except Exception as e:
            self.logger.warning(f'获取基金 {fund_code} 详情失败: {e}')
        return result

    # ── 分红 / 送股（#1179） ──

    @staticmethod
    def _parse_dividend_date(value):
        if value is None:
            return None
        if isinstance(value, (date, datetime)):
            return value.date() if isinstance(value, datetime) else value
        s = str(value).strip()
        if not s or s in ('NaT', 'nan', 'None'):
            return None
        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _to_ratio(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # 基金分红指标的正则：「每10份派现金0.0500元」→ 0.05（每份）。
    # 上游把口径写进**字符串**而不是数值列，故只能解析；解析失败必须返回 None
    # 让调用方跳过该事件，**绝不能当成 0**——0 会在下游被当成「不分红」静默丢弃。
    _FUND_DIV_PER_SHARE_RE = re.compile(r'派(?:发现金|现金|发)?([\d.]+)元')
    # 股票配股比例：「10配3.0」→ 每 10 股配 3 股
    _RIGHTS_RATIO_RE = re.compile(r'10\s*配\s*([\d.]+)')

    @classmethod
    def _parse_fund_div_per_share(cls, text) -> Optional[float]:
        """「每10份派现金0.0500元」→ 0.05（每份分红，元）。解析不出来返回 None。"""
        if text is None:
            return None
        m = cls._FUND_DIV_PER_SHARE_RE.search(str(text))
        if not m:
            return None
        try:
            return float(m.group(1)) / 10.0
        except ValueError:
            return None

    @classmethod
    def _parse_rights_ratio(cls, text) -> Optional[float]:
        """「10配3.0」→ 3.0（每 10 股可配股数）。解析不出来返回 None。"""
        if text is None:
            return None
        m = cls._RIGHTS_RATIO_RE.search(str(text).replace(' ', ''))
        if not m:
            return None
        try:
            return float(m.group(1))
        except ValueError:
            return None

    def fetch_stock_dividend(self, symbol: str) -> List[dict]:
        """股票分红/送转实施方案（ak.stock_dividend_cninfo）。

        一条方案可能**同时**含派息与送转（「10送3股派0.6元」实测常见），故这里不再
        折算成一个 ratio 组，而是把它拆成 `cash_ratio` / `bonus_ratio` /
        `transfer_ratio` 三个独立比例原样带出，由 job 决定拆几条流水（#541）。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        # 巨潮接口只认**裸 6 位码**：传 `SH600000` 会返回一张缺列的空表，
        # 报错还写成 `'实施方案公告日期'`（KeyError），完全指不到「代码带了前缀」这个真因
        # ——#541 实测踩到，表现为「这只股票的历年分红一条都抓不到」。
        bare_code = str(symbol or '').strip().upper()
        bare_code = bare_code[2:] if bare_code[:2] in ('SH', 'SZ', 'BJ') else bare_code
        try:
            df = ak.stock_dividend_cninfo(symbol=bare_code)
            if df is None or df.empty:
                return []
            normalizer = get_normalizer()
            norm, _, _ = normalizer.normalize(symbol)
            out = []
            for _, row in df.iterrows():
                ex_date = self._parse_dividend_date(row.get('除权日'))
                if not ex_date:
                    continue
                bonus = self._to_ratio(row.get('送股比例'))
                transfer = self._to_ratio(row.get('转增比例'))
                cash = self._to_ratio(row.get('派息比例'))
                if bonus <= 0 and transfer <= 0 and cash <= 0:
                    # 三项全空 = 这一行没有可记账内容（股改分红等），别落一条 0 值流水
                    continue
                out.append(
                    {
                        'symbol': norm or symbol,
                        'dividend_type': str(row.get('分红类型', '')),
                        'bonus_ratio': bonus,
                        'transfer_ratio': transfer,
                        'cash_ratio': cash,
                        'regist_date': self._parse_dividend_date(row.get('股权登记日')),
                        'ex_date': ex_date,
                        'pay_date': self._parse_dividend_date(row.get('派息日')),
                        'arrive_date': self._parse_dividend_date(row.get('股份到账日')),
                        'desc': str(row.get('实施方案分红说明', '')),
                        'source': 'akshare_cninfo',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取股票 {symbol} 分红失败: {e}')
            return []

    def fetch_fund_dividend(self, fund_code: str) -> List[dict]:
        """基金分红送配详情（ak.fund_open_fund_info_em，indicator='分红送配详情'）。

        为什么换源（#541）：原先用的 `fund_announcement_dividend_em` 只给**公告日期 + 标题**，
        既无除息日也无每份分红额，下游 `amount=0` 被导入校验剔除——基金分红一条都到不了库。
        本接口给「权益登记日 / 除息日 / 每10份分红 / 发放日」，可按份额算出真实金额。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator='分红送配详情')
            if df is None or df.empty or '除息日' not in df.columns:
                return []
            out = []
            for _, row in df.iterrows():
                per_share = self._parse_fund_div_per_share(row.get('每10份分红'))
                if per_share is None or per_share <= 0:
                    # 解析不出每份分红 → 跳过：落 0 金额流水等于假数据（见同名回归用例）
                    self.logger.debug(f'基金 {fund_code} 分红无每份金额，跳过: {row.get("每10份分红")}')
                    continue
                ex_date = self._parse_dividend_date(row.get('除息日')) or self._parse_dividend_date(
                    row.get('权益登记日')
                )
                if not ex_date:
                    continue
                out.append(
                    {
                        'symbol': fund_code,
                        'ex_date': ex_date,
                        'regist_date': self._parse_dividend_date(row.get('权益登记日')),
                        'pay_date': self._parse_dividend_date(row.get('分红发放日')),
                        'per_share': per_share,
                        'desc': str(row.get('每10份分红', '')),
                        'source': 'akshare_fund_fh',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取基金 {fund_code} 分红失败: {e}')
            return []

    def fetch_fund_split(self, fund_code: str) -> List[dict]:
        """基金拆分（ak.fund_open_fund_info_em，indicator='基金拆分'）。

        拆分与分红是两件事：分红是现金落袋，拆分是份额按比例放大、净值同比例缩小
        （成本不变）。落库走 `split`（零成本份额增加），与送股同口径。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_open_fund_info_em(symbol=fund_code, indicator='基金拆分')
            if df is None or df.empty or '拆分折算日' not in df.columns:
                return []
            out = []
            for _, row in df.iterrows():
                d = self._parse_dividend_date(row.get('拆分折算日'))
                ratio = self._to_ratio(row.get('拆分折算比例'))
                if not d or ratio <= 0:
                    continue
                out.append(
                    {
                        'symbol': fund_code,
                        'ex_date': d,
                        'split_ratio': ratio,  # 每 1 份 → ratio 份
                        'desc': f'基金拆分 1:{ratio}',
                        'source': 'akshare_fund_split',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取基金 {fund_code} 拆分失败: {e}')
            return []

    def fetch_stock_rights_issue(self, symbols: Optional[List[str]] = None) -> List[dict]:
        """配股方案（ak.stock_pg_em，单次返回全市场全历史）。

        一次请求拿全市场，故**必须由调用方按持仓过滤**（数据策略：抓取目标池显式）。
        返回项含「配股比例 / 配股价 / 股权登记日 / 缴款起止 / 上市日」——这四项正好够
        算出「该缴多少钱」与「该到多少股」，无需再找第二源。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.stock_pg_em()
            if df is None or df.empty:
                return []
            wanted = {str(s).strip() for s in symbols} if symbols else None
            normalizer = get_normalizer()
            out = []
            for _, row in df.iterrows():
                code = str(row.get('股票代码', '')).strip()
                if not code:
                    continue
                if wanted is not None and code not in wanted and f'{code}' not in {w[-6:] for w in wanted}:
                    continue
                ratio = self._parse_rights_ratio(row.get('配股比例'))
                price = self._to_ratio(row.get('配股价'))
                regist = self._parse_dividend_date(row.get('股权登记日'))
                if not ratio or not price or not regist:
                    # 三项缺一都无法算出缴款金额，跳过——宁可漏记也不写猜出来的数字
                    continue
                norm, _, _ = normalizer.normalize(code)
                out.append(
                    {
                        'symbol': norm or code,
                        'name': str(row.get('股票简称', '')),
                        'rights_ratio': ratio,  # 每 10 股配 ratio 股
                        'rights_price': price,  # 配股价（元/股）
                        'regist_date': regist,
                        'pay_start': self._parse_dividend_date(row.get('缴款起始日期')),
                        'pay_end': self._parse_dividend_date(row.get('缴款截止日期')),
                        'list_date': self._parse_dividend_date(row.get('上市日')),
                        'desc': f'10配{ratio}，配股价{price}元',
                        'source': 'akshare_pg',
                    }
                )
            return out
        except Exception as e:
            self.logger.error(f'获取配股方案失败: {e}')
            return []

    # ── 基金规模 / 近似股票仓位（#1286 数据底座，复用 akshare 现成接口） ──

    def fetch_fund_scale(self) -> List[dict]:
        """全市场开放式基金规模（ak.fund_scale_open_sina）。

        接口仅给「最近总份额」与「单位净值」，不直接给规模列；规模由调用方按
        shares×nav 估算（亿元）。返回 [{fund_code, shares, nav}]。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_scale_open_sina()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(row.get('基金代码', '')).strip()
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                out.append(
                    {
                        'fund_code': code,
                        'shares': self._to_ratio(row.get('最近总份额')),
                        'nav': self._to_ratio(row.get('单位净值')),
                    }
                )
            self.logger.info(f'获取到 {len(out)} 只基金规模数据')
            return out
        except Exception as e:
            self.logger.error(f'获取基金规模失败: {e}')
            return []

    def fetch_fund_top_holdings(self, fund_code: str, year: Optional[int] = None) -> Dict[str, Any]:
        """单只基金**最近一期**的持仓明细（ak.fund_portfolio_hold_em / 东财基金档案）。

        返回::

            {
                'fund_code': '110022',
                'report_period': '2026Q2',      # 报告期（版本键）
                'report_date': date(2026, 6, 30),
                'holding_basis': 'full',        # 'full'（半年报/年报）| 'top10'（季报）
                'holdings': [
                    {'stock_code', 'stock_name', 'ratio'（占净值比例 %）,
                     'shares'（万股）, 'market_value'（万元）, 'rank'},
                    ...
                ],
            }

        抓不到（无持仓数据 / 解析失败）返回 ``{}`` —— **不是空列表**，语义是「无源数据」，
        调用方据此跳过并保留原值，避免用 0 覆盖掉已有数据。

        两处必须显式处理的坑（#870 打点实测，akshare 1.18.91）：

        1. **``date`` 参数在上游被硬编码为 ``"2024"``**（akshare 源码
           ``fund_portfolio_hold_em(symbol, date: str = "2024")``，两年未更新）。不传参就
           静默拿到两年前的旧数据。且接口按**报告年份**查询，1 月时当年报告尚未披露，
           故当年取空时回退上一年。
        2. **返回的 DataFrame 是按报告期升序拼接的多期明细**（akshare 内部
           ``pd.concat([temp_df, big_df])`` 逐期前插，把每期都挤到已累积数据之前），
           因此 ``df.head(10)`` 命中的是**最老一期**而非最新。此处按 ``季度`` 列显式分组
           取 ``max()``，不依赖行序。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        current_year = year or datetime.now().year
        for probe_year in (current_year, current_year - 1):
            try:
                df = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(probe_year))
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f'基金 {fund_code} 持仓抓取失败（{probe_year}）: {e}')
                continue
            parsed = self._parse_fund_holdings_df(df, fund_code)
            if parsed:
                return parsed
        return {}

    @staticmethod
    def _parse_fund_holdings_df(df, fund_code: str) -> Dict[str, Any]:
        """把 akshare 的多期持仓 DataFrame 收敛为「最近一期」明细（见上方法说明第 2 点）。"""
        if df is None or getattr(df, 'empty', True) or '季度' not in df.columns:
            return {}

        grouped: Dict[tuple, List[Any]] = {}
        for _, row in df.iterrows():
            period = parse_report_period(row.get('季度'))
            if period is None:
                continue
            grouped.setdefault(period, []).append(row)
        if not grouped:
            return {}

        latest = max(grouped)  # (year, quarter) 元组比较即「最近一期」
        holdings = []
        for rank, row in enumerate(grouped[latest], start=1):
            stock_code = str(row.get('股票代码', '') or '').strip()
            if not stock_code:
                continue
            holdings.append(
                {
                    # 港股代码是 5 位（如 '00700'）、A 股 6 位，统一原样保留，不做补零
                    'stock_code': stock_code,
                    'stock_name': str(row.get('股票名称', '') or '').strip(),
                    'ratio': _to_float(row.get('占净值比例')),
                    'shares': _to_float(row.get('持股数')),
                    'market_value': _to_float(row.get('持仓市值')),
                    'rank': rank,
                }
            )
        if not holdings:
            return {}
        return {
            'fund_code': fund_code,
            'report_period': format_report_period(latest),
            'report_date': report_period_date(latest),
            'holding_basis': holding_basis_of(latest[1]),
            'holdings': holdings,
        }

    def fetch_fund_industry_allocation(self, fund_code: str, year: Optional[int] = None) -> Dict[str, Any]:
        """单只基金**最近一期**的行业配置（东财 api.fund.eastmoney.com/f10/HYPZ/）。

        返回::

            {
                'fund_code': '110022',
                'report_period': '2026Q2',
                'report_date': date(2026, 6, 30),
                'items': [{'industry_code', 'industry_name', 'scheme', 'ratio'}, ...],
            }

        抓不到返回 ``{}``。与持仓明细一样，当年取空时回退上一年。

        **为什么不用 akshare 的 ``fund_portfolio_industry_allocation_em``**：该封装把列名
        硬编码成固定 17 项，遇到无数据的基金（QDII 实测 ``QuarterInfos`` 恒为空）会在
        ``pd.DataFrame([])`` 上抛 ``Length mismatch: Expected axis has 1 elements, new values
        have 17``——**空数据被当成异常抛掉**。此处直读 JSON，空数据即空结果。

        *对行业穿透的意义*：证监会要求季报**也**披露行业分类比例（个股只要求前十大），
        实测 Q1 亦有完整行业行，故**行业层在任何报告期都不失真**，只有个股层受季报限制。

        另注：响应里的 ``市值`` 字段单位不统一（实测同库并存 1e9 与 1e5 两个量级），
        因此**只取 ``占净值比例``**，不落市值。
        """
        current_year = year or datetime.now().year
        for probe_year in (current_year, current_year - 1):
            payload = self._fetch_em_industry_payload(fund_code, probe_year)
            parsed = self._parse_em_industry_payload(payload, fund_code)
            if parsed:
                return parsed
        return {}

    def _fetch_em_industry_payload(self, fund_code: str, year: int) -> Optional[dict]:
        """请求东财行业配置端点。响应是 ``callback({...})``，剥壳后即为标准 JSON。"""
        import requests

        try:
            resp = requests.get(
                _EM_HYPZ_URL,
                params={'fundCode': fund_code, 'year': str(year), 'callback': 'callback'},
                # 进程内 core/requests_patch 已全局注入东财浏览器头 + nid cookie + 重试，故只补 Referer
                headers={'Referer': 'https://fundf10.eastmoney.com/'},
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            self.logger.warning(f'基金 {fund_code} 行业配置请求失败（{year}）: {e}')
            return None

        text = resp.text or ''
        start, end = text.find('('), text.rfind(')')
        body = text[start + 1 : end] if 0 <= start < end else text
        try:
            return json.loads(body)
        except (TypeError, ValueError) as e:
            self.logger.warning(f'基金 {fund_code} 行业配置 JSON 解析失败（{year}）: {e}')
            return None

    @staticmethod
    def _parse_em_industry_payload(payload, fund_code: str) -> Dict[str, Any]:
        """把 HYPZ 响应收敛为「最近一期」行业条目（按 ``Quarter`` + ``JZRQ`` 定版本）。"""
        if not isinstance(payload, dict):
            return {}
        data = payload.get('Data') or {}
        quarters = data.get('QuarterInfos') or []

        grouped: Dict[tuple, dict] = {}
        for quarter in quarters:
            if not isinstance(quarter, dict):
                continue
            jzrq = str(quarter.get('JZRQ') or '').strip()
            try:
                quarter_num = int(str(quarter.get('Quarter') or '').strip())
            except (TypeError, ValueError):
                continue
            if len(jzrq) >= 4 and jzrq[:4].isdigit() and 1 <= quarter_num <= 4:
                grouped[(int(jzrq[:4]), quarter_num)] = quarter
        if not grouped:
            return {}

        latest = max(grouped)
        quarter = grouped[latest]
        items = []
        for info in quarter.get('HYPZInfo') or []:
            if not isinstance(info, dict):
                continue
            industry_code = str(info.get('HYDM') or '').strip()
            industry_name = str(info.get('HYMC') or '').strip()
            if not industry_code and not industry_name:
                continue
            items.append(
                {
                    'industry_code': industry_code,
                    'industry_name': industry_name,
                    'scheme': industry_scheme_of(industry_code),
                    'ratio': _to_float(info.get('ZJZBL')),
                }
            )
        if not items:
            return {}
        try:
            report_date = date.fromisoformat(str(quarter.get('JZRQ') or '').strip())
        except ValueError:
            report_date = report_period_date(latest)
        return {
            'fund_code': fund_code,
            'report_period': format_report_period(latest),
            'report_date': report_date,
            'items': items,
        }

    def fetch_index_constituents_csindex(self, index_code: str) -> List[dict]:
        """中证系指数成分（ak.index_stock_cons_csindex）。

        返回 [{symbol, stock_name, index_name}]；非 csindex 系列指数会抛错，由 Job 回退 sina。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_cons_csindex(symbol=index_code)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                out.append(
                    {
                        'symbol': str(row.get('成分券代码', '')).strip(),
                        'stock_name': str(row.get('成分券名称', '')),
                        'index_name': str(row.get('指数名称', '')),
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'csindex 成分获取失败 {index_code}: {e}')
            return []

    def fetch_index_constituents_sina(self, index_code: str) -> List[dict]:
        """新浪指数成分（ak.index_stock_cons），csindex 系列缺失时的回退。

        返回 [{symbol, stock_name, in_date}]。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_cons(symbol=index_code)
            if df is None or df.empty:
                return []
            has_date = '日期' in df.columns
            out = []
            for _, row in df.iterrows():
                out.append(
                    {
                        'symbol': str(row.get('品种代码', '')).strip(),
                        'stock_name': str(row.get('品种名称', '')),
                        'in_date': str(row.get('日期', '')) if has_date else None,
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'sina 成分获取失败 {index_code}: {e}')
            return []

    def fetch_index_catalog(self) -> List[dict]:
        """新浪指数名录（ak.index_stock_info），#1286/#1365 聚合搜索底座之三源之一。

        返回 [{index_code, name, exchange, source}]，归一化为 SH000300 形态。

        兼容两种 akshare 版本形态（#1366 实测）：
        - 旧版：中文列名（代码/名称），代码带 sh/sz 前缀 → 直接拆前缀；
        - 新版（≥1.18.x）：英文列名（index_code/display_name），裸 6 位码无前缀
          → 按交易所惯例归属（39 开头=SZ，其余=SH）；归属歧义由三源去重优先级
          （csindex/cni 后到覆盖不可能——sina 优先，但归属错误风险已被
          「名录仅收录指数、000xxx 沪 / 399xxx 深」的惯例约束收敛）。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_stock_info()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('index_code', '代码'))
            name_col = self._pick_col(df, ('display_name', '名称', '简称'))
            out = []
            for _, row in df.iterrows():
                raw = str(row[code_col]).strip().lower()
                if not raw:
                    continue
                exchange = ''
                if raw.startswith('sh'):
                    exchange, index_code = 'SH', raw[2:]
                elif raw.startswith('sz'):
                    exchange, index_code = 'SZ', raw[2:]
                elif len(raw) == 6 and raw.isdigit():
                    # 新版裸码：39 开头为深交所指数，其余（000/880/950 等）归沪
                    index_code = raw
                    exchange = 'SZ' if raw.startswith('39') else 'SH'
                else:
                    index_code = raw
                out.append(
                    {
                        'index_code': index_code,
                        'name': str(row[name_col]).strip(),
                        'exchange': exchange,
                        'source': 'sina',
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'新浪指数名录获取失败: {e}')
            return []

    @staticmethod
    def _pick_col(df, keywords: tuple) -> str:
        """按子串匹配 DataFrame 列名（防 akshare 版本间列名漂移 + 控制台 mojibake 误判）。"""
        for c in df.columns:
            if any(k in str(c) for k in keywords):
                return c
        raise KeyError(f'未找到含 {keywords} 的列，实际列: {list(df.columns)}')

    def fetch_index_catalog_csindex(self) -> List[dict]:
        """中证指数官网全量名录（ak.index_csindex_all），#1365 三源合并之中证源。

        中证专属代码唯一来源：930950（中证偏股基金）/932000（中证2000）/
        000510（中证A500）等。exchange 记 'CSI' 作统一编码命名空间前缀。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_csindex_all()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('指数代码', '代码'))
            name_col = self._pick_col(df, ('简称', '名称'))
            return [
                {
                    'index_code': str(r[code_col]).strip().zfill(6),
                    'name': str(r[name_col]).strip(),
                    'exchange': 'CSI',
                    'source': 'csindex',
                }
                for _, r in df.iterrows()
                if str(r[code_col]).strip()
            ]
        except Exception as e:
            self.logger.warning(f'中证指数名录获取失败: {e}')
            return []

    def fetch_etf_list(self) -> List[dict]:
        """全市场 ETF 名录（ak.fund_etf_spot_em 的 代码/名称，#1285 §3.8）。

        ⚠️ 该接口**不含「跟踪标的」字段**（2026-09-11 实测 1605 只全无），交易所 ETF
        规模表同样无标的指数 —— 故跨渠道关联只能靠**名称匹配**（见 channel_link_job）。
        返回 [{code, name}]，行情字段此处不用。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_etf_spot_em()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '代码') or '').strip()
                name = str(self._cell(row, '名称') or '').strip()
                if not code or not name:
                    continue
                out.append({'code': code, 'name': name})
            self.logger.info(f'获取到 {len(out)} 只 ETF 名录')
            return out
        except Exception as e:
            self.logger.error(f'获取 ETF 名录失败: {e}')
            return []

    def fetch_etf_list_ths(self) -> List[dict]:
        """同花顺 ETF 名录（ak.fund_etf_category_ths「基金名称」= **基金全称**，#1413）。

        为什么还要这一路：跨渠道关联靠名称匹配，而**匹配成败取决于文本源**
        （2026-09-11 实测，见 services/sync/name_match.py docstring）——
        东财 `fund_etf_spot_em` 给的是**交易所场内简称**（「通信ETF国泰」），指数名被压没了；
        同花顺给的是**基金全称**（「国泰中证全指通信设备ETF」），保留完整指数名，
        与 `index_catalog` 的名录才能对上。
        实测覆盖率：东财简称 45.2% → 同花顺全称 89.0%（毛）/ 67.3%（过滤后落库口径）。

        返回 [{code, name}]；查询失败返回空列表，由调用方回退东财简称（**不阻断**主链路）。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.fund_etf_category_ths(symbol='ETF基金')
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '基金代码') or '').strip()
                name = str(self._cell(row, '基金名称') or '').strip()
                if not code or not name:
                    continue
                out.append({'code': code, 'name': name})
            self.logger.info(f'获取到 {len(out)} 只 ETF 全称名录（同花顺）')
            return out
        except Exception as e:
            self.logger.warning(f'获取同花顺 ETF 名录失败（回退东财简称）: {e}')
            return []

    def fetch_index_valuation_csindex(self, index_code: str) -> List[dict]:
        """中证指数**官方**估值（ak.stock_zh_index_value_csindex，#1285/#1394）。

        读 csindex OSS 的 indicator.xls；免 cookie、按指数代码。官方列名为
        「市盈率1 / 市盈率2 / 股息率1 / 股息率2」，**原样返回**不做主观口径改写
        （口径提示见 IndexValuation 模型注释）。

        注意：官方文件仅下发近约 20 个交易日，故本接口**不能**用于计算历史分位。
        无估值文件的指数会抛错，由 Job 静默跳过。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.stock_zh_index_value_csindex(symbol=index_code)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                d = self._parse_dividend_date(self._cell(row, '日期'))
                if not d:
                    continue
                out.append(
                    {
                        'index_code': index_code,
                        'index_name': str(self._cell(row, '指数中文简称', '指数中文全称') or ''),
                        'trade_date': d,
                        'pe_1': self._num(self._cell(row, '市盈率1')),
                        'pe_2': self._num(self._cell(row, '市盈率2')),
                        'dividend_yield_1': self._num(self._cell(row, '股息率1')),
                        'dividend_yield_2': self._num(self._cell(row, '股息率2')),
                        'source': 'csindex',
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'中证指数估值获取失败 {index_code}: {e}')
            return []

    # 乐咕乐股侧的中文 symbol → 裸 6 位码（#1407 分位基线）。
    # 2026-10-11 实测（akshare 1.18.91）：这 9 个宽基 PE/PB 双成功；深证成指 / 创业板指 /
    # 行业类（消费 / 医疗 / 白酒…）乐咕均 KeyError 无覆盖，A500（000510）/ 中证2000（932000）
    # 同样无源——无源指数不进基线，分位由读路径降级为 None。
    LG_INDEX_NAMES: dict[str, str] = {
        '000016': '上证50',
        '000010': '上证180',
        '000009': '上证380',
        '000015': '上证红利',
        '000300': '沪深300',
        '000903': '中证100',
        '000905': '中证500',
        '000906': '中证800',
        '000852': '中证1000',
    }

    def fetch_index_pe_lg(self, index_code: str) -> List[dict]:
        """乐咕乐股月频 PE 序列（ak.stock_index_pe_lg，#1407 分位基线）。

        返回**全历史**月频序列（实测约 21 年、260 点），近 5 年窗口的裁剪由 Job 负责
        （窗口是产品口径，不属于数据源层）。只取「滚动市盈率」单列——#1407 拍板的
        分位口径，其余 7 个口径列（等权 / 静态 / 中位数…）不落库，避免口径堆砌。

        乐咕返回月频（月末采样），**不是日频**；无覆盖的 symbol 会抛 KeyError，
        由本方法吞掉返回空列表，Job 静默跳过。
        """
        from app.core.akshare_lazy import get_akshare

        name = self.LG_INDEX_NAMES.get(index_code)
        if not name:
            return []
        ak = get_akshare()
        try:
            df = ak.stock_index_pe_lg(symbol=name)
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                d = self._parse_dividend_date(self._cell(row, '日期'))
                if not d:
                    continue
                pe = self._num(self._cell(row, '滚动市盈率'))
                if pe is None:
                    continue
                out.append(
                    {
                        'index_code': index_code,
                        'index_name': name,
                        'trade_date': d,
                        'pe_ttm': pe,
                        'source': 'lg',
                    }
                )
            return out
        except Exception as e:
            self.logger.warning(f'乐咕乐股指数 PE 获取失败 {index_code}({name}): {e}')
            return []

    def fetch_index_catalog_cni(self) -> List[dict]:
        """国证指数官网全量名录（ak.index_all_cni），#1365 三源合并之国证源。

        国证专属代码唯一来源：399303（国证2000）/399317（国证A指，
        万得全A 881001 的权威免费替代）等。exchange 记 'CNI'。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.index_all_cni()
            if df is None or df.empty:
                return []
            code_col = self._pick_col(df, ('指数代码', '代码'))
            name_col = self._pick_col(df, ('简称', '名称'))
            return [
                {
                    'index_code': str(r[code_col]).strip().zfill(6),
                    'name': str(r[name_col]).strip(),
                    'exchange': 'CNI',
                    'source': 'cni',
                }
                for _, r in df.iterrows()
                if str(r[code_col]).strip()
            ]
        except Exception as e:
            self.logger.warning(f'国证指数名录获取失败: {e}')
            return []

    # ── 可转债条款（#1285 消费侧 / #1393） ──

    @staticmethod
    def _num(value) -> Optional[float]:
        """宽松转 float，缺失/不可解析返回 None（区别于 _to_ratio 的 0.0 兜底）。"""
        if value is None:
            return None
        s = str(value).strip()
        if s in ('', 'nan', 'None', '--', '-'):
            return None
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int(value) -> Optional[int]:
        """宽松转 int（强赎天计数等），缺失返回 None。"""
        f = AkshareAdapter._num(value)
        return int(f) if f is not None else None

    @staticmethod
    def _cell(row, *keys):
        """按候选列名宽松取值（防 akshare 版本间列名漂移）；全缺返回 None。"""
        for k in keys:
            if k in row.index:
                v = row[k]
                if v is not None and str(v).strip() not in ('', 'nan', 'None', '--'):
                    return v
        return None

    @staticmethod
    def _parse_redeem_count(value):
        """解析集思录强赎天计数，形如 `3/15 | 3` → (3, 15)：(已达天数, 触发所需天数)。"""
        if value is None:
            return (None, None)
        m = re.search(r'(\d{1,2})\s*/\s*(\d{1,2})', str(value))
        if m:
            return (int(m.group(1)), int(m.group(2)))
        return (AkshareAdapter._int(value), None)

    def fetch_convertible_bond_redeem(self) -> List[dict]:
        """集思录可转债强赎数据（ak.bond_cb_redeem_jsl）。

        覆盖静态条款主集：现价、正股、规模 / 剩余规模、转股价、强赎触发价、
        **强赎天计数**、强赎条款。返回键为 canonical 字段名，Job 负责归一 symbol。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.bond_cb_redeem_jsl()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '代码', '转债代码') or '').strip()
                if not code:
                    continue
                count, required = self._parse_redeem_count(self._cell(row, '强赎天计数'))
                out.append(
                    {
                        'bond_code': code.zfill(6),
                        'name': str(self._cell(row, '名称', '转债名称') or ''),
                        'price': self._num(self._cell(row, '现价', '转债现价')),
                        'stock_name': str(self._cell(row, '正股名称', '正股简称') or ''),
                        'stock_code_raw': str(self._cell(row, '正股代码') or '').strip(),
                        'issue_size': self._num(self._cell(row, '规模', '发行规模')),
                        'remain_size': self._num(self._cell(row, '剩余规模')),
                        'convert_price': self._num(self._cell(row, '转股价')),
                        'force_redeem_price': self._num(self._cell(row, '强赎触发价')),
                        'redeem_trigger_ratio': self._num(self._cell(row, '强赎触发比')),
                        'redeem_count': count,
                        'redeem_required': required,
                        'redeem_status': str(self._cell(row, '强赎状态') or '') or None,
                        'redeem_clause': str(self._cell(row, '强赎条款') or '') or None,
                        # 集思录强赎接口直接给到期日 → 剩余年限可由前端/服务端现算，无需另找数据源
                        'maturity_date': self._cell(row, '到期日'),
                        'source': 'akshare_jsl',
                    }
                )
            self.logger.info(f'获取到 {len(out)} 条可转债强赎数据')
            return out
        except Exception as e:
            self.logger.error(f'获取可转债强赎数据失败: {e}')
            return []

    def fetch_convertible_bond_basic(self) -> List[dict]:
        """可转债基本信息（ak.bond_zh_cov）：评级 / 到期日。

        列名可能随 akshare 版本漂移，故宽松取列；缺失项返回 None，由 Job 与强赎
        数据按 bond_code 合并（不强求齐全）。接口不可用时返回空，不影响主链路。
        """
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            df = ak.bond_zh_cov()
            if df is None or df.empty:
                return []
            out = []
            for _, row in df.iterrows():
                code = str(self._cell(row, '债券代码', '转债代码', '代码') or '').strip()
                if not code:
                    continue
                out.append(
                    {
                        'bond_code': code.zfill(6),
                        'name': str(self._cell(row, '债券简称', '转债简称', '名称') or ''),
                        # 东财 RPT_BOND_CB_LIST 列名（akshare 1.18.91 实测）
                        'rating': self._cell(row, '信用评级', '债券评级'),
                        'issue_size': self._num(self._cell(row, '发行规模')),
                        'convert_price': self._num(self._cell(row, '转股价')),
                        'convert_value': self._num(self._cell(row, '转股价值')),
                        'premium_rate': self._num(self._cell(row, '转股溢价率')),
                        'stock_name': str(self._cell(row, '正股简称', '正股名称') or ''),
                        'stock_code_raw': str(self._cell(row, '正股代码') or '').strip(),
                        'source': 'akshare_bond_zh_cov',
                    }
                )
            self.logger.info(f'获取到 {len(out)} 条可转债基本信息')
            return out
        except Exception as e:
            self.logger.warning(f'获取可转债基本信息失败: {e}')
            return []
