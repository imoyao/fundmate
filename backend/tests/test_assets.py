# backend/tests/test_assets.py
"""测试通用资产 CRUD 及标签字段"""


class TestAssetCRUD:
    """基本 CRUD 测试"""

    def test_create_asset(self, client):
        resp = client.post(
            '/api/assets/', json={'major_category': 'cash', 'name': '活期存款', 'amount': 50000, 'currency': 'CNY'}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '活期存款'
        assert data['amount'] == 50000

    def test_create_asset_with_allocation(self, client):
        """创建带配置目标的资产，应返回对应的中文标签"""
        resp = client.post(
            '/api/assets/', json={'major_category': 'cash', 'name': '货币基金', 'amount': 30000, 'allocation': 'stable'}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['name'] == '货币基金'
        assert data['allocation'] == 'stable'
        assert data['allocation_label'] == '稳健底仓'

    def test_create_asset_without_allocation(self, client):
        """不传配置目标时应默认 longterm 或返回标签"""
        resp = client.post('/api/assets/', json={'major_category': 'fixed', 'name': '房产', 'amount': 2000000})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # 后端可能默认 'longterm'，标签应存在
        assert 'allocation_label' in data
        assert data['allocation_label'] is not None

    def test_list_assets(self, client):
        client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期', 'amount': 10000})
        client.post('/api/assets/', json={'major_category': 'fixed', 'name': '房产', 'amount': 3000000})
        resp = client.get('/api/assets/')
        data = resp.get_json()['data']
        assert len(data) >= 2

    def test_list_assets_contains_labels(self, client):
        """列表接口应返回 type_label、allocation_label 和 signed_amount"""
        client.post('/api/assets/', json={'major_category': 'liability', 'name': '房贷', 'amount': 500000})
        resp = client.get('/api/assets/')
        data = resp.get_json()['data']
        for asset in data:
            assert 'type_label' in asset
            assert asset['type_label'] is not None
            assert 'allocation_label' in asset
            assert 'signed_amount' in asset
            if asset['major_category'] == 'liability':
                assert asset['signed_amount'] < 0

    def test_filter_assets_by_major_category(self, client, db):
        """按大类筛选资产"""
        # amount 必须 > 0，负债也传正数（Schema 要求 >0）
        resp1 = client.post(
            '/api/assets/',
            json={
                'major_category': 'liability',
                'name': '信用卡',
                'amount': 5000,  # 改为正数
                'account_name': '招商银行',
                'currency': 'CNY',
            },
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            '/api/assets/',
            json={
                'major_category': 'cash',
                'name': '活期',
                'amount': 2000,
                'account_name': '招商银行',
            },
        )
        assert resp2.status_code == 200

        # 按大类筛选
        resp = client.get('/api/assets/?major_category=liability')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) >= 1
        assert all(a['major_category'] == 'liability' for a in data)
        # 确认 signed_amount 存在且负债为负
        for a in data:
            assert 'signed_amount' in a
            assert a['signed_amount'] == -a['amount']
            # 验证负债的 type_label
            assert a.get('type_label') is not None


class TestAssetUpdate:
    """更新操作测试"""

    def test_update_asset_amount(self, client):
        """更新资产金额（注意尾部斜杠）"""
        resp = client.post(
            '/api/assets/',
            json={
                'major_category': 'cash',
                'name': '零钱',
                'amount': 2000,
                'account_name': '招商银行',
            },
        )
        asset_id = resp.get_json()['data']['id']

        # PATCH 必须带尾部斜杠
        patch_resp = client.patch(
            f'/api/assets/{asset_id}/',
            json={'amount': 3000},
        )
        assert patch_resp.status_code == 200
        data = patch_resp.get_json()['data']
        assert data['amount'] == 3000
        # 更新后 signed_amount 也应同步
        assert data['signed_amount'] == 3000
        # 标签应保留
        assert 'type_label' in data
        assert 'allocation_label' in data

    def test_update_asset_allocation(self, client):
        """更新配置目标，标签应同步变化"""
        resp = client.post(
            '/api/assets/', json={'major_category': 'cash', 'name': '备用金', 'amount': 10000, 'allocation': 'liquid'}
        )
        asset_id = resp.get_json()['data']['id']

        patch_resp = client.patch(f'/api/assets/{asset_id}/', json={'allocation': 'speculative'})
        assert patch_resp.status_code == 200
        data = patch_resp.get_json()['data']
        assert data['allocation'] == 'speculative'
        assert data['allocation_label'] == '高风险博弈'

    def test_delete_asset(self, client):
        """删除资产（注意尾部斜杠）"""
        resp = client.post(
            '/api/assets/',
            json={
                'major_category': 'cash',
                'name': '删除测试',
                'amount': 1,
                'account_name': '测试',
            },
        )
        asset_id = resp.get_json()['data']['id']

        del_resp = client.delete(f'/api/assets/{asset_id}/')
        assert del_resp.status_code == 200


class TestAssetValidation:
    """边界验证测试"""

    def test_create_asset_zero_amount(self, client):
        """金额为 0 应被后端拒绝"""
        resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '零钱', 'amount': 0})
        assert resp.status_code == 422

    def test_create_asset_negative_amount(self, client):
        """金额为负应被拒绝"""
        resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '测试', 'amount': -100})
        assert resp.status_code == 422

    def test_create_asset_missing_fields(self, client):
        """缺少必填字段应返回 422"""
        resp = client.post('/api/assets/', json={'name': '缺少分类'})
        assert resp.status_code == 422
