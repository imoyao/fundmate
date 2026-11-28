# -*- coding: utf-8 -*-
"""资产快照的组合维度（D135）：写行、读档、互斥与反向判据。

背景：复盘页口径切换器的第三档（组合）此前被「净值曲线读不到组合档」卡住
（D134 第 4 洞）。组合档**不走** as-of 引擎：真库实测组合 #1 全周期派生 7.83s，
而快照读 240ms，一张曲线不该付 8 秒。故给 `asset_snapshots` 加 `portfolio_id`。

四条判据：

1. **写**：每个组合各落一行，值 = 该组合的持仓市值（显式归属覆盖账户继承）；
2. **读**：三档互不串味（家庭行不看组合参数、组合档不带账户/家庭行）；
3. **反向**：按成员账本过滤会把「改派走的持仓」算回来 ⇒ 组合一多出 100 元；
4. **参数**：两档同传 / 组合不存在 一律 `ValueError`（视图映射 400）。

夹具刻意让「继承」与「改派」两只同账户：「按账户过滤」的实现能把第 3 条判据
做成 200（等于「碰巧对」），而它正是真库那次 257→164 的同款错法。
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.domains.funds.models import DailyWorth
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.summary.models import AssetSnapshot
from app.services.summary_service import get_snapshots, write_asset_snapshot

SNAP_DATE = '2026-11-20'
DAY = dt.date(2026, 11, 20)


def _ledger(db, name, portfolio_id=None):
    row = Ledger(name=name, ledger_type='bank', family_id=1, portfolio_id=portfolio_id)
    db.add(row)
    db.commit()
    return row


def _nav(db, code, unit_nav):
    db.add(DailyWorth(fund_code=code, date=DAY, unit_nav=unit_nav))
    db.commit()


@pytest.fixture()
def seeded(db, make_position):
    """三只持仓 × 三种归属；净值取整，市值即「份额 × 净值」。"""
    p1 = Portfolio(name='组合一', family_id=1)
    p2 = Portfolio(name='组合二', family_id=1)
    p3 = Portfolio(name='空组合', family_id=1)
    db.add_all([p1, p2, p3])
    db.commit()
    l1 = _ledger(db, '继承账本', portfolio_id=p1.id)  # 账户默认归 p1
    l2 = _ledger(db, '外部账本')  # 不属于任何组合

    # 继承：随账户进 p1；改派：账户在 l1 但显式归 p2；外部显式：账本在 l2、显式归 p1
    make_position(symbol='000001', name='继承', quantity=100, avg_price=1.0, asset_type='fund', ledger_id=l1.id)
    make_position(
        symbol='000002',
        name='改派',
        quantity=100,
        avg_price=1.0,
        asset_type='fund',
        ledger_id=l1.id,
        portfolio_id=p2.id,
    )
    make_position(
        symbol='000003',
        name='外部显式',
        quantity=100,
        avg_price=1.0,
        asset_type='fund',
        ledger_id=l2.id,
        portfolio_id=p1.id,
    )
    _nav(db, '000001', 1.0)  # 100
    _nav(db, '000002', 1.0)  # 100
    _nav(db, '000003', 2.0)  # 200
    return {'p1': p1, 'p2': p2, 'p3': p3, 'l1': l1, 'l2': l2}


def _row(db, portfolio_id):
    return (
        db.query(AssetSnapshot)
        .filter(
            AssetSnapshot.family_id == 1,
            AssetSnapshot.portfolio_id == portfolio_id,
            AssetSnapshot.snapshot_date == DAY,
        )
        .one()
    )


class TestSnapshotWriteScope:
    def test_组合行按显式归属覆盖继承(self, db, seeded):
        """p1 = 继承 100 + 外部显式 200；改派到 p2 的那只不算进来。"""
        write_asset_snapshot(db, 1, SNAP_DATE)

        assert _row(db, seeded['p1'].id).total_assets == 30000  # 分
        assert _row(db, seeded['p2'].id).total_assets == 10000
        # 组合行不可能是负债：持仓没有负债语义，通用资产也不归组合
        assert _row(db, seeded['p1'].id).total_liabilities == 0
        assert _row(db, seeded['p1'].id).net_worth == 30000

    def test_空组合也落一行零值(self, db, seeded):
        """连续曲线需要每天都有点；「0」是「当前没有持仓」，不是「没记录」。"""
        write_asset_snapshot(db, 1, SNAP_DATE)
        assert _row(db, seeded['p3'].id).total_assets == 0

    def test_同日重复写入不新增行(self, db, seeded):
        """幂等：唯一键含 COALESCE(portfolio_id, -1)，同日覆盖而非新增。"""
        write_asset_snapshot(db, 1, SNAP_DATE)
        write_asset_snapshot(db, 1, SNAP_DATE)
        rows = db.query(AssetSnapshot).filter(AssetSnapshot.snapshot_date == DAY).all()
        # 家庭 1 + 账户 2（l1/l2）+ 组合 3
        assert len(rows) == 6
        assert _row(db, seeded['p1'].id).total_assets == 30000


class TestSnapshotReadScope:
    def test_三档互不串味(self, db, seeded):
        write_asset_snapshot(db, 1, SNAP_DATE)

        family = get_snapshots(db, 1)
        assert [r['net_worth'] for r in family] == [400.0]
        assert family[0]['portfolio_id'] is None

        ledger = get_snapshots(db, 1, ledger_id=seeded['l1'].id)
        assert [r['net_worth'] for r in ledger] == [200.0]

        portfolio = get_snapshots(db, 1, portfolio_id=seeded['p1'].id)
        assert [r['net_worth'] for r in portfolio] == [300.0]
        assert portfolio[0]['portfolio_id'] == seeded['p1'].id
        assert portfolio[0]['ledger_id'] is None

    def test_组合不存在抛错而不是返回空序列(self, db, seeded):
        """空曲线看起来是「还没记录」，真因却是「id 不存在」——必须 400。"""
        with pytest.raises(ValueError, match='投资组合不存在'):
            get_snapshots(db, 1, portfolio_id=999999)

    def test_两档同传抛错(self, db, seeded):
        with pytest.raises(ValueError, match='互斥'):
            get_snapshots(db, 1, ledger_id=seeded['l1'].id, portfolio_id=seeded['p1'].id)
