# -*- coding: utf-8 -*-
"""账本迁移 / 孤儿治理的服务层单测（#1606）。

存在的意义：这些**业务规则**（三分类与决议、去重/合并、守恒校验、单事务回滚、
孤儿归入与清理）下沉到 `services/ledger_migration_service.py` 后，**不必起 HTTP 栈**
即可直接测——这正是 #1606 的收益之一（此前跨账户迁移这种高风险操作没有服务层测试入口）。

分工：本文件钉**服务层语义**（含异常类型与状态码）；对外 API 契约（端点、状态码、
错误文案、响应字段）仍由 `tests/domains/test_ledger_migration_twophase.py` 与
`tests/domains/test_ledgers.py` 覆盖，两侧都通过即「对外零变更」。
"""

import pytest

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution
from app.domains.transactions.models import Transaction
from app.services import ledger_migration_service as svc


def _ledger(db, name, ledger_type='fund', **kwargs):
    ledger = Ledger(name=name, ledger_type=ledger_type, family_id=1, **kwargs)
    db.add(ledger)
    db.commit()
    return ledger


def _pos(db, symbol, ledger, name='基金一', quantity=100, avg_price=1.0, current_price=1.0, **kwargs):
    """构造持仓（quantity 单位：份；avg_price/current_price 单位：元，此处统一换算）。"""
    pos = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type='fund',
        account_name=ledger.name if ledger else '',
        ledger_id=ledger.id if ledger else None,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        current_price=Money.yuan_to_price_units(current_price),
        family_id=1,
        **kwargs,
    )
    db.add(pos)
    db.commit()
    return pos


def _asset(db, ledger, name='余额', amount=5000.0, **kwargs):
    asset = Asset(
        user_id=1,
        family_id=1,
        major_category='cash',
        minor_category='bank',
        name=name,
        amount=Money.yuan_to_cents(amount),
        account_name=ledger.name if ledger else '',
        ledger_id=ledger.id if ledger else None,
        **kwargs,
    )
    db.add(asset)
    db.commit()
    return asset


