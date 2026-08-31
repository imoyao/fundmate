# -*- coding: utf-8 -*-
"""账户维度资产快照单测（#1181）。

覆盖 issue 验收标准：
1. GET /api/summary/snapshots/ 支持 ledger_id 筛选
2. 能查到某账户在指定日期区间的市值序列
3. 无净值产品（balance 模式）的市值能正确进入快照
4. 后端单测覆盖账户维度查询与跨家庭隔离
"""

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.summary.models import AssetSnapshot
from app.services.summary_service import get_snapshots, write_asset_snapshot

SNAP_DATE = '2026-08-30'


def _position_in(make_position, account_name, *, price=2.0, quantity=100.0, **extra):
    """在某个账户下建一笔持仓，返回持仓对象（ledger_id 由 fixture 自动建账户）。"""
    return make_position(
        symbol='000001',
        asset_type='fund',
        market='CN_A',
        quantity=quantity,
        avg_price=1.0,
        current_price=price,
        account_name=account_name,
        **extra,
    )


class TestLedgerScopedSnapshot:
    def test_write_snapshot_creates_family_and_ledger_rows(self, db, make_position):
        """一次快照同时落「家庭级」与「各账户级」两类行。"""
        pos_a = _position_in(make_position, '账户A', price=2.0, quantity=100.0)  # 市值 200元
        pos_b = _position_in(make_position, '账户B', price=3.0, quantity=100.0)  # 市值 300元

        result = write_asset_snapshot(db, 1, SNAP_DATE)
        assert result['ledger_id'] is None  # 写入侧返回家庭级行

        family_rows = db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id.is_(None)).all()
        ledger_rows = db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id.isnot(None)).all()

        assert len(family_rows) == 1
        assert family_rows[0].total_assets == Money.yuan_to_cents(500)  # 200 + 300
        assert {r.ledger_id for r in ledger_rows} == {pos_a.ledger_id, pos_b.ledger_id}

        by_ledger = {r.ledger_id: r for r in ledger_rows}
        assert by_ledger[pos_a.ledger_id].total_assets == Money.yuan_to_cents(200)
        assert by_ledger[pos_b.ledger_id].total_assets == Money.yuan_to_cents(300)

    def test_upsert_idempotent_per_ledger(self, db, make_position):
        """同一天重复快照：每个账户作用域内仍是覆盖而非新增。"""
        pos = _position_in(make_position, '账户A', price=2.0, quantity=100.0)
        write_asset_snapshot(db, 1, SNAP_DATE)

        pos.current_price = Money.yuan_to_price_units(5.0)  # 市值 200 → 500
        db.commit()
        write_asset_snapshot(db, 1, SNAP_DATE)

        rows = db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id == pos.ledger_id).all()
        assert len(rows) == 1
        assert rows[0].total_assets == Money.yuan_to_cents(500)

    def test_no_ledger_rows_for_orphan_amounts(self, db):
        """无账户归属的资产不单独立行（哨兵键 0 不是合法账户 id）。"""
        db.add(
            Asset(
                family_id=1,
                major_category='cash',
                name='游离现金',
                amount=Money.yuan_to_cents(1000),
                currency='CNY',
            )
        )
        db.commit()
        write_asset_snapshot(db, 1, SNAP_DATE)

        assert db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id == 0).count() == 0
        family_row = db.query(AssetSnapshot).filter(AssetSnapshot.ledger_id.is_(None)).one()
        assert family_row.total_assets == Money.yuan_to_cents(1000)


