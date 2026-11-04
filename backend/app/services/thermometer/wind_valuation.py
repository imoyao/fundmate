# -*- coding: utf-8 -*-
"""指数 / 申万一级行业估值（Wind 指数域 → 市场温度计，#2749）。

落点：``market_multi_items``（``MarketMultiItem``，``item_type='index'|'industry'``），
读侧走通用透传 ``GET /api/temperature/multi?source=wind_valuation``，不新增路由。

为什么挂在 ``TemperatureJob`` 而不是单开 job：
- 与 bias / industry_crowding 同为「多维快照」维度，共享每日 20:00 调度与
  「按 source 删当天重插」的写路径（``TemperatureService.save_multi_items``）；
- 单开 job 得重复实现调度注册与失败汇总，换来的只有「可独立重跑」，暂不需要。

记录形状与 ``industry_crowding`` 相同（扁平 multi 行，``kind/source/item_type/
item_code/item_name/data/stale``），``_save_data`` 按 kind 分流时直接进 multi。

上游注意事项（真机 2026-10-30，详见适配器 docstring）：
- 问句一律不含「加权」（多标的场景会把 PE 放大百倍）；
- 估值表与分位表是两张并列表，适配器已按代码归并；
- 单次问句实体数控制在 10 个以内（get_stock_basicinfo 实测边界；指数域未实测
  更大批量，不赌）。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.core.time_utils import now_shanghai
from app.services.adapters import wind_index_valuation
from app.services.bias.constants import SW_LEVEL1_INDUSTRIES

#: 温度计侧数据源标识。刻意不等于适配器内的 ``SOURCE_WIND='wind'``：
#: ``market_multi_items`` 的唯一键是 ``(source, item_type, item_code, collected_at)``，
#: 用更具体的标识便于与将来其它 Wind 维度并存且互不覆盖。
WIND_VALUATION_SOURCE = 'wind_valuation'

#: 单次问句的最大实体数（与 wind_stock.STOCK_CHUNK_SIZE 同边界）。
CHUNK_SIZE = 10

#: 宽基目标（稳定代码空间，必须传代码不传名称——上游按名称查询时返回的代码
#: 可能不一致，实测同一问句两次分别返回 399300.SZ 与 000300.SH）。
BROAD_INDEX_TARGETS: Dict[str, str] = {
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
    '000016.SH': '上证50',
    '000015.SH': '上证红利',
    '399006.SZ': '创业板指',
}


def fetch_wind_valuation_records(
    collected_at: Optional[datetime] = None,
    *,
    provider: Any = None,
    transport: Any = None,
) -> Tuple[List[dict], List[dict]]:
    """拉取宽基 + 申万一级行业估值，返回 ``(multi_records, errors)``。

    - Token 未配置 → ``([], [])`` 静默跳过（其它温度维度照常）；
    - 单块失败 → 该块记入 ``errors``，其余块照常落库（块间独立，不整组标 stale）；
    - 行内缺名字且映射表也认不出 → 跳过该行并告警（``item_name`` 非空约束）。
    """
    if not wind_index_valuation.is_available():
        logger.info('Wind 指数域未配置 Token，跳过指数/行业估值维度')
        return [], []

    collected_at = collected_at or now_shanghai()
    entities = list(BROAD_INDEX_TARGETS) + list(SW_LEVEL1_INDUSTRIES)
    records: List[dict] = []
    errors: List[dict] = []
    for start in range(0, len(entities), CHUNK_SIZE):
        chunk = entities[start : start + CHUNK_SIZE]
        label = f'{chunk[0]}…{chunk[-1]}'
        try:
            rows = wind_index_valuation.fetch_index_valuations(
                chunk, with_percentile=True, provider=provider, transport=transport
            )
        except Exception as e:  # noqa: BLE001  单块失败不拖垮其它块
            logger.error(f'Wind 估值分块失败（{label}）: {e}')
            errors.append({'source': WIND_VALUATION_SOURCE, 'error': f'{label}: {e}'})
            continue
        for row in rows:
            record = _to_multi_record(row, collected_at)
            if record is not None:
                records.append(record)
    return records, errors


def _to_multi_record(row: dict, collected_at: datetime) -> Optional[dict]:
    code = str(row.get('wind_code') or '').strip()
    if not code:
        return None
    item_name = BROAD_INDEX_TARGETS.get(code) or SW_LEVEL1_INDUSTRIES.get(code) or row.get('name')
    if not item_name:
        logger.warning(f'[{WIND_VALUATION_SOURCE}] 估值行无名字可用，已跳过：{code}')
        return None
    return {
        'kind': 'multi',
        'source': WIND_VALUATION_SOURCE,
        'item_type': 'industry' if code in SW_LEVEL1_INDUSTRIES else 'index',
        'item_code': code,
        'item_name': item_name,
        # 键集固定（缺值补 None），读侧不用猜 schema；valuation_date 是估值自身的
        # 交易日（通常为上一交易日），与 collected_at（采集时刻）语义分开。
        'data': {
            'pe': row.get('pe'),
            'pb': row.get('pb'),
            'dividend_yield': row.get('dividend_yield'),
            'pe_percentile': row.get('pe_percentile'),
            'valuation_date': row.get('date'),
        },
        'collected_at': collected_at,
        'stale': False,
    }


__all__ = [
    'BROAD_INDEX_TARGETS',
    'CHUNK_SIZE',
    'WIND_VALUATION_SOURCE',
    'fetch_wind_valuation_records',
]
