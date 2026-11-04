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


def _shadow_position(db, symbol: str, *, quantity: float = 1000.0, account_name: str = '基金E账户'):
    """E账户对账镜像行：按真实形态造——`ledger_id` 恒为 NULL、`account_name` 恒为「基金E账户」。"""
    pos = Position(
        symbol=symbol,
        name=f'测试{symbol}',
        asset_type='fund',
        ledger_id=None,
        account_name=account_name,
        family_id=1,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(1.0),
        ownership_status=OwnershipStatus.SHADOW.value,
        source='e_account_holding',
    )
    db.add(pos)
    db.flush()
    return pos


class TestPositionListHidesShadow:
    """`GET /api/positions/` 不得返回 E账户对账镜像行（2026-10-28 实测事故）。

    事故形态：021180 在产品详情「我的持仓」出现两组——「基金E账户 3,421.96 份」
    与「微众银行 3,421.9622 份」，市值翻倍。根因是 `build_position_list` 只挂了
    `exclude_cleared`，镜像行经 `ledger_id IS NULL` 通道原样返回，前端
    `groupByLedger` 又把 `account_name` 当渠道名，于是凭空多出一个「账户」。

    四个入口都锁：分页列表 / 产品维度过滤（详情页「我的持仓」）/ 按账户分组 /
    未归档过滤（`ledger_id='null'`）——它们是同一个 query 的不同分支，任一漏掉
    都会让镜像行从另一条缝里钻回来。
    """

    def _build(self, db, **kwargs):
        from app.services.position_service import PositionService

        params = dict(family_id=1, group_by='', page=1, per_page=20, ledger_id_raw='')
        params.update(kwargs)
        return PositionService.build_position_list(db, **params)

    def test_paginated_list_hides_shadow(self, db, ledger):
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _shadow_position(db, '000002')

        data = self._build(db)

        assert [i['symbol'] for i in data['data']] == ['000001'], '持仓列表不能出现对账镜像行'
        assert data['total'] == 1

    def test_symbol_filter_hides_shadow(self, db, ledger):
        """产品详情「我的持仓」走 `symbol=` 过滤，镜像行必须以同一口径消失。"""
        _position(db, ledger, '021180', status=OwnershipStatus.ACTIVE.value, quantity=3421.9622)
        _shadow_position(db, '021180', quantity=3421.96)

        data = self._build(db, symbol='021180')

        assert len(data['data']) == 1, '同一只基金不能同时出现真身与镜像行'
        assert data['data'][0]['ledger_id'] == ledger.id
        assert data['data'][0]['account_name'] != '基金E账户'

    def test_group_by_account_has_no_unfiled_group_for_shadow_only(self, db, ledger):
        """按账户分组时，镜像行的 `ledger_id IS NULL` 会落进 'unfiled' 组——不得出现。"""
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _shadow_position(db, '000002')

        data = self._build(db, group_by='account')

        assert 'unfiled' not in (data['data'] or {}), f'未归档分组里不该只有镜像行，实际: {data["data"]}'

    def test_unfiled_filter_hides_shadow(self, db, ledger):
        """`ledger_id='null'`（未归档持仓）分支同样不能返回镜像行。"""
        _position(db, ledger, '000001', status=OwnershipStatus.ACTIVE.value)
        _shadow_position(db, '000002')

        data = self._build(db, ledger_id_raw='null')

        assert data['data'] == [], '本地库 93 条 NULL-ledger 行全是镜像行，没有真实未归档持仓'
        assert data['total'] == 0

    def test_keeps_real_unfiled_active_position(self, db, ledger):
        """防修复过宽：真实的未归档持仓（active + ledger_id NULL）必须照旧可见。

        刻意只断言「在」，不断言完整列表——完整列表会让本条在修复前也变红，
        就失去了「区分修复过宽 / 修复到位」的作用：这条要在修复前后**都绿**。
        """
        real_unfiled = Position(
            symbol='000003',
            name='测试000003',
            asset_type='fund',
            ledger_id=None,
            account_name='某渠道',
            family_id=1,
            quantity=Money.shares_to_min_unit(500.0),
            avg_price=Money.yuan_to_price_units(1.0),
            ownership_status=OwnershipStatus.ACTIVE.value,
            source='manual',
        )
        db.add(real_unfiled)
        _shadow_position(db, '000002')
        db.flush()

        data = self._build(db, ledger_id_raw='null')

        symbols = [i['symbol'] for i in data['data']]
        assert '000003' in symbols, '真实的未归档持仓不能被一并过滤掉（修复过宽）'
