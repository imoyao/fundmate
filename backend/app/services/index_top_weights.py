# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/17
# File : index_top_weights.py
# app/services/index_top_weights.py
"""指数十大权重（#2278 · 详情页指数区块「前十大权重是谁、集中度多高」）。

数据源：akshare ``index_stock_cons_weight_csindex``（中证官网成分权重接口，
实测 931151 → 50 行 / 000300 → 300 行，含**日期 / 成分券代码 / 名称 / 权重 /
交易所**列）。**月频**——权重随样本调整按月更新，故 TTL 放宽到 12h（月频数据
一天一取足够；降级语义见 #2271 简介缓存同纪律）。按需取 + 缓存 + 可降级
（L3/L4 口径），**不入库**（#2278 准入前提：不新增任何表/列）。

口径：

- 返回**权重降序前 N（默认 10）**行 + 前 N 合计 + 全成分总数；
- 权重单位为百分比（源侧即 % 形态，如 9.218 = 9.218%）；
- ``as_of`` 取源侧「日期」列（该批权重的截止日期），前端必须连同「月频」
  口径一起标注——权重是**滞后数据**，别当实时值解读。

降级：码族未收录 / 源侧异常 → ``None``（整块「—」）。与阶段性收益同纪律：
**异常与空结果都不缓存**——瞬时故障下次重试，未收录码的重复探测成本可接受
（打开详情页才触发，非轮询路径）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.core.akshare_lazy import get_akshare

# 进程内 TTL 缓存：code → (抓取时刻 monotonic, 聚合结果)。月频数据 12h 足够。
_TTL_SECONDS = 12 * 3600
_weights_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _bare_code(symbol: str) -> str:
    """抽裸 6 位指数码（与 index_profile / index_period_returns 同款归一）。"""
    m = re.search(r'\d{6}', (symbol or '').strip().upper())
    return m.group(0) if m else ''


def _pick_rows(df: Any, top_n: int) -> Dict[str, Any]:
    """DataFrame → 前 N 大权重聚合（纯转换，便于测试注入）。

    列名以源侧实测为准（2026-10-17）：日期 / 指数代码 / 指数名称 / 指数英文名称 /
    成分券代码 / 成分券名称 / 成分券英文名称 / 交易所 / 交易所英文名称 / 权重。
    源侧返回顺序**不是**权重降序（实测 931151 首行权重 1.266 而最大权重
    9.218 在后），必须自行排序。
    """
    needed = ('日期', '成分券代码', '成分券名称', '权重')
    if not hasattr(df, 'columns') or any(c not in df.columns for c in needed):
        return {}
    if len(df) == 0:
        return {}
    as_of = str(df['日期'].iloc[0])[:10]
    rows: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        try:
            weight = float(r['权重'])
        except (TypeError, ValueError):
            continue  # 坏行丢弃不编数
        rows.append(
            {
                'symbol': str(r['成分券代码']),
                'name': str(r['成分券名称']),
                'weight': weight,
            }
        )
    if not rows:
        return {}
    rows.sort(key=lambda x: x['weight'], reverse=True)
    top = rows[:top_n]
    return {
        'as_of': as_of,
        'rows': top,
        'top_sum': round(sum(x['weight'] for x in top), 4),
        'total_count': len(rows),
    }


def fetch_top_weights(symbol: str, top_n: int = 10) -> Optional[Dict[str, Any]]:
    """按需取指数十大权重（详情页指数区块；L3：按需 + TTL 缓存 + 降级 None）。"""
    code = _bare_code(symbol)
    if not code:
        return None
    now = time.monotonic()
    if code in _weights_cache:
        ts, payload = _weights_cache[code]
        if now - ts < _TTL_SECONDS:
            return payload
    try:
        df = get_akshare().index_stock_cons_weight_csindex(symbol=code)
    except Exception as e:  # noqa: BLE001 —— 源异常不可阻断详情页
        logger.warning(f'指数权重抓取失败 code={code}: {e}')
        return None
    result = _pick_rows(df, top_n)
    if not result:
        return None  # 空结果不缓存（瞬时故障下次重试）
    _weights_cache[code] = (now, result)
    return result
