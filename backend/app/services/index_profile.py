# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/11
# File : index_profile.py
# app/services/index_profile.py
"""指数资料聚合（#2028 · 详情页指数详情区块）。

沿用 #1968 / #1969 的硬规则「拼不出首屏就在本卡内补端点」：指数的资料散在
``index_catalog``（名录 / 发布机构）、``index_valuations``（官方估值最新一期）、
``index_valuation_baselines``（乐咕月频分位基线）三张表，且三张表**都没有 API
出口**（indices 域无蓝图）。故一次查完返回，前端一次请求拿到首屏。

分位在**本读路径现算**而非落库：基线是月频近 5 年，窗口是参数（见
``index_percentile``），落库会把窗口焊死在写入时刻。PE 分位口径 = 乐咕滚动
市盈率；股息率分位本期**恒为 None**（乐咕无股息率序列，自建日频积累未满 1 年），
前端降级「—」（#1407 拍板第 3 条）。

字段缺失一律返回 ``None``，前端降级为「—」，不编造占位值（设计 §10）。
``description``（指数简介）是唯一的例外：它是散文不是指标，``None`` 时前端
**整段隐藏**而不显示「—」占位——简介抓自中证官网 ``index-basic-info``
（``indexCnDesc``，编制方案描述原文），按需取 + 进程内缓存 + 降级 ``None``。

#2278 在同一响应里追加三块（**不新增端点**——products/views.py 行数冻结在
437 基线，且验收只要求「各区块独立降级、互不拖垮」，与端点数无关）：

1. **快照字段**（publish_date / cons_number / weighting_type / currency）——
   复用 ``index-basic-info`` 同一请求顺手取（边际成本≈0）；
2. **阶段性收益** ``period_returns``——``index_period_returns`` 按需拉日线现算
   区间收益与年化波动，算完即弃不入库；
3. **十大权重** ``top_weights``——``index_top_weights`` 走 akshare 月频接口。

三块各自独立 try/except 降级（外部源异常只影响本块，不拖垮资料/估值首屏）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

import requests
from loguru import logger
from sqlalchemy.orm import Session

from app.domains.indices.models import (
    INDEX_PUBLISHER_LABELS,
    IndexCatalog,
    IndexValuation,
    IndexValuationBaseline,
)
from app.services.index_percentile import (
    MIN_BASELINE_POINTS,
    compute_percentile,
    window_cutoff,
)
from app.services.index_period_returns import fetch_period_returns
from app.services.index_top_weights import fetch_top_weights


def _bare_index_code(symbol: str) -> str:
    """抽裸 6 位指数码：``SH000300`` / ``000300.SH`` / ``000300`` → ``000300``。

    详情页路径段的指数码可能带交易所前缀或后缀（``product_identity`` 已按裸码
    命中 ``index_catalog``，此处是读路径的同款归一，不信任入口形态）。
    """
    m = re.search(r'\d{6}', (symbol or '').strip().upper())
    return m.group(0) if m else ''


# 中证官网「指数基础信息」接口：indexCnDesc 是官方简介正文（编制方案描述）；
# #2278 起同一响应还提供快照字段（publishDate / consNumber / weightingType /
# currencyCn）。实测覆盖（2026-10-16/17）：0 系、9 系(6 位)、899、H、L 有简介；
# 399 系、4 系(CNH)、CES/B 系、8 位 98 系返回 data=null——只对覆盖码族发请求，
# 省掉注定扑空的请求。
_CSI_DESC_CODE_RE = re.compile(r'^(?:[089]\d{5}|H\d+|L\d+)$')
_CSI_BASIC_INFO_URL = 'https://www.csindex.com.cn/csindex-home/indexInfo/index-basic-info/{code}'

# 进程内 basic-info 缓存：code → data dict 或 None（None = 官网确认无 data 的
# 负缓存，防止同一码每次打开详情页都发一遍请求）；网络异常**不写**缓存——
# 瞬时故障下次查看时重试，不把故障焊死。编制方案正文与快照字段极稳定，
# 缓存不设 TTL。#2278 起缓存整 dict（简介与快照同一请求顺手取）。
_csi_basic_cache: Dict[str, Optional[Dict[str, Any]]] = {}


def fetch_csi_basic_info(code: str) -> Optional[Dict[str, Any]]:
    """按需抓中证官网指数基础信息（整个 data dict；含简介 + 快照字段）。

    L3 参考数据：按需取 + 进程内缓存 + 降级 None。未覆盖码族不发请求也不进缓存。
    """
    if code in _csi_basic_cache:
        return _csi_basic_cache[code]
    if not _CSI_DESC_CODE_RE.match(code):
        return None  # 未覆盖码族直接降级（不发注定扑空的请求，也不进缓存）
    try:
        resp = requests.get(_CSI_BASIC_INFO_URL.format(code=code), timeout=5)
        resp.raise_for_status()
        data = resp.json().get('data') or None
    except Exception as e:
        logger.warning(f'中证基础信息抓取失败 code={code}: {e}')
        return None  # 瞬时故障不缓存，下次查看时重试
    _csi_basic_cache[code] = data
    return data


def fetch_csi_index_desc(code: str) -> Optional[str]:
    """中证官网指数简介（``indexCnDesc``）；未收录 / 失败降级 None。

    内部走 ``fetch_csi_basic_info`` 同一缓存——#2278 起简介与快照字段
    共用一次请求（此前各发一次的实现作废）。
    """
    data = fetch_csi_basic_info(code)
    return (data or {}).get('indexCnDesc') or None


def fetch_csi_snapshot(code: str) -> Optional[Dict[str, Any]]:
    """中证官网快照字段（#2278：发布日期 / 样本数 / 加权方式 / 币种）。

    与简介同请求顺手取（``fetch_csi_basic_info`` 缓存）；data 缺失时返回 None
    （整块降级「—」），字段级缺失由 data 内 None 表达。
    """
    data = fetch_csi_basic_info(code)
    if not data:
        return None
    return {
        'publish_date': data.get('publishDate') or None,
        'cons_number': data.get('consNumber') or None,
        'weighting_type': data.get('weightingType') or None,
        'currency': data.get('currencyCn') or None,
    }


def build_index_profile(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """一次拼出单只指数的资料 + 估值 + 历史分位 + 快照/收益/权重（详情页指数区块）。

    Args:
        db: **market 域**会话（三张表均在 market 域）。
        symbol: 指数代码（裸码或带交易所前/后缀形态均可）。

    Returns:
        资料 dict；**指数不在名录时返回 None**（由调用方转 404）。
    """
    code = _bare_index_code(symbol)
    if not code:
        raise ValueError('缺少指数代码')

    catalog = db.query(IndexCatalog).filter(IndexCatalog.index_code == code).first()
    if catalog is None:
        return None

    # 最新一期官方估值（中证官方口径，pe_1 / dividend_yield_1）
    latest = (
        db.query(IndexValuation)
        .filter(IndexValuation.index_code == code)
        .order_by(IndexValuation.trade_date.desc())
        .first()
    )

    # 分位基线：窗口内月频序列（乐咕），现算 PE 分位
    rows = (
        db.query(IndexValuationBaseline.trade_date, IndexValuationBaseline.pe_ttm)
        .filter(
            IndexValuationBaseline.index_code == code,
            IndexValuationBaseline.trade_date >= window_cutoff(),
        )
        .order_by(IndexValuationBaseline.trade_date)
        .all()
    )
    series = [float(pe) for _d, pe in rows if pe is not None]
    pe_percentile: Optional[float] = None
    percentile_date: Optional[str] = None
    if len(series) >= MIN_BASELINE_POINTS:
        # current = 序列最新点（同口径自比：乐咕滚动 PE 在乐咕序列里的位置——
        # 不可拿中证官方 pe_1 去比乐咕序列，两套口径不可混）
        pe_percentile = compute_percentile(series[-1], series, direction='asc')
        percentile_date = rows[-1][0].isoformat() if rows[-1][0] else None

    # #2278 快照字段（basic-info 同请求顺手取；未收录 / 失败为 None）
    snapshot = fetch_csi_snapshot(code) or {}

    # #2278 阶段性收益 + 十大权重：外部源按需抓，各自独立降级「互不拖垮」——
    # 子服务内部已 best-effort 捕获源异常，这里的兜底 try 是第二道防线
    # （防聚合期计算 bug 拖垮整卡首屏）。
    try:
        period_returns = fetch_period_returns(code)
    except Exception as e:  # noqa: BLE001
        logger.warning(f'阶段性收益聚合失败 code={code}: {e}')
        period_returns = None
    try:
        top_weights = fetch_top_weights(code)
    except Exception as e:  # noqa: BLE001
        logger.warning(f'十大权重聚合失败 code={code}: {e}')
        top_weights = None

    return {
        'index_code': code,
        'name': catalog.name,
        'publisher_label': INDEX_PUBLISHER_LABELS.get(catalog.publisher or '', None),
        'is_core': bool(catalog.is_core),
        # 官方简介（中证官网 indexCnDesc，按需抓取 + 进程内缓存；未收录/失败为 None）
        'description': fetch_csi_index_desc(code),
        # 官方估值（中证口径，最新一期）
        'pe': float(latest.pe_1) if latest and latest.pe_1 is not None else None,
        'dividend_yield': (float(latest.dividend_yield_1) if latest and latest.dividend_yield_1 is not None else None),
        'valuation_date': latest.trade_date.isoformat() if latest and latest.trade_date else None,
        # 历史分位（乐咕滚动 PE，近 5 年月频窗口；样本不足为 None）
        'pe_percentile': pe_percentile,
        # 分位口径元数据（§3.10「存口径元数据，不只存数字」）：前端脚注直接展示
        'percentile_metric': '滚动市盈率（乐咕乐股月频）',
        'percentile_date': percentile_date,
        # 快照字段（#2278：basic-info 同请求顺手取；字段缺失为 None）
        'publish_date': snapshot.get('publish_date'),
        'cons_number': snapshot.get('cons_number'),
        'weighting_type': snapshot.get('weighting_type'),
        'currency': snapshot.get('currency'),
        # 阶段性收益（#2278：日线现算 6 窗口 + 年化波动；取不到整块 None）
        'period_returns': period_returns,
        # 十大权重（#2278：akshare 月频前 N 大；取不到整块 None）
        'top_weights': top_weights,
    }
