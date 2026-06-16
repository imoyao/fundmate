# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 11:02
# File : test_ledgers.py
"""测试资金容器 CRUD"""

from datetime import date

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position


class TestLedgerCRUD:
    def test_create_ledger(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '华泰证券'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '华泰证券'
        assert data['ledger_type'] == 'stock'

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


class TestLedgerLinkedCash:
    """测试关联现金账户"""

    def test_create_stock_with_valid_cash_ledger(self, client, db):
        """证券账户关联有效的现金账户"""
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
        cash_id = cash_resp.get_json()['data']['id']
        resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': cash_id}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['linked_cash_ledger_id'] == cash_id

    def test_create_fund_with_valid_cash_ledger(self, client, db):
        """基金平台关联有效的现金账户"""
        cash_resp = client.post('/api/ledgers/', json={'name': '余额宝', 'ledger_type': 'cash'})
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
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
        cash_id = cash_resp.get_json()['data']['id']
        resp = client.post(
            '/api/ledgers/', json={'name': '另一个现金', 'ledger_type': 'cash', 'linked_cash_ledger_id': cash_id}
        )
        assert resp.status_code == 400
        assert '只有证券账户或基金平台' in resp.get_json()['message']

    def test_update_ledger_link_cash(self, client, db):
        """更新账户关联现金账户"""
        # 创建现金账户和证券账户
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
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
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
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
        cash_resp = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
        cash_id = cash_resp.get_json()['data']['id']
        stock_resp = client.post(
            '/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock', 'linked_cash_ledger_id': cash_id}
        )
        stock_id = stock_resp.get_json()['data']['id']

        # 直接修改类型为 cash，同时不传 linked_cash_ledger_id
        resp = client.patch(f'/api/ledgers/{stock_id}/', json={'ledger_type': 'cash'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['ledger_type'] == 'cash'
        # 注意：当前后端在修改类型时不会自动清空关联，但前端会在切换时清空并传递 null。
        # 为保险，可以在测试中显式传递 null，我们额外测一次。
        # 如果只改类型而不传 linked_cash_ledger_id，字段保持不变（设计如此），所以本测试仅验证状态。
        # 可补充一个用例：同时传递 ledger_type 和 linked_cash_ledger_id=null。
        resp2 = client.patch(f'/api/ledgers/{stock_id}/', json={'ledger_type': 'cash', 'linked_cash_ledger_id': None})
        assert resp2.status_code == 200
        assert resp2.get_json()['data']['linked_cash_ledger_id'] is None


class TestLedgerOverview:
    """测试账户资金全景接口"""

    def test_overview_empty(self, client):
        """无账户时应返回空结构"""
        resp = client.get('/api/ledgers/overview/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'groups' in data
        assert data['liability_total'] == 0
        assert data['net_worth'] == 0

    def test_overview_with_accounts_and_positions(self, client, db):
        """有账户和持仓时，应正确汇总"""
        # 创建账户
        cash = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
        cash_id = cash.get_json()['data']['id']
        stock = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        stock_id = stock.get_json()['data']['id']

        # 创建持仓（关联到证券账户）
        pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            quantity=Money.shares_to_min_unit(1000),
            avg_price=Money.yuan_to_cents(10.0),
            current_price=Money.yuan_to_cents(12.0),
            confirm_date=date.today(),
        )
        db.add(pos)
        # 创建现金持仓（通过资产表）
        asset_cash = Asset(
            user_id=1,
            major_category='cash',
            name='储蓄',
            amount=Money.yuan_to_cents(50000),
            account_name='招商银行',
            currency='CNY',
        )
        db.add(asset_cash)
        # 负债
        asset_liability = Asset(
            user_id=1,
            major_category='liability',
            name='房贷',
            amount=Money.yuan_to_cents(300000),
            account_name='招商银行',
            currency='CNY',
        )
        db.add(asset_liability)
        db.commit()

        resp = client.get('/api/ledgers/overview/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        groups = {g['type']: g for g in data['groups']}
        # 证券账户：1个，市值 1000*12=12000
        stock_group = groups.get('stock')
        assert stock_group is not None
        assert stock_group['count'] == 1
        assert stock_group['total'] == 12000
        # 现金账户：1个，市值 50000
        cash_group = groups.get('cash')
        assert cash_group is not None
        assert cash_group['count'] == 1
        assert cash_group['total'] == 50000
        # 负债总额 300000
        assert data['liability_total'] == 300000
        # 净资产 = (12000+50000) - 300000 = -238000
        assert data['net_worth'] == -238000

    def test_overview_with_deleted_account(self, client, db):
        """已删除账户的持仓应出现在 'deleted' 分组"""
        # 创建账户
        resp = client.post('/api/ledgers/', json={'name': '已删证券', 'ledger_type': 'stock'})
        lid = resp.get_json()['data']['id']
        # 创建持仓关联到该账户名
        pos = Position(
            symbol='000002',
            name='万科',
            market='CN_A',
            asset_type='stock',
            account_name='已删证券',
            quantity=Money.shares_to_min_unit(500),
            avg_price=Money.yuan_to_cents(8.0),
            current_price=Money.yuan_to_cents(10.0),
        )
        db.add(pos)
        db.commit()
        # 绕过 API 保护，直接通过 ORM 删除账户（模拟手动删除）
        ledger = db.query(Ledger).get(lid)
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
    """测试账户持仓批量迁移"""

    def test_migrate_stock_to_stock(self, client, db):
        """正常迁移：两个证券账户，迁移后源为空，目标增加"""
        # 创建两个证券账户
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '中信证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        # 创建持仓和资产（关联到源账户）
        pos = Position(
            symbol='000001',
            name='平安银行',
            market='CN_A',
            asset_type='stock',
            account_name='华泰证券',
            quantity=1000,
            avg_price=10,
            current_price=12,
        )
        db.add(pos)
        asset_cash = Asset(
            user_id=1, major_category='cash', name='余额', amount=5000, account_name='华泰证券', currency='CNY'
        )
        db.add(asset_cash)
        # 另一个资产（非负债）
        asset_other = Asset(user_id=1, major_category='fixed', name='房产', amount=100000, account_name='华泰证券')
        db.add(asset_other)
        db.commit()

        # 执行迁移
        resp = client.post(f'/api/ledgers/{src_id}/migrations/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total'] == 3  # 1 position + 2 assets
        assert '中信证券' in resp.get_json()['message']

        # 验证源账户下已无持仓/资产
        src_positions = db.query(Position).filter(Position.account_name == '华泰证券').all()
        src_assets = db.query(Asset).filter(Asset.account_name == '华泰证券').all()
        assert len(src_positions) == 0
        assert len(src_assets) == 0

        # 验证目标账户下已增加
        tgt_positions = db.query(Position).filter(Position.account_name == '中信证券').all()
        tgt_assets = db.query(Asset).filter(Asset.account_name == '中信证券').all()
        assert len(tgt_positions) == 1
        assert len(tgt_assets) == 2

    def test_migrate_cross_type_rejected(self, client, db):
        """跨类型迁移应被拒绝"""
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '招商银行', 'ledger_type': 'cash'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        resp = client.post(f'/api/ledgers/{src_id}/migrations/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 400
        assert '同类型' in resp.get_json()['message']

    def test_migrate_target_not_found(self, client, db):
        """目标账户不存在"""
        src = client.post('/api/ledgers/', json={'name': '华泰证券', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']

        resp = client.post(f'/api/ledgers/{src_id}/migrations/', json={'target_ledger_id': 9999})
        assert resp.status_code == 404

    def test_migrate_source_not_found(self, client):
        """源账户不存在"""
        resp = client.post('/api/ledgers/9999/migrations/', json={'target_ledger_id': 1})
        assert resp.status_code == 404

    def test_migrate_empty_source(self, client, db):
        """源账户无持仓/资产时，迁移成功但数量为0"""
        src = client.post('/api/ledgers/', json={'name': '空账户', 'ledger_type': 'stock'})
        tgt = client.post('/api/ledgers/', json={'name': '目标账户', 'ledger_type': 'stock'})
        src_id = src.get_json()['data']['id']
        tgt_id = tgt.get_json()['data']['id']

        resp = client.post(f'/api/ledgers/{src_id}/migrations/', json={'target_ledger_id': tgt_id})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total'] == 0
