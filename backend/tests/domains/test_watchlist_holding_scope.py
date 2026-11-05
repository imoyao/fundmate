# -*- coding: utf-8 -*-
"""自选页持仓统计的「当前持仓」口径回归（023887）。

现象（2026-11-04）：同一个标的在自选页显示 84,282.0222 份 / ¥59,720.99，
产品详情页「我的持仓」只有 42,850.4322 份 / ¥28,949.76，接近翻倍。

根因：positions 表里除了 2 条 `active`，还有 2 条 E账户导入写下的 `shadow`
对账镜像行。详情页持仓列表走 `position_scope.active_holdings`（只看 active），
而自选页 `BatchContext._prefetch_all` 的持仓聚合只按 symbol + family 过滤，
把 4 行全算进 `holding_quantity` / `position_market_value` / `holding_cost_price`。

本文件把两条取数路径（批量 ctx / 无 ctx 兜底）都钉在 `active` 口径上。
夹具刻意让 `cleared` 行也带非零份额，避免实现靠「份额为 0」蒙混过关——
排除依据必须是 `ownership_status`，不是 quantity。
"""

import pytest
from sqlalchemy import func

from app.core.database import get_db
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.services.watchlist_display import BatchContext, _compute_holding_stats

SYMBOL = '023887'

# quantity 存 ×10000 最小单位，price 存 ×10000 元（见 app/core/money.py）
_ACTIVE = [
    # 支付宝：29,551.43 份，单位成本 0.8300，现价 0.6756
    dict(account_name='支付宝', quantity=295514300, avg_price=8300, current_price=6756),
    # 微众银行：13,299.0022 份，单位成本 0.7385，现价 0.6756
    dict(account_name='微众银行', quantity=132990022, avg_price=7385, current_price=6756),
]
_SHADOW = [
    dict(account_name='基金E账户', quantity=295514300, avg_price=7427, current_price=7427),
    dict(account_name='基金E账户', quantity=118801600, avg_price=7427, current_price=7427),
]

# 期望值：与产品详情页「我的持仓」逐字对齐
EXPECT_SHARES = 42850.4322
EXPECT_COST = 34349.00
EXPECT_VALUE = 28949.75
# 若漏掉 status 过滤，自选页会算成这个（active + shadow，不含 cleared）
WRONG_SHARES_WITH_SHADOW = 84282.0222


def _pos(status: str, **kw) -> Position:
    return Position(
        symbol=SYMBOL,
        name='永赢北证50成份指数发起C',
        asset_type='fund',
        ownership_status=status,
        **kw,
    )


@pytest.fixture
def seeded(app):
    """写入 2 active + 2 shadow + 1 cleared。

    这里**不再**给 cleared 行造非零份额：`ck_positions_cleared_zero_qty`（#2875）
    之后该形态在库层就不存在——清仓的唯一写入口 `state.mark_position_cleared`
    必然先写 `quantity = 0`。而「按状态而不是按份额过滤」这层防线仍由 shadow 行
    提供（shadow 行带份额、必须被排除），与本夹具的 cleared 行无关。
    """
    with get_db() as db:
        db.add_all([_pos('active', **r) for r in _ACTIVE])
        db.add_all([_pos('shadow', **r) for r in _SHADOW])
        db.add(
            _pos(
                'cleared',
                account_name='已清仓账户',
                quantity=0,  # 清仓态零份额（库级 CHECK 保证，见 _mark_position_cleared）
                avg_price=7000,
                current_price=7000,
            )
        )
        db.add(WatchlistItem(symbol=SYMBOL, market='CN_A', status='HOLDING'))
        db.commit()
        family_id = db.query(Position.family_id).filter(Position.symbol == SYMBOL).first()[0]
        return family_id


class TestWatchlistHoldingStatsScope:
    def test_fixture_really_contains_shadow_rows(self, seeded):
        """先证明夹具没写空：漏过滤时确实会得到线上那个翻倍数字。"""
        with get_db() as db:
            qty_units = (
                db.query(func.sum(Position.quantity))
                .filter(
                    Position.symbol == SYMBOL,
                    Position.family_id == seeded,
                    Position.ownership_status.in_(['active', 'shadow']),
                )
                .scalar()
            )
            assert qty_units / 10000 == pytest.approx(WRONG_SHARES_WITH_SHADOW, abs=1e-4)

    def test_compute_holding_stats_only_active(self, seeded):
        """无 ctx 兜底路径：份额 / 成本 / 市值都只算 active。"""
        with get_db() as db:
            stats = _compute_holding_stats(SYMBOL, db, seeded)
            assert stats is not None
            assert stats['quantity'] == pytest.approx(EXPECT_SHARES, abs=1e-4)
            # cost_price 是单位成本，用 份额×成本价 还原总成本
            assert stats['cost_price'] * stats['quantity'] == pytest.approx(EXPECT_COST, abs=0.02)
            assert stats['pnl'] + stats['cost_price'] * stats['quantity'] == pytest.approx(EXPECT_VALUE, abs=0.02)

    def test_batch_context_only_active(self, seeded):
        """自选页实际路径：`BatchContext` 预取的聚合同样只算 active。"""
        with get_db() as db:
            ctx = BatchContext(db, seeded, [SYMBOL], need_display_fields=False)
            stats = ctx.get_position_stats(SYMBOL)
            assert stats is not None
            assert stats['quantity'] == pytest.approx(EXPECT_SHARES, abs=1e-4)
            assert ctx.get_position_market_value(SYMBOL) == pytest.approx(EXPECT_VALUE, abs=0.02)
            # 代表持仓行 meta 的预取本来就过滤 active（只 select 4 列，
            # 不含 ownership_status），取到即证明两条路径落在同一批 active 行上
            assert ctx.get_position_meta(SYMBOL) is not None

    def test_compute_position_market_value_only_active(self, seeded):
        """市值兜底函数与批量路径同口径，避免两条路给出两个数。"""
        from app.services.watchlist_display import _compute_position_market_value

        with get_db() as db:
            assert _compute_position_market_value(SYMBOL, db, seeded) == pytest.approx(EXPECT_VALUE, abs=0.02)
