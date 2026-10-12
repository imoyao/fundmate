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
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

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


def _bare_index_code(symbol: str) -> str:
    """抽裸 6 位指数码：``SH000300`` / ``000300.SH`` / ``000300`` → ``000300``。

    详情页路径段的指数码可能带交易所前缀或后缀（``product_identity`` 已按裸码
    命中 ``index_catalog``，此处是读路径的同款归一，不信任入口形态）。
    """
    m = re.search(r'\d{6}', (symbol or '').strip().upper())
    return m.group(0) if m else ''


def build_index_profile(db: Session, symbol: str) -> Optional[Dict[str, Any]]:
    """一次拼出单只指数的资料 + 估值 + 历史分位（详情页指数区块）。

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

    return {
        'index_code': code,
        'name': catalog.name,
        'publisher_label': INDEX_PUBLISHER_LABELS.get(catalog.publisher or '', None),
        'is_core': bool(catalog.is_core),
        # 官方估值（中证口径，最新一期）
        'pe': float(latest.pe_1) if latest and latest.pe_1 is not None else None,
        'dividend_yield': (float(latest.dividend_yield_1) if latest and latest.dividend_yield_1 is not None else None),
        'valuation_date': latest.trade_date.isoformat() if latest and latest.trade_date else None,
        # 历史分位（乐咕滚动 PE，近 5 年月频窗口；样本不足为 None）
        'pe_percentile': pe_percentile,
        # 分位口径元数据（§3.10「存口径元数据，不只存数字」）：前端脚注直接展示
        'percentile_metric': '滚动市盈率（乐咕乐股月频）',
        'percentile_date': percentile_date,
    }
