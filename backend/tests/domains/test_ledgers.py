# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 11:02
# File : test_ledgers.py
"""测试资金容器 CRUD"""

import pytest

from app.domains.assets.models import Asset
from app.domains.positions.models import Position


@pytest.fixture(autouse=True)
def debug_routes(app):
    """打印所有已注册的 positions 和 assets 路由，用于排查 404"""
    print('\n===== 已注册的路由（positions / assets / ledgers）=====')
    for rule in app.url_map.iter_rules():
        if any(x in rule.rule for x in ['positions', 'assets', 'ledgers']):
            print(f'  {rule.methods} -> {rule.rule}')
    print('======================================================\n')
    yield


class TestLedgerCRUD:
    def test_create_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['ledger_type'] == 'general'

    def test_list_ledgers(self, client, db):
        client.post('/api/ledgers/', json={'name': 'L1'})
        client.post('/api/ledgers/', json={'name': 'L2'})
        resp = client.get('/api/ledgers/')
        assert resp.status_code == 200
        assert len(resp.get_json()['data']) >= 2

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
