# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11
# File : test_transactions.py

from datetime import date, timedelta

import pytest

from app.core.constants import PositionSource
from app.core.database import get_db
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.transaction_service import fee_breakdown_yuan
from tests.domains.test_positions import _get, _post


def test_transaction_types_coverage(client):
    """覆盖所有操作类型：buy, sell, dividend, deposit, withdraw"""
    # 1. 买入创建持仓
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions/')
    pos_id = list_resp.get_json()['data'][0]['id']

    # 2. 卖出部分
    _post(
        client,
        '/api/positions/',
        {
            'op_type': 'sell',
            'position_id': pos_id,
            'quantity': 30,
            'avg_price': 400,
            'trade_date': '2026-05-03',
            'account_name': '富途',
        },
    )
    # 3. 分红
    _post(
        client,
        '/api/positions/',
        {
            'op_type': 'dividend',
            'position_id': pos_id,
            'avg_price': 500,  # 分红金额暂存
            'trade_date': '2026-05-04',
            'account_name': '富途',
        },
    )
    # 4. 存入
    _post(
        client,
        '/api/positions/',
        {
            'op_type': 'deposit',
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 360,
            'currency': 'HKD',
            'trade_date': '2026-05-02',
        },
    )
    # 5. 取出（先取出部分，避免清空）
    _post(
        client,
        '/api/positions/',
        {
            'op_type': 'withdraw',
            'position_id': pos_id,
            'quantity': 20,
            'avg_price': 370,
            'trade_date': '2026-05-05',
            'account_name': '富途',
        },
    )

    # 查询所有流水
    resp = _get(client, '/api/transactions')
    txn_list = resp.get_json()['data']
    assert len(txn_list) == 5
    type_set = {t['type'] for t in txn_list}
    assert type_set == {'buy', 'sell', 'dividend', 'deposit', 'withdraw'}


def test_transactions_filter_by_type(client):
    """按操作类型筛选"""
    _post(
        client,
        '/api/positions/',
        {
            'symbol': 'AAPL',
            'name': '苹果',
            'type': 'stock',
            'market': 'US',
            'account_name': '富途',
            'quantity': 10,
            'avg_price': 180,
            'currency': 'USD',
            'trade_date': '2026-05-01',
        },
    )
    list_resp = _get(client, '/api/positions/')
    pos_id = list_resp.get_json()['data'][0]['id']
    _post(
        client,
        '/api/positions/',
        {
            'op_type': 'sell',
            'position_id': pos_id,
            'quantity': 10,
            'avg_price': 190,
            'trade_date': '2026-05-05',
            'account_name': '富途',
        },
    )

    resp_buy = _get(client, '/api/transactions', {'type': 'buy'})
    assert len(resp_buy.get_json()['data']) == 1

    resp_sell = _get(client, '/api/transactions', {'type': 'sell'})
    assert len(resp_sell.get_json()['data']) == 1


def test_transactions_time_range(client):
    """时间范围筛选"""
    today = date.today()
    old_date = (today - timedelta(days=400)).isoformat()
    recent_date = (today - timedelta(days=5)).isoformat()

    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': old_date,
        },
    )
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 50,
            'avg_price': 380,
            'currency': 'HKD',
            'trade_date': recent_date,
        },
    )

    resp = _get(client, '/api/transactions', {'time_range': '1m'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['trade_date'] == recent_date


def test_transactions_pagination(client):
    """分页测试"""
    for i in range(5):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': f'00{i}00.HK',
                'name': f'股票{i}',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 100,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )

    resp = _get(client, '/api/transactions', {'page': 1, 'per_page': 2})
    result = resp.get_json()
    assert len(result['data']) == 2
    assert result['total'] == 5
    assert result['page'] == 1


def test_transactions_asset_type_filter(client):
    """按资产类型筛选（stock / fund）"""
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
        },
    )
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '000001',
            'name': '华夏成长',
            'type': 'fund',
            'market': 'CN_A',
            'account_name': '支付宝',
            'quantity': 1000,
            'avg_price': 1.5,
            'currency': 'CNY',
            'trade_date': '2026-05-01',
        },
    )

    resp_stock = _get(client, '/api/transactions', {'asset_type': 'stock'})
    data_stock = resp_stock.get_json()['data']
    assert len(data_stock) == 1

    resp_fund = _get(client, '/api/transactions', {'asset_type': 'fund'})
    data_fund = resp_fund.get_json()['data']
    assert len(data_fund) == 1


