# -*- coding: utf-8 -*-
"""盈亏时间序列单测（#1220）。

验收标准：
- 能查到指定日期区间的已实现/未实现/总盈亏序列（按 family / ledger / 日期区间）
- 与 performance/xirr_engine.py 现金流口径一致（total = realized + unrealized）
- 后端单测覆盖：按账户查询、跨家庭隔离、区间边界
"""

from datetime import date as _date
from datetime import datetime as _dt

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.summary.models import AssetSnapshot
from app.services.analytics.cleared_cycles import build_cleared_cycles
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


class TestMarketValueBasisUnification:
    """TD-010：总资产市值统一到 T 日库内最新净值（与品类聚合同源），不再用 T-1 快照价。"""

    def test_total_assets_uses_t_day_nav(self, db, make_position):
        # 持仓快照价 2.0、库内最新净值 3.0 —— 两者必须能区分
        pos = make_position(
            symbol='000001',
            asset_type='fund',
            market='CN_A',
            quantity=100.0,
            avg_price=1.0,
            current_price=2.0,
            account_name='账户A',
        )
        db.add(DailyWorth(fund_code='000001', date=_date.today(), unit_nav=3.0))
        db.commit()
        result = write_asset_snapshot(db, 1, SNAP_DATE)
        # 100 份 × 3.0 净值 = 300 元；若回退快照价则是 200 元（TD-010 旧 bug）
        assert result['total_assets'] == 300.0


class TestFifoCanonicalRealizedPnl:
    """TD-011：已实现盈亏唯一真值源 = FIFO（cleared_cycles），且快照四列（移动平均）与之不同源。

    cleared_cycles 仅对「完全清仓（份额归零）」的周期给出 realized_pnl
    （见 cleared_cycles.py:252 `if not cycle['partial']`）；未清仓的部分卖出
    不产生可结算 FIFO 盈亏（pnl_known=False）。而快照四列读 transactions.realized_pnl
    （移动加权平均），部分卖出即有值。两者是**不同口径**，快照四列不得被当作
    FIFO 真值展示。
    """

    def test_fifo_canonical_realized_on_closed_position(self, db, make_position, make_transaction):
        """完全清仓时 FIFO 给出唯一真值：买 100@10、卖 100@14 → 已实现 400。"""
        pos = make_position(
            symbol='000001',
            asset_type='fund',
            market='CN_A',
            quantity=100.0,
            avg_price=10.0,
            current_price=10.0,
            account_name='账户A',
        )
        make_transaction(pos.id, pos.ledger_id, txn_type='buy', quantity=100, price=10.0, trade_date=_dt(2026, 1, 1))
        make_transaction(pos.id, pos.ledger_id, txn_type='sell', quantity=100, price=14.0, trade_date=_dt(2026, 2, 1))
        cycles = build_cleared_cycles(db, 1)['cycles']
        # 完全清仓 → 一个已关闭周期，FIFO 已实现 = 100×(14−10) = 400（唯一真值源）
        assert len(cycles) == 1
        assert cycles[0]['pnl_known'] is True
        assert cycles[0]['realized_pnl'] == 400.0

    def test_snapshot_realized_diverges_from_fifo(self, db, make_position, make_transaction):
        """未清仓时：快照四列（移动平均）= −100，而 FIFO 真值源尚无（不得静默统一两套口径）。"""
        pos = make_position(
            symbol='000001',
            asset_type='fund',
            market='CN_A',
            quantity=200.0,
            avg_price=15.0,
            current_price=15.0,
            account_name='账户A',
        )
        make_transaction(pos.id, pos.ledger_id, txn_type='buy', quantity=100, price=10.0, trade_date=_dt(2026, 1, 1))
        make_transaction(pos.id, pos.ledger_id, txn_type='buy', quantity=100, price=20.0, trade_date=_dt(2026, 1, 2))
        # 移动加权平均成本 = 15；部分卖出 100@14 → 移动平均已实现 = 100×(14−15) = −100
        make_transaction(
            pos.id,
            pos.ledger_id,
            txn_type='sell',
            quantity=100,
            price=14.0,
            realized_pnl=Money.yuan_to_cents(-100),
            trade_date=_dt(2026, 2, 1),
        )
        result = write_asset_snapshot(db, 1, SNAP_DATE)
        snapshot_realized = result['realized_pnl']
        # 快照四列读 transactions.realized_pnl（移动加权平均），部分卖出即有值 = −100
        assert snapshot_realized == -100.0
        # FIFO 真值源：持仓未完全清仓 → 无已关闭周期，canonical 不应给出已实现盈亏
        cycles = build_cleared_cycles(db, 1)['cycles']
        closed = [c for c in cycles if c['pnl_known']]
        assert closed == []
        # 守卫：两套口径不可静默统一 —— 快照有值、FIFO 暂无，证明它们来自不同计算
        assert snapshot_realized != 0
