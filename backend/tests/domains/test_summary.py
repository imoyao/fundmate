# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 22:01
# File : test_summary.py
# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11
# File : test_summary.py

from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from tests.domains.test_positions import _post


def test_summary_empty(client):
    """无持仓和资产时总资产为0"""
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']
    assert data['total_assets_cny'] == 0
    assert data['total_pnl_cny'] == 0
    assert data['total_liabilities_cny'] == 0
    assert data['net_assets_cny'] == 0


def test_summary_with_positions_and_liabilities(client):
    """持仓、现金资产和负债的汇总计算"""
    # 1. 创建港股持仓：100股腾讯，成本350 HKD，当前价同成本，盈亏为0
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    # 2. 创建现金资产：10万人民币
    cash_resp = client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期存款', 'amount': 100000})
    assert cash_resp.status_code == 200

    # 3. 创建负债：信用卡欠款5000元（正数表示负债金额）
    liability_resp = client.post('/api/assets/', json={'major_category': 'liability', 'name': '信用卡', 'amount': 5000})
    assert liability_resp.status_code == 200

    # 4. 获取汇总
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']

    # 预期计算：
    # 持仓市值：100 * 350 * 0.92(HKD→CNY) = 32200
    # 现金：100000
    # 总资产 = 32200 + 100000 = 132200
    # 负债 = 5000
    # 净资产 = 132200 - 5000 = 127200
    # 盈亏：持仓现价等于成本，为0
    assert data['total_assets_cny'] == 132200.0
    assert data['total_liabilities_cny'] == 5000.0
    assert data['net_assets_cny'] == 127200.0
    assert data['total_pnl_cny'] == 0.0
    # 验证市场分布（至少包含港股）
    assert 'CN_HK' in data['market_distribution']


def test_summary_with_pnl_and_multi_currency(client):
    """不同货币持仓的盈亏与资产汇总"""
    # 港股持仓：100股腾讯，成本350，现价400，盈利
    _post(
        client,
        '/api/positions',
        {
            'symbol': '00700.HK',
            'name': '腾讯',
            'type': 'stock',
            'market': 'CN_HK',
            'account_name': '富途',
            'quantity': 100,
            'avg_price': 350,
            'currency': 'HKD',
            'purchase_date': '2026-05-01',
        },
    )
    # 更新市价为400（通过 PATCH 接口）
    list_resp = client.get('/api/positions/')
    positions = list_resp.get_json()['data']
    tencent = [p for p in positions if p['name'] == '腾讯'][0]
    client.patch(f'/api/positions/{tencent["id"]}', json={'current_price': 400.0})

    # 美股持仓：10股苹果，成本180 USD，现价200 USD
    _post(
        client,
        '/api/positions',
        {
            'symbol': 'AAPL',
            'name': '苹果',
            'type': 'stock',
            'market': 'US',
            'account_name': '富途',
            'quantity': 10,
            'avg_price': 180,
            'currency': 'USD',
            'purchase_date': '2026-05-01',
        },
    )
    # 查找苹果持仓（因 symbol 可能被标准化，按名称查找更可靠）
    list_resp2 = client.get('/api/positions/')
    positions2 = list_resp2.get_json()['data']
    apple = [p for p in positions2 if p['name'] == '苹果'][0]
    client.patch(f'/api/positions/{apple["id"]}', json={'current_price': 200.0})

    # 汇总
    resp = client.get('/api/summary/')
    data = resp.get_json()['data']

    # 计算：
    # 腾讯市值：100 * 400 * 0.92 = 36800  盈亏：(400-350)*100*0.92 = 4600
    # 苹果市值：10 * 200 * 7.25 = 14500   盈亏：(200-180)*10*7.25 = 1450
    # 总资产 = 36800 + 14500 = 51300
    # 总盈亏 = 4600 + 1450 = 6050
    assert data['total_assets_cny'] == 51300.0
    assert data['total_pnl_cny'] == 6050.0
    assert len(data['market_distribution']) == 2


