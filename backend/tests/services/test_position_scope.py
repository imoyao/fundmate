# -*- coding: utf-8 -*-
"""持仓可见性口径（`services/position_scope.py`）的回归网 —— issue #2343 第一步。

## 锁的是什么

引入 `ownership_status='cleared'` 之前，全仓 68 处 `query(Position)` 里只有 6 处
显式过滤状态。持仓列表 `build_position_list` 和账户统计/分页（`ledger_service`）
**都没过滤**，靠的是「表里每一行都是当前持仓」这个隐含前提。

清仓改为「保留行 + 标记 cleared」后，这个前提被打破。本文件锁两件事：

1. **过滤器本身正确**：`exclude_cleared` 只排 cleared、不动 active/shadow；
   `active_holdings` 连 shadow 也排掉。
2. **过滤器是恒等变换**：库里没有 cleared 行时，挂了过滤器的查询与不挂返回同一批行。
   这是「先铺过滤器、再改删除行为」这个两阶段迁移得以安全的前提——
   第一步上线时**不允许**有任何可见变化。
"""

import pytest

from app.core.constants import OwnershipStatus
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.ledger_service import LedgerService
from app.services.position_scope import active_holdings, exclude_cleared


@pytest.fixture
def ledger(db):
    lg = Ledger(name='基金账户', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger, symbol: str, *, status: str, quantity: float = 1000.0, avg_price: float = 1.0):
    pos = Position(
        symbol=symbol,
        name=f'测试{symbol}',
        asset_type='fund',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        ownership_status=status,
        source='manual',
    )
    db.add(pos)
    db.flush()
    return pos


def _symbols(rows):
    return sorted(p.symbol for p in rows)


class TestFilterSemantics:
    def test_no_cleared_rows_means_identity(self, db, ledger):
        """恒等变换：库里没有 cleared 行时，过滤前后返回同一批行。

        这条是两阶段迁移的安全底线——第一步上线不允许有任何可见变化。
        """
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000002', status=OwnershipStatus.SHADOW.value, quantity=0.0)
        db.flush()

        raw = _symbols(db.query(Position).filter(Position.ledger_id == ledger.id).all())
        scoped = _symbols(exclude_cleared(db.query(Position).filter(Position.ledger_id == ledger.id)).all())

        assert raw == ['000001', '000002'], '夹具应同时覆盖 active 与 shadow'
        assert scoped == raw, '无 cleared 行时过滤器必须是恒等变换'

    def test_exclude_cleared_drops_only_cleared(self, db, ledger):
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000002', status=OwnershipStatus.SHADOW.value, quantity=0.0)
        _position(db, ledger, '000003', status=OwnershipStatus.CLEARED.value, quantity=0.0)
        db.flush()

        scoped = _symbols(exclude_cleared(db.query(Position).filter(Position.ledger_id == ledger.id)).all())

        # shadow 不在持仓列表之外——它要等用户归属，必须看得见
        assert scoped == ['000001', '000002']

    def test_active_holdings_drops_shadow_too(self, db, ledger):
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000002', status=OwnershipStatus.SHADOW.value, quantity=0.0)
        _position(db, ledger, '000003', status=OwnershipStatus.CLEARED.value, quantity=0.0)
        db.flush()

        scoped = _symbols(active_holdings(db.query(Position).filter(Position.ledger_id == ledger.id)).all())

        # 总资产口径：未归属的 shadow 与已清仓都不能计入
        assert scoped == ['000001']


class TestCurrentHoldingViews:
    """真正会被用户看到的入口：已清仓行必须消失，其余行为不变。"""

    def test_positions_paginated_hides_cleared(self, db, ledger):
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000003', status=OwnershipStatus.CLEARED.value, quantity=0.0)
        db.flush()

        rows, total = LedgerService.get_positions_paginated(db, ledger.id, page=1, per_page=20)

        assert total == 1, '分页 total 不能把已清仓行算进去，否则前端出现空页'
        assert [r['symbol'] for r in rows] == ['000001']

    def test_positions_paginated_keeps_shadow(self, db, ledger):
        """shadow（E账户未归属）在账户明细里仍要可见——本次只排 cleared。"""
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000002', status=OwnershipStatus.SHADOW.value, quantity=0.0)
        db.flush()

        _, total = LedgerService.get_positions_paginated(db, ledger.id, page=1, per_page=20)

        assert total == 2

    def test_build_position_list_hides_cleared(self, db, ledger):
        from app.services.position_service import PositionService

        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _position(db, ledger, '000003', status=OwnershipStatus.CLEARED.value, quantity=0.0)
        db.flush()

        data = PositionService.build_position_list(
            db,
            family_id=1,
            group_by='',
            page=1,
            per_page=20,
            ledger_id_raw=str(ledger.id),
        )

        symbols = sorted(item['symbol'] for item in data['data'])
        assert symbols == ['000001'], '持仓列表不能出现已清仓行'
        assert data['total'] == 1
