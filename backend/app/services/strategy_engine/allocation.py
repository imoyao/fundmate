# -*- coding: utf-8 -*-
"""目标配比与偏离（#2237）：算「当前占比 vs 目标占比」并产出偏离提醒候选。

口径契约
--------
1. **市值唯一口径**：一律走 `services/position_valuation.market_value_cents`
   （全系统唯一入口），禁止在本模块重写——否则 `market_value_override` /
   balance 模式的持仓会被算错（summary_service 里曾有过这种漂移）。
2. **折 CNY 后再算占比**：配比是跨标的的相对关系，不同币种必须先折同一币种，
   否则港美股占比会因汇率被系统性放大。`rate` 取 `core.constants.EXCHANGE_RATES`。
3. **净值取本地**：`NavService.get_latest_navs(..., allow_remote=False)`——
   请求路径不得为拿净值去阻塞首屏。取不到的标的回退 `current_price` 快照价。
4. **按 symbol 聚合**：同一标的分散在多账户是常态，先合并再算占比。

合规
----
本模块只产出**事实陈述**：「当前占比 46.20%，目标 40.00%，偏离 +6.20 个百分点」。
禁止产出「建议减仓 / 建议加仓」——是否行动、怎么行动由用户决定，这也是本功能
与「给建议」的根本区别（见需求文档 §合规）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.domains.positions.models import Position
from app.domains.strategy.models import TargetAllocation
from app.services.nav_service import NavService
from app.services.notification_service import build_dedup_key
from app.services.position_scope import exclude_cleared
from app.services.position_valuation import market_value_cents

# 偏离阈值（百分点）：超出即视为「越过了你自己定的线」。
# 5 个百分点是再平衡实践里最常见的容忍带，保守到不至于天天提醒。
DEFAULT_THRESHOLD_PCT = 5.0

SOURCE_TYPE = 'allocation_deviation'
# 提醒级别：P1（消息盒）。再平衡不是紧急事项，占首页横栏（P0）会挤掉真正紧急的。
REMINDER_LEVEL = 'P1'


def _to_float(value: Any) -> Optional[float]:
    """Numeric/Decimal → float；None 直传（「未设置」是合法状态，不退化成 0）。"""
    if value is None:
        return None
    return float(value)


def read_targets(db: Session, family_id: int) -> dict[str, float]:
    """读取目标配比：{symbol: 目标占比（百分点）}。"""
    rows = db.query(TargetAllocation).filter(TargetAllocation.family_id == family_id).all()
    return {r.symbol: _to_float(r.target_weight) for r in rows if _to_float(r.target_weight) is not None}


def save_targets(db: Session, family_id: int, items: Sequence[dict[str, Any]]) -> int:
    """批量保存（按 symbol upsert），返回落库条数。

    为什么是「整体覆盖」而不是逐条 PATCH：目标配比是一组相互制衡的约定，
    逐条改容易出现「改完一只、整体早已失衡却看不见」；整体提交让用户在保存前
    就能看到总和与偏离预览。
    """
    existing = {r.symbol: r for r in db.query(TargetAllocation).filter(TargetAllocation.family_id == family_id).all()}
    touched: set[str] = set()
    for item in items:
        symbol = str(item.get('symbol') or '').strip()
        if not symbol:
            continue
        weight = Decimal(str(item['target_weight']))
        row = existing.get(symbol)
        if row is None:
            db.add(
                TargetAllocation(
                    family_id=family_id,
                    symbol=symbol,
                    target_weight=weight,
                    notes=(item.get('notes') or None),
                )
            )
        else:
            row.target_weight = weight
            row.notes = item.get('notes') or None
        touched.add(symbol)
    # 未出现在本次提交里的旧目标视为被移除（整体覆盖语义）
    for symbol, row in existing.items():
        if symbol not in touched:
            db.delete(row)
    db.flush()
    return len(touched)


def clear_targets(db: Session, family_id: int) -> int:
    """清空目标配比，返回清除条数。"""
    count = db.query(TargetAllocation).filter(TargetAllocation.family_id == family_id).count()
    db.query(TargetAllocation).filter(TargetAllocation.family_id == family_id).delete(synchronize_session=False)
    db.flush()
    return int(count)


def _position_weights(db: Session, family_id: int) -> tuple[int, dict[str, dict[str, Any]]]:
    """按 symbol 聚合市值（分，已折 CNY）与展示名，返回 (总市值, {symbol: 聚合行})。"""
    positions = exclude_cleared(db.query(Position).filter(Position.family_id == family_id)).all()
    if not positions:
        return 0, {}

    symbols = [p.symbol for p in positions if p.symbol]
    # allow_remote=False：请求路径不得为取净值阻塞首屏（position_aggregation 同口径）
    navs = NavService.get_latest_navs(db, symbols, allow_remote=False) if symbols else {}

    aggregated: dict[str, dict[str, Any]] = {}
    for pos in positions:
        symbol = pos.symbol
        if not symbol:
            continue
        rate = EXCHANGE_RATES.get(getattr(pos, 'currency', None) or 'CNY', 1.0)
        value = market_value_cents(pos, effective_nav_yuan=navs.get(symbol), rate=rate)
        bucket = aggregated.setdefault(
            symbol,
            {'symbol': symbol, 'name': pos.name or symbol, 'market_value_cents': 0},
        )
        bucket['market_value_cents'] += value
        if not bucket.get('name') or bucket['name'] == symbol:
            if pos.name:
                bucket['name'] = pos.name

    total = sum(b['market_value_cents'] for b in aggregated.values())
    return total, aggregated


def compute_deviation(
    db: Session,
    family_id: int,
    *,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
) -> dict[str, Any]:
    """当前占比 vs 目标占比。

    返回：
        {
          total_value_cents, threshold_pct, configured_count,
          items: [{symbol, name, market_value_cents, weight_pct,
                   target_pct, deviation_pct, breached}],
          breached_count
        }
    未设目标的标的 `target_pct`/`deviation_pct` 为 None 且 `breached=False`——
    「没定规矩」不该被判成「违反规矩」。
    """
    total, aggregated = _position_weights(db, family_id)
    targets = read_targets(db, family_id)

    items: list[dict[str, Any]] = []
    for symbol in sorted(aggregated):
        bucket = aggregated[symbol]
        value = bucket['market_value_cents']
        weight = round(value / total * 100, 2) if total > 0 else 0.0
        target = targets.get(symbol)
        deviation = round(weight - target, 2) if target is not None else None
        items.append(
            {
                'symbol': symbol,
                'name': bucket['name'],
                'market_value_cents': value,
                'weight_pct': weight,
                'target_pct': target,
                'deviation_pct': deviation,
                'breached': bool(deviation is not None and abs(deviation) >= threshold_pct),
            }
        )

    breached = [i for i in items if i['breached']]
    return {
        'total_value_cents': total,
        'threshold_pct': threshold_pct,
        'configured_count': len([i for i in items if i['target_pct'] is not None]),
        'target_sum_pct': round(sum(t for t in targets.values()), 2),
        'items': items,
        'breached_count': len(breached),
    }


def collect_reminders(
    db: Session,
    family_id: int,
    *,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    today: Optional[date] = None,
) -> list[dict[str, Any]]:
    """把越线的偏离转成通知候选（不写库），供 `notification_service.emit_many` 消费。

    措辞只陈述事实 + 提醒「这是你定的线」，不给任何方向性建议。
    """
    result = compute_deviation(db, family_id, threshold_pct=threshold_pct)
    day = today or date.today()
    candidates: list[dict[str, Any]] = []
    for item in result['items']:
        if not item['breached']:
            continue
        deviation = item['deviation_pct']
        direction = '高于' if deviation > 0 else '低于'
        candidates.append(
            {
                'level': REMINDER_LEVEL,
                'category': 'strategy',
                'title': f'配比偏离：{item["name"]} 当前 {item["weight_pct"]:.2f}%，目标 {item["target_pct"]:.2f}%',
                'body': (
                    f'{direction}目标 {abs(deviation):.2f} 个百分点'
                    f'（你设定的容忍带 {threshold_pct:.1f}）。'
                    f'这条线是你自己定的，仅在越线当天提醒一次。'
                ),
                'dedup_key': build_dedup_key(SOURCE_TYPE, item['symbol'], day),
                'source_type': SOURCE_TYPE,
                'source_key': item['symbol'],
            }
        )
    return candidates


def refresh_reminders(
    db: Session,
    family_id: int,
    *,
    threshold_pct: float = DEFAULT_THRESHOLD_PCT,
    today: Optional[date] = None,
) -> int:
    """跑一次偏离扫描并写入站内通知，返回**新建**条数（已存在则跳过）。

    导入放在函数内而非模块顶层：`notification_service` 与本模块同属 services 层，
    顶层互引会在将来调整包结构时触发循环导入，延后到调用时更安全。
    """
    from app.services import notification_service  # noqa: PLC0415

    candidates = collect_reminders(db, family_id, threshold_pct=threshold_pct, today=today)
    return notification_service.emit_many(db, family_id, candidates)
