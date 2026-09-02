# -*- coding: utf-8 -*-
"""统一对账测试（#1232 §6.1 / §6.2 / P1）。

覆盖：三表可建、域 B 数量差异、孤儿检测、幂等 upsert、忽略（临时/永久）、
域 C（导入后自动触发）孤儿检测与清理范围、API。
"""

import json
from datetime import date, datetime

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy, ReconciliationRun
from app.domains.transactions.models import Transaction
from app.services.reconciliation_service import run_domain_b_reconciliation, run_reconciliation


def _buy_txn(db, ledger_id, symbol, quantity, confirm_date, position_id=None):
    txn = Transaction(
        position_id=position_id,
        ledger_id=ledger_id,
        family_id=1,
        symbol=symbol,
        txn_type='buy',
        quantity=Money.shares_to_min_unit(quantity),
        price=Money.yuan_to_price_units(1.0),
        amount=Money.yuan_to_cents(quantity),
        confirm_date=confirm_date,
        trade_date=datetime.combine(confirm_date, datetime.min.time()),
        position_name=symbol,
        account_name='测试',
        status='success',
        entry_status='success',
    )
    db.add(txn)
    db.flush()
    return txn


def _sell_txn(db, ledger_id, symbol, quantity, confirm_date, position_id=None):
    txn = Transaction(
        position_id=position_id,
        ledger_id=ledger_id,
        family_id=1,
        symbol=symbol,
        txn_type='sell',
        quantity=Money.shares_to_min_unit(quantity),
        price=Money.yuan_to_price_units(1.0),
        amount=Money.yuan_to_cents(quantity),
        confirm_date=confirm_date,
        trade_date=datetime.combine(confirm_date, datetime.min.time()),
        position_name=symbol,
        account_name='测试',
        status='success',
        entry_status='success',
    )
    db.add(txn)
    db.flush()
    return txn


class TestThreeTables:
    """三表（discrepancies / reconciliation_runs / adjustment_logs）可建可用。"""

    def test_models_creatable(self, db):
        """三表模型可建行、可查询。"""
        run = ReconciliationRun(family_id=1, domain='B', triggered_by='manual')
        db.add(run)
        db.flush()
        disc = ReconciliationDiscrepancy(
            family_id=1,
            ledger_id=1,
            domain='B',
            symbol='S1',
            discrepancy_type='quantity',
            expected_value=100,
            actual_value=90,
            diff=10,
            status='pending',
        )
        db.add(disc)
        db.flush()
        log = AdjustmentLog(family_id=1, run_id=run.id, discrepancy_id=disc.id, action='ignore_temporary')
        db.add(log)
        db.commit()
        assert run.id and disc.id and log.id