def test_transactions_status_filter(client, db):
    """按交易状态筛选（手动创建非 success 记录）"""
    # 先创建一个普通 success 记录
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
        },
    )

    # 插入一条 failed 记录
    failed_txn = Transaction(
        position_id=1,
        txn_type='buy',
        trade_date=date.today(),
        quantity=50,
        price=100,
        amount=5000,
        status='failed',
        position_name='测试',
        account_name='测试账户',
    )
    db.add(failed_txn)
    db.commit()

    resp = _get(client, '/api/transactions', {'status': 'failed'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['status'] == 'failed'


def test_transaction_type_field(client):
    """交易流水返回的 type 字段正确映射"""
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 10,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
        },
    )
    resp = _get(client, '/api/transactions')
    t_list = resp.get_json()['data']
    assert len(t_list) == 1
    assert t_list[0]['type'] == 'buy'


def test_transactions_export_csv(client):
    """交易流水导出 CSV：列与金额换算正确，且包含家庭内全部交易。"""
    _post(
        client,
        '/api/positions/',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
        },
    )

    resp = client.get('/api/transactions/export/')
    assert resp.status_code == 200
    assert resp.mimetype.startswith('text/csv')
    assert 'filename=transactions_' in resp.headers.get('Content-Disposition', '')

    text = resp.get_data(as_text=True)
    lines = text.strip().splitlines()
    # 表头 + 1 条流水
    assert len(lines) == 2
    header = lines[0]
    assert '业务类型' in header
    row = lines[1]
    # 价格 350元（0.0001元 单位下存储为 3500000）经 price_units_to_yuan 导出为 350.00；数量 100 正常落入 CSV
    assert '350.00' in row
    assert row.split(',')[0] == '2026-05-01'


def _make_txn(db, **kw):
    """在给定会话内构造一条交易流水（family_id 默认 1，对齐生产契约）。"""
    txn = Transaction(
        position_id=kw.get('position_id'),
        ledger_id=kw.get('ledger_id'),
        family_id=1,
        txn_type=kw['txn_type'],
        quantity=Money.shares_to_min_unit(kw.get('quantity', 0)),
        price=Money.yuan_to_cents(kw.get('price', 0)),
        symbol=kw.get('symbol'),
        position_name=kw.get('position_name'),
        account_name=kw.get('account_name'),
    )
    db.add(txn)
    db.flush()
    return txn