class TestSankeyEndpoint:
    """桑基图端点测试套件"""

    def test_empty_data_returns_empty(self, client):
        """空数据库返回空 nodes 和 links，不报错"""
        resp = client.get('/api/summary/sankey/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['nodes'] == []
        assert data['links'] == []

    def test_only_positions_no_assets(self, client, db):
        """仅有持仓数据时，负债分支消失，其他流向正常"""
        pos = Position(
            symbol='SH600519',
            name='贵州茅台',
            market='SH',
            asset_type='stock',
            quantity=100,
            avg_price=1600.0,
            current_price=1800.0,
            currency='CNY',
            allocation='longterm',
        )
        db.add(pos)
        db.commit()

        resp = client.get('/api/summary/sankey/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        nodes = {n['name'] for n in data['nodes']}
        links = {(link['source'], link['target']) for link in data['links']}

        # 核心节点（资产大类、总资产、净资产、五笔钱、产品类型）
        assert '投资理财' in nodes
        assert '总资产' in nodes
        assert '净资产' in nodes
        assert '长期增值' in nodes
        assert '股票' in nodes  # 翻译为中文
        assert '负债' not in nodes
        assert '总负债' not in nodes

        # 链路验证
        assert ('投资理财', '总资产') in links
        assert ('总资产', '净资产') in links
        assert ('净资产', '长期增值') in links
        assert ('长期增值', '股票') in links

    def test_only_assets_no_positions(self, client, db):
        """仅有通用资产数据，投资理财分支消失，负债分支正常"""
        house = Asset(user_id=1, major_category='fixed', name='阳光花园', amount=5_000_000, currency='CNY')
        credit = Asset(user_id=1, major_category='liability', name='招商银行信用卡', amount=5000, currency='CNY')
        db.add_all([house, credit])
        db.commit()

        resp = client.get('/api/summary/sankey/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        nodes = {n['name'] for n in data['nodes']}
        links = {(link['source'], link['target']) for link in data['links']}

        # 资产大类节点（不再有具体资产名）
        assert '固定资产' in nodes
        assert '总资产' in nodes
        assert '净资产' in nodes
        # 负债明细节点仍然存在
        assert '总负债' in nodes
        assert '招商银行信用卡' in nodes

        # 链路
        assert ('固定资产', '总资产') in links
        assert ('总资产', '净资产') in links
        assert ('总资产', '总负债') in links
        assert ('总负债', '招商银行信用卡') in links

    def test_full_data_with_allocation(self, client, db):
        """完整的混合数据，验证五笔钱分流和产品类型展开"""
        stock = Position(
            symbol='SH600519',
            name='茅台',
            market='SH',
            asset_type='stock',
            quantity=50,
            avg_price=1600,
            current_price=1800,
            currency='CNY',
            allocation='longterm',
        )
        fund = Position(
            symbol='000001',
            name='某基金',
            market='SZ',
            asset_type='fund',
            quantity=1000,
            avg_price=1.5,
            current_price=1.8,
            currency='CNY',
            allocation='stable',
        )
        db.add_all([stock, fund])

        cash = Asset(user_id=1, major_category='cash', name='活期存款', amount=200_000, currency='CNY')
        mortgage = Asset(user_id=1, major_category='liability', name='房屋贷款', amount=100_000, currency='CNY')
        db.add_all([cash, mortgage])
        db.commit()

        resp = client.get('/api/summary/sankey/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        nodes = {n['name'] for n in data['nodes']}
        links = {(link['source'], link['target']) for link in data['links']}

        # 资产大类（不再有“活期存款”节点）
        assert '流动资金' in nodes
        assert '投资理财' in nodes
        assert '总资产' in nodes
        assert '净资产' in nodes
        assert '总负债' in nodes
        assert '房屋贷款' in nodes  # 负债明细仍存在
        assert '长期增值' in nodes
        assert '稳健底仓' in nodes
        assert '股票' in nodes
        assert '基金' in nodes

        # 链路
        assert ('流动资金', '总资产') in links
        assert ('投资理财', '总资产') in links
        assert ('总资产', '净资产') in links
        assert ('总资产', '总负债') in links
        assert ('总负债', '房屋贷款') in links
        assert ('净资产', '长期增值') in links
        assert ('净资产', '稳健底仓') in links
        assert ('长期增值', '股票') in links
        assert ('稳健底仓', '基金') in links

    def test_currency_conversion(self, client, db):
        """外币持仓正确换算为 CNY，验证汇率生效"""
        pos = Position(
            symbol='HK00700',
            name='腾讯控股',
            market='HK',
            asset_type='stock',
            quantity=100,
            avg_price=300,
            current_price=350,
            currency='HKD',
        )
        db.add(pos)
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']

        # 市值 = 100 * 350 * 0.92 = 32200.0，应体现在 投资理财 → 总资产 的链接中
        invest_link = next(
            link for link in data['links'] if link['source'] == '投资理财' and link['target'] == '总资产'
        )
        assert invest_link['value'] == 32200.0

    def test_node_deduplication(self, client, db):
        """重复节点名称不重复添加"""
        p1 = Position(symbol='A', name='股A', asset_type='stock', quantity=1, current_price=10)
        p2 = Position(symbol='B', name='股B', asset_type='stock', quantity=1, current_price=20)
        db.add_all([p1, p2])
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']

        # '股票' 节点应仅出现一次
        stock_nodes = [n for n in data['nodes'] if n['name'] == '股票']
        assert len(stock_nodes) == 1

    def test_aggregation_by_category(self, client, db):
        """同一大类多条资产正确聚合"""
        # 两条流动资金
        a1 = Asset(user_id=1, major_category='cash', name='银行卡A', amount=10000, currency='CNY')
        a2 = Asset(user_id=1, major_category='cash', name='银行卡B', amount=20000, currency='CNY')
        db.add_all([a1, a2])
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']

        # 流动资金 → 总资产 的链接值应为 30000
        cat_link = next(link for link in data['links'] if link['source'] == '流动资金' and link['target'] == '总资产')
        assert cat_link['value'] == 30000.0

    def test_liabilities_isolated_from_net_worth(self, client, db):
        """负债不影响净资产流向五笔钱"""
        # 持仓
        pos = Position(
            symbol='SH600519',
            name='茅台',
            market='SH',
            asset_type='stock',
            quantity=10,
            avg_price=1000,
            current_price=2000,
            currency='CNY',
            allocation='speculative',
        )
        db.add(pos)
        # 负债
        liability = Asset(user_id=1, major_category='liability', name='花呗', amount=5000, currency='CNY')
        db.add(liability)
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']

        # 净资产流向高风险博弈的金额 = 持仓市值（20000），而非减去负债
        alloc_link = next(
            link for link in data['links'] if link['source'] == '净资产' and link['target'] == '高风险博弈'
        )
        assert alloc_link['value'] == 20000.0

    def test_zero_value_assets_ignored(self, client, db):
        """金额为 0 的资产不参与桑基图"""
        zero_asset = Asset(user_id=1, major_category='cash', name='空账户', amount=0, currency='CNY')
        db.add(zero_asset)
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']
        node_names = [n['name'] for n in data['nodes']]
        assert '空账户' not in node_names
