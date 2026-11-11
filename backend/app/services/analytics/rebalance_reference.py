# -*- coding: utf-8 -*-
"""Q3「持仓再平衡客观参考」工具的取数与组装层（#3049 §10 / #3050）。

与 ``rebalance_reference_rules`` 的分工：本模块只负责**从本地已落库数据取值**
（持仓市值 / 宽基估值分位），所有阈值判断与输出组装交给纯计算模块。
零外部请求、零新增 MCP 客户端、零模型参与（D19 + L1 数据真实性铁律）。

取数口径与 ``list_position_pnl`` 同源：``exclude_cleared`` + ``market_value_cents``，
保证「同一持仓在两个工具里市值一致」。估值分位读 ``market_multi_items`` 里
``source=wind_valuation`` 的最新一条宽基记录；取不到就返回 None，由规则层显式
声明缺口，不补 0、不近似、不拿其它口径替代。
"""

from typing import Any, Dict, Optional

from sqlalchemy import desc

from app.core import database
from app.core.money import Money
from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.temperature.models import MarketMultiItem
from app.services.analytics.rebalance_reference_rules import build_rebalance_report
from app.services.position_scope import exclude_cleared
from app.services.position_valuation import market_value_cents
from app.services.thermometer.wind_valuation import BROAD_INDEX_TARGETS, WIND_VALUATION_SOURCE

DEFAULT_BENCHMARK = '000300.SH'


def _latest_index_percentile(db, benchmark: str) -> Optional[Dict[str, Any]]:
    """取本地最新一条宽基估值分位；无记录 / 无分位值一律返回 None。"""
    row = (
        db.query(MarketMultiItem)
        .filter(
            MarketMultiItem.source == WIND_VALUATION_SOURCE,
            MarketMultiItem.item_type == 'index',
            MarketMultiItem.item_code == benchmark,
            MarketMultiItem.stale.is_not(True),
        )
        .order_by(desc(MarketMultiItem.collected_at))
        .first()
    )
    if row is None:
        return None
    data = row.data or {}
    return {
        'index': benchmark,
        'item_name': BROAD_INDEX_TARGETS.get(benchmark, row.item_name),
        'pe_percentile': data.get('pe_percentile'),
        'valuation_date': data.get('valuation_date'),
        'collected_at': row.collected_at.isoformat() if row.collected_at else None,
    }


def build_rebalance_reference(params: dict) -> dict:
    """工具入口：``params`` 由 ToolExecutor 注入权威 family_id 后传入。"""
    try:
        family_id = int(params.get('family_id') or 1)
    except (TypeError, ValueError):
        family_id = 1
    benchmark = params.get('benchmark') or DEFAULT_BENCHMARK
    with database.get_session() as db:
        positions = exclude_cleared(db.query(Position).filter(Position.family_id == family_id)).all()
        rows = [
            {
                'symbol': p.symbol,
                'name': p.name,
                'market_value': Money.cents_to_yuan(market_value_cents(p)),
            }
            for p in positions
        ]
        valuation = _latest_index_percentile(db, benchmark)
    return build_rebalance_report(
        positions=rows,
        as_of=now_shanghai().date().isoformat(),
        scope=f'family_id={family_id}',
        valuation=valuation,
    )


__all__ = ['BROAD_INDEX_TARGETS', 'DEFAULT_BENCHMARK', 'build_rebalance_reference']