class TestTransactionDeleteRollback:
    """删除交易记录须回滚持仓份额（#948 后续）。

    删除单条交易不再只是删流水，而是按该持仓剩余流水重算份额，
    从而把卖出/取出减少的份额加回，避免账面份额丢失。
    端点已从 ledgers 域迁出至 transactions 域：DELETE /api/transactions/<id>/
    归属按 Transaction.family_id 校验，回滚逻辑收口在 PositionService。

    测试统一在应用上下文内用 get_db() 落库，与端点会话共享同一内存库，
    规避 sqlite :memory: 每连接独立库的隔离问题（数据须经 get_db 写入才对端点可见）。
    """

    def _seed_position_with_sell(self, app, sell_qty=30):
        with app.app_context():
            with get_db() as db:
                pos = Position(
                    symbol='600519',
                    name='贵州茅台',
                    asset_type='stock',
                    market='CN_A',
                    account_name='测试账户',
                    quantity=Money.shares_to_min_unit(100),
                    avg_price=Money.yuan_to_cents(10),
                    current_price=Money.yuan_to_cents(10),
                    family_id=1,
                    ledger_id=1,
                )
                db.add(pos)
                db.flush()
                # 模拟「已卖出 sell_qty 股」后的持仓状态（process_sell 已扣减份额）
                pos.quantity = Money.shares_to_min_unit(100 - sell_qty)
                db.flush()
                _make_txn(
                    db,
                    position_id=pos.id,
                    ledger_id=pos.ledger_id,
                    txn_type='buy',
                    quantity=100,
                    price=10,
                    symbol='600519',
                    position_name='贵州茅台',
                    account_name='测试账户',
                )
                sell_txn = _make_txn(
                    db,
                    position_id=pos.id,
                    ledger_id=pos.ledger_id,
                    txn_type='sell',
                    quantity=sell_qty,
                    price=12,
                    symbol='600519',
                    position_name='贵州茅台',
                    account_name='测试账户',
                )
                db.commit()
                return pos.id, sell_txn.id

    def test_delete_sell_restores_position_quantity(self, app, client):
        pos_id, sell_txn_id = self._seed_position_with_sell(app, 30)
        resp = client.delete(f'/api/transactions/{sell_txn_id}/')
        assert resp.status_code == 200
        with app.app_context():
            with get_db() as db:
                pos = db.query(Position).get(pos_id)
                # 删除卖出流水后份额应加回：70 + 30 = 100
                assert pos.quantity == Money.shares_to_min_unit(100)

    def test_delete_buy_reduces_position_quantity(self, app, client):
        pos_id, _ = self._seed_position_with_sell(app, 30)
        with app.app_context():
            with get_db() as db:
                pos = db.query(Position).get(pos_id)
                buy_txn = _make_txn(
                    db,
                    position_id=pos_id,
                    ledger_id=1,
                    txn_type='buy',
                    quantity=20,
                    price=10,
                    symbol='600519',
                    position_name='贵州茅台',
                    account_name='测试账户',
                )
                # 该笔买入已使持仓 +20（70 → 90）
                pos.quantity = Money.shares_to_min_unit(90)
                db.commit()
                buy_id = buy_txn.id
        # 删除该买入流水 → 持仓回退 20（90 → 70）
        resp = client.delete(f'/api/transactions/{buy_id}/')
        assert resp.status_code == 200
        with app.app_context():
            with get_db() as db:
                pos = db.query(Position).get(pos_id)
                assert pos.quantity == Money.shares_to_min_unit(70)

    def test_delete_full_sell_rebuilds_position(self, app, client):
        # 整笔买入后整笔卖出清空持仓（持仓行已被 process_sell 删除），
        # 再删除该卖出流水应重建持仓行并恢复份额。
        pos_id, sell_txn_id = self._seed_position_with_sell(app, 100)
        with app.app_context():
            with get_db() as db:
                pos = db.query(Position).get(pos_id)
                db.delete(pos)  # 模拟清仓后持仓行不存在
                db.commit()
        resp = client.delete(f'/api/transactions/{sell_txn_id}/')
        assert resp.status_code == 200
        with app.app_context():
            with get_db() as db:
                rebuilt = db.query(Position).filter(Position.symbol == '600519', Position.ledger_id == 1).first()
                assert rebuilt is not None
                assert rebuilt.quantity == Money.shares_to_min_unit(100)


