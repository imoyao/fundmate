# -*- coding: utf-8 -*-
"""场内前复权锚点查询（services/adj_close_lookup.py · #2773）测试。

只钉三件事，都是「会静默算错账」的地方：

1. **取 <= target 的最近一条**，不是精确相等——卖出日不一定是交易日；
2. **adj_close 缺失就不给数**，绝不回落到未复权 `close`；
3. **跨分红时两种口径给出方向相反的结果**——这条是本模块存在的理由，
   用 `close` 会把除权当成下跌。
"""

from datetime import date

from app.domains.price_history.models import PriceHistory
from app.services.adj_close_lookup import get_adj_close_at_or_before, symbol_of_exchange_identity


def _bar(db, symbol, day, close, adj_close=None, low=None, high=None):
    db.add(
        PriceHistory(
            security_id=1,
            symbol=symbol,
            trade_date=day,
            open=close,
            high=high if high is not None else close,
            low=low if low is not None else close,
            close=close,
            adj_close=adj_close,
        )
    )


def test_picks_latest_bar_at_or_before_target(db):
    """目标日不是交易日（周末）→ 取之前最近一条，并回真实交易日。"""
    _bar(db, 'SZ000001', date(2026, 5, 29), close=10.0, adj_close=10.0)
    _bar(db, 'SZ000001', date(2026, 6, 2), close=11.0, adj_close=11.0)
    db.commit()

    got = get_adj_close_at_or_before(db, ['SZ000001'], date(2026, 5, 31))

    assert got['SZ000001'] == (10.0, date(2026, 5, 29))


def test_missing_adj_close_is_absent_not_fallback_to_close(db):
    """只有 close 没有 adj_close → **缺席**，不拿未复权价顶替。

    顶替会让跨分红的收益凭空多出一截，比「没有数」更糟：用户看不出这是错的。
    """
    _bar(db, 'SZ000001', date(2026, 5, 29), close=10.0, adj_close=None)
    db.commit()

    assert get_adj_close_at_or_before(db, ['SZ000001'], date(2026, 5, 31)) == {}


def test_dividend_case_adj_close_differs_from_close(db):
    """跨分红：用 close 会算出 −5%（把除权当下跌），用 adj_close 是 +5.5%。

    这就是「场内必须用 adj_close」的可执行判据（#2773 验收标准原话）。
    """
    _bar(db, 'SZ000001', date(2026, 6, 1), close=10.0, adj_close=10.0)
    # 除权日：close 向下跳一个分红台阶，adj_close 连续
    _bar(db, 'SZ000001', date(2026, 7, 15), close=9.0, adj_close=10.0)
    _bar(db, 'SZ000001', date(2026, 10, 30), close=9.5, adj_close=10.55)
    db.commit()

    anchor = get_adj_close_at_or_before(db, ['SZ000001'], date(2026, 6, 1))['SZ000001'][0]
    latest = get_adj_close_at_or_before(db, ['SZ000001'], date(2026, 12, 31))['SZ000001'][0]

    assert round((latest / anchor - 1) * 100, 2) == 5.5

    # 用同一批数据的 close 会得出相反结论 —— 证明选择口径不是「等价实现」
    from app.domains.price_history.models import PriceHistory as PH

    closes = [row[0] for row in db.query(PH.close).filter(PH.symbol == 'SZ000001').order_by(PH.trade_date).all()]
    assert round((closes[-1] / closes[0] - 1) * 100, 2) == -5.0


def test_symbol_is_normalized_before_lookup(db):
    """调用方传裸码也能命中（行情表存的是归一形态）。"""
    _bar(db, 'SH600519', date(2026, 5, 29), close=1500.0, adj_close=1500.0)
    db.commit()

    assert 'SH600519' in get_adj_close_at_or_before(db, ['600519'], date(2026, 5, 31))


def test_empty_input_returns_empty(db):
    assert get_adj_close_at_or_before(db, [], date(2026, 5, 31)) == {}


def test_symbol_of_exchange_identity():
    """身份键 → 行情表代码；非场内返回 None（不猜）。"""
    assert symbol_of_exchange_identity('EXCHANGE:SZ000001') == 'SZ000001'
    assert symbol_of_exchange_identity('OTC:004369') is None
    assert symbol_of_exchange_identity('NO_VENUE:MGR_001') is None
    assert symbol_of_exchange_identity(None) is None