class TestDomainBReconciliation:
    """域 B 数量差异与孤儿检测。"""

    def test_no_flow_skips(self, db):
        """无流水持仓 → skip（不检测不告警，§6.1 边界）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run, _ = run_domain_b_reconciliation(db, 1)
        discs = db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id).all()
        assert discs == []

    def test_quantity_mismatch(self, db):
        """流水重建净额与持仓数量不一致 → 报 quantity 差异。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        # 流水：买入 100
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        # 持仓只有 60（数据不一致，少了 40）
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run, _ = run_domain_b_reconciliation(db, 1)
        discs = db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id).all()
        assert len(discs) == 1
        d = discs[0]
        assert d.discrepancy_type == 'quantity'
        assert d.symbol == 'S1'
        # 理论（流水净额）= 100，实际 = 60，diff = 60-100 = -40
        assert d.expected_value == Money.shares_to_min_unit(100)
        assert d.actual_value == Money.shares_to_min_unit(60)
        assert d.diff == Money.shares_to_min_unit(-40)

    def test_orphan_detection(self, db):
        """流水推演净额 > 0 但系统无持仓 → 报 orphan。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        db.commit()
        run, _ = run_domain_b_reconciliation(db, 1)
        discs = db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id).all()
        assert len(discs) == 1
        assert discs[0].discrepancy_type == 'orphan'

    def test_match_no_discrepancy(self, db):
        """流水与持仓一致 → 无数量差异。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run, _ = run_domain_b_reconciliation(db, 1)
        discs = db.query(ReconciliationDiscrepancy).filter_by(last_run_id=run.id).all()
        assert discs == []

    def test_upsert_not_duplicate(self, db):
        """同业务键差异多次 run → 不产生重复行（upsert 更新）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run1, _ = run_domain_b_reconciliation(db, 1)
        run2, _ = run_domain_b_reconciliation(db, 1)
        discs = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').all()
        assert len(discs) == 1
        assert discs[0].last_run_id == run2.id

    def test_permanent_ignore_preserved(self, db):
        """永久忽略的差异在后续 run 不被覆盖（保持 ignored）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run1, _ = run_domain_b_reconciliation(db, 1)
        d = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').one()
        d.status = 'ignored'
        d.is_permanent = True
        db.commit()
        run2, _ = run_domain_b_reconciliation(db, 1)
        d2 = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').one()
        assert d2.status == 'ignored'
        assert d2.is_permanent is True

    def test_summary_cleared_count(self, db):
        """差异消失后重新 run，cleared 计数为 1。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run1, _ = run_domain_b_reconciliation(db, 1)
        assert json.loads(run1.summary_json)['pending'] == 1

        # 补录持仓使差异消失
        pos.quantity = Money.shares_to_min_unit(100)
        db.commit()
        run2, _ = run_domain_b_reconciliation(db, 1)
        summary2 = json.loads(run2.summary_json)
        assert summary2['cleared'] == 1
        assert summary2['pending'] == 0

    def test_summary_ignored_count(self, db):
        """永久忽略的差异在后续 run 中 ignored 计数正确。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        run1, _ = run_domain_b_reconciliation(db, 1)
        assert json.loads(run1.summary_json)['pending'] == 1

        # 永久忽略（不修改持仓，diff 仍不为 0）
        d = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').one()
        d.status = 'ignored'
        d.is_permanent = True
        db.commit()
        run2, _ = run_domain_b_reconciliation(db, 1)
        summary2 = json.loads(run2.summary_json)
        assert summary2['ignored'] == 1
        assert summary2['pending'] == 0


class TestDomainCReconciliation:
    """域 C（导入完成后自动触发，§6.2）：只做孤儿检测，清理范围不得跨到域 B。"""

    def test_domain_c_run_keeps_domain_b_pending(self, db):
        """回归：域 C run 曾因清理漏传 domain 而误清域 B 的待裁决差异。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        # S1：流水 100 / 持仓 60 → 域 B 数量差异（用户待裁决）
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        db.add(
            Position(
                symbol='S1',
                name='股1',
                asset_type='stock',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(60),
                avg_price=Money.yuan_to_price_units(10),
                current_price=Money.yuan_to_price_units(10),
                source='manual',
                ownership_status='active',
            )
        )
        # S2：有流水无持仓 → 孤儿（域 C 关注）
        _buy_txn(db, ledger.id, 'S2', 50, date(2026, 5, 2))
        db.commit()

        run_domain_b_reconciliation(db, 1)
        b_disc = db.query(ReconciliationDiscrepancy).filter_by(domain='B', symbol='S1').one()
        assert b_disc.status == 'pending'

        run_c, _ = run_reconciliation(db, 1, domain='C')

        # 域 C 由导入触发，须与手工对账区分（§6.2）
        assert run_c.triggered_by == 'import'
        # 域 B 的待裁决差异仍在，未被跨域清理
        db.refresh(b_disc)
        assert b_disc.status == 'pending'
        # 域 C 只报孤儿，不做数量比对
        c_discs = db.query(ReconciliationDiscrepancy).filter_by(domain='C').all()
        assert len(c_discs) == 1
        assert c_discs[0].symbol == 'S2'
        assert c_discs[0].discrepancy_type == 'orphan'

    def test_domain_c_stale_orphan_cleared(self, db):
        """域 C 孤儿补录持仓后，再次 run 应置 cleared（清理范围须覆盖域 C）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        db.commit()

        run_reconciliation(db, 1, domain='C')
        disc = db.query(ReconciliationDiscrepancy).filter_by(domain='C', symbol='S1').one()
        assert disc.status == 'pending'

        # 补录持仓，孤儿消除
        db.add(
            Position(
                symbol='S1',
                name='股1',
                asset_type='stock',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(100),
                avg_price=Money.yuan_to_price_units(10),
                current_price=Money.yuan_to_price_units(10),
                source='manual',
                ownership_status='active',
            )
        )
        db.commit()

        run_reconciliation(db, 1, domain='C')
        db.refresh(disc)
        assert disc.status == 'cleared'


