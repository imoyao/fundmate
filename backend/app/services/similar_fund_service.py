# -*- coding: utf-8 -*-
"""相似基金读取服务（#2480）：按需取上游相似度名单，不落库。

数据来源只有一处：韭圈儿免登录端点（``adapter.fetch_similar_funds``，2026-10-21
实测）。**不落库**——相似度是快照概念、名单月变，建历史无消费场景（违反
「按需存」原则，issue #2480 边界已写明）；以 ``CacheService`` 做进程内 + 文件
两级缓存降压（公开行情/自建分析结果才可进缓存，本数据属公开参照，红线内）。

降级契约（与 issue 验收第 3 条对应）：上游失败/超时/形态异常 → 返回
``{'items': [], 'degraded': True, 'error': ...}``，**不向视图抛异常**——
展示接口不该因一个外部源 500。相似度口径是上游黑盒，展示层须注明来源。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from loguru import logger

from app.core.cache import CacheService
from app.services.adapters.jiucaishuo_adapter import SIMILAR_SOURCE, JiucaishuoAdapter
from app.services.fund_utils import normalize_fund_code

# 缓存 6h：相似度名单月变量级，6h 足够抗详情页重复打开；上游另有 2s 模块级节流
_SIMILAR_CACHE = CacheService(namespace='similar_funds')
_SIMILAR_TTL_SECONDS = 6 * 3600

# 上游返回条数实测 5-6 条；留一点余量兜上游扩列，防异常放大
SIMILAR_MAX_ITEMS = 20


def _degraded(fund_code: str, error: str) -> Dict[str, Any]:
    return {
        'fund_code': fund_code,
        'items': [],
        'degraded': True,
        'error': error,
        'source': SIMILAR_SOURCE,
        'fetched_at': None,
    }


def get_similar_funds(fund_code: str) -> Dict[str, Any]:
    """相似基金列表（详情页「相似基金」块）。

    Args:
        fund_code: 6 位基金代码（带交易所前缀的 symbol 先归一化）。

    Returns:
        ``{'fund_code', 'items': [{fund_code, fund_name, similarity,
        income_1y_pct, window}], 'degraded': bool, 'error': str|None,
        'source', 'fetched_at'}``。``degraded=True`` 时 items 为空、error 有值。
    """
    code = normalize_fund_code(fund_code)
    if not code:
        return _degraded(fund_code or '', f'基金代码无法归一化: {fund_code!r}')

    cached = _SIMILAR_CACHE.get(f'similar:{code}')
    if cached is not None:
        return cached

    started = time.monotonic()
    try:
        result = JiucaishuoAdapter().fetch_similar_funds(code)
    except Exception as e:  # noqa: BLE001 - 降级不抛：外部源失败转空列表 + 标记
        logger.warning(f'相似基金 {code} 取数失败（降级回空）: {e}')
        return _degraded(code, str(e))

    items: List[Dict[str, Any]] = (result.get('items') or [])[:SIMILAR_MAX_ITEMS]
    payload = {
        'fund_code': code,
        'items': items,
        'degraded': False,
        'error': None,
        'source': SIMILAR_SOURCE,
        'fetched_at': round(time.monotonic() - started, 3),
    }
    _SIMILAR_CACHE.set(f'similar:{code}', payload, ttl=_SIMILAR_TTL_SECONDS)
    return payload
