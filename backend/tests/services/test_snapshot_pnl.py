# -*- coding: utf-8 -*-
"""盈亏时间序列单测（#1220）。

验收标准：
- 能查到指定日期区间的已实现/未实现/总盈亏序列（按 family / ledger / 日期区间）
- 与 performance/xirr_engine.py 现金流口径一致（total = realized + unrealized）
- 后端单测覆盖：按账户查询、跨家庭隔离、区间边界
"""

from app.core.money import Money
from app.domains.summary.models import AssetSnapshot
from app.services.summary_service import get_snapshots, write_asset_snapshot

SNAP_DATE = '2026-08-30'


def _position_in(make_position, account_name, *, price=2.0, quantity=100.0, avg_price=1.0, **extra):
    """在某个账户下建一笔持仓，返回持仓对象（ledger_id 由 fixture 自动建账户）。"""
    return make_position(
        symbol='000001',
        asset_type='fund',
        market='CN_A',
        quantity=quantity,
        avg_price=avg_price,
        current_price=price,
        account_name=account_name,
        **extra,
    )


class TestSnapshotPnlColumns:
    def test_family_pnl_columns_written(self, db, make_position, make_transaction):
        """家庭级快照落 realized/unrealized/total 三列（分）。"""
        pos = _position_in(make_position, '账户A', price=3.0, quantity=100.0, avg_price=1.0)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=50,
            price=3.0,
            realized_pnl=Money.yuan_to_cents(50),
        )
        result = write_asset_snapshot(db, 1, SNAP_DATE)
        # unrealized = (3-1)*100 = 200元；realized=50元；total=250元
        assert result['realized_pnl'] == 50.0
        assert result['unrealized_pnl'] == 200.0
        assert result['total_pnl'] == 250.0

    def test_identity_total_equals_realized_plus_unrealized(self, db, make_position, make_transaction):
        """恒等式：total = realized + unrealized（与 XIRR 现金流口径一致）。"""
        pos = _position_in(make_position, '账户A', price=4.0, quantity=100.0, avg_price=2.0)
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=30,
            price=4.0,
            realized_pnl=Money.yuan_to_cents(80),
        )
        write_asset_snapshot(db, 1, SNAP_DATE)
        row = db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id.is_(None)).one()
        assert row.total_pnl_cents == row.realized_pnl_cents + row.unrealized_pnl_cents


class TestLedgerScopedPnl:
    def test_ledger_pnl_series(self, db, make_position):
        """按 ledger_id 查到该账户的盈亏序列（验收：按账户查询）。"""
        pos_a = _position_in(make_position, '账户A', price=3.0, quantity=100.0, avg_price=1.0)  # unrealized=200
        _position_in(make_position, '账户B', price=5.0, quantity=100.0, avg_price=2.0)  # unrealized=300
        write_asset_snapshot(db, 1, SNAP_DATE)

        series = get_snapshots(db, 1, ledger_id=pos_a.ledger_id)
        assert len(series) == 1
        assert series[0]['realized_pnl'] == 0.0
        assert series[0]['unrealized_pnl'] == 200.0
        assert series[0]['total_pnl'] == 200.0

    def test_date_range_boundary(self, db, make_position):
        """账户级盈亏序列支持日期区间筛选（验收：区间边界）。"""
        pos = _position_in(make_position, '账户A', price=3.0, quantity=100.0, avg_price=1.0)
        write_asset_snapshot(db, 1, '2026-08-01')
        write_asset_snapshot(db, 1, '2026-08-10')
        write_asset_snapshot(db, 1, '2026-08-20')

        series = get_snapshots(db, 1, start_date='2026-08-05', end_date='2026-08-15', ledger_id=pos.ledger_id)
        assert [row['snapshot_date'] for row in series] == ['2026-08-10']


class TestFamilyIsolationPnl:
    def test_pnl_isolated_across_families(self, db, make_position):
        """跨家庭隔离：家庭 2 的盈亏快照对家庭 1 不可见（验收：跨家庭隔离）。"""
        pos_a = _position_in(make_position, '账户A', price=3.0, quantity=100.0, avg_price=1.0)
        write_asset_snapshot(db, 1, SNAP_DATE)

        pos_b = make_position(
            symbol='000002',
            asset_type='fund',
            market='CN_A',
            quantity=100.0,
            avg_price=1.0,
            current_price=9.0,
            account_name='家庭2账户',
            family_id=2,
        )
        write_asset_snapshot(db, 2, SNAP_DATE)

        assert get_snapshots(db, 1, ledger_id=pos_b.ledger_id) == []
        assert len(get_snapshots(db, 2, ledger_id=pos_b.ledger_id)) == 1
        assert len(get_snapshots(db, 1, ledger_id=pos_a.ledger_id)) == 1


class TestBalanceModePnl:
    def test_balance_mode_unrealized_uses_net_invested(self, db, make_position, make_transaction):
        """balance 模式：成本基数取净投入，未实现盈亏 = 市值 - 净投入。"""
        pos = make_position(
            symbol='LC001',
            asset_type='other',
            market='CN_A',
            quantity=0,
            avg_price=0,
            current_price=0,
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(500),
            account_name='理财账户',
        )
        # 净投入 300元（一笔 deposit），unrealized = 500 - 300 = 200元
        make_transaction(pos.id, pos.ledger_id, txn_type='deposit', quantity=0, price=0, amount=300)
        write_asset_snapshot(db, 1, SNAP_DATE)
        series = get_snapshots(db, 1, ledger_id=pos.ledger_id)
        assert series[0]['unrealized_pnl'] == 200.0
