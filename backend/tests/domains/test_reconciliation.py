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
from app.services.reconciliation_consistency import get_ledger_snapshot_consistency
from app.services.reconciliation_service import (
    run_domain_b_reconciliation,
    run_reconciliation,
)


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

    def test_orphan_cleared_when_key_becomes_quantity_gap(self, db):
        """孤儿 → 补建持仓后仍有份额缺口：旧 orphan 行须置 cleared，不留幽灵 pending。

        回归：`seen_keys` 曾只登记 (ledger_id, symbol)，而差异行身份是
        (ledger_id, symbol, discrepancy_type)。同一业务键「孤儿 → 数量差异」后，
        补建持仓的动作（模板/改挂/重建）都会把旧 orphan 行永久留在 pending，
        而它已不可能被任何入口修掉。
        """
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 100, date(2026, 5, 1))
        db.commit()

        run1, _ = run_domain_b_reconciliation(db, 1)
        orphan = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').one()
        assert orphan.discrepancy_type == 'orphan'
        assert orphan.last_run_id == run1.id

        # 补建持仓但份额不足（另一条同标的流水仍悬空）→ 该键改走数量比对分支
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
        db.commit()
        run2, _ = run_domain_b_reconciliation(db, 1)

        db.refresh(orphan)
        assert orphan.status == 'cleared'
        assert orphan.last_run_id == run2.id
        pending = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1', status='pending').all()
        assert [d.discrepancy_type for d in pending] == ['quantity']

    def test_quantity_stays_quantity_when_position_cleared(self, db):
        """持仓清仓（`cleared` + 份额归零）但流水净额仍 > 0 → 仍是**数量差异**，不是孤儿。

        为什么不是孤儿：孤儿的口径是「系统里**没有**这只标的的持仓行」（前端据此把人指向
        「按流水重建持仓」），而这里持仓行在、只是份额被清零。判成孤儿会让用户点进
        「补充这笔」后被拦下，改去「修正数据」又会因「同账本已有持仓行」被拒——两条路
        都是死胡同（真库实测 8 条，2026-11-14）。判成数量差异才有唯一可用入口。
        """
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
        quantity = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1').one()
        assert quantity.discrepancy_type == 'quantity'
        assert quantity.last_run_id == run1.id

        # 清仓：行保留、份额归零（库级 CHECK：cleared ⇒ quantity = 0）
        pos.ownership_status = 'cleared'
        pos.quantity = 0
        db.commit()
        run2, _ = run_domain_b_reconciliation(db, 1)

        db.refresh(quantity)
        assert quantity.discrepancy_type == 'quantity'
        assert quantity.status == 'pending'
        assert quantity.last_run_id == run2.id
        assert quantity.actual_value == 0
        assert quantity.diff == -Money.shares_to_min_unit(100)
        pending = db.query(ReconciliationDiscrepancy).filter_by(symbol='S1', status='pending').all()
        assert [d.discrepancy_type for d in pending] == ['quantity'], '不得再生出一条孤儿行'

    def test_orphan_when_only_non_literal_symbol_notation(self, db):
        """持仓写成 `SZ004369`、流水写成 `004369` → 同一只标的，不得判成孤儿（#1662 同源）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, '004369', 100, date(2026, 5, 1))
        db.add(
            Position(
                symbol='SZ004369',
                name='测试基金',
                asset_type='fund',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(100),
                avg_price=Money.yuan_to_price_units(1),
                current_price=Money.yuan_to_price_units(1),
                source='manual',
                ownership_status='active',
            )
        )
        db.commit()

        run, _ = run_domain_b_reconciliation(db, 1)

        assert db.query(ReconciliationDiscrepancy).count() == 0, '同一标的两种写法不是孤儿、也没有数量差'
        assert json.loads(run.summary_json)['orphan'] == 0

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

    def test_discrepancies_api_returns_shares(self, client, db):
        """列表接口按份额（而非最小单位）返回理论/实际/差异（#1260 验收）。"""
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
        assert len(discs) == 1
        d = discs[0]
        # 数据库存最小单位（份×10000），接口须经 Money.min_unit_to_shares 换算为份额
        assert d['expected_value'] == 100  # 理论 = 流水净额 100 份
        assert d['actual_value'] == 60  # 实际持仓 60 份
        assert d['diff'] == -40  # 实际 - 理论

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

    def test_ledger_consistency_endpoint(self, client, db):
        """GET /ledger-consistency/ 返回快照滞后明细（只读、不写 discrepancies）。"""
        from app.domains.ledgers.models import Ledger
        from app.domains.positions.models import PositionImportMeta

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 1000, date(2026, 6, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(1200),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.flush()
        # 锚点份额：理论持仓 = 1000（快照）+ 快照后流水（无）= 1000，实际 1200 → diff 200。
        # 缺这一列时函数会跳过（算不出基线），接口返回空列表。
        pos.snapshot_quantity = Money.shares_to_min_unit(1000)
        pos.snapshot_avg_price = Money.yuan_to_price_units(10)
        pos.snapshot_date = date(2026, 6, 12)
        pos.anchor_kind = 'external'
        db.add(
            PositionImportMeta(
                position_id=pos.id,
                symbol='S1',
                ledger_id=ledger.id,
                family_id=1,
                snapshot_date=date(2026, 6, 12),
            )
        )
        db.commit()

        resp = client.get('/api/reconciliation/ledger-consistency/')
        assert resp.status_code == 200
        items = resp.get_json()['data']['items']
        assert len(items) == 1
        assert items[0]['symbol'] == 'S1'
        assert items[0]['ledger_id'] == ledger.id
        assert items[0]['diff_qty'] == 200
        # 同时校验绝对值，防止 expected/actual 同时偏移导致 diff 误通过（#ai-review）
        assert items[0]['expected_qty'] == 1000
        assert items[0]['actual_qty'] == 1200
        # 不写 discrepancies 表（对照工作台域 B 落点）
        assert db.query(ReconciliationDiscrepancy).count() == 0


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

    def _make_sell_target(self, db, symbol='SZ159869', hold_qty=10000):
        """构造一笔可卖出的 ETF 持仓（卖出量用 100 的整数倍，避免被整手校验挡住）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        pos = Position(
            symbol=symbol,
            name='华夏中证动漫游戏ETF',
            asset_type='etf',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(hold_qty),
            avg_price=Money.yuan_to_price_units(1.365),
            current_price=Money.yuan_to_price_units(1.365),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.commit()
        return ledger, pos

    def test_sell_supplement_resolves_position_id(self, client, db):
        """卖出补录不带 position_id → 按统一身份键定位持仓，200 且扣减份额。

        用户实测：POST adjustments 补一笔卖出（payload 只有 symbol/ledger_id）返回 500，
        栈为 position_sell_command.prepare_sell 的 `KeyError: 'position_id'` ——
        对账补录没有持仓下拉，给不出 id；本用例钉住修复后的行为。
        """
        ledger, pos = self._make_sell_target(db)

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'sell',
                'symbol': 'SZ159869',
                'name': '华夏中证动漫游戏ETF',
                'ledger_id': ledger.id,
                'quantity': 6500,
                'avg_price': 1.365,
                'fee': 5,
                'confirm_date': '2026-05-08',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['action'] == 'supplement'
        assert data['after']['position_id'] == pos.id

        # 持仓份额按卖出量减少（10000 - 6500 = 3500）
        db.refresh(pos)
        assert pos.quantity == Money.shares_to_min_unit(3500)
        # 卖出流水已写，费用按分落库（fee=5 元 → 500 分）
        txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='sell').one()
        assert txn.quantity == Money.shares_to_min_unit(6500)
        assert txn.fee == 500

    def test_withdraw_supplement_resolves_position_id(self, client, db):
        """取出（withdraw）补录同样不带 position_id → 200 且扣减份额。"""
        ledger, pos = self._make_sell_target(db, symbol='SZ000001', hold_qty=2000)

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'withdraw',
                'symbol': 'SZ000001',
                'name': '某股票',
                'ledger_id': ledger.id,
                'quantity': 500,
                'avg_price': 10.0,
                'confirm_date': '2026-05-08',
            },
        )
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.quantity == Money.shares_to_min_unit(1500)
        txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='withdraw').one()
        assert txn.quantity == Money.shares_to_min_unit(500)

    def test_sell_supplement_position_not_found_returns_400(self, client, db):
        """symbol 与任何持仓都不匹配 → 400（ValueError 转译），不新增流水。"""
        ledger, _ = self._make_sell_target(db)
        txn_count_before = db.query(Transaction).count()

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'sell',
                'symbol': 'SH999999',
                'name': '不存在的标的',
                'ledger_id': ledger.id,
                'quantity': 100,
                'avg_price': 1.0,
                'confirm_date': '2026-05-08',
            },
        )
        assert resp.status_code == 400
        assert '找不到这笔持仓' in resp.get_json()['message']
        # 不新增流水
        assert db.query(Transaction).count() == txn_count_before

    def test_sell_supplement_explicit_position_id_passthrough(self, client, db):
        """显式传 position_id 的既有路径仍 200（helper 不得覆盖正常入参）。"""
        ledger, pos = self._make_sell_target(db)

        resp = client.post(
            '/api/reconciliation/adjustments/',
            json={
                'kind': 'increment',
                'op_type': 'sell',
                'position_id': pos.id,
                'symbol': 'SZ159869',
                'name': '华夏中证动漫游戏ETF',
                'ledger_id': ledger.id,
                'quantity': 100,
                'avg_price': 1.365,
                'confirm_date': '2026-05-08',
            },
        )
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.quantity == Money.shares_to_min_unit(9900)
        txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='sell').one()
        assert txn.quantity == Money.shares_to_min_unit(100)


class TestLedgerSnapshotConsistency:
    """账户持仓快照一致性（#1133 §4 温柔提醒数据源）：只读、不写 discrepancies 表。"""

    def _add_meta(self, db, position, snapshot_date, anchor_qty=None):
        """写溯源 meta；`anchor_qty` 非空时同时写 positions 层锚点。

        锚点模型下理论持仓 = `snapshot_quantity + Σ(快照日之后的流水)`。只有
        `position_import_meta.snapshot_date`、没有 `snapshot_quantity` 的持仓算不出
        基线（迁移后的存量行就是这种），函数会**跳过**而不是退回全量流水蒙一个数。
        所以「要报差异」的用例必须显式给 anchor_qty。
        """
        from app.domains.positions.models import PositionImportMeta

        if anchor_qty is not None:
            position.snapshot_quantity = Money.shares_to_min_unit(anchor_qty)
            position.snapshot_avg_price = position.avg_price or Money.yuan_to_price_units(10)
            position.snapshot_date = snapshot_date
            position.anchor_kind = 'external'
            db.flush()

        meta = PositionImportMeta(
            position_id=position.id,
            symbol=position.symbol,
            ledger_id=position.ledger_id,
            family_id=position.family_id,
            snapshot_date=snapshot_date,
        )
        db.add(meta)
        db.flush()
        return meta

    def test_pure_snapshot_skipped(self, db):
        """纯快照模式（有快照、无流水）→ 跳过，不误报（#1133 §4 边界）。"""
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
            quantity=Money.shares_to_min_unit(1000),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.flush()
        self._add_meta(db, pos, date(2026, 6, 12), anchor_qty=1000)
        db.commit()
        items = get_ledger_snapshot_consistency(db, 1)
        assert items == []

    def test_snapshot_stale_flagged(self, db):
        """锚点 + 快照后流水 ≠ 实际持仓 → 标记滞后（diff != 0）。

        锚点口径：theoretical = 1000（快照）+ 200（快照后买入）= 1200。
        实际 1300 才说明「账对不上」；若实际正好 1200 则是对齐的（见 test_match_not_flagged）。
        旧口径会把「快照前买入 1000」再算一遍当理论值，与本模型正好相反。
        """
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        # 快照前买入 1000（已被快照包含，不再计入理论值）
        _buy_txn(db, ledger.id, 'S1', 1000, date(2026, 6, 1))
        # 持仓实际 1300：锚点 1000 + 快照后买入 200 = 1200，差 100
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(1300),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.flush()
        self._add_meta(db, pos, date(2026, 6, 12), anchor_qty=1000)
        # 快照后买入 200（确认存在期后活动）
        _buy_txn(db, ledger.id, 'S1', 200, date(2026, 8, 15))
        db.commit()
        items = get_ledger_snapshot_consistency(db, 1)
        assert len(items) == 1
        it = items[0]
        assert it['symbol'] == 'S1'
        assert it['ledger_id'] == ledger.id
        # 理论 = 快照 1000 + 快照后 200 = 1200，实际 = 1300，diff = +100
        assert it['expected_qty'] == 1200
        assert it['actual_qty'] == 1300
        assert it['diff_qty'] == 100
        assert it['snapshot_date'] == '2026-06-12'
        assert it['last_txn_date'] == '2026-08-15'

    def test_match_not_flagged(self, db):
        """流水与持仓一致 → 无差异。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        _buy_txn(db, ledger.id, 'S1', 1000, date(2026, 6, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(1000),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.flush()
        self._add_meta(db, pos, date(2026, 6, 12), anchor_qty=1000)
        db.commit()
        items = get_ledger_snapshot_consistency(db, 1)
        assert items == []

    def test_none_confirm_date_skipped(self, db):
        """confirm_date 为 None 的流水无法定位快照日前后，跳过不计入 theoretical（#ai-review）。"""
        from app.domains.ledgers.models import Ledger

        ledger = Ledger(name='账户A', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        # 快照前买入 1000（截至快照日应有 1000）
        _buy_txn(db, ledger.id, 'S1', 1000, date(2026, 6, 1))
        pos = Position(
            symbol='S1',
            name='股1',
            asset_type='stock',
            market='CN_A',
            ledger_id=ledger.id,
            family_id=1,
            quantity=Money.shares_to_min_unit(1000),
            avg_price=Money.yuan_to_price_units(10),
            current_price=Money.yuan_to_price_units(10),
            source='manual',
            ownership_status='active',
        )
        db.add(pos)
        db.flush()
        self._add_meta(db, pos, date(2026, 6, 12), anchor_qty=1000)
        # 一笔 confirm_date=None 的流水（不应被计入 theoretical）
        db.add(
            Transaction(
                position_id=pos.id,
                ledger_id=ledger.id,
                family_id=1,
                symbol='S1',
                txn_type='buy',
                quantity=Money.shares_to_min_unit(500),
                price=Money.yuan_to_price_units(1.0),
                amount=Money.yuan_to_cents(500),
                confirm_date=None,
                trade_date=None,
                position_name='S1',
                account_name='测试',
                status='success',
                entry_status='success',
            )
        )
        db.commit()
        items = get_ledger_snapshot_consistency(db, 1)
        # None 日期流水被跳过 → theoretical=1000 == 持仓 1000 → 不报
        # （修复前会误算 theoretical=1500，diff=-500 而误报）
        assert items == []


# ── 2026-11-07 第二轮：差异列表出参批量补产品名 ──────────────────────
def test_resolve_display_names_prefers_position_name(db, make_position):
    """持仓里用户自己记的名字优先；查不到返回空串，由前端降级显示代码、不丢行。"""
    from app.services.reconciliation_query import resolve_display_names

    make_position(
        symbol='600519',
        name='贵州茅台',
        asset_type='stock',
        account_name='测试',
        quantity=100,
        avg_price=10.0,
    )
    names = resolve_display_names(db, 1, ['600519', 'NO_SUCH_CODE', ''])
    assert names.get('600519') == '贵州茅台'
    assert 'NO_SUCH_CODE' not in names
    assert '' not in names


def test_resolve_display_names_strips_exchange_prefix(db):
    """场内基金带 SH/SZ 前缀时，按裸 6 位码回退查基金名录。"""
    from app.domains.funds.models import Fund
    from app.services.reconciliation_query import resolve_display_names

    db.add(Fund(fund_code='511990', name='华宝添益'))
    db.commit()
    names = resolve_display_names(db, 1, ['SH511990'])
    assert names.get('SH511990') == '华宝添益'