class TestTransactionSource:
    """#1232 决策 11 / #1238：transactions.source 列。

    - 手动记账（记一笔）流水 source 应落 manual（与 positions.source 同源）。
    - PositionSource 新增 reconciliation_adjustment，供对账补录标记。
    - 非法 source 被枚举校验拒绝。
    - import_hash 去重不受 source 列落地影响（uq_txn_import_hash 仍生效）。
    """

    def test_manual_buy_sets_source_manual(self, client, db):
        """手动记账买入 → 流水 source = manual。"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        assert resp.status_code == 200
        pos_id = resp.get_json()['data']['id']
        txn = db.query(Transaction).filter_by(position_id=pos_id).first()
        assert txn is not None
        assert txn.source == PositionSource.MANUAL.value

    def test_list_transactions_exposes_source(self, client):
        """流水列表接口返回 source 字段。"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 180,
                'currency': 'USD',
                'trade_date': '2026-05-01',
            },
        )
        resp = _get(client, '/api/transactions')
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['source'] == PositionSource.MANUAL.value

    def test_invalid_source_rejected(self, db):
        """非法 source 被枚举校验拒绝（@validates 约束）。"""
        with pytest.raises(ValueError):
            Transaction(
                position_id=1,
                family_id=1,
                txn_type='buy',
                quantity=0,
                price=0,
                amount=0,
                position_name='测试',
                account_name='测试账户',
                source='not_a_source',
            )

    def test_reconciliation_adjustment_enum_exists(self):
        """PositionSource 已含 reconciliation_adjustment，供对账补录标记。"""
        assert PositionSource.RECONCILIATION_ADJUSTMENT.value == 'reconciliation_adjustment'
        from app.core.constants import POSITION_SOURCE_LABELS

        assert 'reconciliation_adjustment' in POSITION_SOURCE_LABELS

    def test_reconciliation_source_manual_commit(self, client, db):
        """对账补录来源 reconciliation_adjustment 可正确落库（模拟域 B/C 补充动作）。"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
                'source': PositionSource.RECONCILIATION_ADJUSTMENT.value,
            },
        )
        assert resp.status_code == 200
        pos_id = resp.get_json()['data']['id']
        txn = db.query(Transaction).filter_by(position_id=pos_id).first()
        assert txn is not None
        assert txn.source == PositionSource.RECONCILIATION_ADJUSTMENT.value

    def test_import_hash_dedup_still_works(self, client):
        """source 列落地后，import_hash 去重（uq_txn_import_hash）仍生效（409 幂等拦截）。"""
        payload = {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'trade_date': '2026-05-01',
            'import_hash': 'idem-source-409',
        }
        resp1 = _post(client, '/api/positions/', payload)
        assert resp1.status_code == 200
        resp2 = _post(client, '/api/positions/', payload)
        assert resp2.status_code == 409
        assert '已记录' in (resp2.get_json() or {}).get('message', '')


def _txn_kwargs(**kw):
    """费用拆分测试共用的流水构造参数（family_id=1，金额单位分）。"""
    base = {
        'family_id': 1,
        'txn_type': 'buy',
        'quantity': 0,
        'price': 0,
        'amount': 0,
        'position_name': '测试',
        'account_name': '测试账户',
    }
    base.update(kw)
    return base


def _detail(client, txn_id: int) -> dict:
    """取单条流水详情（`GET /api/transactions/<id>/`），非 200 直接失败并带上原因。"""
    resp = client.get(f'/api/transactions/{txn_id}/')
    assert resp.status_code == 200, f'详情接口返回 {resp.status_code}: {resp.get_json()}'
    return resp.get_json()['data']


def _listed(client, txn_id: int) -> dict:
    """从列表接口里取同一行——用来断言「列表与详情同一口径」。"""
    rows = _get(client, '/api/transactions').get_json()['data']
    return next(t for t in rows if t['id'] == txn_id)


class TestTransactionFeeBreakdown:
    """#2137 费用拆分四列（commission/stamp_duty/transfer_fee/other_fee，分）。

    不变量由 Transaction 的 before_insert / before_update 兜底：
    - 四列全 NULL = 未拆分（存量数据与未提供拆分的路径的默认态）；
    - 一旦拆分必须四列齐全，且其和必须等于聚合 fee。
    """

    def test_unsplit_fee_accepted_and_reads_as_none(self, db):
        """未拆分：四列全 NULL + 聚合 fee，存量行为不变（不报错、明细读作 None）。"""
        txn = Transaction(**_txn_kwargs(fee=1500))
        db.add(txn)
        db.flush()
        assert txn.commission is None
        assert txn.stamp_duty is None
        assert fee_breakdown_yuan(txn) is None

    def test_consistent_breakdown_accepted(self, db):
        """四列齐全且和=fee：正常落库，明细按元读出。"""
        txn = Transaction(
            **_txn_kwargs(
                fee=1500,
                commission=500,
                stamp_duty=850,
                transfer_fee=100,
                other_fee=50,
            )
        )
        db.add(txn)
        db.flush()
        assert fee_breakdown_yuan(txn) == {
            'commission': 5.0,
            'stamp_duty': 8.5,
            'transfer_fee': 1.0,
            'other_fee': 0.5,
        }

    def test_zero_fee_with_zero_breakdown_accepted(self, db):
        """分红/兑付等零费用行也可显式拆分（四列全 0，和=fee=0）。"""
        txn = Transaction(
            **_txn_kwargs(
                fee=0,
                commission=0,
                stamp_duty=0,
                transfer_fee=0,
                other_fee=0,
            )
        )
        db.add(txn)
        db.flush()
        assert fee_breakdown_yuan(txn) == {
            'commission': 0.0,
            'stamp_duty': 0.0,
            'transfer_fee': 0.0,
            'other_fee': 0.0,
        }

    def test_sum_mismatch_rejected_on_insert(self, db):
        """拆分之和不等于 fee → before_insert fail closed。"""
        with pytest.raises(ValueError, match='不一致'):
            txn = Transaction(
                **_txn_kwargs(
                    fee=1500,
                    commission=500,
                    stamp_duty=800,  # 850 → 800，和 1450 ≠ 1500
                    transfer_fee=100,
                    other_fee=50,
                )
            )
            db.add(txn)
            db.flush()

    def test_partial_breakdown_rejected_on_insert(self, db):
        """只给部分拆分列 → before_insert fail closed（缺的类别必须显式传 0）。"""
        with pytest.raises(ValueError, match='四列齐全'):
            txn = Transaction(**_txn_kwargs(fee=500, commission=500))
            db.add(txn)
            db.flush()

    def test_sum_mismatch_rejected_on_update(self, db):
        """存量未拆分行被改坏时，before_update 同样拦截。"""
        txn = Transaction(**_txn_kwargs(fee=1500))
        db.add(txn)
        db.flush()
        db.refresh(txn)
        txn.commission = 500
        txn.stamp_duty = 800
        txn.transfer_fee = 100
        txn.other_fee = 50
        with pytest.raises(ValueError, match='不一致'):
            db.flush()
        db.rollback()

    def test_manual_buy_carries_breakdown_via_api(self, client, db):
        """记一笔带四类费用 → 流水四列落库，列表接口回显 fee_breakdown（元）。"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
                'fee': 15,
                'fee_commission': 5,
                'fee_stamp_duty': 8.5,
                'fee_transfer_fee': 1,
                'fee_other': 0.5,
            },
        )
        assert resp.status_code == 200
        pos_id = resp.get_json()['data']['id']
        txn = db.query(Transaction).filter_by(position_id=pos_id).first()
        assert txn is not None
        assert txn.fee == 1500
        assert (txn.commission, txn.stamp_duty, txn.transfer_fee, txn.other_fee) == (500, 850, 100, 50)

        list_resp = _get(client, '/api/transactions')
        row = next(t for t in list_resp.get_json()['data'] if t['id'] == txn.id)
        assert row['fee_breakdown'] == {
            'commission': 5.0,
            'stamp_duty': 8.5,
            'transfer_fee': 1.0,
            'other_fee': 0.5,
        }

    def test_manual_buy_without_breakdown_reads_none(self, client, db):
        """不带拆分的记一笔：fee_breakdown 为 None（前端按单值展示，存量语义）。"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 180,
                'currency': 'USD',
                'trade_date': '2026-05-01',
                'fee': 3,
            },
        )
        assert resp.status_code == 200
        list_resp = _get(client, '/api/transactions')
        row = next(t for t in list_resp.get_json()['data'] if t['symbol'] == 'US:AAPL')
        assert row['fee_breakdown'] is None
        assert row['fee'] == 3.0

    def test_edit_transaction_sets_breakdown(self, client, db):
        """编辑交易可补录四类费用（PATCH ledgers 域交易编辑入口）。"""
        ledger = client.post('/api/ledgers/', json={'name': '华泰证券'}).get_json()['data']
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '600519',
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '华泰证券',
                'ledger_id': ledger['id'],
                'quantity': 100,
                'avg_price': 1500,
                'trade_date': '2026-05-01',
            },
        )
        assert resp.status_code == 200
        txn = db.query(Transaction).filter_by(symbol='SH600519').first()
        assert txn is not None

        patch_resp = client.patch(
            f'/api/ledgers/{ledger["id"]}/transactions/{txn.id}/',
            json={
                'fee': 15,
                'fee_commission': 5,
                'fee_stamp_duty': 8.5,
                'fee_transfer_fee': 1,
                'fee_other': 0.5,
            },
        )
        assert patch_resp.status_code == 200
        data = patch_resp.get_json()['data']
        assert data['fee_breakdown'] == {
            'commission': 5.0,
            'stamp_duty': 8.5,
            'transfer_fee': 1.0,
            'other_fee': 0.5,
        }
        db.refresh(txn)
        assert (txn.commission, txn.stamp_duty, txn.transfer_fee, txn.other_fee) == (500, 850, 100, 50)

    def test_edit_transaction_partial_breakdown_rejected(self, client, db):
        """编辑交易只给部分拆分列 → 400（而不是撞模型不变量变 500）。"""
        ledger = client.post('/api/ledgers/', json={'name': '华泰证券'}).get_json()['data']
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '600519',
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '华泰证券',
                'ledger_id': ledger['id'],
                'quantity': 100,
                'avg_price': 1500,
                'trade_date': '2026-05-01',
            },
        )
        assert resp.status_code == 200
        txn = db.query(Transaction).filter_by(symbol='SH600519').first()
        assert txn is not None
        patch_resp = client.patch(
            f'/api/ledgers/{ledger["id"]}/transactions/{txn.id}/',
            json={'fee': 15, 'fee_commission': 5},
        )
        assert patch_resp.status_code == 400
        assert '四类齐全' in (patch_resp.get_json() or {}).get('message', '')


class TestTransactionDetail:
    """单条流水详情（行展开按需取，`GET /api/transactions/<id>/`）。

    存在理由：费用拆分以外的溯源信息（导入哈希 / 更新时间 / 定投计划）与**持仓现状**
    （当前份额、是否已清仓）只有展开某一行才需要。并进列表等于给每页 20 行各算一遍。
    """

    def test_detail_carries_list_row_plus_detail_only_fields(self, client, db, make_position, make_transaction):
        """详情 = 列表行 ∪ 详情专属字段；列表行那部分逐字相同（同一组装函数）。"""
        pos = make_position(symbol='004369', name='测试基金', asset_type='fund', quantity=100, avg_price=1.0)
        txn = make_transaction(position_id=pos.id, ledger_id=None, symbol='004369', position_name='测试基金')
        db.commit()

        detail = _detail(client, txn.id)
        listed = next(t for t in _get(client, '/api/transactions').get_json()['data'] if t['id'] == txn.id)

        # 列表行部分：详情不多不少，与列表逐键相同（防止两条路径各声明一套字段）
        for key, value in listed.items():
            assert detail[key] == value, f'详情与列表的 {key} 不一致：详情={detail[key]!r} 列表={value!r}'

        # 详情专属（列表没有）
        for key in ('import_hash', 'updated_at', 'plan_id', 'position'):
            assert key in detail, f'详情缺字段 {key}'
            assert key not in listed, f'{key} 不该出现在列表行里（那是「一次性全拿到」）'

        assert detail['position']['id'] == pos.id
        assert detail['position']['quantity'] == 100.0
        # 不返回 ownership_status（与 position_state 是同一件事的两种写法），
        # 多出来的是清仓时间：未清仓过 → None
        assert 'ownership_status' not in detail['position']
        assert detail['position']['cleared_at'] is None

    def test_detail_404_for_unknown_id(self, client):
        resp = client.get('/api/transactions/999999/')
        assert resp.status_code == 404

    def test_detail_404_for_other_family(self, client, db, make_position):
        """跨家庭按 404 处理（不返 403 泄漏「这一行存在」）。

        不用 `make_transaction`：该 fixture 把 `family_id` 写死为 1，要造「别家的流水」
        只能直接建行——否则测出来的是「同家庭能读」，永远绿。
        """
        pos = make_position(symbol='004369', name='别家的', asset_type='fund', quantity=1, avg_price=1.0, family_id=2)
        txn = Transaction(**_txn_kwargs(family_id=2, position_id=pos.id, symbol='004369'))
        db.add(txn)
        db.commit()
        assert client.get(f'/api/transactions/{txn.id}/').status_code == 404


class TestTransactionPositionState:
    """流水行的持仓状态（`held` / `cleared` / `account`）——设计 §三 的**唯一**判据。

    这一组钉住设计 v1.0 初判的一处实测失效：

    > 「`position_id === null` → 已清仓」

    #2343 起清仓**不再删行**（`ownership_status='cleared'`，锚点留存），所以已清仓的
    流水 `position_id` 依然有值 —— 按 null 判会让「已清仓」胶囊几乎永不出现，
    而用户会以为这个标记坏了。反过来，`position_id` 非空但持仓行已被删（#2343 之前的
    历史数据，真库实测 621 笔）本来就是已清仓，判成 held 会长期撒谎。
    """

    def test_held_when_position_row_is_active(self, client, db, make_position, make_transaction):
        pos = make_position(symbol='004369', name='测试基金', asset_type='fund', quantity=100, avg_price=1.0)
        txn = make_transaction(position_id=pos.id, ledger_id=None, symbol='004369')
        db.commit()

        assert _detail(client, txn.id)['position_state'] == 'held'
        assert _listed(client, txn.id)['position_state'] == 'held'

    def test_cleared_when_position_kept_but_cleared(self, client, db, make_position, make_transaction):
        """#2343：清仓不删行 → `position_id` 仍有值，状态必须是 cleared。

        这条是本组的主用例：它正是「按 `position_id is None` 判已清仓」失效的场景。
        """
        pos = make_position(
            symbol='004369',
            name='测试基金',
            asset_type='fund',
            quantity=0,
            avg_price=1.0,
            ownership_status='cleared',
        )
        txn = make_transaction(position_id=pos.id, ledger_id=None, symbol='004369')
        db.commit()

        assert _detail(client, txn.id)['position_state'] == 'cleared'
        assert _listed(client, txn.id)['position_state'] == 'cleared'

    def test_cleared_when_position_id_dangles(self, client, db, make_transaction):
        """`position_id` 指向已不存在的持仓（历史删行）→ cleared，且不编造持仓摘要。"""
        txn = make_transaction(position_id=987654, ledger_id=None, symbol='004369')
        db.commit()

        detail = _detail(client, txn.id)
        assert detail['position_state'] == 'cleared'
        assert detail['position'] is None, '悬空 id 时不得编造持仓现状'

    def test_account_state_for_deposit_and_withdraw(self, client, db, make_transaction):
        """资金流水（存入 / 取出）本来就没有持仓行 → account，不是「已清仓」。"""
        for txn_type in ('deposit', 'withdraw'):
            txn = make_transaction(position_id=None, ledger_id=None, txn_type=txn_type, symbol=None)
            db.commit()
            assert _detail(client, txn.id)['position_state'] == 'account'

    def test_cleared_for_orphan_non_account_type(self, client, db, make_transaction):
        """无持仓行且不是资金流水（历史孤儿买入）→ cleared，不是 account。"""
        txn = make_transaction(position_id=None, ledger_id=None, txn_type='buy', symbol='004369')
        db.commit()
        assert _detail(client, txn.id)['position_state'] == 'cleared'


def _summary(client, **params) -> dict:
    """取汇总条数据（`GET /api/transactions/summary/`），非 200 直接失败并带上原因。"""
    resp = client.get('/api/transactions/summary/', query_string=params)
    assert resp.status_code == 200, f'汇总接口返回 {resp.status_code}: {resp.get_json()}'
    return resp.get_json()['data']


class TestTransactionSummary:
    """汇总条（设计 §四 口径）：净投入 = 买入 + 手续费 − 卖出 − 分红。

    这批用例存在的理由：汇总条是全页**唯一**的聚合数字，算错了页面不会报错——
    它只会安静地给出一个和列表对不上的数。所以判据全写死成可手算的已知数据。
    """

    def test_net_invested_formula_from_spec_fixture(self, client, db):
        """规格里的已知数据：买入 100 / 卖出 40 / 分红 5 / 手续费 1 → 净投入 **56**。

        手续费**不摊进买入**（否则「买入」不再等于成交额，拿汇总条去核表格会差一笔），
        所以四个数各自可核：100 / 40 / 5 / 1。
        """
        db.add_all(
            [
                Transaction(**_txn_kwargs(txn_type='buy', amount=10000, fee=100)),
                Transaction(**_txn_kwargs(txn_type='sell', amount=4000)),
                Transaction(**_txn_kwargs(txn_type='dividend', amount=500)),
            ]
        )
        db.commit()

        s = _summary(client)
        assert s['buy'] == {'count': 1, 'amount': 100.0}
        assert s['sell'] == {'count': 1, 'amount': 40.0}
        assert s['dividend'] == {'count': 1, 'amount': 5.0}
        assert s['fee'] == 1.0
        assert s['net_invested'] == 56.0
        # 公式本身也断一遍：日后改结构（比如加字段）时这条仍能抓住口径漂移
        assert s['net_invested'] == pytest.approx(
            s['buy']['amount'] + s['fee'] - s['sell']['amount'] - s['dividend']['amount']
        )

    def test_summary_counts_every_row_not_just_one_page(self, client, db):
        """汇总覆盖**全部**命中行，不是当页 20 条——拿列表数据求和是最坏的一种错。

        这条用例的作用是钉住「独立聚合查询」：一旦有人图省事改成对列表 `data`
        求和，25 条会变成 10 条（或 20 条），而页面照样渲染得漂漂亮亮。
        """
        db.add_all([Transaction(**_txn_kwargs(txn_type='buy', amount=1000)) for _ in range(25)])
        db.commit()

        page = _get(client, '/api/transactions', {'per_page': 10}).get_json()
        assert len(page['data']) == 10, '前提：列表分页只返回 10 条'

        s = _summary(client)
        assert s['buy']['count'] == 25
        assert s['buy']['amount'] == 250.0

    def test_summary_follows_same_filters_as_list(self, client, db):
        """同一组筛选下，汇总的笔数与列表的 total 必须一致（两条路径共用 WHERE）。"""
        db.add_all(
            [
                Transaction(**_txn_kwargs(txn_type='buy', amount=1000)),
                Transaction(**_txn_kwargs(txn_type='buy', amount=2000)),
                Transaction(**_txn_kwargs(txn_type='sell', amount=500)),
            ]
        )
        db.commit()

        s = _summary(client, type='buy')
        listed = _get(client, '/api/transactions', {'type': 'buy'}).get_json()
        assert s['buy']['count'] == 2
        assert s['sell']['count'] == 0, 'type=buy 时卖出不该混进来'
        assert s['buy']['count'] == listed['total']
        # 净投入随筛选变化：只剩两笔买入、无手续费 → 30
        assert s['net_invested'] == 30.0

    def test_summary_scoped_to_own_family(self, client, db):
        """别的家庭的流水不进汇总（跨家庭泄漏在这里同样是「数字对不上」）。"""
        db.add(Transaction(**_txn_kwargs(txn_type='buy', amount=99999)))
        db.add(Transaction(**_txn_kwargs(family_id=2, txn_type='buy', amount=88888)))
        db.commit()

        s = _summary(client)
        assert s['buy'] == {'count': 1, 'amount': 999.99}

    def test_fee_covers_all_types_but_net_only_uses_four(self, client, db):
        """手续费取**全类型**求和（含存入），但净投入公式只认买入/卖出/分红。

        存入 1000 + 手续费 3：手续费要算进来，存入本身不进净投入——它是资金搬运，
        不是「为持仓投进去的钱」。这条差异必须被钉住，否则下次会把存入也算进净投入。
        """
        db.add(Transaction(**_txn_kwargs(txn_type='deposit', amount=100000, fee=300)))
        db.commit()

        s = _summary(client)
        assert s['fee'] == 3.0
        assert s['buy']['count'] == 0
        assert s['net_invested'] == 3.0

    def test_empty_range_returns_zeros_not_none(self, client, db):
        """无命中行时四个数都是 0（不是 None）：前端要直接渲染，不该在这做空值判断。"""
        s = _summary(client, time_range='custom', start_date='2099-01-01', end_date='2099-12-31')
        assert s == {
            'buy': {'count': 0, 'amount': 0.0},
            'sell': {'count': 0, 'amount': 0.0},
            'dividend': {'count': 0, 'amount': 0.0},
            'fee': 0.0,
            'net_invested': 0.0,
        }
