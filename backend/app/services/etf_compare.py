# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : etf_compare.py
# app/services/etf_compare.py
"""指数详情页关联 ETF 对比表（#2275 · P0：净值 / 当日涨幅 / 成交额 / 区间涨跌幅 / 跟踪差）。

数据策略与 #2278 同款：**按需抓 + TTL 缓存 + 不入库 + 可降级**——用户打开指数详情页
时才抓该指数关联 ETF（``channel_links`` 的 ``index_etf`` 关系，通常 2~10 只）的数据，
缓存窗口内重复打开零外部请求。不做全市场 ETF 入库（目标池 = 用户触达的关联标的）。

数据链（2026-10-17 实测定型，akshare 1.18.91 + 仓内 TLS 补丁）：

- **关联 ETF 清单**：本地 ``channel_links``（``related_symbols`` 服务双向查，
  ``peer_role == 'etf'`` 即对比表行集）。覆盖率约 66.4%（#1419），对比表**继承
  该边界**——列不全不是本服务的问题，页面沿用覆盖率说明。
- **最新净值**：``fund_etf_fund_daily_em``（全市场一次请求，实测 1686 行）。
  ⚠️ 列名是**动态日期**（``2026-10-16-单位净值``），且主键列叫 ``基金代码``；
  净值止于 T-1 的既有纪律不变。
- **当日涨幅 / 成交额**：``fund_etf_category_sina``（新浪，全市场一次请求）。
  ⚠️ 2026-10-17 实测东财 ``fund_etf_spot_em``（push2delay 域名）三连挂
  RemoteDisconnected——与 2026-09-22 仓内记录一致，该源不可靠，**直接用新浪**，
  不走「东财优先 + 新浪兜底」。新浪代码形态 ``sh510300`` / ``sz159915``，抽数字归一。
- **近 1 / 3 / 6 / 12 月涨跌幅**：逐只 ``direct_feeds.fetch_daily_tencent``（ETF 裸码
  路由正确：5 开头→sh、1 开头→sz，正是 ETF 代码段；给定 start_date 单页取完），
  复用 #2278 的 ``compute_period_returns`` 自然月窗口口径（参数化窗口集）。
- **跟踪差（近 1 年）**：ETF 近 1 年涨幅 − 指数近 1 年涨幅（指数侧复用
  ``build_index_returns``，自带 1h 缓存）。口径注释：两者同为「自然月回溯 12 个月
  的区间收益之差」，ETF 用场内价格（含折溢价噪声）、指数用收盘点位，差值非严格
  跟踪误差（后者需净值与指数逐日对比），作为**购买决策的粗粒度贴合度参考**足够。

缓存：整体结果 30min（盘中新浪快照会变，净值/日线日频不变，取折中）。
负结果（含「两侧全空」的 ``{'data': None}``）同样进缓存——``CacheService`` 以
``None`` 表示「未命中」，故整体包成 ``{'data': ...}`` 再存，避免每次打开详情页
都重打一轮外部请求。

边界与降级：任一字段抓取失败 → 该字段 ``None`` 前端「—」，**不阻塞整表**；
ETF 清单来自本地关系表，永远可用（哪怕外部全挂，表壳 + 名称仍在）。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from pandas import isna as pd_isna
from sqlalchemy.orm import Session

from app.core.cache import CacheService
from app.services.adapters import direct_feeds
from app.services.index_metrics import _catalog_entry, compute_period_returns
from app.services.related_symbols import build_related_symbols

# 对比表窗口（key 与前端 IndexEtfCompareRow.returns 对齐）：无 ytd/y2/y3——
# 同指数 ETF 对比场景用不到，窗口越少外部计算越省
_ETF_WINDOWS = (('m1', 1), ('m3', 3), ('m6', 6), ('y1', 12))

_ETF_COMPARE_CACHE = CacheService(namespace='index_detail')
# 整体 30min：新浪快照盘中变化 vs 净值/日线日频的折中；首批打开约 N 只 × 1 请求
_ETF_COMPARE_TTL_SECONDS = 1800
# 逐只日线回看天数：覆盖近 1 年窗口（12 个自然月 ≈ 366 天）+ 节假日余量
_ETF_HIST_LOOKBACK_DAYS = 430


# ── 纯函数：快照解析（便于确定性单测）──────────────────────────────────
def _pick_nav(df: Any) -> Dict[str, Dict[str, Any]]:
    """``fund_etf_fund_daily_em`` DataFrame → ``{裸码: {nav, nav_date, nav_change_pct}}``。

    ⚠️ 源侧主键列叫 ``基金代码``（不是 ``代码``）；单位净值列是**动态日期名**
    （``2026-10-16-单位净值``，可能有两列——取日期最新的那列）。坏行丢弃不编数。
    """
    if not hasattr(df, 'columns') or '基金代码' not in df.columns:
        return {}
    nav_cols = sorted(
        (c for c in df.columns if str(c).endswith('-单位净值')),
        reverse=True,  # 列名含 ISO 日期，字典序倒排 = 最新在前
    )
    if not nav_cols:
        return {}
    nav_col = nav_cols[0]
    nav_date = str(nav_col)[:10]
    change_col = '增长率' if '增长率' in df.columns else None

    out: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        raw_code = str(r['基金代码']).strip()
        if raw_code.isdigit() and len(raw_code) < 6:
            raw_code = raw_code.zfill(6)  # 防御 pandas 吃掉前导零
        if not (raw_code.isdigit() and len(raw_code) == 6):
            continue
        try:
            nav = float(r[nav_col])
        except (TypeError, ValueError):
            continue
        if pd_isna(nav):
            continue
        change: Optional[float] = None
        if change_col is not None:
            try:
                change = float(r[change_col])
            except (TypeError, ValueError):
                pass
            # pandas 把源侧 None 存成 NaN，float(nan) 不抛异常 → 必须显式拦
            if change is not None and pd_isna(change):
                change = None
        out[raw_code] = {'nav': round(nav, 4), 'nav_date': nav_date, 'nav_change_pct': change}
    return out


def _pick_spot(df: Any) -> Dict[str, Dict[str, Any]]:
    """``fund_etf_category_sina`` DataFrame → ``{裸码: {last, change_pct, amount}}``。

    新浪代码形态 ``sh510300`` / ``sz159915`` → 抽数字归一为裸码（与 channel_links 对齐）。
    """
    if not hasattr(df, 'columns') or '代码' not in df.columns:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        bare = ''.join(ch for ch in str(r['代码']) if ch.isdigit())
        if not (bare.isdigit() and len(bare) == 6):
            continue

        def _f(key: str) -> Optional[float]:
            try:
                value = float(r[key])
            except (TypeError, ValueError):
                return None
            # pandas 把源侧 None 存成 NaN，float(nan) 不抛异常 → 必须显式拦
            return None if pd_isna(value) else value

        out[bare] = {
            'last': _f('最新价'),
            'change_pct': _f('涨跌幅'),
            'amount': _f('成交额'),
        }
    return out


# ── 降级形态 ───────────────────────────────────────────────────────────
def _empty_compare(code: str) -> Dict[str, Any]:
    """对比表空形态：名录命中但无关联 ETF / 全部降级时共用，前端整块隐藏或「—」。"""
    return {
        'index_code': code,
        'as_of': None,
        'rows': [],
    }


def _etf_row_returns(etf_code: str) -> Optional[Dict[str, Optional[float]]]:
    """单只 ETF 的四窗口收益（腾讯日线 + 自然月口径）；取不到序列 → None。

    **不注入 today**：与指数侧（``build_index_returns`` → ``compute_period_returns``
    默认锚数据日，#2299 口径）保持一致——周末/节假日若显式锚日历今天，ETF 侧基期
    会比指数侧前移一个交易日，跟踪差两侧锚点不一致。
    """
    rows = direct_feeds.fetch_daily_tencent(etf_code, start_date=date.today() - timedelta(days=_ETF_HIST_LOOKBACK_DAYS))
    if not rows:
        return None
    result = compute_period_returns(rows, windows=_ETF_WINDOWS, volatility=False)
    return result['returns'] if result else None


# ── 编排层：关联清单 + 快照 + 逐只日线 + 跟踪差 ─────────────────────────
def build_etf_compare(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """关联 ETF 对比表（详情页关联标的区块内，TTL 30min）。

    Returns:
        结果 dict；**指数不在名录时返回 None**（调用方转 404，与 index-returns 同约定）；
        名录命中但无关联 ETF → 空形态（``rows: []``，不是错误）。

    负结果（含「两侧全空」的 ``{'data': None}``）同样进缓存——``CacheService`` 以
    ``None`` 表示「未命中」，故整体包成 ``{'data': ...}`` 再存，避免每次打开详情页
    都重打一轮外部请求。
    """
    entry = _catalog_entry(db, symbol)
    if entry is None:
        return None
    code, _exchange = entry

    key = f'etf_compare:{code}'
    hit = _ETF_COMPARE_CACHE.get(key)
    if hit is not None:
        return hit['data']
    data = _compute(db, code)
    _ETF_COMPARE_CACHE.set(key, {'data': data}, ttl=_ETF_COMPARE_TTL_SECONDS)
    return data


def _compute(db: Session, code: str) -> Dict[str, Any]:
    related = build_related_symbols(db, code)
    etfs = [link for link in related['links'] if link.get('peer_role') == 'etf']
    if not etfs:
        return _empty_compare(code)

    nav_map: Dict[str, Dict[str, Any]] = {}
    spot_map: Dict[str, Dict[str, Any]] = {}
    try:
        from app.core.akshare_lazy import get_akshare

        ak = get_akshare()
        try:
            nav_map = _pick_nav(ak.fund_etf_fund_daily_em())
        except Exception as e:  # noqa: BLE001 - 单源失败不阻塞整表
            logger.warning(f'ETF 净值快照失败（净值列降级—）: {e}')
        try:
            spot_map = _pick_spot(ak.fund_etf_category_sina(symbol='ETF基金'))
        except Exception as e:  # noqa: BLE001
            logger.warning(f'ETF 现货快照失败（当日涨幅/成交额降级—）: {e}')
    except Exception as e:  # noqa: BLE001 - akshare 本体起不来：全字段降级
        logger.warning(f'akshare 不可用，ETF 对比表全字段降级: {e}')

    # 指数侧收益（跟踪差基准 + 对比表基准行）；build_index_returns 自带 1h 缓存
    index_returns: Optional[Dict[str, Optional[float]]] = None
    index_as_of: Optional[str] = None
    try:
        from app.services.index_metrics import build_index_returns

        idx = build_index_returns(db, code)
        if idx is not None:
            index_returns = idx.get('returns')
            index_as_of = idx.get('as_of')
    except Exception as e:  # noqa: BLE001
        logger.warning(f'指数侧收益取数失败（跟踪差/基准行降级—）: {e}')

    rows: List[Dict[str, Any]] = []
    for etf in etfs:
        etf_code = etf['code']
        returns = _etf_row_returns(etf_code)
        nav_info = nav_map.get(etf_code, {})
        spot_info = spot_map.get(etf_code, {})
        etf_y1 = (returns or {}).get('y1')
        idx_y1 = (index_returns or {}).get('y1')
        tracking_diff = round(etf_y1 - idx_y1, 2) if (etf_y1 is not None and idx_y1 is not None) else None
        rows.append(
            {
                'code': etf_code,
                'name': etf.get('name'),
                'nav': nav_info.get('nav'),
                'nav_date': nav_info.get('nav_date'),
                'nav_change_pct': nav_info.get('nav_change_pct'),
                'change_pct': spot_info.get('change_pct'),
                'amount': spot_info.get('amount'),
                'returns': returns or {key: None for key, _ in _ETF_WINDOWS},
                'tracking_diff_y1': tracking_diff,
            }
        )

    # 排序：成交额降序（活跃优先，None 沉底）；同额按代码稳定
    rows.sort(key=lambda r: (r['amount'] is None, -(r['amount'] or 0), r['code']))

    nav_dates = [r['nav_date'] for r in rows if r.get('nav_date')]
    etf_latest = max(nav_dates) if nav_dates else None
    # 共同最新交易日 = 指数序列最新日 与 ETF 侧最新日 的较小者（两侧都有数据的最新一天）；
    # 单侧缺失取另一侧，双侧全缺 → None（整包降级由调用方决定渲染）
    if index_as_of and etf_latest:
        as_of = min(index_as_of, etf_latest)
    else:
        as_of = index_as_of or etf_latest
    return {
        'index_code': code,
        'as_of': as_of,
        'index_returns': index_returns,
        'rows': rows,
    }
