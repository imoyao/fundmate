# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/26
# File : test_ledger_migration_twophase.py
"""账本批量迁移两段式改造专项测试（设计文档 docs/design/ledger-merge-design.md §9）。

覆盖：preview 三分类与 suggestion 规则、commit 守恒/去重、merge 加权平均（整除与
四舍五入）、conflict 未决议拦截、守恒失败整体回滚、资产四种决议行为。
"""

from datetime import date

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, SalesInstitution
from app.domains.transactions.models import Transaction


def _make_pair(client, prefix='基金'):
    """创建同类型源/目标账本，返回 (src_id, tgt_id)。"""
    src = client.post('/api/ledgers/', json={'name': f'{prefix}源', 'ledger_type': 'fund'})
    tgt = client.post('/api/ledgers/', json={'name': f'{prefix}目标', 'ledger_type': 'fund'})
    return src.get_json()['data']['id'], tgt.get_json()['data']['id']


def _pos(symbol, name, ledger_id, account_name, quantity, avg_price, current_price=1000, **kwargs):
    """构造持仓（quantity 单位：份；avg_price/current_price 单位：元，由 fixture 口径换算）。"""
    return Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type='fund',
        account_name=account_name,
        ledger_id=ledger_id,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        current_price=Money.yuan_to_price_units(current_price),
        **kwargs,
    )


class TestMigrationPreview:
    """预览三分类正确 + suggestion 两种规则各一例。"""

    def test_preview_classifications_and_suggestions(self, client, db):
        src_id, tgt_id = _make_pair(client)
        # keep：目标无同 symbol
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        # duplicate：目标已有字段完全一致的同 symbol
        db.add(_pos('000002', '基金二', src_id, '基金源', 200, 2.0))
        db.add(_pos('000002', '基金二', tgt_id, '基金目标', 200, 2.0))
        # conflict + suggestion=keep_target：份额与成本价全等，仅成本日不同
        db.add(_pos('000003', '基金三', src_id, '基金源', 300, 3.0, confirm_date=date(2026, 8, 1)))
        db.add(_pos('000003', '基金三', tgt_id, '基金目标', 300, 3.0, confirm_date=date(2026, 1, 1)))
        # conflict + suggestion=merge：份额不同
        db.add(_pos('000004', '基金四', src_id, '基金源', 400, 4.0))
        db.add(_pos('000004', '基金四', tgt_id, '基金目标', 100, 4.0))
        # 资产行：preview 必须带出分类键（commit 决议按 name+major+minor 定位资产）
        db.add(
            Asset(
                user_id=1,
                major_category='cash',
                minor_category='bank',
                name='余额',
                amount=50000,
                account_name='基金源',
                ledger_id=src_id,
            )
        )
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        items = {i['symbol']: i for i in resp.get_json()['data']['items']}

        assert items['000001']['classification'] == 'keep'
        assert items['000001']['suggestion'] is None
        assert items['000001']['target'] is None

        assert items['000002']['classification'] == 'duplicate'
        assert items['000002']['suggestion'] is None
        assert items['000002']['conflict_fields'] == []

        assert items['000003']['classification'] == 'conflict'
        assert items['000003']['suggestion'] == 'keep_target'
        assert items['000003']['conflict_fields'] == ['confirm_date']

        assert items['000004']['classification'] == 'conflict'
        assert items['000004']['suggestion'] == 'merge'
        assert set(items['000004']['conflict_fields']) == {'quantity'}

        # 可读单位：份/元/ISO 日期
        assert items['000004']['source']['quantity'] == 400.0
        assert items['000004']['source']['avg_price'] == 4.0
        assert items['000003']['source']['confirm_date'] == '2026-08-01'

        # 资产行携带决议定位键（契约缺口回归：缺键前端无法组装资产决议）
        asset_items = [i for i in resp.get_json()['data']['items'] if i['kind'] == 'asset']
        assert len(asset_items) == 1
        assert asset_items[0]['name'] == '余额'
        assert asset_items[0]['major_category'] == 'cash'
        assert asset_items[0]['minor_category'] == 'bank'
        assert asset_items[0]['classification'] == 'keep'

    def test_preview_conservation_counts(self, client, db, make_transaction):
        """conservation 报告源迁出份额总量、目标净增份额总量与账户级交易条数"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))  # keep：净增 100 份
        db.add(_pos('000002', '基金二', src_id, '基金源', 200, 2.0))  # duplicate：净增 0
        db.add(_pos('000002', '基金二', tgt_id, '基金目标', 200, 2.0))
        db.commit()
        # 账户级交易（position_id 为空）：commit 时无条件归并，预览只报数
        make_transaction(position_id=None, ledger_id=src_id, txn_type='buy', quantity=0, price=1.0, amount=50.0)
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        data = resp.get_json()['data']
        conservation = data['conservation']
        # 最小单位：100 份 = 1000000
        assert conservation['source_out_positions'] == 3000000
        assert conservation['target_in_positions'] == 1000000
        assert conservation['account_level_transactions'] == 1


class TestMigrationCommitKeepDuplicate:
    """commit keep/duplicate 数量守恒、精确重复不翻倍。"""

    def test_commit_keep_conserves_quantity(self, client, db):
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 123.4567, 1.5))
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        kept = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        # 守恒：份额最小单位原样迁移，无精度损失
        assert kept.quantity == 1234567
        assert kept.avg_price == 15000
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0

    def test_duplicate_not_doubled(self, client, db):
        """精确重复只保留一份，份额不为两份之和"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 100, 1.0))
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        rows = db.query(Position).filter(Position.ledger_id == tgt_id).all()
        assert len(rows) == 1
        assert rows[0].quantity == 1000000  # 未翻倍


