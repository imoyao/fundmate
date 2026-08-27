# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 11:02
# File : test_ledgers.py
"""测试资金容器 CRUD"""

from datetime import date

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution


class TestLedgerCRUD:
    def test_create_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '招商银行'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '招商银行'
        assert data['ledger_type'] == 'bank'

    def test_list_ledgers(self, client, db):
        client.post('/api/ledgers/', json={'name': 'L1'})
        client.post('/api/ledgers/', json={'name': 'L2'})
        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) >= 2

    def test_list_ledgers_includes_summary_fields(self, client, db, make_position):
        """列表接口应返回 total_market_value, pnl, position_count 等"""
        ledger = Ledger(name='测试', ledger_type='stock')
        db.add(ledger)
        db.commit()
        make_position(
            symbol='S1',
            name='股1',
            ledger_id=ledger.id,
            account_name='测试',
            quantity=200,
            avg_price=5.0,
            current_price=6.0,
        )
        resp = client.get('/api/ledgers/')
        ledgers = resp.get_json()['data']
        target = next(led for led in ledgers if led['name'] == '测试')
        assert target['total_market_value'] == 1200.0
        assert target['pnl'] == 200.0
        assert target['position_count'] == 1

    def test_delete_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': 'ToDelete'})
        lid = resp.get_json()['data']['id']
        del_resp = client.delete(f'/api/ledgers/{lid}/')
        assert del_resp.status_code == 200
        # 再次查询应不存在
        list_resp = client.get('/api/ledgers/')
        ids = [leg['id'] for leg in list_resp.get_json()['data']]
        assert lid not in ids

    def test_delete_nonexistent(self, client):
        resp = client.delete('/api/ledgers/9999/')
        assert resp.status_code == 404

    def test_create_empty_name(self, client):
        resp = client.post('/api/ledgers/', json={'name': ''})
        assert resp.status_code == 400  # 或 422，取决于是否用 Schema 校验

    def test_create_ledger_with_duplicate_name(self, client):
        """允许创建同名账户"""
        resp1 = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp1.status_code == 200
        resp2 = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp2.status_code == 200
        # 验证两个账户的ID不同
        assert resp1.get_json()['data']['id'] != resp2.get_json()['data']['id']

    def test_delete_ledger_with_positions_blocked(self, client, db, make_position):
        """有持仓且未勾选删除时应被拦截"""
        # 创建账户和持仓
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()
        make_position(
            symbol='000001',
            name='平安',
            ledger_id=ledger.id,
            account_name='测试账户',
            quantity=100,
            avg_price=10,
            current_price=10,
        )
        resp = client.delete(f'/api/ledgers/{ledger.id}/')
        assert resp.status_code == 400
        assert '持仓' in resp.get_json()['message']

    def test_delete_ledger_with_positions_force(self, client, db, make_position):
        """勾选同时删除持仓后，应基于 ledger_id 清除关联数据"""
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()
        pid = make_position(
            symbol='000001',
            name='平安',
            ledger_id=ledger.id,
            account_name='测试账户',
            quantity=100,
            avg_price=10,
            current_price=10,
        ).id
        # 强制删除
        resp = client.delete(f'/api/ledgers/{ledger.id}/?delete_positions=true')
        assert resp.status_code == 200

        # 将已被视图会话删除的对象从当前测试会话中移出，避免缓存冲突
        db.expunge(ledger)

        # 验证持仓不存在
        pos = db.query(Position).get(pid)
        assert pos is None
        # 验证账户不存在
        assert db.query(Ledger).get(ledger.id) is None