class TestReconciliationAPI:
    """对账 API 端点。"""

    def test_run_and_list(self, client, db):
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()

        resp = client.post('/api/reconciliation/run/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['domain'] == 'B'
        assert data['run_id']

        resp2 = client.get('/api/reconciliation/discrepancies/')
        assert resp2.status_code == 200
        discs = resp2.get_json()['data']
        assert len(discs) == 1
        assert discs[0]['symbol'] == 'S1'
        assert discs[0]['discrepancy_type'] == 'quantity'

    def test_ignore_discrepancy(self, client, db):
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        client.post('/api/reconciliation/run/')
        discs = client.get('/api/reconciliation/discrepancies/').get_json()['data']
        disc_id = discs[0]['id']

        resp = client.post(
            f'/api/reconciliation/discrepancies/{disc_id}/ignore/', json={'permanent': True, 'reason': '测试忽略'}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['status'] == 'ignored'
        assert data['is_permanent'] is True

        # 审计日志已写（用户主动操作，§5.5）
        log = db.query(AdjustmentLog).filter_by(discrepancy_id=disc_id).one()
        assert log.action == 'ignore_permanent'


class TestInContextSupplement:
    """就地补充/调整裁决（§5.4 / P2）——API + 语义分派 + 审计。"""

    def test_increment_supplement_writes_txn_and_position(self, client, db):
        """增量型补充：补一笔买入 → 写 Transaction + 建/更新 Position。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='fund', family_id=1)
        db.add(ledger)
        db.commit()

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'buy',
                'symbol': '000001',
                'name': '华夏成长',
                'asset_type': 'fund',
                'market': 'CN_A',
                'ledger_id': ledger.id,
                'account_name': '账户A',
                'quantity': 500,
                'avg_price': 1.2,
                'confirm_date': '2026-05-01',
                'reason': '补齐缺失申购',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['action'] == 'supplement'

        # 持仓已建（500 份）
        pos = db.query(Position).filter_by(symbol='000001', ledger_id=ledger.id).one()
        assert pos.quantity == Money.shares_to_min_unit(500)
        # 流水已写（增量型必须产生流水，与 process_* 汇点一致）
        txn = db.query(Transaction).filter_by(position_id=pos.id).one()
        assert txn.txn_type == 'buy'
        assert txn.quantity == Money.shares_to_min_unit(500)
        # 审计日志
        log = db.query(AdjustmentLog).filter_by(discrepancy_id=None).first()
        assert log is not None
        assert log.action == 'supplement'
        assert log.reason == '补齐缺失申购'

    def test_set_supplement_no_transaction(self, client, db):
        """设定型补充（期初建仓）：只 SET 持仓，不建流水（§5.4 硬约束）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='fund', family_id=1)
        db.add(ledger)
        db.commit()

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'set',
                'symbol': '000002',
                'name': '某基金',
                'asset_type': 'fund',
                'market': 'CN_A',
                'ledger_id': ledger.id,
                'account_name': '账户A',
                'quantity': 800,
                'avg_price': 1.5,
                'snapshot_date': '2026-05-01',
            },
        )
        assert resp.status_code == 200
        pos = db.query(Position).filter_by(symbol='000002', ledger_id=ledger.id).one()
        assert pos.quantity == Money.shares_to_min_unit(800)
        # 设定型不建流水
        txns = db.query(Transaction).filter_by(symbol='000002').all()
        assert txns == []

    def test_supplement_clears_linked_discrepancy(self, client, db):
        """补充关联差异后，该差异置 cleared。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(60),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        client.post('/api/reconciliation/run/')
        discs = client.get('/api/reconciliation/discrepancies/').get_json()['data']
        disc_id = discs[0]['id']

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'buy',
                'discrepancy_id': disc_id,
                'symbol': 'S1',
                'name': '股1',
                'asset_type': 'stock',
                'market': 'CN_A',
                'ledger_id': ledger.id,
                'account_name': '账户A',
                # A股买入受整手限制（min_unit=100），补充量须合法
                'quantity': 100,
                'avg_price': 10,
                'confirm_date': '2026-05-02',
            },
        )
        assert resp.status_code == 200
        after = client.get('/api/reconciliation/discrepancies/').get_json()['data']
        target = [d for d in after if d['id'] == disc_id]
        assert target
        assert target[0]['status'] == 'cleared'

    def test_adjustment_requires_symbol(self, client):
        """缺 symbol → 400。"""
        resp = client.post('/api/reconciliation/adjustments/', json={'kind': 'increment', 'op_type': 'buy'})
        assert resp.status_code == 400
