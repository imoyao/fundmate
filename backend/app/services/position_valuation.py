# -*- coding: utf-8 -*-
"""持仓市值的读口径与写分摊（#1174 / 决策 D1 方案 A）。

本模块是「持仓市值」这一知识的**唯一归口**，含读写两侧：

- 读：:func:`market_value_cents` —— 单笔持仓市值（分），全系统唯一口径；
- 写：:func:`allocate_value` —— 按各账户市值占比把产品总价分摊写入
  ``market_value_override``（P1-4 / roadmap P1-4）。

两者合并的理由：分摊的**分母就是读口径**（`market_value_cents`），拆成两个文件时
「口径改了、分摊没改」会直接产生金额错误；合并后同一知识只有一处定义。

## 读口径 WHY

历史上三处各自计算市值且**口径不同源**：
- `services/position_aggregation.py` 走 NavService 最新净值
- `services/summary_service.py` 走 `current_price` 快照价
- `domains/positions/views.py` 再算一遍
新增 `market_value_override` 后若三处各加各的判断，就会出现第四个口径。
本模块是**唯一入口**，三处必须委托到这里，禁止再各自实现。

优先级（固定顺序，与计价模式解耦）:

    1. `market_value_override`：人工录入的可写市值（单位：分），非空即优先——
       任何计价模式下都生效，用于投顾/理财等拿不到净值的标的
    2. `balance` 模式：没有份额可乘，市值只能来自 override；走到这里说明未录入，
       按 0 计并告警（不静默给错误数字）
    3. `nav` 模式：份额 × 有效净值；无净值时回退 `current_price` 快照价

数据域约束（仅读口径）：只读持仓自身字段与调用方传入的净值，**不查库、不跨数据域**
（对比 `position_aggregation.py`：跨域读可以、写不行）。写分摊侧需要查库，
但只操作 user 域的 `positions` / `transactions`，不跨 market 域。

## 写分摊口径约束

- 分母复用本文件的 :func:`market_value_cents`，不另开一套；
- 整数分 + ROUND_HALF_UP；尾差归占比最大一笔（与 position_aggregation 的尾差处理一致）；
- 假设分摊标的均为本币（CNY）场景；跨币种 balance 分摊非本期范围。
- 只写 ``market_value_override`` / ``value_override_at``，不建交易流水、
  不动 quantity；调用方（端点）负责 commit。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import func

from app.core.constants import ValuationMode
from app.core.money import Money
from app.core.trading_calendar import next_trading_day
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

# 视为「资金进出」的流水类型（#1217）：申购/赎回与分红都会改变实际持有情况，
# 但不会体现在 market_value_override 上，故据此判定分摊基数是否已经过期
_CASH_FLOW_TXN_TYPES = ('buy', 'sell', 'deposit', 'withdraw', 'dividend')


def market_value_cents(
    position,
    *,
    effective_nav_yuan: float | None = None,
    rate: float | None = None,
) -> int:
    """单笔持仓市值（分）——全系统唯一口径。

    Args:
        position: 持仓记录。需要 `currency` / `valuation_mode` / `quantity` /
            `current_price` / `market_value_override`；用 getattr 兜底，
            缺字段时按 nav 模式安全降级（兼容 mock 对象与老数据）。
        effective_nav_yuan: 有效净值（元）。基金/货基传 NavService 取到的最新净值；
            其他类型或无净值时为 None（回退 `current_price` 快照价）。
        rate: 本币 → CNY 汇率。**None 时按 1.0（本币直算）**——是否折汇率由调用方决定，
            本函数不自动查 EXCHANGE_RATES。原因：单条持仓明细的口径要求市值与
            `current_price` 保持同一币种（见 positions/views 的既有约定），
            只有聚合/仪表盘口径才折算成 CNY（total_*_cny）。
    """
    if rate is None:
        rate = 1.0

    # 1) 人工录入的可写市值优先（与计价模式无关）
    override = getattr(position, 'market_value_override', None)
    if override is not None:
        return int((Decimal(str(override)) * Decimal(str(rate))).to_integral_value(rounding='ROUND_HALF_UP'))

    mode = getattr(position, 'valuation_mode', None) or ValuationMode.NAV.value

    # 2) balance 模式：无份额可乘，市值只能来自 override——此处必为空，记 0 并告警
    if mode == ValuationMode.BALANCE.value:
        logger.warning(
            f'balance 模式持仓未录入市值（market_value_override 为空）：position_id={getattr(position, "id", "?")}，市值按 0 计'
        )
        return 0

    # 3) nav 模式：份额 × 有效净值（无净值回退快照价），与历史口径一致
    shares = Money.min_unit_to_shares(position.quantity)
    if effective_nav_yuan is not None and effective_nav_yuan > 0:
        price_yuan = effective_nav_yuan
    else:
        price_yuan = Money.price_units_to_yuan(position.current_price)

    yuan = shares * price_yuan * rate
    return int((Decimal(str(yuan)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))


def _has_cash_flow_since(db, family_id: int, symbol: str, since: Optional[date]) -> bool:
    """上次录入市值之后是否发生过资金进出。

    Args:
        since: 基准日（上次 `value_override_at`）。**None 表示从未人工录入过市值**，
            没有可比基准，按「无资金进出」处理，避免首次录入就误报提示。
    """
    if since is None:
        return False

    # 以确认日为准，未确认的流水退回交易日
    occurred = func.coalesce(Transaction.confirm_date, func.date(Transaction.trade_date))
    exists = (
        db.query(Transaction.id)
        .filter(
            Transaction.family_id == family_id,
            Transaction.symbol == symbol,
            Transaction.txn_type.in_(_CASH_FLOW_TXN_TYPES),
            occurred > since,
        )
        .exists()
    )
    return bool(db.query(exists).scalar())


def allocate_value(
    db,
    family_id: int,
    symbol: str,
    total_value_yuan: float,
    *,
    as_of: Optional[date] = None,
    ledger_id: Optional[int] = None,
) -> dict:
    """按各账户当前市值占比，把产品总价分摊写入每笔持仓的可写市值。

    Args:
        db: 数据库会话（调用方负责 commit）。
        family_id: 家庭 ID。
        symbol: 产品代码。
        total_value_yuan: 产品维度新总价（元）。
        as_of: 市值录入日期，默认今天。
        ledger_id: 限定只分摊到某账户；缺省跨全部活跃账户。

    Returns:
        dict: ``{ symbol, total_value_cents, total_weight_cents, as_of, allocations[] }``
        ``allocations[]``: ``{ position_id, ledger_id, allocated_cents, allocated_yuan, ratio }``

    Raises:
        ValueError: 无活跃持仓 / 分母（各账户市值之和）为 0 无法按比例分摊。
    """
    positions = (
        db.query(Position)
        .filter(
            Position.family_id == family_id,
            Position.symbol == symbol,
            Position.ownership_status == 'active',
        )
        .all()
    )
    if ledger_id is not None:
        positions = [p for p in positions if p.ledger_id == ledger_id]

    if not positions:
        raise ValueError(f'未找到 symbol={symbol} 的活跃持仓，无法分摊总价')

    # 分母：复用本文件的唯一市值口径（本币直算，balance 场景均为 CNY）
    weights = [market_value_cents(p) for p in positions]
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError('当前各账户市值均为 0，无法按比例分摊；请先逐账户录入市值或使用其他方式')

    total_cents = int((Decimal(str(total_value_yuan)) * 100).to_integral_value(rounding='ROUND_HALF_UP'))

    # 首轮按占比四舍五入（整数分）
    allocated = [
        int((Decimal(w) * total_cents / total_weight).to_integral_value(rounding='ROUND_HALF_UP')) for w in weights
    ]

    # 尾差（分）归占比最大一笔，保证 Σ(分配) == 总价，杜绝一分钱对不上
    diff = total_cents - sum(allocated)
    if diff != 0:
        max_idx = weights.index(max(weights))
        allocated[max_idx] += diff

    as_of_date = as_of or date.today()

    # ── 资金进出检测（#1217）──
    # 必须在覆写 value_override_at **之前**取旧值：上次录入市值之后若又发生了申购/赎回/分红，
    # 「按各账户既有市值占比」这一分摊基数就不能反映实际持有了，需要提示用户在
    # 下一个开盘日更新其他存量持仓的总价（用户原始诉求）。
    last_override_at = max((p.value_override_at for p in positions if p.value_override_at), default=None)
    since_date = last_override_at.date() if last_override_at is not None else None
    has_cash_flow = _has_cash_flow_since(db, family_id, symbol, since_date)

    allocations = []
    for pos, cents in zip(positions, allocated):
        pos.market_value_override = cents
        pos.value_override_at = as_of_date
        allocations.append(
            {
                'position_id': pos.id,
                'ledger_id': pos.ledger_id,
                'allocated_cents': cents,
                'allocated_yuan': Money.cents_to_yuan(cents),
                'ratio': round(cents / total_cents, 6) if total_cents else 0.0,
            }
        )

    db.flush()
    return {
        'symbol': symbol,
        'total_value_cents': total_cents,
        'total_weight_cents': total_weight,
        'as_of': as_of_date.isoformat(),
        'allocations': allocations,
        # #1217：有资金进出时给出「下一个开盘日」提示，前端据此引导用户更新其他持仓
        'cash_flow_detected': has_cash_flow,
        'next_trading_day': next_trading_day(as_of_date).isoformat() if has_cash_flow else None,
    }


__all__ = ['allocate_value', 'market_value_cents']