class TestMigrationMerge:
    """merge 决议：加权平均（整除/四舍五入各一例）、成本日取较新、meta CASCADE、字段保全。"""

    def _commit_merge(self, client, src_id, tgt_id, symbol):
        resp = client.post(
            f'/api/ledgers/{src_id}/migrations/commit/',
            json={
                'target_ledger_id': tgt_id,
                'resolutions': [{'kind': 'position', 'symbol': symbol, 'action': 'merge'}],
            },
        )
        return resp

    def test_merge_weighted_average_divisible(self, client, db):
        """能整除：100份@10元 + 100份@20元 → 200份@15元；成本日取较新；目标字段保全"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0, confirm_date=date(2026, 8, 1)))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 100, 20.0, confirm_date=date(2026, 5, 1)))
        db.commit()
        # 给目标持仓设置备注，验证合并后保留目标原值（含 portfolio_id 等不动）
        tgt_pos = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        tgt_pos.notes = '目标备注'
        tgt_pos.portfolio_id = 42
        db.commit()

        resp = self._commit_merge(client, src_id, tgt_id, '000001')
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['merged_count'] == 1

        merged = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        assert merged.quantity == 2000000  # 份额相加（最小单位整数）
        assert merged.avg_price == 150000  # (100*10 + 100*20) / 200 = 15 元 = 150000 price_units，整除无余数
        assert merged.confirm_date == date(2026, 8, 1)  # 成本日取较新
        assert merged.notes == '目标备注'  # 其余字段保留目标原值
        assert merged.portfolio_id == 42
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0

    def test_merge_weighted_average_rounds_half_up(self, client, db):
        """不能整除：10份@10.05元 + 10份@10.00元 → 加权均值 10.025 元，四舍五入到分取 10.03"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 10, 10.05))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 10, 10.00))
        db.commit()

        resp = self._commit_merge(client, src_id, tgt_id, '000001')
        assert resp.status_code == 200, resp.get_json()
        merged = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        # (100000*1005 + 100000*1000 + 100000) // 200000 = 1003 分 = 10.03 元
        assert merged.quantity == 200000
        assert merged.avg_price == 100250

    def test_merge_cascades_source_meta_and_keeps_target_meta(self, client, db):
        """merge 后源持仓被删除、其 PositionImportMeta 一并清除，目标溯源记录不受影响"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 100, 20.0))
        db.commit()
        src_pos = db.query(Position).filter(Position.ledger_id == src_id).one()
        tgt_pos = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        db.add(PositionImportMeta(position_id=src_pos.id, symbol='000001', source='', fund_manager='源管理人'))
        db.add(PositionImportMeta(position_id=tgt_pos.id, symbol='000001', source='', fund_manager='目标管理人'))
        db.commit()
        # 提前取 id：API 调用后测试会话对象过期，再访问属性会触发对已删行的刷新报错
        src_pos_id, tgt_pos_id = src_pos.id, tgt_pos.id

        resp = self._commit_merge(client, src_id, tgt_id, '000001')
        assert resp.status_code == 200, resp.get_json()

        # 源持仓已删，其 meta 随 CASCADE 清除（用 filter 查询绕过测试会话的身份映射缓存）
        assert db.query(Position).filter(Position.id == src_pos_id).first() is None
        assert db.query(PositionImportMeta).filter(PositionImportMeta.position_id == src_pos_id).first() is None
        # 目标溯源记录仍在
        kept_meta = db.query(PositionImportMeta).filter_by(position_id=tgt_pos_id).one()
        assert kept_meta.fund_manager == '目标管理人'

    def test_merge_moves_source_transactions(self, client, db, make_transaction):
        """merge 后源持仓名下交易并入目标持仓（position_id 改挂），源行删除"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 100, 20.0))
        db.commit()
        src_pos = db.query(Position).filter(Position.ledger_id == src_id).one()
        make_transaction(position_id=src_pos.id, ledger_id=src_id, txn_type='buy', quantity=50.0, price=9.0)
        db.commit()

        resp = self._commit_merge(client, src_id, tgt_id, '000001')
        assert resp.status_code == 200, resp.get_json()
        merged = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        txn = db.query(Transaction).filter(Transaction.ledger_id == tgt_id).one()
        assert txn.position_id == merged.id
        assert txn.account_name == '基金目标'


