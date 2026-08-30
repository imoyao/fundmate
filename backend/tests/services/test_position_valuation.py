# -*- coding: utf-8 -*-
"""持仓市值唯一口径单测（#1174 / 决策 D1 方案 A）。

覆盖三种情形：

- `nav` 模式：份额 × 有效净值（无净值时回退快照价）
- `balance` 模式：市值只能来自 override；未录入时按 0 计并告警
- `override`：人工录入市值优先于任何派生计算

`market_value_cents` 是纯函数（不查库、不跨数据域），故用轻量 stub 承载字段即可，
无需数据库夹具。

单位约定（与 Money 工具类一致）：
- `quantity`：最小单位 ×10000（1000000 → 100 份）
- `current_price`：price_units ×10000（15000 → 1.5 元）
- `market_value_override`：分（15000 → 150 元）
"""

from types import SimpleNamespace

from app.core.constants import ValuationMode
from app.services.position_valuation import market_value_cents


def _nav_position(quantity: int = 1000000, current_price: int = 15000, currency: str = 'CNY'):
    """100 份 × 1.5 元 = 150 元 = 15000 分。"""
    return SimpleNamespace(
        id=1,
        quantity=quantity,
        current_price=current_price,
        avg_price=10000,
        currency=currency,
        valuation_mode=ValuationMode.NAV.value,
        market_value_override=None,
    )


def test_nav_mode_uses_shares_times_price():
    """基线：份额 × 快照价（无净值时回退 current_price）。"""
    assert market_value_cents(_nav_position()) == 15000


def test_nav_mode_prefers_effective_nav():
    """传了有效净值就用净值，忽略快照价——与 NavService 口径一致。"""
    assert market_value_cents(_nav_position(), effective_nav_yuan=2.0) == 20000


def test_override_wins_over_nav_calculation():
    """人工录入市值优先于派生计算（投顾/理财等拿不到净值的标的）。"""
    p = _nav_position()
    p.market_value_override = 88888
    # 即便传了净值，override 仍然胜出
    assert market_value_cents(p, effective_nav_yuan=2.0) == 88888


def test_balance_mode_with_override():
    """balance 模式没有份额可乘，市值完全由 override 提供。"""
    p = _nav_position(quantity=0, current_price=0)
    p.valuation_mode = ValuationMode.BALANCE.value
    p.market_value_override = 123456
    assert market_value_cents(p) == 123456


def test_balance_mode_without_override_is_zero():
    """balance 模式未录入市值 → 0，绝不静默给错误数字（函数内已记 warning）。"""
    p = _nav_position(quantity=0, current_price=0)
    p.valuation_mode = ValuationMode.BALANCE.value
    assert market_value_cents(p) == 0


def test_rate_applies_to_override():
    """汇率对 override 同样生效（本币分 → CNY 分）。"""
    p = _nav_position(currency='USD')
    p.market_value_override = 10000
    assert market_value_cents(p, rate=7.0) == 70000


def test_missing_fields_fall_back_to_nav():
    """缺 valuation_mode / market_value_override 字段时按 nav 安全降级（兼容老数据与 mock）。"""
    legacy = SimpleNamespace(id=2, quantity=1000000, current_price=15000, currency='CNY')
    assert market_value_cents(legacy) == 15000
