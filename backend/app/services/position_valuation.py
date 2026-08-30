# -*- coding: utf-8 -*-
"""持仓市值计算的唯一口径（#1174 / 决策 D1 方案 A）。

WHY
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

数据域约束：只读持仓自身字段与调用方传入的净值，**不查库、不跨数据域**
（对比 `position_aggregation.py:137-143`：跨域读可以、写不行）。
"""

from decimal import Decimal

from loguru import logger

from app.core.constants import ValuationMode
from app.core.money import Money


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