class TestMigrationConflictResolution:
    """conflict 未决议拦截、keep_source 反向归并交易、守恒失败回滚。"""

    def test_conflict_without_resolution_rejected(self, client, db):
        """conflict 缺 resolution → 400 列出未决议项，且源数据不变"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 200, 20.0))
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 400
        assert '000001' in resp.get_json()['message']
        # 源/目标数据原样
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 1
        assert db.query(Position).filter(Position.ledger_id == tgt_id).count() == 1
        assert db.query(Position).filter(Position.ledger_id == src_id).one().quantity == 1000000

    def test_keep_source_moves_target_transactions(self, client, db, make_transaction):
        """keep_source：目标持仓名下交易先改挂源持仓（方向相反的去重归并），
        目标行删除后源行改挂目标账本，交易最终落在目标账本的目标持仓上"""
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0))
        db.add(_pos('000001', '基金一', tgt_id, '基金目标', 200, 20.0))
        db.commit()
        src_pos = db.query(Position).filter(Position.ledger_id == src_id).one()
        tgt_pos = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        make_transaction(
            position_id=tgt_pos.id, ledger_id=tgt_id, txn_type='buy', quantity=100.0, price=19.0, import_hash='t-hash'
        )
        make_transaction(position_id=src_pos.id, ledger_id=src_id, txn_type='sell', quantity=30.0, price=11.0)
        db.commit()
        # 提前取 id：API 调用后测试会话对象过期，再访问属性会触发对已删行的刷新报错
        src_pos_id, tgt_pos_id = src_pos.id, tgt_pos.id

        resp = client.post(
            f'/api/ledgers/{src_id}/migrations/commit/',
            json={
                'target_ledger_id': tgt_id,
                'resolutions': [{'kind': 'position', 'symbol': '000001', 'action': 'keep_source'}],
            },
        )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['keep_source_count'] == 1

        # 源行存活并改挂目标账本，值保持源数据
        kept = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        assert kept.id == src_pos_id
        assert kept.quantity == 1000000
        # 两笔交易都落在存续持仓下，且账本归属为目标
        txns = db.query(Transaction).filter(Transaction.position_id == kept.id).all()
        assert len(txns) == 2
        assert all(t.ledger_id == tgt_id for t in txns)
        assert db.query(Position).filter(Position.id == tgt_pos_id).first() is None

    def test_conservation_failure_rolls_back(self, client, db, monkeypatch):
        """守恒校验被注入异常 → 500 且整体回滚，源数据原样"""
        from app.domains.ledgers import views as ledger_views

        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 10.0))
        db.commit()

        def _boom(*args, **kwargs):
            raise RuntimeError('注入的守恒校验失败')

        monkeypatch.setattr(ledger_views, '_verify_migration_conservation', _boom)

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 500
        # 回滚后源数据原样
        src_pos = db.query(Position).filter(Position.ledger_id == src_id).one()
        assert src_pos.quantity == 1000000
        assert src_pos.ledger_id == src_id
        assert db.query(Position).filter(Position.ledger_id == tgt_id).count() == 0


class TestMigrationAssetResolutions:
    """资产四种决议行为：keep_source / keep_target / duplicate / conflict 留源。"""

    def _seed_conflict(self, client, db, src_amount_yuan, tgt_amount_yuan):
        src_id, tgt_id = _make_pair(client, prefix='资产')
        db.add(
            Asset(
                user_id=1,
                major_category='cash',
                name='余额',
                amount=Money.yuan_to_cents(src_amount_yuan),
                account_name='资产源',
                ledger_id=src_id,
            )
        )
        db.add(
            Asset(
                user_id=1,
                major_category='cash',
                name='余额',
                amount=Money.yuan_to_cents(tgt_amount_yuan),
                account_name='资产目标',
                ledger_id=tgt_id,
            )
        )
        db.commit()
        return src_id, tgt_id

    def _resolution(self, action):
        return [{'kind': 'asset', 'name': '余额', 'major_category': 'cash', 'action': action}]

    def test_asset_keep_source_deletes_target_row(self, client, db):
        src_id, tgt_id = self._seed_conflict(client, db, 5000, 3000)
        resp = client.post(
            f'/api/ledgers/{src_id}/migrations/commit/',
            json={'target_ledger_id': tgt_id, 'resolutions': self._resolution('keep_source')},
        )
        assert resp.status_code == 200, resp.get_json()
        kept = db.query(Asset).filter(Asset.ledger_id == tgt_id).one()
        assert kept.amount == 500000  # 源值覆盖
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 0

    def test_asset_keep_target_deletes_source_row(self, client, db):
        src_id, tgt_id = self._seed_conflict(client, db, 5000, 3000)
        resp = client.post(
            f'/api/ledgers/{src_id}/migrations/commit/',
            json={'target_ledger_id': tgt_id, 'resolutions': self._resolution('keep_target')},
        )
        assert resp.status_code == 200, resp.get_json()
        kept = db.query(Asset).filter(Asset.ledger_id == tgt_id).one()
        assert kept.amount == 300000  # 目标原值不变
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 0

    def test_asset_duplicate_auto_dedup_without_resolution(self, client, db):
        """金额一致的精确重复自动去重，无需用户决议"""
        src_id, tgt_id = self._seed_conflict(client, db, 5000, 5000)
        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        rows = db.query(Asset).filter(Asset.ledger_id == tgt_id).all()
        assert len(rows) == 1
        assert rows[0].amount == 500000  # 未翻倍
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 0

    def test_asset_conflict_unresolved_stays_in_source(self, client, db):
        """资产 conflict 未决议 → 400，源资产行保留"""
        src_id, tgt_id = self._seed_conflict(client, db, 5000, 3000)
        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 400
        assert '余额' in resp.get_json()['message']
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 1
        assert db.query(Asset).filter(Asset.ledger_id == tgt_id).count() == 1


class TestMigrationAccountLevelTransactions:
    """账户级交易（position_id 为空）无条件归并到目标账户。"""

    def test_account_level_txns_merged_on_commit(self, client, db, make_transaction):
        src_id, tgt_id = _make_pair(client)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        db.commit()
        make_transaction(position_id=None, ledger_id=src_id, txn_type='buy', quantity=0, price=1.0, amount=88.0)
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['data']['transaction_count'] == 1
        txn = db.query(Transaction).filter(Transaction.position_id.is_(None)).one()
        assert txn.ledger_id == tgt_id
        assert txn.account_name == '基金目标'
        assert db.query(Ledger).get(src_id) is not None  # 源账本本身不被删除


class TestMigrationInstitutionGate:
    """销售机构软优先 + 显式确认：preview 报告 institution 块，commit 跨机构须显式放行。"""

    @staticmethod
    def _make_institution(db, org_name, display_name=None):
        inst = SalesInstitution(org_name=org_name, org_type='独立基金销售机构', display_name=display_name)
        db.add(inst)
        db.commit()
        return inst

    @staticmethod
    def _bind(db, ledger_id, institution_id):
        ledger = db.query(Ledger).filter(Ledger.id == ledger_id).first()
        ledger.sales_institution_id = institution_id
        db.commit()

    def test_preview_same_institution_not_cross(self, client, db):
        """双方绑定同一机构 → cross_institution=false"""
        src_id, tgt_id = _make_pair(client)
        inst = self._make_institution(db, '蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        self._bind(db, src_id, inst.id)
        self._bind(db, tgt_id, inst.id)

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        block = resp.get_json()['data']['institution']
        assert block['source'] == {'id': inst.id, 'name': '支付宝'}
        assert block['target'] == {'id': inst.id, 'name': '支付宝'}
        assert block['cross_institution'] is False

    def test_preview_cross_institution_true(self, client, db):
        """双方绑定不同机构 → cross_institution=true；display_name 缺省回退 org_name"""
        src_id, tgt_id = _make_pair(client)
        inst_a = self._make_institution(db, '蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        inst_b = self._make_institution(db, '浙江同花顺基金销售有限公司')  # 无 display_name
        self._bind(db, src_id, inst_a.id)
        self._bind(db, tgt_id, inst_b.id)

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        block = resp.get_json()['data']['institution']
        assert block['source'] == {'id': inst_a.id, 'name': '支付宝'}
        assert block['target'] == {'id': inst_b.id, 'name': '浙江同花顺基金销售有限公司'}
        assert block['cross_institution'] is True

    def test_preview_unbound_side_is_null_and_not_cross(self, client, db):
        """任一方未绑定机构 → 对应侧为 null 且 cross_institution=false"""
        src_id, tgt_id = _make_pair(client)
        inst = self._make_institution(db, '蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        self._bind(db, src_id, inst.id)  # 仅源绑定，目标未绑定

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        block = resp.get_json()['data']['institution']
        assert block['source'] == {'id': inst.id, 'name': '支付宝'}
        assert block['target'] is None
        assert block['cross_institution'] is False

    def test_commit_cross_institution_requires_explicit_confirm(self, client, db):
        """跨机构 commit 未带 allow_cross_institution → 400 且源数据不变；带 true → 成功"""
        src_id, tgt_id = _make_pair(client)
        inst_a = self._make_institution(db, '蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        inst_b = self._make_institution(db, '浙江同花顺基金销售有限公司')
        self._bind(db, src_id, inst_a.id)
        self._bind(db, tgt_id, inst_b.id)
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        db.commit()

        # 未显式确认 → 400，不写任何数据
        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 400
        assert '跨销售机构' in resp.get_json()['message']
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 1
        assert db.query(Position).filter(Position.ledger_id == tgt_id).count() == 0

        # 显式确认 → 放行成功
        resp = client.post(
            f'/api/ledgers/{src_id}/migrations/commit/',
            json={'target_ledger_id': tgt_id, 'allow_cross_institution': True},
        )
        assert resp.status_code == 200, resp.get_json()
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0
        kept = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        assert kept.quantity == 1000000

    def test_commit_unbound_or_same_institution_passes_without_flag(self, client, db):
        """任一方未绑定机构 → 不拦截；同机构同理（此处验证未绑定路径）"""
        src_id, tgt_id = _make_pair(client)
        inst = self._make_institution(db, '蚂蚁（杭州）基金销售有限公司', display_name='支付宝')
        self._bind(db, src_id, inst.id)  # 目标未绑定
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/commit/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0


class TestMigrationPreviewAssetType:
    """preview 持仓行携带 asset_type，供前端切换展示术语。"""

    def test_position_item_includes_asset_type(self, client, db):
        src_id, tgt_id = _make_pair(client)
        # _pos 助手默认 asset_type='fund'（基金语境）
        db.add(_pos('000001', '基金一', src_id, '基金源', 100, 1.0))
        db.commit()

        resp = client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200, resp.get_json()
        item = resp.get_json()['data']['items'][0]
        assert item['kind'] == 'position'
        assert item['asset_type'] == 'fund'