class TestGetSnapshotsByLedger:
    def test_filter_by_ledger_returns_only_that_account(self, db, make_position):
        """传入 ledger_id 只返回该账户的序列（验收第 1、2 条）。"""
        pos_a = _position_in(make_position, '账户A', price=2.0, quantity=100.0)  # 200元
        _position_in(make_position, '账户B', price=3.0, quantity=100.0)  # 300元
        write_asset_snapshot(db, 1, SNAP_DATE)

        series = get_snapshots(db, 1, ledger_id=pos_a.ledger_id)
        assert len(series) == 1
        assert series[0]['ledger_id'] == pos_a.ledger_id
        assert series[0]['total_assets'] == 200.0

    def test_family_series_excludes_ledger_rows(self, db, make_position):
        """不传 ledger_id 时只返回家庭级序列，账户行不得混入（否则走势被重复计算）。"""
        _position_in(make_position, '账户A', price=2.0, quantity=100.0)
        write_asset_snapshot(db, 1, SNAP_DATE)

        series = get_snapshots(db, 1)
        assert len(series) == 1
        assert series[0]['ledger_id'] is None
        assert series[0]['total_assets'] == 200.0

    def test_date_range_filter(self, db, make_position):
        """账户级序列同样支持日期区间筛选。"""
        pos = _position_in(make_position, '账户A', price=2.0, quantity=100.0)
        write_asset_snapshot(db, 1, '2026-08-01')
        write_asset_snapshot(db, 1, '2026-08-10')
        write_asset_snapshot(db, 1, '2026-08-20')

        series = get_snapshots(db, 1, start_date='2026-08-05', end_date='2026-08-15', ledger_id=pos.ledger_id)
        assert [row['snapshot_date'] for row in series] == ['2026-08-10']

    def test_yoy_base_stays_within_ledger_scope(self, db, make_position):
        """账户级同比基准必须取自同一账户，不能拿家庭总额去比账户走势。"""
        pos = _position_in(make_position, '账户A', price=1.0, quantity=100.0)  # 100元
        write_asset_snapshot(db, 1, '2025-08-30')

        pos.current_price = Money.yuan_to_price_units(1.5)  # 150元
        db.commit()
        write_asset_snapshot(db, 1, '2026-08-30')

        series = get_snapshots(db, 1, ledger_id=pos.ledger_id)
        latest = series[-1]
        assert latest['net_worth'] == 150.0
        assert latest['yearly_change_pct'] == 50.0  # (150-100)/100

    def test_family_isolation(self, db, make_position):
        """跨家庭隔离：家庭 2 的账户快照对家庭 1 不可见。"""
        pos_a = _position_in(make_position, '账户A', price=2.0, quantity=100.0)
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

        # 家庭 1 按 ledger_id 查不到家庭 2 的账户
        assert get_snapshots(db, 1, ledger_id=pos_b.ledger_id) == []
        # 家庭 2 能看到自己的账户序列
        assert len(get_snapshots(db, 2, ledger_id=pos_b.ledger_id)) == 1
        # 家庭 1 的账户序列不受影响
        assert len(get_snapshots(db, 1, ledger_id=pos_a.ledger_id)) == 1


class TestBalanceModeInSnapshot:
    def test_balance_mode_market_value_enters_snapshot(self, db, make_position):
        """balance 模式（份额/价格为 0、市值靠 override）必须正确计入快照（验收第 3 条）。

        这是 `_pos_mv` 口径分叉修复的回归锁：修复前该函数裸算「份额 × 快照价」，
        balance 模式恒为 0，无净值产品永远进不了资产快照。
        """
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
        write_asset_snapshot(db, 1, SNAP_DATE)

        series = get_snapshots(db, 1, ledger_id=pos.ledger_id)
        assert series[0]['total_assets'] == 500.0

        family_series = get_snapshots(db, 1)
        assert family_series[0]['total_assets'] == 500.0

    def test_balance_mode_consistent_with_dashboard(self, db, make_position):
        """快照总额必须与仪表盘总额同口径（快照源自分账户聚合，不得再分叉）。"""
        from app.services.summary_service import get_distributions, get_ledger_distributions

        make_position(
            symbol='LC002',
            asset_type='other',
            market='CN_A',
            quantity=0,
            avg_price=0,
            current_price=0,
            valuation_mode='balance',
            market_value_override=Money.yuan_to_cents(800),
            account_name='理财账户',
        )
        db.commit()

        family = get_distributions(db, 1)['total_assets']
        per_ledger_sum = sum(v['total_assets'] for v in get_ledger_distributions(db, 1).values())
        assert round(per_ledger_sum, 2) == family


class TestSnapshotsEndpointLedgerFilter:
    def test_endpoint_accepts_ledger_id(self, client, db, make_position):
        """GET /api/summary/snapshots/?ledger_id=N 只返回该账户序列（验收第 1 条）。"""
        pos_a = _position_in(make_position, '账户A', price=2.0, quantity=100.0)
        _position_in(make_position, '账户B', price=7.0, quantity=100.0)
        db.commit()

        resp = client.post('/api/summary/snapshots/', json={'snapshot_date': SNAP_DATE})
        assert resp.status_code == 200

        resp = client.get(f'/api/summary/snapshots/?ledger_id={pos_a.ledger_id}')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['ledger_id'] == pos_a.ledger_id
        assert data[0]['total_assets'] == 200.0

    def test_endpoint_without_ledger_returns_family(self, client, db, make_position):
        """不带 ledger_id 时保持既有行为：返回家庭级序列。"""
        _position_in(make_position, '账户A', price=2.0, quantity=100.0)
        db.commit()
        client.post('/api/summary/snapshots/', json={'snapshot_date': SNAP_DATE})

        data = client.get('/api/summary/snapshots/').get_json()['data']
        assert len(data) == 1
        assert data[0]['ledger_id'] is None