class TestTargetValidation:
    """目标合法性校验：同家庭（防 IDOR）+ 同类型（计算口径一致）。"""

    def test_cross_family_rejected_with_403(self, db):
        source = _ledger(db, '源')
        other = _ledger(db, '别家')
        other.family_id = 2
        db.commit()

        with pytest.raises(svc.MigrationError) as exc:
            svc.check_migration_target(source, other)
        assert exc.value.status_code == 403
        assert exc.value.message == '只能迁移到同家庭账户'

    def test_cross_type_rejected_with_400(self, db):
        source = _ledger(db, '基金源', ledger_type='fund')
        target = _ledger(db, '证券目标', ledger_type='stock')

        with pytest.raises(svc.MigrationError) as exc:
            svc.check_migration_target(source, target)
        assert exc.value.status_code == 400
        assert exc.value.message == '只能迁移到同类型账户'

    def test_same_family_same_type_passes(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        assert svc.check_migration_target(source, target) is None


class TestPreview:
    """预览：三分类 + 守恒预估 + 机构块（只读，不写库）。"""

    def test_classifies_and_estimates_conservation(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        _pos(db, '000001', source, quantity=100)  # keep：净增 100 份
        _pos(db, '000002', source, quantity=200)  # duplicate：净增 0
        _pos(db, '000002', target, quantity=200)
        _pos(db, '000004', source, quantity=400)  # conflict：建议 merge
        _pos(db, '000004', target, quantity=100)
        _asset(db, source, amount=5000)

        payload = svc.preview_migration(db, source, target, 1)
        items = {i['symbol']: i for i in payload['items'] if i['kind'] == 'position'}

        assert items['000001']['classification'] == 'keep'
        assert items['000002']['classification'] == 'duplicate'
        assert items['000004']['classification'] == 'conflict'
        assert items['000004']['suggestion'] == 'merge'
        # 守恒预估：源迁出 700 份（最小单位 7_000_000），目标净增 = 100(keep) + 400(merge 建议)
        assert payload['conservation']['source_out_positions'] == 7_000_000
        assert payload['conservation']['target_in_positions'] == 5_000_000
        # 资产行带决议定位键（缺键则前端无法组装资产决议）
        asset_items = [i for i in payload['items'] if i['kind'] == 'asset']
        assert asset_items[0]['major_category'] == 'cash'
        assert asset_items[0]['minor_category'] == 'bank'
        # 预览是只读的：源账本持仓一条不少
        assert db.query(Position).filter(Position.ledger_id == source.id).count() == 3

    def test_institution_block_marks_cross(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        inst_a = SalesInstitution(org_name='蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        inst_b = SalesInstitution(org_name='浙江同花顺基金销售有限公司')
        db.add_all([inst_a, inst_b])
        db.commit()
        source.sales_institution_id = inst_a.id
        target.sales_institution_id = inst_b.id
        db.commit()

        block = svc.institution_block(db, source, target)
        assert block['source'] == {'id': inst_a.id, 'name': '支付宝'}  # display_name 优先
        assert block['target'] == {'id': inst_b.id, 'name': '浙江同花顺基金销售有限公司'}  # 缺省回退全称
        assert block['cross_institution'] is True

    def test_unbound_side_is_not_cross(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        inst = SalesInstitution(org_name='蚂蚁（杭州）基金销售有限公司')
        db.add(inst)
        db.commit()
        source.sales_institution_id = inst.id
        db.commit()

        block = svc.institution_block(db, source, target)
        assert block['target'] is None
        assert block['cross_institution'] is False


class TestCommit:
    """提交：单事务写入 + 决议拦截 + 守恒回滚（服务层直接驱动，无 HTTP）。"""

    def test_keep_moves_position_and_transactions(self, db, make_transaction):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        pos = _pos(db, '000001', source, quantity=123.4567, avg_price=1.5)
        make_transaction(position_id=pos.id, ledger_id=source.id, txn_type='buy', quantity=100, price=1.4)
        db.commit()

        counts = svc.commit_migration(db, source, target, 1, resolutions=[])

        assert counts['position_count'] == 1
        assert counts['transaction_count'] == 1
        moved = db.query(Position).filter(Position.ledger_id == target.id).one()
        # 守恒：最小单位原样迁移，无精度损失
        assert moved.quantity == 1234567
        assert moved.avg_price == 15000
        txn = db.query(Transaction).one()
        assert txn.ledger_id == target.id
        assert txn.account_name == '目标'

    def test_merge_uses_weighted_average_and_drops_source_row(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        _pos(db, '000001', source, quantity=100, avg_price=10.0)
        _pos(db, '000001', target, quantity=100, avg_price=20.0)

        counts = svc.commit_migration(
            db,
            source,
            target,
            1,
            resolutions=[{'kind': 'position', 'symbol': '000001', 'action': 'merge'}],
        )

        assert counts['merged_count'] == 1
        merged = db.query(Position).filter(Position.ledger_id == target.id).one()
        assert merged.quantity == 2000000
        assert merged.avg_price == 150000  # (100×10 + 100×20) / 200 = 15 元
        assert db.query(Position).filter(Position.ledger_id == source.id).count() == 0

    def test_unresolved_conflict_raises_and_writes_nothing(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        _pos(db, '000001', source, quantity=100, avg_price=10.0)
        _pos(db, '000001', target, quantity=200, avg_price=20.0)

        with pytest.raises(svc.MigrationError) as exc:
            svc.commit_migration(db, source, target, 1, resolutions=[])
        assert exc.value.status_code == 400
        assert '000001' in exc.value.message
        # 未确认不写库：两侧数据原样
        assert db.query(Position).filter(Position.ledger_id == source.id).one().quantity == 1000000
        assert db.query(Position).filter(Position.ledger_id == target.id).one().quantity == 2000000

    def test_asset_conflict_requires_resolution(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        _asset(db, source, amount=5000)
        _asset(db, target, amount=3000)

        with pytest.raises(svc.MigrationError) as exc:
            svc.commit_migration(db, source, target, 1, resolutions=[])
        assert '余额' in exc.value.message
        assert db.query(Asset).filter(Asset.ledger_id == target.id).one().amount == 300000

        counts = svc.commit_migration(
            db,
            source,
            target,
            1,
            resolutions=[
                {
                    'kind': 'asset',
                    'name': '余额',
                    'major_category': 'cash',
                    'minor_category': 'bank',  # 决议定位键：缺 minor_category 会被判为未决议
                    'action': 'keep_source',
                }
            ],
        )
        assert counts['asset_count'] == 1
        assert db.query(Asset).filter(Asset.ledger_id == target.id).one().amount == 500000  # 源值覆盖

    def test_cross_institution_gate_needs_explicit_flag(self, db):
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        inst_a = SalesInstitution(org_name='蚂蚁（杭州）基金销售有限公司')
        inst_b = SalesInstitution(org_name='浙江同花顺基金销售有限公司')
        db.add_all([inst_a, inst_b])
        db.commit()
        source.sales_institution_id = inst_a.id
        target.sales_institution_id = inst_b.id
        db.commit()
        _pos(db, '000001', source)

        with pytest.raises(svc.MigrationError) as exc:
            svc.commit_migration(db, source, target, 1, resolutions=[])
        assert exc.value.status_code == 400
        assert '跨销售机构' in exc.value.message
        assert db.query(Position).filter(Position.ledger_id == source.id).count() == 1

        counts = svc.commit_migration(db, source, target, 1, resolutions=[], allow_cross_institution=True)
        assert counts['position_count'] == 1

    def test_conservation_failure_rolls_back(self, db, monkeypatch):
        """守恒校验失败 → 整体回滚并抛 500（写入不得半途落库）。"""
        source = _ledger(db, '源')
        target = _ledger(db, '目标')
        _pos(db, '000001', source, quantity=100, avg_price=10.0)

        def _boom(*args, **kwargs):
            raise RuntimeError('注入的守恒校验失败')

        monkeypatch.setattr(svc, '_verify_migration_conservation', _boom)

        with pytest.raises(svc.MigrationError) as exc:
            svc.commit_migration(db, source, target, 1, resolutions=[])
        assert exc.value.status_code == 500
        assert exc.value.message == '迁移失败，已整体回滚，源数据未变动'
        # 源数据原样、目标为空
        pos = db.query(Position).filter(Position.ledger_id == source.id).one()
        assert pos.quantity == 1000000
        assert db.query(Position).filter(Position.ledger_id == target.id).count() == 0


class TestOrphan:
    """孤儿（未归置）数据：明细 / 归入 / 清理，服务层直接驱动。"""

    def test_detail_reports_rows_and_summary(self, db):
        _pos(db, '510300', None, name='沪深300ETF', quantity=1234.56, avg_price=3.9, current_price=4.0)
        _asset(db, None, name='活期', amount=1000)
        db.add(
            Transaction(
                position_id=None,
                ledger_id=None,
                family_id=1,
                txn_type='buy',
                symbol='510300',
                position_name='沪深300ETF',
                account_name='',
                quantity=0,
                price=0,
                amount=Money.yuan_to_cents(88),
                status='success',
            )
        )
        db.commit()

        payload = svc.build_orphan_detail(db, 1)
        assert payload['summary']['position_count'] == 1
        assert payload['summary']['asset_count'] == 1
        assert payload['summary']['transaction_count'] == 1
        # 市值 = 4.0 × 1234.56 = 4938.24；盈亏 = (4.0 − 3.9) × 1234.56 = 123.46
        assert payload['positions'][0]['market_value'] == 4938.24
        assert payload['positions'][0]['pnl'] == 123.46
        assert payload['summary']['total_market_value'] == 5938.24

    def test_detail_excludes_ledger_rows(self, db):
        ledger = _ledger(db, '正常账户')
        _pos(db, '510300', ledger)
        _asset(db, ledger)

        payload = svc.build_orphan_detail(db, 1)
        assert payload['positions'] == []
        assert payload['assets'] == []
        assert payload['summary']['total_market_value'] == 0.0

    def test_migrate_assigns_target_and_keeps_snapshot(self, db):
        target = _ledger(db, '目标账户')
        pos = _pos(db, '510300', None, name='沪深300ETF')
        _asset(db, None, name='活期', amount=1000)
        db.add(
            Transaction(
                position_id=pos.id,
                ledger_id=None,
                family_id=1,
                txn_type='buy',
                symbol='510300',
                position_name='沪深300ETF',
                account_name='',
                quantity=0,
                price=0,
                amount=Money.yuan_to_cents(88),
                status='success',
            )
        )
        db.commit()

        counts = svc.migrate_orphan_data(db, target, 1)
        assert counts == {'position_count': 1, 'asset_count': 1, 'transaction_count': 1, 'total': 3}

        assert db.query(Position).one().ledger_id == target.id
        assert db.query(Position).one().account_name == '目标账户'
        assert db.query(Transaction).one().ledger_id == target.id
        assert db.query(Asset).one().ledger_id == target.id
        # 归入后不应再有孤儿
        assert svc.build_orphan_detail(db, 1)['summary']['position_count'] == 0

    def test_migrate_conflict_with_existing_symbol_raises_400(self, db):
        """归入会撞 uq_positions_ledger_symbol（目标已有同名持仓）→ 回滚 + 400。"""
        target = _ledger(db, '目标账户')
        _pos(db, '510300', target, name='目标已有')
        _pos(db, '510300', None, name='孤儿')  # ledger_id 为空，SQLite 唯一键不冲突

        with pytest.raises(svc.MigrationError) as exc:
            svc.migrate_orphan_data(db, target, 1)
        assert exc.value.status_code == 400
        assert '同名持仓' in exc.value.message
        # 回滚后仍是孤儿
        assert svc.build_orphan_detail(db, 1)['summary']['position_count'] == 1

    def test_delete_removes_all_orphans(self, db):
        pos = _pos(db, '510300', None, name='沪深300ETF')
        _asset(db, None, name='活期', amount=1000)
        db.add(
            Transaction(
                position_id=pos.id,
                ledger_id=None,
                family_id=1,
                txn_type='buy',
                symbol='510300',
                position_name='沪深300ETF',
                account_name='',
                quantity=0,
                price=0,
                amount=Money.yuan_to_cents(88),
                status='success',
            )
        )
        db.commit()

        counts = svc.delete_orphan_data(db, 1)
        assert counts == {'position_count': 1, 'asset_count': 1, 'transaction_count': 1}
        assert db.query(Position).count() == 0
        assert db.query(Asset).count() == 0
        assert db.query(Transaction).count() == 0

    def test_delete_keeps_ledger_scoped_rows(self, db):
        ledger = _ledger(db, '正常账户')
        _pos(db, '510300', ledger)
        db.commit()

        assert svc.delete_orphan_data(db, 1) == {'position_count': 0, 'asset_count': 0, 'transaction_count': 0}
        assert db.query(Position).count() == 1