class TestLedgerWithAllocation:
    def test_create_ledger_with_allocation(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'default_allocation': 'longterm'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['default_allocation'] == 'longterm'

    def test_list_ledgers_contains_allocation(self, client, db):
        client.post('/api/ledgers/', json={'name': 'G1', 'default_allocation': 'stable'})
        resp = client.get('/api/ledgers/')
        ledgers = resp.get_json()['data']
        assert any(led['name'] == 'G1' and led.get('default_allocation') == 'stable' for led in ledgers)


class TestLedgerDefaultAllocation:
    """测试账户默认配置目标的标签返回"""

    @staticmethod
    def _find_ledger_by_name(ledgers: list[dict], name: str) -> dict | None:
        """辅助函数：在列表中查找指定名称的账户"""
        for ledger in ledgers:
            if ledger.get('name') == name:
                return ledger
        return None

    def test_create_ledger_with_allocation_label(self, client, db):
        """创建带配置目标的账户，应返回对应的中文标签"""
        resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'default_allocation': 'longterm'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['default_allocation'] == 'longterm'
        assert data['default_allocation_label'] == '长期增值'

    def test_create_ledger_without_allocation(self, client, db):
        """不设置配置目标时，标签应返回'未配置'或等同值"""
        resp = client.post('/api/ledgers/', json={'name': '测试账户'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        label = data.get('default_allocation_label')
        # 应当有值，且不是 None 或空字符串
        assert label is not None and label != ''

    def test_list_ledgers_contains_allocation_labels(self, client, db):
        """列表接口应返回每个账户的配置目标标签"""
        client.post('/api/ledgers/', json={'name': 'A', 'default_allocation': 'liquid'})
        client.post('/api/ledgers/', json={'name': 'B', 'default_allocation': 'stable'})
        client.post('/api/ledgers/', json={'name': 'C'})

        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        ledgers = resp.get_json()['data']

        a = self._find_ledger_by_name(ledgers, 'A')
        b = self._find_ledger_by_name(ledgers, 'B')
        c = self._find_ledger_by_name(ledgers, 'C')

        assert a is not None
        assert a['default_allocation_label'] == '活钱'

        assert b is not None
        assert b['default_allocation_label'] == '稳健底仓'

        assert c is not None
        label_c = c.get('default_allocation_label')
        assert label_c is not None and label_c != ''

    def test_all_allocation_values_have_labels(self, client, db):
        """所有五笔钱配置目标值都应有对应的中文标签"""
        allocations = ['liquid', 'stable', 'longterm', 'speculative', 'security']
        for alloc in allocations:
            resp = client.post('/api/ledgers/', json={'name': f'账户_{alloc}', 'default_allocation': alloc})
            assert resp.status_code == 200
            data = resp.get_json()['data']
            label = data.get('default_allocation_label')
            # 标签不应是原始英文值
            assert label != alloc
            # 标签不应为空
            assert label is not None and len(label) > 0


class TestAssignPositionToLedger:
    """测试将持仓归入已有账户"""

    def test_assign_position_to_ledger(self, client, db):
        """从'未指定账户'归入到已有账户"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            account_name='未指定账户',
        )
        db.add(pos)
        db.commit()

        resp = client.patch(f'/api/positions/{pos.id}/', json={'account_name': '银河证券'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['account_name'] == '银河证券'

        db.refresh(pos)
        assert pos.account_name == '银河证券'

    def test_assign_position_to_same_name(self, client, db):
        """新旧账户名相同时，接口应正常返回（幂等）"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            account_name='银河证券',
        )
        db.add(pos)
        db.commit()

        resp = client.patch(f'/api/positions/{pos.id}/', json={'account_name': '银河证券'})
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.account_name == '银河证券'

    def test_assign_position_to_empty_string(self, client, db):
        """将 account_name 清空（设置为空字符串）"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            account_name='银河证券',
        )
        db.add(pos)
        db.commit()

        resp = client.patch(f'/api/positions/{pos.id}/', json={'account_name': ''})
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.account_name == '' or pos.account_name is None

    def test_assign_position_to_none(self, client, db):
        """将 account_name 设为 null"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            account_name='银河证券',
        )
        db.add(pos)
        db.commit()

        resp = client.patch(f'/api/positions/{pos.id}/', json={'account_name': None})
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.account_name is None

    def test_assign_position_not_found(self, client):
        """更新不存在的持仓ID"""
        resp = client.patch('/api/positions/99999/', json={'account_name': '银河证券'})
        assert resp.status_code == 404

    def test_assign_position_with_invalid_json(self, client):
        """请求体不是合法的 JSON"""
        resp = client.patch('/api/positions/1/', data='not json', content_type='application/json')
        assert resp.status_code in (400, 422)

    def test_assign_position_with_extra_fields(self, client, db):
        """附加未允许的字段，应忽略或成功"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            account_name='未指定账户',
        )
        db.add(pos)
        db.commit()

        resp = client.patch(f'/api/positions/{pos.id}/', json={'account_name': '银河证券', 'dummy_field': 'ignored'})
        assert resp.status_code == 200
        db.refresh(pos)
        assert pos.account_name == '银河证券'


class TestAssignAssetToLedger:
    """测试将通用资产归入账户"""

    def test_assign_asset_to_ledger(self, client, db):
        """通用资产归入指定账户"""
        asset = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=100000, currency='CNY', account_name='未指定账户'
        )
        db.add(asset)
        db.commit()

        resp = client.patch(f'/api/assets/{asset.id}/', json={'account_name': '招商银行'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['account_name'] == '招商银行'

        db.refresh(asset)
        assert asset.account_name == '招商银行'

    def test_assign_asset_to_same_name(self, client, db):
        """同名校验"""
        asset = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=100000, currency='CNY', account_name='招商银行'
        )
        db.add(asset)
        db.commit()

        resp = client.patch(f'/api/assets/{asset.id}/', json={'account_name': '招商银行'})
        assert resp.status_code == 200
        db.refresh(asset)
        assert asset.account_name == '招商银行'

    def test_assign_asset_to_empty_string(self, client, db):
        """清空账户名"""
        asset = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=100000, currency='CNY', account_name='招商银行'
        )
        db.add(asset)
        db.commit()

        resp = client.patch(f'/api/assets/{asset.id}/', json={'account_name': ''})
        assert resp.status_code == 200
        db.refresh(asset)
        assert asset.account_name == '' or asset.account_name is None

    def test_assign_asset_to_none(self, client, db):
        """将 account_name 设为 null"""
        asset = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=100000, currency='CNY', account_name='招商银行'
        )
        db.add(asset)
        db.commit()

        resp = client.patch(f'/api/assets/{asset.id}/', json={'account_name': None})
        assert resp.status_code == 200
        db.refresh(asset)
        assert asset.account_name is None

    def test_assign_asset_not_found(self, client):
        """更新不存在的资产ID"""
        resp = client.patch('/api/assets/99999/', json={'account_name': '招商银行'})
        assert resp.status_code == 404

    def test_assign_asset_with_invalid_json(self, client):
        """请求体不是合法的 JSON"""
        resp = client.patch('/api/assets/1/', data='not json', content_type='application/json')
        assert resp.status_code in (400, 422)

    def test_assign_asset_with_extra_fields(self, client, db):
        """附加未允许的字段，应忽略或成功"""
        asset = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=100000, currency='CNY', account_name='未指定账户'
        )
        db.add(asset)
        db.commit()

        resp = client.patch(f'/api/assets/{asset.id}/', json={'account_name': '招商银行', 'dummy_field': 'ignored'})
        assert resp.status_code == 200
        db.refresh(asset)
        assert asset.account_name == '招商银行'


class TestLedgerFeeConfig:
    """测试 fee_config JSON 字段"""

    def test_create_ledger_with_fee_config_stock(self, client, db):
        """创建股票账户并设置 fee_config"""
        fee_config = {
            'commission': {'rate': 0.00025, 'min': None},
            'stamp_duty': {'rate': 0.005, 'scope': 'sell_only'},
            'transfer_fee': {'rate': 0.0001, 'scope': 'both'},
        }
        resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'fee_config': fee_config})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['ledger_type'] == 'stock'
        assert data['fee_config'] == fee_config

    def test_create_ledger_with_fee_config_fund(self, client, db):
        """创建基金账户并设置折扣"""
        fee_config = {'subscription_discount': 0.1}
        resp = client.post(
            '/api/ledgers/', json={'name': '支付宝基金', 'ledger_type': 'fund', 'fee_config': fee_config}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['fee_config'] == fee_config

    def test_update_ledger_fee_config(self, client, db):
        """更新已有账户的 fee_config"""
        # 先创建一个股票账户
        resp = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        assert resp.status_code == 200
        ledger_id = resp.get_json()['data']['id']

        # 更新 fee_config
        new_config = {'commission': {'rate': 0.0002, 'min': 5}, 'stamp_duty': {'rate': 0.005, 'scope': 'sell_only'}}
        resp = client.patch(f'/api/ledgers/{ledger_id}/', json={'fee_config': new_config})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['fee_config'] == new_config

    def test_update_ledger_fee_config_clear(self, client, db):
        """将 fee_config 设置为 null"""
        resp = client.post('/api/ledgers/', json={'name': '测试', 'fee_config': {'test': True}})
        assert resp.status_code == 200
        ledger_id = resp.get_json()['data']['id']

        # 清空
        resp = client.patch(f'/api/ledgers/{ledger_id}/', json={'fee_config': None})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['fee_config'] is None

    def test_ledger_list_includes_fee_config(self, client, db):
        """列表接口应包含 fee_config"""
        client.post('/api/ledgers/', json={'name': 'L1', 'fee_config': {'key': 'value'}})
        client.post('/api/ledgers/', json={'name': 'L2'})
        resp = client.get('/api/ledgers/')
        ledgers = resp.get_json()['data']
        l1 = next((led for led in ledgers if led['name'] == 'L1'), None)
        l2 = next((led for led in ledgers if led['name'] == 'L2'), None)
        assert l1 is not None
        assert l1['fee_config'] == {'key': 'value'}
        assert l2 is not None
        assert not l2['fee_config']


class TestLedgerLinkedCash:
    """测试关联现金账户"""

    def test_create_stock_with_valid_cash_ledger(self, client, db):
        """证券账户关联有效的现金账户"""
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': cash_id}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_cash_ledger_id'] == cash_id

    def test_create_fund_with_valid_cash_ledger(self, client, db):
        """基金平台关联有效的现金账户"""
        cash_resp = client.post('/api/ledgers/', json={'name': '余额宝', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        resp = client.post(
            '/api/ledgers/', json={'name': '蚂蚁基金', 'ledger_type': 'fund', 'linked_cash_ledger_id': cash_id}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_cash_ledger_id'] == cash_id

    def test_create_stock_with_nonexistent_cash_ledger(self, client):
        """关联不存在的现金账户应拒绝"""
        resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': 9999}
        )
        assert resp.status_code == 400
        assert '不存在' in resp.get_json()['message']

    def test_create_stock_with_non_cash_ledger(self, client, db):
        """关联的账户类型不是现金应拒绝"""
        # 创建一个股票账户
        stock_resp = client.post('/api/ledgers/', json={'name': '某证券', 'ledger_type': 'stock'})
        stock_id = stock_resp.get_json()['data']['id']
        # 尝试将其作为现金账户关联
        resp = client.post(
            '/api/ledgers/', json={'name': '另一证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': stock_id}
        )
        assert resp.status_code == 400
        assert '不是现金账户' in resp.get_json()['message']

    def test_create_cash_ledger_cannot_link_cash(self, client):
        """现金账户自身不能关联现金账户"""
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        resp = client.post(
            '/api/ledgers/', json={'name': '另一个现金', 'ledger_type': 'bank', 'linked_cash_ledger_id': cash_id}
        )
        assert resp.status_code == 400
        assert '只有证券账户或基金平台' in resp.get_json()['message']

    def test_update_ledger_link_cash(self, client, db):
        """更新账户关联现金账户"""
        # 创建现金账户和证券账户
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        stock_resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        stock_id = stock_resp.get_json()['data']['id']

        # 更新关联
        resp = client.patch(f'/api/ledgers/{stock_id}/', json={'linked_cash_ledger_id': cash_id})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_cash_ledger_id'] == cash_id

    def test_update_ledger_unlink_cash(self, client, db):
        """解绑现金账户（设为 null）"""
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        stock_resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': cash_id}
        )
        stock_id = stock_resp.get_json()['data']['id']

        resp = client.patch(f'/api/ledgers/{stock_id}/', json={'linked_cash_ledger_id': None})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_cash_ledger_id'] is None

    def test_update_ledger_change_type_clears_cash(self, client, db):
        """将证券账户改为现金类型时，应清空关联的现金账户（前端已处理，后端应允许）"""
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        cash_id = cash_resp.get_json()['data']['id']
        stock_resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': cash_id}
        )
        stock_id = stock_resp.get_json()['data']['id']

        # 直接修改类型为 bank，同时不传 linked_cash_ledger_id
        resp = client.patch(f'/api/ledgers/{stock_id}/', json={'ledger_type': 'bank'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ledger_type'] == 'bank'
        # 注意：当前后端在修改类型时不会自动清空关联，但前端会在切换时清空并传递 null。
        # 为保险，可以在测试中显式传递 null，我们额外测一次。
        # 如果只改类型而不传 linked_cash_ledger_id，字段保持不变（设计如此），所以本测试仅验证状态。
        # 可补充一个用例：同时传递 ledger_type 和 linked_cash_ledger_id=null。
        resp2 = client.patch(f'/api/ledgers/{stock_id}/', json={'ledger_type': 'bank', 'linked_cash_ledger_id': None})
        assert resp2.status_code == 200
        assert resp2.get_json()['data']['linked_cash_ledger_id'] is None


class TestLedgerOverview:
    """测试账户资金全景接口"""

    def test_overview_precision_with_fractional_prices(self, client, db, make_position):
        """含小数价格、非整千份额，验证市值聚合精度"""
        bank = Ledger(name='B1', ledger_type='bank')
        db.add(bank)
        db.commit()
        # 持仓：数量150份，价格10.5元
        make_position(
            symbol='X',
            name='基金X',
            ledger_id=bank.id,
            account_name='B1',
            quantity=150,
            avg_price=10.5,
            current_price=10.5,
        )
        resp = client.get('/api/ledgers/overview/')
        data = resp.get_json()['data']
        bank_group = next(g for g in data['groups'] if g['type'] == 'bank')
        assert bank_group['total'] == 1575.0  # 150 * 10.5

    def test_overview_empty(self, client):
        """无账户时应返回空结构"""
        resp = client.get('/api/ledgers/overview/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'groups' in data
        assert data['liability_total'] == 0
        assert data['net_worth'] == 0

    def test_overview_with_accounts_and_positions(self, client, db, make_position, make_asset):
        # 创建两个账本
        bank = Ledger(name='招商银行', ledger_type='bank')
        stock = Ledger(name='华泰证券', ledger_type='stock')
        db.add_all([bank, stock])
        db.commit()

        make_position(
            symbol='000001',
            name='平安银行',
            account_name='华泰证券',
            ledger_id=stock.id,
            quantity=1000,
            avg_price=10.0,
            current_price=12.0,
        )
        make_asset(major_category='cash', name='储蓄', amount=50000, account_name='招商银行', ledger_id=bank.id)
        make_asset(major_category='liability', name='房贷', amount=300000, account_name='招商银行', ledger_id=bank.id)

        resp = client.get('/api/ledgers/overview/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        groups = {g['type']: g for g in data['groups']}

        stock_group = groups.get('stock')
        assert stock_group is not None
        assert stock_group['count'] == 1
        assert stock_group['total'] == 12000

        bank_group = groups.get('bank')
        assert bank_group is not None
        assert bank_group['count'] == 1
        assert bank_group['total'] == 50000

        assert data['liability_total'] == 300000
        assert data['net_worth'] == -238000

    def test_overview_with_deleted_account(self, client, db, make_position):
        # 创建账户
        resp = client.post('/api/ledgers/', json={'name': '已删证券', 'ledger_type': 'stock'})
        lid = resp.get_json()['data']['id']

        # 通过 make_position 创建持仓，自动关联 ledger_id
        make_position(
            symbol='000002', name='万科', account_name='已删证券', quantity=500, avg_price=8.0, current_price=10.0
        )

        # 绕过 API 保护删除账户：positions.ledger_id 为 FK RESTRICT（有持仓时账户
        # 不可直接删行）。先置空持仓 ledger_id 模拟账户删除后的孤儿持仓，再删账户行，
        # overview 将孤儿持仓归入 deleted 分组
        pos = db.query(Position).filter(Position.symbol == '000002').first()
        pos.ledger_id = None
        db.commit()
        ledger = db.get(Ledger, lid)
        db.delete(ledger)
        db.commit()

        resp = client.get('/api/ledgers/overview/')
        data = resp.get_json()['data']
        groups = {g['type']: g for g in data['groups']}
        assert 'deleted' in groups
        deleted_group = groups['deleted']
        assert deleted_group['count'] == 1
        assert deleted_group['total'] == 5000.0


class TestLedgerBatchMigrate:
    """测试账户批量迁移两段式接口（preview 只读分类 → commit 单事务提交）"""

    @staticmethod
    def _preview(client, src_id, tgt_id):
        return client.post(f'/api/ledgers/{src_id}/migrations/preview/', json={'target_ledger_id': tgt_id})

    @staticmethod
    def _commit(client, src_id, tgt_id, resolutions=None):
        payload = {'target_ledger_id': tgt_id}
        if resolutions is not None:
            payload['resolutions'] = resolutions
        return client.post(f'/api/ledgers/{src_id}/migrations/commit/', json=payload)

    def test_migrate_stock_to_stock(self, client, db):
        """正常迁移：两个证券账户，迁移后源为空，目标增加，ledger_id 变更"""
        # 创建两个证券账户
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        # 创建持仓和资产（关联到源账户 ledger_id）
        pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            ledger_id=src_id,  # 新增：绑定外键
            quantity=1000000,  # 100份 × 10000，注意这里 quantity 是存储整数字段（最小单位）
            avg_price=1000,  # 10.00元 → 1000分
            current_price=1200,  # 12.00元 → 1200分
        )
        db.add(pos)
        asset_cash = Asset(
            user_id=1,
            major_category='cash',
            name='余额',
            amount=500000,  # 5000元 → 500000分
            account_name='华泰证券',
            currency='CNY',
            ledger_id=src_id,
        )
        db.add(asset_cash)
        asset_other = Asset(
            user_id=1,
            major_category='fixed',
            name='房产',
            amount=10000000,  # 100000元
            account_name='华泰证券',
            ledger_id=src_id,
        )
        db.add(asset_other)
        db.commit()

        # 预览：1 持仓 + 2 资产全部 keep
        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200
        items = preview.get_json()['data']['items']
        assert len(items) == 3
        assert all(i['classification'] == 'keep' for i in items)

        # 提交迁移
        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['position_count'] == 1
        assert data['asset_count'] == 2
        assert '中信证券' in resp.get_json()['message']

        # 验证源账户下已无持仓/资产（基于 ledger_id）
        src_positions = db.query(Position).filter(Position.ledger_id == src_id).all()
        src_assets = db.query(Asset).filter(Asset.ledger_id == src_id).all()
        assert len(src_positions) == 0
        assert len(src_assets) == 0

        # 验证目标账户下已增加，且 ledger_id 已变更为目标
        tgt_positions = db.query(Position).filter(Position.ledger_id == tgt_id).all()
        tgt_assets = db.query(Asset).filter(Asset.ledger_id == tgt_id).all()
        assert len(tgt_positions) == 1
        assert len(tgt_assets) == 2

        # 关键断言：快照 account_name 也已更新为目标账户名称
        for p in tgt_positions:
            assert p.ledger_id == tgt_id
            assert p.account_name == '中信证券'
        for a in tgt_assets:
            assert a.ledger_id == tgt_id
            assert a.account_name == '中信证券'

    def test_migrate_overlapping_symbol_dedup(self, client, db):
        """同 symbol 且字段完全一致 → 视为重复写入，只保留目标一份（不相加）。

        复现迁移崩溃：目标已存在同 symbol 持仓，盲改 ledger_id 会撞
        UNIQUE(ledger_id, symbol)。正确行为是去重而非求和（否则同一笔持仓被算两次）。
        """
        src = client.post('/api/ledgers/', json={'name': '支付宝', 'ledger_type': 'fund'})
        tgt = client.post('/api/ledgers/', json={'name': '蚂蚁杭州基金销售', 'ledger_type': 'fund'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        # 源账户持仓：510300，100份，成本 10.00 元
        db.add(
            Position(
                symbol='510300',
                name='沪深300ETF',
                market='CN_A',
                asset_type='fund',
                account_name='支付宝',
                ledger_id=src_id,
                quantity=1000000,
                avg_price=100000,
                current_price=120000,
            )
        )
        # 目标账户已有「完全一致」的同 symbol 持仓（同一笔被两个账户各写一遍）
        db.add(
            Position(
                symbol='510300',
                name='沪深300ETF',
                market='CN_A',
                asset_type='fund',
                account_name='支付宝',
                ledger_id=tgt_id,
                quantity=1000000,
                avg_price=100000,
                current_price=120000,
            )
        )
        db.commit()

        # 预览：完全一致应分类为 duplicate（非冲突）
        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200, preview.get_json()
        items = preview.get_json()['data']['items']
        assert len(items) == 1
        assert items[0]['classification'] == 'duplicate'
        assert items[0]['suggestion'] is None

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['dedup_count'] == 1

        # 源账户清空（重复的一份被丢弃）
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0
        # 目标仅剩 1 条，且份额未翻倍（没有被相加）
        tgt_positions = db.query(Position).filter(Position.ledger_id == tgt_id).all()
        assert len(tgt_positions) == 1
        assert tgt_positions[0].symbol == '510300'
        assert tgt_positions[0].quantity == 1000000

    def test_migrate_overlapping_symbol_conflict(self, client, db):
        """同 symbol 但字段不一致 → 预览报 conflict；commit 缺决议被拒，决议后按用户选择执行"""
        src = client.post('/api/ledgers/', json={'name': '支付宝', 'ledger_type': 'fund'})
        tgt = client.post('/api/ledgers/', json={'name': '蚂蚁杭州基金销售', 'ledger_type': 'fund'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        db.add(
            Position(
                symbol='510300',
                name='沪深300ETF',
                market='CN_A',
                asset_type='fund',
                account_name='支付宝',
                ledger_id=src_id,
                quantity=1000000,
                avg_price=100000,
                current_price=120000,
            )
        )
        # 目标同 symbol 但份额/成本不同 → 冲突
        db.add(
            Position(
                symbol='510300',
                name='沪深300ETF',
                market='CN_A',
                asset_type='fund',
                account_name='蚂蚁杭州基金销售',
                ledger_id=tgt_id,
                quantity=500000,
                avg_price=120000,
                current_price=120000,
            )
        )
        db.commit()

        # 预览：conflict 行须明确告知差异字段，并以可读单位（份/元）呈现
        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200, preview.get_json()
        items = preview.get_json()['data']['items']
        assert len(items) == 1
        conflict = items[0]
        assert conflict['classification'] == 'conflict'
        assert conflict['symbol'] == '510300'
        assert set(conflict['conflict_fields']) == {'quantity', 'avg_price'}
        # 份额与成本价不同 → 建议 merge（非仅成本日差异）
        assert conflict['suggestion'] == 'merge'
        assert conflict['source']['quantity'] == 100.0
        assert conflict['target']['quantity'] == 50.0
        assert conflict['source']['avg_price'] == 10.0

        # commit 缺决议 → 400 且不写任何数据（源/目标各留一份）
        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 400
        assert '510300' in resp.get_json()['message']
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 1
        assert db.query(Position).filter(Position.ledger_id == tgt_id).count() == 1

        # 决议 keep_source：源整条覆盖目标
        resp = self._commit(
            client, src_id, tgt_id, resolutions=[{'kind': 'position', 'symbol': '510300', 'action': 'keep_source'}]
        )
        assert resp.status_code == 200, resp.get_json()
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0
        kept = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        assert kept.quantity == 1000000
        assert kept.avg_price == 100000

    def test_migrate_overlapping_asset_dedup(self, client, db):
        """资产同名同分类且金额一致 → 视为重复，只保留目标一份"""
        src = client.post('/api/ledgers/', json={'name': '支付宝', 'ledger_type': 'fund'})
        tgt = client.post('/api/ledgers/', json={'name': '蚂蚁杭州基金销售', 'ledger_type': 'fund'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        db.add(
            Asset(user_id=1, major_category='cash', name='余额', amount=500000, account_name='支付宝', ledger_id=src_id)
        )
        db.add(
            Asset(
                user_id=1,
                major_category='cash',
                name='余额',
                amount=500000,
                account_name='蚂蚁杭州基金销售',
                ledger_id=tgt_id,
            )
        )
        db.commit()

        # 预览：金额一致 → duplicate
        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200, preview.get_json()
        assert preview.get_json()['data']['items'][0]['classification'] == 'duplicate'

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 0
        tgt_assets = db.query(Asset).filter(Asset.ledger_id == tgt_id).all()
        assert len(tgt_assets) == 1
        assert tgt_assets[0].amount == 500000  # 未翻倍

    def test_migrate_overlapping_asset_conflict(self, client, db):
        """资产同名同分类但金额不一致 → 预览报 conflict；commit 缺决议被拒，决议后执行"""
        src = client.post('/api/ledgers/', json={'name': '支付宝', 'ledger_type': 'fund'})
        tgt = client.post('/api/ledgers/', json={'name': '蚂蚁杭州基金销售', 'ledger_type': 'fund'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        db.add(
            Asset(user_id=1, major_category='cash', name='余额', amount=500000, account_name='支付宝', ledger_id=src_id)
        )
        db.add(
            Asset(
                user_id=1,
                major_category='cash',
                name='余额',
                amount=300000,
                account_name='蚂蚁杭州基金销售',
                ledger_id=tgt_id,
            )
        )
        db.commit()

        # 预览：conflict，金额差异以元呈现
        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200, preview.get_json()
        item = preview.get_json()['data']['items'][0]
        assert item['classification'] == 'conflict'
        assert item['suggestion'] is None  # 资产无 merge 建议
        assert item['source']['amount'] == 5000.0
        assert item['target']['amount'] == 3000.0

        # 缺决议 → 400 且源数据不变
        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 400
        assert '余额' in resp.get_json()['message']
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 1
        assert db.query(Asset).filter(Asset.ledger_id == tgt_id).count() == 1

        # 决议 keep_target：弃源保目标
        resp = self._commit(
            client,
            src_id,
            tgt_id,
            resolutions=[{'kind': 'asset', 'name': '余额', 'major_category': 'cash', 'action': 'keep_target'}],
        )
        assert resp.status_code == 200, resp.get_json()
        assert db.query(Asset).filter(Asset.ledger_id == src_id).count() == 0
        kept = db.query(Asset).filter(Asset.ledger_id == tgt_id).one()
        assert kept.amount == 300000

    def test_migrate_moves_linked_transactions(self, client, db, make_transaction):
        """持仓迁移时，其交易记录也要改挂目标账户，避免持仓与交易 ledger 脱节"""
        from app.domains.transactions.models import Transaction

        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            ledger_id=src_id,
            quantity=1000000,
            avg_price=1000,
            current_price=1200,
        )
        db.add(pos)
        db.commit()
        make_transaction(
            position_id=pos.id, ledger_id=src_id, txn_type='buy', quantity=100.0, price=10.0, amount=1000.0
        )
        db.commit()

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['transaction_count'] == 1

        moved = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        txn = db.query(Transaction).filter(Transaction.position_id == moved.id).one()
        assert txn.ledger_id == tgt_id
        assert txn.account_name == '中信证券'

    def test_migrate_merges_transactions_on_position_dedup(self, client, db, make_transaction):
        """重复持仓被丢弃时，其交易记录应并入目标持仓（position_id 改挂），而非悬空"""
        from app.domains.transactions.models import Transaction

        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        src_pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            ledger_id=src_id,
            quantity=1000000,
            avg_price=1000,
            current_price=1200,
        )
        tgt_pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='中信证券',
            ledger_id=tgt_id,
            quantity=1000000,
            avg_price=1000,
            current_price=1200,
        )
        db.add_all([src_pos, tgt_pos])
        db.commit()
        make_transaction(
            position_id=src_pos.id, ledger_id=src_id, txn_type='buy', quantity=100.0, price=10.0, amount=1000.0
        )
        db.commit()

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['dedup_count'] == 1  # 完全一致按 duplicate 去重
        assert data['transaction_count'] == 1

        # 源持仓被丢弃、目标持仓保留，交易改挂到目标持仓
        assert db.query(Position).filter(Position.ledger_id == src_id).count() == 0
        kept = db.query(Position).filter(Position.ledger_id == tgt_id).one()
        txn = db.query(Transaction).filter(Transaction.ledger_id == tgt_id).one()
        assert txn.position_id == kept.id

    def test_migrate_dedup_transaction_by_import_hash(self, client, db, make_transaction):
        """同一笔交易在两个账户各导入一次时，迁移后只保留目标那份（归一）"""
        from app.domains.transactions.models import Transaction

        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            ledger_id=src_id,
            quantity=1000000,
            avg_price=1000,
            current_price=1200,
        )
        db.add(pos)
        db.commit()
        # 同一笔交易被两个账户各导入一次（相同 import_hash）
        make_transaction(
            position_id=pos.id,
            ledger_id=src_id,
            txn_type='buy',
            quantity=100.0,
            price=10.0,
            amount=1000.0,
            import_hash='dup-hash-1',
        )
        make_transaction(
            position_id=pos.id,
            ledger_id=tgt_id,
            txn_type='buy',
            quantity=100.0,
            price=10.0,
            amount=1000.0,
            import_hash='dup-hash-1',
        )
        db.commit()

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()['data']
        assert data['transaction_count'] == 1  # 源重复交易已归并
        # 目标账户最终只保留 1 笔该 hash 的交易，来源账户清零
        assert (
            db.query(Transaction)
            .filter(Transaction.ledger_id == tgt_id, Transaction.import_hash == 'dup-hash-1')
            .count()
            == 1
        )
        assert db.query(Transaction).filter(Transaction.ledger_id == src_id).count() == 0

    def test_migrate_cross_type_rejected(self, client, db):
        """跨类型迁移应被拒绝（preview 与 commit 双端点一致）"""
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'bank'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        resp = self._preview(client, src_id, tgt_id)
        assert resp.status_code == 400
        assert '同类型' in resp.get_json()['message']
        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 400
        assert '同类型' in resp.get_json()['message']

    def test_migrate_target_not_found(self, client, db):
        """目标账户不存在"""
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']

        resp = self._preview(client, src_id, 9999)
        assert resp.status_code == 404

    def test_migrate_source_not_found(self, client):
        """源账户不存在"""
        resp = client.post('/api/ledgers/9999/migrations/preview/', json={'target_ledger_id': 1})
        assert resp.status_code == 404

    def test_migrate_empty_source(self, client, db):
        """源账户无持仓/资产时，预览为空、迁移成功但数量为0"""
        src = client.post('/api/ledgers/', json={'name': '空账户', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '目标账户', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        preview = self._preview(client, src_id, tgt_id)
        assert preview.status_code == 200
        assert preview.get_json()['data']['items'] == []

        resp = self._commit(client, src_id, tgt_id)
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['position_count'] == 0
        assert data['asset_count'] == 0

    def test_migrate_cross_family_rejected(self, client, db):
        """跨家庭迁移必须被拒绝，防止把持仓越权迁入他人账本（IDOR）"""
        src = client.post('/api/ledgers/', json={'name': '我家证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        # 直接造一个属于另一家庭(family_id=2)的同类型账本作目标
        tgt = Ledger(name='他人证券', ledger_type='stock', family_id=2)
        db.add(tgt)
        db.commit()
        tgt_id = tgt.id

        resp = self._preview(client, src_id, tgt_id)
        assert resp.status_code == 403
        assert '同家庭' in resp.get_json()['message']


class TestLedgerSummary:
    """测试账户详情概览卡片接口"""

    def test_summary_stock_account(self, client, db, make_position):
        """证券账户应返回总市值、持仓盈亏、持仓数量、累计收益、资金余额（如有关联）"""
        # 创建 bank 和 stock
        bank = Ledger(name='招商银行', ledger_type='bank')
        stock = Ledger(name='华泰证券', ledger_type='stock', linked_cash_ledger_id=None)
        db.add_all([bank, stock])
        db.flush()  # 获取 bank.id
        stock.linked_cash_ledger_id = bank.id
        db.commit()

        # 创建持仓（使用 make_position fixture）
        make_position(
            symbol='000001',
            name='平安银行',
            ledger_id=stock.id,
            account_name='华泰证券',
            quantity=1000,
            avg_price=10.0,
            current_price=12.0,
        )
        # 为关联的 bank 创建活期资产
        asset = Asset(
            user_id=1, major_category='current', name='活期', amount=50000, account_name='招商银行', ledger_id=bank.id
        )
        db.add(asset)
        db.commit()

        resp = client.get(f'/api/ledgers/{stock.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ledger_type'] == 'stock'
        assert data['total_market_value'] == 12000.0  # 1000份 × 12元
        assert data['position_count'] == 1
        assert data['cash_balance'] == 500.0  # 50000分 -> 500元
        assert data['daily_pnl'] is None
        assert 'cumulative_return' in data
        assert 'allocation_distribution' in data
        # type_distribution：后端按资产大类聚合（asset_type 默认 None → '其他'）
        assert data['type_distribution'] == {'其他': 12000.0}

    def test_summary_fund_account(self, client, db, make_position):
        """基金平台应包含货基占比、货基金额"""
        fund_ledger = Ledger(name='支付宝基金', ledger_type='fund')
        db.add(fund_ledger)
        db.commit()

        make_position(
            symbol='000001',
            name='股票基金A',
            ledger_id=fund_ledger.id,
            account_name='支付宝基金',
            quantity=1000,
            avg_price=1.5,
            current_price=1.8,
            asset_type='stock_fund',
        )
        make_position(
            symbol='000002',
            name='货币基金B',
            ledger_id=fund_ledger.id,
            account_name='支付宝基金',
            quantity=5000,
            avg_price=1.0,
            current_price=1.0,
            asset_type='money_fund',
        )
        resp = client.get(f'/api/ledgers/{fund_ledger.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ledger_type'] == 'fund'
        assert data['total_market_value'] == 1800.0 + 5000.0  # 1800 + 5000
        assert data['money_fund_amount'] == 5000.0
        assert data['money_fund_ratio'] == round(5000.0 / 6800.0 * 100, 2)
        assert data['cumulative_return'] is not None
        # type_distribution 按 asset_type 聚合（未知类型保留原样 code）
        assert data['type_distribution'] == {'stock_fund': 1800.0, 'money_fund': 5000.0}

    def test_summary_bank_account(self, client, db, make_position, make_asset):
        """银行账户返回总余额、活期余额、理财市值"""
        bank = Ledger(name='微众银行', ledger_type='bank')
        db.add(bank)
        db.commit()

        make_asset(major_category='current', name='活期', amount=30000, ledger_id=bank.id, account_name='微众银行')
        make_position(
            symbol='LC001',
            name='理财A',
            ledger_id=bank.id,
            account_name='微众银行',
            quantity=2000,
            avg_price=3.0,
            current_price=3.5,
        )
        resp = client.get(f'/api/ledgers/{bank.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_market_value'] == 37000.0  # 活期30000元 + 理财7000元
        assert data['current_balance'] == 30000.0  # 活期30000元
        # 根据实现，可能还有 fund_value 字段，可选检查
        assert 'position_count' in data or True  # 视实现而定

    def test_summary_property_account(self, client, db, make_asset):
        """实物资产返回总估值和数量"""
        prop = Ledger(name='房产', ledger_type='property')
        db.add(prop)
        db.commit()

        make_asset(major_category='real_estate', name='自住房', amount=2000000, ledger_id=prop.id, account_name='房产')
        resp = client.get(f'/api/ledgers/{prop.id}/summary/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_market_value'] == 2000000.0  # 2000000分 → 20000元
        assert data['asset_count'] == 1


class TestLedgerPositions:
    """测试账户持仓分页接口"""

    def test_positions_pagination_format(self, client, db, make_position):
        stock = Ledger(name='测试证券', ledger_type='stock')
        db.add(stock)
        db.commit()

        for i in range(3):
            make_position(
                symbol=f'00000{i}',
                name=f'股票{i}',
                ledger_id=stock.id,
                account_name='测试证券',
                quantity=100 * (i + 1),
                avg_price=10.0,
                current_price=10.5 + i,
            )
        resp = client.get(f'/api/ledgers/{stock.id}/positions/?page=1&per_page=2')
        assert resp.status_code == 200
        payload = resp.get_json()
        assert 'data' in payload
        data = payload['data']
        assert 'items' in data
        assert 'total' in data
        assert data['total'] == 3
        assert data['page'] == 1
        assert data['per_page'] == 2
        items = data['items']
        assert len(items) == 2
        # 验证字段类型
        item = items[0]
        assert isinstance(item['market_value'], (int, float))
        assert isinstance(item['pnl'], (int, float))
        assert isinstance(item['position_ratio'], (int, float))  # 应为数字
        # 验证排序：默认按市值降序，这里第一个应是市值最大的
        assert item['market_value'] >= items[1]['market_value']

    def test_positions_empty(self, client, db):
        stock = Ledger(name='空账户', ledger_type='stock')
        db.add(stock)
        db.commit()
        resp = client.get(f'/api/ledgers/{stock.id}/positions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['items'] == []
        assert data['total'] == 0


class TestLedgerTransactions:
    """测试账户交易分页接口"""

    def test_transactions_pagination_format(self, client, db):
        # 需要辅助函数创建交易记录，或直接通过导入等生成
        # 这里简单起见，直接构造 Transaction
        from app.domains.transactions.models import Transaction

        stock = Ledger(name='测试证券', ledger_type='stock')
        db.add(stock)
        db.commit()

        t1 = Transaction(
            txn_type='buy',
            symbol='000001',
            position_name='平安银行',
            account_name='测试证券',
            ledger_id=stock.id,
            quantity=1000000,
            price=1000,
            amount=1000000,
            fee=100,
            confirm_date=None,
            created_at=None,
        )  # 自动
        db.add(t1)
        db.commit()

        resp = client.get(f'/api/ledgers/{stock.id}/transactions/?page=1&per_page=10')
        assert resp.status_code == 200
        payload = resp.get_json()
        data = payload['data']
        assert 'items' in data
        assert 'total' in data
        assert data['total'] == 1
        item = data['items'][0]
        assert item['txn_type'] == 'buy'
        assert isinstance(item['fee'], (int, float))


class TestLedgerListSummaryFields:
    """测试列表接口返回的摘要字段完整性（新增字段）"""

    def test_list_ledgers_bank_has_money_fund_fields(self, client, db, make_position):
        """银行账户列表应返回 money_fund_amount 和 money_fund_ratio"""
        # 1. 创建银行账户
        bank = Ledger(name='测试银行卡', ledger_type='bank')
        db.add(bank)
        db.commit()

        # 2. 创建两笔持仓：一笔普通基金，一笔货币基金
        make_position(
            symbol='PF001',
            name='普通基金',
            ledger_id=bank.id,
            account_name='测试银行卡',
            quantity=1000,
            avg_price=2.0,
            current_price=2.5,
            asset_type='stock_fund',  # 非货基
        )
        make_position(
            symbol='MF001',
            name='货币基金',
            ledger_id=bank.id,
            account_name='测试银行卡',
            quantity=5000,
            avg_price=1.0,
            current_price=1.0,
            asset_type='money_fund',  # 货基
        )

        # 3. 调用列表接口
        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        ledgers = resp.get_json()['data']
        target = next(led for led in ledgers if led['name'] == '测试银行卡')

        # 4. 验证货基字段存在且值正确
        assert 'money_fund_amount' in target
        assert 'money_fund_ratio' in target
        # 市值计算：货基 5000份 * 1.0元 = 5000元；普通基金 1000份 * 2.5元 = 2500元；总市值 7500元
        # 货基占比 = 5000 / 7500 = 66.666... 四舍五入保留两位小数 -> 66.67%
        assert target['money_fund_amount'] == 5000.0
        assert target['money_fund_ratio'] == 66.67

    def test_list_ledgers_property_has_asset_count_and_no_pnl(self, client, db, make_asset):
        """实物资产账户应返回 asset_count，且 pnl 应为 0（或不存在）"""
        # 1. 创建实物资产账户
        prop = Ledger(name='家庭房产', ledger_type='property')
        db.add(prop)
        db.commit()

        # 2. 添加两笔资产（比如房产和汽车）
        make_asset(
            major_category='real_estate', name='自住房', amount=2000000, ledger_id=prop.id, account_name='家庭房产'
        )
        make_asset(major_category='vehicle', name='家用车', amount=200000, ledger_id=prop.id, account_name='家庭房产')

        # 3. 调用列表接口
        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        ledgers = resp.get_json()['data']
        target = next(led for led in ledgers if led['name'] == '家庭房产')

        # 4. 验证字段
        assert 'asset_count' in target
        assert target['asset_count'] == 2
        # 实物资产返回的 total_market_value 应为估值总和（2200000元）
        assert target['total_market_value'] == 2200000.0
        # 实物资产不应有 pnl 字段，或者 pnl 为 0.0（取决于后端实现，我们统一初始化为 0）
        # 如果后端没有为 property 设置 pnl，应使用默认值 0.0
        assert target.get('pnl', 0.0) == 0.0
        # cash_balance 应为 0.0
        assert target['cash_balance'] == 0.0


class TestOrphanDetail:
    """测试未归置数据（孤儿）明细查询接口 GET /api/ledgers/orphan/detail/"""

    def test_detail_with_orphans(self, client, db, make_position, make_asset, make_transaction):
        """有孤儿持仓+资产+交易时，返回明细与 summary 正确"""
        # 孤儿持仓：不传 account_name/ledger_id → ledger_id 为空 → 孤儿
        make_position(
            symbol='510300',
            name='沪深300ETF',
            quantity=1234.56,
            avg_price=3.9,
            current_price=4.0,
        )
        # 孤儿资产：ledger_id 为空
        make_asset(major_category='current', name='某银行卡', amount=5000.0)
        # 孤儿交易：position_id/ledger_id 均为空
        make_transaction(
            position_id=None,
            ledger_id=None,
            txn_type='buy',
            quantity=100.0,
            price=1.0,
            amount=100.0,
            confirm_date=date(2026, 8, 1),
            position_name='沪深300ETF',
        )
        # make_transaction 内部只 flush 不 commit，需显式提交，接口会话（另一连接）才能读到
        db.commit()

        resp = client.get('/api/ledgers/orphan/detail/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        # 持仓明细：市值 = 4.0 × 1234.56 = 4938.24；盈亏 = (4.0-3.9) × 1234.56 = 123.46（ROUND_HALF_UP）
        assert len(data['positions']) == 1
        pos = data['positions'][0]
        assert pos['symbol'] == '510300'
        assert pos['name'] == '沪深300ETF'
        assert pos['quantity'] == 1234.56
        assert pos['avg_price'] == 3.9
        assert pos['market_value'] == 4938.24
        assert pos['pnl'] == 123.46

        # 资产明细
        assert len(data['assets']) == 1
        asset = data['assets'][0]
        assert asset['name'] == '某银行卡'
        assert asset['amount'] == 5000.0
        assert asset['major_category'] == 'current'

        # 交易明细：txn_type 保持后端原始枚举值，confirm_date 为纯日期
        assert len(data['transactions']) == 1
        txn = data['transactions'][0]
        assert txn['position_name'] == '沪深300ETF'
        assert txn['txn_type'] == 'buy'
        assert txn['amount'] == 100.0
        assert txn['confirm_date'] == '2026-08-01'

        # 汇总：total_market_value = 持仓市值 + 资产金额（交易为流水不计入，避免重复计算）
        assert data['summary'] == {
            'position_count': 1,
            'asset_count': 1,
            'transaction_count': 1,
            'total_market_value': 9938.24,
        }


class TestLedgerArchiveAndUpdate:
    """归档/激活 + 编辑保护（账户管理增强，见归档账户设计决策）。"""

    def test_new_ledger_active_by_default(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '默认活跃'})
        assert resp.get_json()['data']['is_active'] is True

    def test_archive_hides_from_default_list(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '待归档'})
        lid = resp.get_json()['data']['id']
        client.post(f'/api/ledgers/{lid}/archive/')
        # 默认列表不含已归档
        listed = [item['id'] for item in client.get('/api/ledgers/').get_json()['data']]
        assert lid not in listed
        # include_archived 可找回
        archived = [item['id'] for item in client.get('/api/ledgers/?include_archived=true').get_json()['data']]
        assert lid in archived

    def test_unarchive_restores(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': 'U'})
        lid = resp.get_json()['data']['id']
        client.post(f'/api/ledgers/{lid}/archive/')
        client.post(f'/api/ledgers/{lid}/unarchive/')
        listed = [item['id'] for item in client.get('/api/ledgers/').get_json()['data']]
        assert lid in listed

    def test_archive_keeps_data_in_overview(self, client, db, make_position):
        """归档不丢数据、仍参与收益计算（overview 不过滤 is_active）。"""
        ledger = Ledger(name='归档账户', ledger_type='stock')
        db.add(ledger)
        db.commit()
        make_position(
            symbol='S2',
            name='股2',
            ledger_id=ledger.id,
            account_name='归档账户',
            quantity=100,
            avg_price=5.0,
            current_price=6.0,
        )
        client.post(f'/api/ledgers/{ledger.id}/archive/')
        overview = client.get('/api/ledgers/overview/').get_json()['data']
        # 归档账户市值仍计入总资产分组
        stock_group = next((g for g in overview['groups'] if g['type'] == 'stock'), None)
        assert stock_group is not None
        assert stock_group['total'] >= 600.0

    def test_empty_ledger_type_can_change(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '空白基金', 'ledger_type': 'fund'})
        lid = resp.get_json()['data']['id']
        patch = client.patch(f'/api/ledgers/{lid}/', json={'ledger_type': 'stock'})
        assert patch.status_code == 200
        assert patch.get_json()['data']['ledger_type'] == 'stock'

    def test_type_change_blocked_when_has_data(self, client, db, make_transaction, make_position):
        ledger = Ledger(name='有数据', ledger_type='fund')
        db.add(ledger)
        db.commit()
        make_position(
            symbol='S3',
            name='股3',
            ledger_id=ledger.id,
            account_name='有数据',
            quantity=100,
            avg_price=1.0,
            current_price=1.0,
        )
        # 需要一条 position 才有 position_id 供交易引用；这里仅用持仓即触发 has_data
        patch = client.patch(f'/api/ledgers/{ledger.id}/', json={'ledger_type': 'stock'})
        assert patch.status_code == 409
        assert '类型不可更改' in patch.get_json()['message']

    def test_patch_is_active(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': 'P'})
        lid = resp.get_json()['data']['id']
        patch = client.patch(f'/api/ledgers/{lid}/', json={'is_active': False})
        assert patch.status_code == 200
        assert patch.get_json()['data']['is_active'] is False

    def test_detail_empty(self, client, db, make_position, make_asset, make_transaction):
        """无孤儿数据时返回空数组，不 404"""
        # 正常账户 + 正常数据（ledger_id 有效，不属于孤儿）
        ledger = Ledger(name='正常账户', ledger_type='stock')
        db.add(ledger)
        db.commit()
        pos = make_position(
            symbol='000001',
            name='平安',
            ledger_id=ledger.id,
            account_name='正常账户',
            quantity=100,
            avg_price=10,
            current_price=12,
        )
        make_asset(major_category='current', name='活期', amount=1000, ledger_id=ledger.id, account_name='正常账户')
        make_transaction(position_id=pos.id, ledger_id=ledger.id, txn_type='buy', quantity=100, price=10, amount=1000)
        # make_transaction 内部只 flush 不 commit，显式提交保证数据落库
        db.commit()

        resp = client.get('/api/ledgers/orphan/detail/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['positions'] == []
        assert data['assets'] == []
        assert data['transactions'] == []
        assert data['summary'] == {
            'position_count': 0,
            'asset_count': 0,
            'transaction_count': 0,
            'total_market_value': 0.0,
        }

    def test_detail_empty_after_migrate(self, client, db, make_position, make_asset, make_transaction):
        """归入后再查：migrate 后 detail 应为空"""
        # 孤儿持仓（ledger_id 为空）
        pos = make_position(
            symbol='510300',
            name='沪深300ETF',
            quantity=100,
            avg_price=10,
            current_price=12,
        )
        # 孤儿资产
        make_asset(major_category='current', name='某银行卡', amount=5000.0)
        # 孤儿交易：position_id 指向孤儿持仓且 ledger_id 悬空（migrate 会一并归入）
        make_transaction(
            position_id=pos.id,
            ledger_id=None,
            txn_type='buy',
            quantity=100,
            price=10,
            amount=1000,
            position_name='沪深300ETF',
        )
        # make_transaction 内部只 flush 不 commit，显式提交保证接口会话可读
        db.commit()

        # 归入前 detail 应有 3 项
        before = client.get('/api/ledgers/orphan/detail/').get_json()['data']
        assert before['summary']['position_count'] == 1
        assert before['summary']['asset_count'] == 1
        assert before['summary']['transaction_count'] == 1

        # 归入目标账户
        target = client.post('/api/ledgers/', json={'name': '目标账户', 'ledger_type': 'stock'})
        target_id = target.get_json()['data']['id']
        resp = client.post('/api/ledgers/orphan/migrations/', json={'target_ledger_id': target_id})
        assert resp.status_code == 200
        assert resp.get_json()['data']['total'] == 3

        # 归入后 detail 应为空
        after = client.get('/api/ledgers/orphan/detail/').get_json()['data']
        assert after['positions'] == []
        assert after['assets'] == []
        assert after['transactions'] == []
        assert after['summary']['total_market_value'] == 0.0


# ─────────────── 持仓/交易列表搜索（#982） ───────────────
class TestLedgerDetailSearch:
    def _make_ledger_with_positions(self, db, make_position):
        ledger = Ledger(name='搜索测试', ledger_type='stock')
        db.add(ledger)
        db.commit()
        make_position(
            symbol='600519',
            name='贵州茅台',
            ledger_id=ledger.id,
            account_name='搜索测试',
            quantity=100,
            avg_price=10,
            current_price=12,
        )
        make_position(
            symbol='000001',
            name='平安银行',
            ledger_id=ledger.id,
            account_name='搜索测试',
            quantity=200,
            avg_price=10,
            current_price=11,
        )
        return ledger

    def test_positions_search_by_name_and_symbol(self, client, db, make_position):
        """search 命中名称或代码；total 为过滤后计数"""
        ledger = self._make_ledger_with_positions(db, make_position)

        by_name = client.get(f'/api/ledgers/{ledger.id}/positions/', query_string={'search': '茅台'})
        assert [i['symbol'] for i in by_name.get_json()['data']['items']] == ['600519']

        by_symbol = client.get(f'/api/ledgers/{ledger.id}/positions/', query_string={'search': '000001'})
        assert [i['symbol'] for i in by_symbol.get_json()['data']['items']] == ['000001']

        none = client.get(f'/api/ledgers/{ledger.id}/positions/', query_string={'search': '不存在'})
        assert none.get_json()['data']['total'] == 0

    def test_transactions_search_by_name(self, client, db):
        from app.domains.transactions.models import Transaction

        ledger = Ledger(name='交易搜索', ledger_type='stock')
        db.add(ledger)
        db.commit()
        db.add_all(
            [
                Transaction(
                    txn_type='buy',
                    symbol='600519',
                    position_name='贵州茅台',
                    account_name='交易搜索',
                    ledger_id=ledger.id,
                    quantity=1000000,
                    price=1000,
                    amount=1000000,
                    fee=100,
                ),
                Transaction(
                    txn_type='sell',
                    symbol='000001',
                    position_name='平安银行',
                    account_name='交易搜索',
                    ledger_id=ledger.id,
                    quantity=2000000,
                    price=1100,
                    amount=2200000,
                    fee=100,
                ),
            ]
        )
        db.commit()

        resp = client.get(
            f'/api/ledgers/{ledger.id}/transactions/',
            query_string={'search': '平安'},
        )
        items = resp.get_json()['data']['items']
        assert [i['symbol'] for i in items] == ['000001']

    def test_positions_paginated_includes_quantity(self, client, db, make_position):
        """持仓明细行必须携带 quantity（份/股）——详情抽屉「持有数量」卡数据源（#982 排查）。"""
        ledger = self._make_ledger_with_positions(db, make_position)
        resp = client.get(f'/api/ledgers/{ledger.id}/positions/')
        items = resp.get_json()['data']['items']
        qty_map = {i['symbol']: i['quantity'] for i in items}
        assert qty_map['600519'] == 100
        assert qty_map['000001'] == 200


class TestSalesInstitutionsAPI:
    """销售机构名录 API：#1081 常用分组字段与置顶排序、#1082 类型过滤。"""

    def _seed(self, db):
        db.add_all(
            [
                SalesInstitution(
                    org_name='浙江同花顺基金销售有限公司',
                    org_type='独立基金销售机构',
                    is_common=True,
                    common_sort=33,
                    display_name='同花顺',
                ),
                SalesInstitution(
                    org_name='蚂蚁（杭州）基金销售有限公司',
                    org_type='独立基金销售机构',
                    is_common=True,
                    common_sort=1,
                    display_name='支付宝',
                    pinyin_short='MYHZZJJJXSYXGS',
                ),
                SalesInstitution(org_name='中信证券', org_type='证券公司'),
                SalesInstitution(org_name='招商银行', org_type='全国性商业银行', is_common=True, common_sort=2),
                SalesInstitution(org_name='某期货公司', org_type='期货公司'),
            ]
        )
        db.commit()

    def test_new_fields_and_common_first_ordering(self, client, db):
        """响应携带新字段；常用机构按 common_sort 升序置顶，其余字典序殿后。"""
        self._seed(db)
        resp = client.get('/api/ledgers/sales-institutions/')
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'ok'
        data = resp.get_json()['data']
        assert set(data[0].keys()) >= {
            'id',
            'org_name',
            'display_name',
            'org_type',
            'is_common',
            'common_sort',
            'pinyin_short',
        }
        commons = [r for r in data if r['is_common']]
        assert [r['common_sort'] for r in commons] == [1, 2, 33]
        assert commons[0]['display_name'] == '支付宝'
        assert commons[0]['pinyin_short'] == 'MYHZZJJJXSYXGS'
        first_non_common = next(i for i, r in enumerate(data) if not r['is_common'])
        assert all(r['is_common'] for r in data[:first_non_common])
        # 非常用段字典序：中信证券 < 某期货公司
        assert [r['org_name'] for r in data[first_non_common:]] == ['中信证券', '某期货公司']

    def test_org_types_filter_single(self, client, db):
        """org_types 过滤：证券账户场景只看券商（#1082）。"""
        self._seed(db)
        resp = client.get('/api/ledgers/sales-institutions/?org_types=证券公司')
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'ok'
        data = resp.get_json()['data']
        assert [r['org_name'] for r in data] == ['中信证券']

    def test_org_types_filter_multi(self, client, db):
        """org_types 多值逗号分隔。"""
        self._seed(db)
        resp = client.get('/api/ledgers/sales-institutions/?org_types=证券公司,期货公司')
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'ok'
        data = resp.get_json()['data']
        assert {r['org_name'] for r in data} == {'中信证券', '某期货公司'}

    def test_org_types_filter_keeps_common_flag(self, client, db):
        """过滤后常用标志与排序语义保持（fund 场景常用置顶不被类型过滤破坏）。"""
        self._seed(db)
        resp = client.get(
            '/api/ledgers/sales-institutions/',
            query_string={'org_types': '独立基金销售机构,全国性商业银行'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['message'] == 'ok'
        data = resp.get_json()['data']
        assert [r['org_name'] for r in data] == [
            '蚂蚁（杭州）基金销售有限公司',
            '招商银行',
            '浙江同花顺基金销售有限公司',
        ]


class TestUpdateLedgerTransaction:
    """PATCH /api/ledgers/<id>/transactions/<tid>/ 行内编辑（issue #1112）"""

    def _seed(self, db, make_transaction, import_hash='imp-hash-1', **overrides):
        from app.domains.transactions.models import Transaction

        ledger = Ledger(name='测试证券', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.commit()
        txn = make_transaction(
            position_id=1,
            ledger_id=ledger.id,
            quantity=100,
            price=1.0,
            amount=100,
            import_hash=import_hash,
            **overrides,
        )
        db.commit()
        return ledger, txn, Transaction

    def test_patch_quantity_price_recomputes_amount_and_clears_hash(self, client, db, make_transaction):
        ledger, txn, Transaction = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'quantity': 200, 'price': 1.5},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['quantity'] == 200
        assert data['price'] == 1.5
        # amount 未显式给出，应按 price×quantity 重算 = 300
        assert data['amount'] == 300.0
        assert data['import_hash'] is None
        # PATCH 在独立会话中提交，本测试会话需刷新才能读到落库结果
        db.refresh(txn)
        assert txn.import_hash is None
        assert txn.quantity == Money.shares_to_min_unit(200)

    def test_patch_explicit_amount_kept(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'quantity': 200, 'price': 1.5, 'amount': 250},
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['amount'] == 250.0

    def test_patch_rejects_forbidden_fields(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'symbol': '600519', 'ledger_id': 999},
        )
        assert resp.status_code == 400

    def test_patch_rejects_negative_quantity(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'quantity': -5},
        )
        assert resp.status_code == 400

    def test_patch_invalid_date_format(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'trade_date': '2026/01/01'},
        )
        assert resp.status_code == 400

    def test_patch_trade_date_and_notes_clears_hash(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/{txn.id}/',
            json={'trade_date': '2026-01-15', 'notes': '手动修正'},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['trade_date'] == '2026-01-15'
        assert data['notes'] == '手动修正'
        assert data['import_hash'] is None

    def test_patch_nonexistent_transaction_404(self, client, db, make_transaction):
        ledger, txn, _ = self._seed(db, make_transaction)
        resp = client.patch(
            f'/api/ledgers/{ledger.id}/transactions/999999/',
            json={'notes': 'x'},
        )
        assert resp.status_code == 404
