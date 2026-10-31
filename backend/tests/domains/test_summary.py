# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 22:01
# File : test_summary.py

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.domains.summary.models import AssetSnapshot
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
    # 更新市价为400（通过 PATCH 接口）
    list_resp = client.get('/api/positions/')
    positions = list_resp.get_json()['data']
    tencent = [p for p in positions if p['name'] == '腾讯'][0]
    client.patch(f'/api/positions/{tencent["id"]}/', json={'current_price': 400.0})

    # 美股持仓：10股苹果，成本180 USD，现价200 USD
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
    # 查找苹果持仓（因 symbol 可能被标准化，按名称查找更可靠）
    list_resp2 = client.get('/api/positions/')
    positions2 = list_resp2.get_json()['data']
    apple = [p for p in positions2 if p['name'] == '苹果'][0]
    client.patch(f'/api/positions/{apple["id"]}/', json={'current_price': 200.0})

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
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(1600.0),
            current_price=Money.yuan_to_price_units(1800.0),
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
        house = Asset(
            user_id=1, major_category='fixed', name='阳光花园', amount=Money.yuan_to_cents(5_000_000), currency='CNY'
        )
        credit = Asset(
            user_id=1,
            major_category='liability',
            name='招商银行信用卡',
            amount=Money.yuan_to_cents(5000),
            currency='CNY',
        )
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
            quantity=Money.shares_to_min_unit(50),
            avg_price=Money.yuan_to_price_units(1600),
            current_price=Money.yuan_to_price_units(1800),
            currency='CNY',
            allocation='longterm',
        )
        fund = Position(
            symbol='000001',
            name='某基金',
            market='SZ',
            asset_type='fund',
            quantity=Money.shares_to_min_unit(1000),
            avg_price=Money.yuan_to_price_units(1.5),
            current_price=Money.yuan_to_price_units(1.8),
            currency='CNY',
            allocation='stable',
        )
        db.add_all([stock, fund])

        cash = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=Money.yuan_to_cents(200_000), currency='CNY'
        )
        mortgage = Asset(
            user_id=1, major_category='liability', name='房屋贷款', amount=Money.yuan_to_cents(100_000), currency='CNY'
        )
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
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(300),
            current_price=Money.yuan_to_price_units(350),
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
        p1 = Position(
            symbol='A',
            name='股A',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(1),
            current_price=Money.yuan_to_price_units(10),
        )
        p2 = Position(
            symbol='B',
            name='股B',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(1),
            current_price=Money.yuan_to_price_units(20),
        )
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
        a1 = Asset(user_id=1, major_category='cash', name='银行卡A', amount=Money.yuan_to_cents(10000), currency='CNY')
        a2 = Asset(user_id=1, major_category='cash', name='银行卡B', amount=Money.yuan_to_cents(20000), currency='CNY')
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
            quantity=Money.shares_to_min_unit(10),
            avg_price=Money.yuan_to_price_units(1000),
            current_price=Money.yuan_to_price_units(2000),
            currency='CNY',
            allocation='speculative',
        )
        db.add(pos)
        # 负债
        liability = Asset(
            user_id=1, major_category='liability', name='花呗', amount=Money.yuan_to_cents(5000), currency='CNY'
        )
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
        zero_asset = Asset(
            user_id=1, major_category='cash', name='空账户', amount=Money.yuan_to_cents(0), currency='CNY'
        )
        db.add(zero_asset)
        db.commit()

        resp = client.get('/api/summary/sankey/')
        data = resp.get_json()['data']
        node_names = [n['name'] for n in data['nodes']]
        assert '空账户' not in node_names


class TestDistributionsEndpoint:
    """分布聚合接口 /api/summary/distributions/ 测试套件（批次 2）"""

    def test_empty_data(self, client):
        """无持仓与资产时所有分布为空、汇总为 0"""
        resp = client.get('/api/summary/distributions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['type_distribution'] == []
        assert data['allocation_distribution'] == []
        assert data['market_distribution'] == []
        assert data['account_distribution'] == []
        assert data['category_distribution'] == []
        assert data['total_assets'] == 0
        assert data['total_liabilities'] == 0
        assert data['net_worth'] == 0
        assert data['positions_total_mv'] == 0

    def test_mixed_data(self, client, db):
        """持仓（含外币汇率换算）+ 现金资产 + 负债的分布聚合"""
        pos = Position(
            symbol='HK00700',
            name='腾讯控股',
            market='CN_HK',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(300),
            current_price=Money.yuan_to_price_units(350),
            currency='HKD',
            allocation='longterm',
            account_name='富途',
        )
        db.add(pos)
        cash = Asset(
            user_id=1, major_category='cash', name='活期存款', amount=Money.yuan_to_cents(100000), currency='CNY'
        )
        credit = Asset(
            user_id=1, major_category='liability', name='信用卡', amount=Money.yuan_to_cents(5000), currency='CNY'
        )
        db.add_all([cash, credit])
        db.commit()

        resp = client.get('/api/summary/distributions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        # 持仓市值：100 * 350 * 0.92 = 32200
        assert data['positions_total_mv'] == 32200.0
        # 总资产 = 32200 + 100000；负债 5000；净资产 = 总资产 - 负债
        assert data['total_assets'] == 132200.0
        assert data['total_liabilities'] == 5000.0
        assert data['net_worth'] == 127200.0

        def _find(dist, name):
            return next((d['value'] for d in dist if d['name'] == name), None)

        # 持仓四维分布
        assert _find(data['type_distribution'], '股票') == 32200.0
        assert _find(data['allocation_distribution'], '长期增值') == 32200.0
        assert _find(data['market_distribution'], '港股') == 32200.0
        assert _find(data['account_distribution'], '富途') == 32200.0
        # 大类分布：现金入流动资金，持仓归投资理财；负债不入大类分布
        assert _find(data['category_distribution'], '流动资金') == 100000.0
        assert _find(data['category_distribution'], '投资理财') == 32200.0
        assert _find(data['category_distribution'], '负债') is None
        # 负债明细单独列出（正数）
        assert _find(data['liability_distribution'], '信用卡') == 5000.0

    def test_single_market_still_multi_category(self, client, db):
        """同一回归锚点：全持仓同市场时，资产大类仍须多档（#1955）。

        背景：首页环形图曾消费 `summary.market_distribution`（按持仓 `market`
        分组）。本机实测 154 笔持仓全为 `CN_A` → 只回一个扇区，环上画成整圈
        单色，首页表现为「一个完整的红色圆环」，看起来像没取到数。
        本测试锁定服务端行为：`category_distribution` 与市场数无关，
        大类维度上必须能出多档，且各项之和等于 `total_assets`。
        """
        # 两笔同市场（CN_A）持仓 + 一笔现金资产 + 一笔固定资产
        db.add_all(
            [
                Position(
                    symbol='SH600519',
                    name='茅台',
                    market='CN_A',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(100),
                    current_price=Money.yuan_to_price_units(1000),
                    currency='CNY',
                ),
                Position(
                    symbol='SH601318',
                    name='平安',
                    market='CN_A',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(100),
                    current_price=Money.yuan_to_price_units(500),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='cash',
                    name='活期存款',
                    amount=Money.yuan_to_cents(80000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='fixed',
                    name='自住房',
                    amount=Money.yuan_to_cents(2000000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        resp = client.get('/api/summary/distributions/')
        data = resp.get_json()['data']

        # 前提成立：市场维度确实只有一档（这正是旧实现的坑）
        assert len(data['market_distribution']) == 1

        # 但大类维度必须多档
        assert len(data['category_distribution']) >= 3

        def _find(dist, name):
            return next((d['value'] for d in dist if d['name'] == name), None)

        assert _find(data['category_distribution'], '固定资产') == 2000000.0
        assert _find(data['category_distribution'], '流动资金') == 80000.0
        assert _find(data['category_distribution'], '投资理财') == 150000.0

        # 口径闭合：各大类之和 === total_assets（与首页「家庭总资产」对得上）
        total = sum(d['value'] for d in data['category_distribution'])
        assert total == data['total_assets']

    def test_distribution_sorted_desc(self, client, db):
        """分布按市值降序返回，便于前端直接取最大项"""
        p1 = Position(
            symbol='SH600519',
            name='茅台',
            market='CN_A',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(100),
            current_price=Money.yuan_to_price_units(1000),
            currency='CNY',
        )
        p2 = Position(
            symbol='SH601318',
            name='平安',
            market='CN_A',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(100),
            current_price=Money.yuan_to_price_units(500),
            currency='CNY',
        )
        db.add_all([p1, p2])
        db.commit()

        resp = client.get('/api/summary/distributions/')
        data = resp.get_json()['data']
        account_values = [d['value'] for d in data['account_distribution']]
        assert account_values == sorted(account_values, reverse=True)


class TestPositionGroupsEndpoint:
    """维度分组接口 /api/summary/groups/ 测试套件（批次 2b）"""

    def _make_pos(self, db, **kwargs):
        defaults = dict(
            symbol='SH600519',
            name='茅台',
            market='CN_A',
            asset_type='stock',
            quantity=Money.shares_to_min_unit(100),
            avg_price=Money.yuan_to_price_units(900),
            current_price=Money.yuan_to_price_units(1000),
            currency='CNY',
            allocation='longterm',
            account_name='华泰',
        )
        defaults.update(kwargs)
        pos = Position(**defaults)
        db.add(pos)
        return pos

    def test_empty_data(self, client):
        resp = client.get('/api/summary/groups/?dimension=type')
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_unsupported_dimension(self, client):
        resp = client.get('/api/summary/groups/?dimension=foo')
        assert resp.status_code == 400

    def test_type_groups_with_pnl_and_currency(self, client, db):
        """产品类型分组：汇率换算 + 盈亏 + 明细字段"""
        self._make_pos(
            db,
            symbol='HK00700',
            name='腾讯',
            asset_type='stock',
            market='CN_HK',
            quantity=Money.shares_to_min_unit(100),
            current_price=Money.yuan_to_price_units(350),
            avg_price=Money.yuan_to_price_units(300),
            currency='HKD',
            account_name='富途',
        )
        self._make_pos(
            db,
            symbol='000001',
            name='某基金',
            asset_type='fund',
            quantity=Money.shares_to_min_unit(1000),
            current_price=Money.yuan_to_price_units(1.8),
            avg_price=Money.yuan_to_price_units(1.5),
        )
        db.commit()

        resp = client.get('/api/summary/groups/?dimension=type')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert [g['name'] for g in data] == ['股票', '基金']
        stock = next(g for g in data if g['name'] == '股票')
        # 腾讯市值 100*350*0.92 = 32200，盈亏 (350-300)*100*0.92 = 4600
        assert stock['total'] == 32200.0
        assert stock['total_pnl'] == 4600.0
        assert stock['count'] == 1
        assert len(stock['items']) == 1
        item = stock['items'][0]
        assert item['name'] == '腾讯'
        assert item['type_label'] == '股票'
        assert item['market_label'] == '港股'
        assert item['market_value'] == 32200.0
        assert item['pnl'] == 4600.0

    def test_account_groups_mix_positions_and_assets(self, client, db):
        """账户分组混合持仓与非负债通用资产；负债不计入"""
        self._make_pos(db, name='茅台', account_name='华泰')
        cash = Asset(
            user_id=1,
            major_category='cash',
            name='活期存款',
            amount=Money.yuan_to_cents(100000),
            currency='CNY',
            account_name='华泰',
        )
        credit = Asset(
            user_id=1,
            major_category='liability',
            name='信用卡',
            amount=Money.yuan_to_cents(5000),
            currency='CNY',
            account_name='华泰',
        )
        db.add_all([cash, credit])
        db.commit()

        resp = client.get('/api/summary/groups/?dimension=account')
        data = resp.get_json()['data']
        assert len(data) == 1
        acc = data[0]
        assert acc['name'] == '华泰'
        # 茅台 100*1000 + 现金 100000 = 200000，负债不计入
        assert acc['total'] == 200000.0
        assert acc['count'] == 2
        assert acc['total_pnl'] == (1000 - 900) * 100

    def test_allocation_groups(self, client, db):
        """配置目标分组；缺省 allocation 被模型 default 兜底为 longterm"""
        self._make_pos(db, allocation='longterm')
        self._make_pos(db, symbol='B', name='货基', asset_type='fund', allocation=None)
        self._make_pos(db, symbol='C', name='博弈', allocation='speculative')
        db.commit()

        resp = client.get('/api/summary/groups/?dimension=allocation')
        data = resp.get_json()['data']
        names = {g['name'] for g in data}
        assert names == {'长期增值', '高风险博弈'}
        longterm = next(g for g in data if g['name'] == '长期增值')
        # allocation=None 被列 default 兜底为 longterm，与持仓 A 同组
        assert longterm['count'] == 2

    def test_groups_sorted_desc(self, client, db):
        """分组按 total 降序"""
        self._make_pos(db, name='小', quantity=Money.shares_to_min_unit(10))
        self._make_pos(db, symbol='B', name='大', quantity=Money.shares_to_min_unit(200))
        db.commit()

        resp = client.get('/api/summary/groups/?dimension=account')
        data = resp.get_json()['data']
        totals = [g['total'] for g in data]
        assert totals == sorted(totals, reverse=True)


class TestSnapshotsEndpoint:
    """资产快照接口 /api/summary/snapshots/ 测试套件（资产总览同比真实化）"""

    def test_empty_list(self, client):
        """无快照返回空列表"""
        resp = client.get('/api/summary/snapshots/')
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_create_takes_snapshot_of_current_assets(self, client, db):
        """POST 后自动聚合当前家庭资产/负债/净资产，金额精确到分"""
        cash = Asset(
            family_id=1, major_category='cash', name='活期存款', amount=Money.yuan_to_cents(100000), currency='CNY'
        )
        credit = Asset(
            family_id=1,
            major_category='liability',
            name='信用卡',
            amount=Money.yuan_to_cents(5000),
            currency='CNY',
        )
        db.add_all([cash, credit])
        db.commit()

        resp = client.post('/api/summary/snapshots/', json={})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['total_assets'] == 100000.0
        assert data['total_liabilities'] == 5000.0
        assert data['net_worth'] == 95000.0
        assert 'snapshot_date' in data
        assert 'monthly_change_pct' not in data  # 写入侧不返回同比

    def test_create_upsert_idempotent_same_date(self, client, db):
        """同 natural 日重复 POST 只保留一条记录，且以最新聚合覆盖"""
        cash = Asset(
            family_id=1, major_category='cash', name='活期存款', amount=Money.yuan_to_cents(1000), currency='CNY'
        )
        db.add(cash)
        db.commit()

        client.post('/api/summary/snapshots/', json={})
        # 修改金额后再次快照，仍但同日的行被覆盖更新
        cash.amount = Money.yuan_to_cents(2000)
        db.commit()
        client.post('/api/summary/snapshots/', json={})

        rows = db.query(AssetSnapshot).all()
        assert len(rows) == 1
        assert rows[0].total_assets == Money.yuan_to_cents(2000)

    def test_list_sorted_asc_with_yoy(self, client, db):
        """GET 返回升序列表，且 monthly/yearly 同比正确计算（基准取当天或之前最近一条）"""
        from datetime import date

        db.add_all(
            [
                AssetSnapshot(
                    family_id=1,
                    snapshot_date=date(2025, 8, 10),
                    total_assets=100000,
                    total_liabilities=0,
                    net_worth=100000,
                ),
                AssetSnapshot(
                    family_id=1,
                    snapshot_date=date(2026, 6, 10),
                    total_assets=100000,
                    total_liabilities=0,
                    net_worth=100000,
                ),
                AssetSnapshot(
                    family_id=1,
                    snapshot_date=date(2026, 7, 10),
                    total_assets=110000,
                    total_liabilities=0,
                    net_worth=110000,
                ),
                AssetSnapshot(
                    family_id=1,
                    snapshot_date=date(2026, 8, 10),
                    total_assets=121000,
                    total_liabilities=0,
                    net_worth=121000,
                ),
                AssetSnapshot(
                    family_id=1,
                    snapshot_date=date(2026, 8, 15),
                    total_assets=133100,
                    total_liabilities=0,
                    net_worth=133100,
                ),
            ]
        )
        db.commit()

        resp = client.get('/api/summary/snapshots/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        dates = [d['snapshot_date'] for d in data]
        assert dates == sorted(dates)

        # 8/10 较上月（7/10，+10%）与去年（2025/8/10，+21%）
        aug10 = next(d for d in data if d['snapshot_date'] == '2026-08-10')
        assert aug10['monthly_change_pct'] == 10.0
        assert aug10['yearly_change_pct'] == 21.0
        # 8/15 较上月取 7/10（2026-07-15 当天或之前最近一条）
        aug15 = next(d for d in data if d['snapshot_date'] == '2026-08-15')
        assert aug15['monthly_change_pct'] == 21.0
        # 7/10 较上月（6/10 → +10%）；去年 7/10 之前无快照 → yearly None
        jul10 = next(d for d in data if d['snapshot_date'] == '2026-07-10')
        assert jul10['monthly_change_pct'] == 10.0
        assert jul10['yearly_change_pct'] is None

    def test_yoy_null_when_no_history(self, client, db):
        """积累期无任何历史快照时，同比返回 None（前端降级展示）"""
        from datetime import date

        db.add(
            AssetSnapshot(
                family_id=1, snapshot_date=date(2026, 8, 10), total_assets=1000, total_liabilities=0, net_worth=1000
            )
        )
        db.commit()

        resp = client.get('/api/summary/snapshots/')
        data = resp.get_json()['data']
        only = data[0]
        assert only['monthly_change_pct'] is None
        assert only['yearly_change_pct'] is None

    def test_family_isolation(self, client, db):
        """不同 family_id 的快照互不可见"""
        from datetime import date

        db.add(
            AssetSnapshot(
                family_id=2, snapshot_date=date(2026, 8, 10), total_assets=999999, total_liabilities=0, net_worth=999999
            )
        )
        db.commit()

        # 默认家庭 1 查不到家庭 2 的快照
        resp = client.get('/api/summary/snapshots/')
        assert resp.get_json()['data'] == []

    def test_snapshot_date_range_filters(self, client, db):
        """start_date/end_date 筛选闭区间"""
        from datetime import date

        db.add_all(
            [
                AssetSnapshot(
                    family_id=1, snapshot_date=date(2026, 8, 1), total_assets=100, total_liabilities=0, net_worth=100
                ),
                AssetSnapshot(
                    family_id=1, snapshot_date=date(2026, 8, 10), total_assets=200, total_liabilities=0, net_worth=200
                ),
                AssetSnapshot(
                    family_id=1, snapshot_date=date(2026, 8, 20), total_assets=300, total_liabilities=0, net_worth=300
                ),
            ]
        )
        db.commit()

        resp = client.get('/api/summary/snapshots/?start_date=2026-08-02&end_date=2026-08-20')
        data = resp.get_json()['data']
        dates = [d['snapshot_date'] for d in data]
        assert dates == ['2026-08-10', '2026-08-20']

    def test_invalid_date_returns_400(self, client):
        """非法日期格式的 snapshot_date 拒绝写入"""
        resp = client.post('/api/summary/snapshots/', json={'snapshot_date': '2026/08/10'})
        assert resp.status_code == 400


class TestClearedCyclesEndpoint:
    """#2131 清仓周期统计端点（GET /api/summary/cleared-cycles/）"""

    def test_empty_returns_envelope(self, client):
        """无流水：空形态 + 标准信封，比率为 null 不画 0。"""
        resp = client.get('/api/summary/cleared-cycles/')
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload['message'] == 'ok'
        data = payload['data']
        assert data['cycles'] == []
        assert data['summary']['cycle_count'] == 0
        assert data['summary']['win_rate'] is None
        assert data['summary']['realized_pnl_total'] is None

    def test_cycle_visible_after_full_sell(self, client):
        """买入 → 清仓卖出：周期可查（信封 + 周期字段 + 汇总胜率）。

        走真实写入口（POST /api/positions/ op_type=buy/sell），覆盖
        「持仓行清仓即删、盈亏只能从流水聚合」这条端到端路径。
        """
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
        list_resp = client.get('/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']
        sell_resp = _post(
            client,
            '/api/positions/',
            {
                'position_id': pos_id,
                'op_type': 'sell',
                'symbol': '00700.HK',
                'quantity': 100,
                'avg_price': 400,
                'trade_date': '2026-06-01',
            },
        )
        assert sell_resp.status_code == 200

        resp = client.get('/api/summary/cleared-cycles/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data['cycles']) == 1
        c = data['cycles'][0]
        assert c['symbol'] == '00700.HK'
        assert c['first_buy_date'] == '2026-05-01'
        assert c['last_sell_date'] == '2026-06-01'
        assert c['trade_count'] == 2
        # 100 股 × (400−350) = 5000（流水币种原值，不折汇率——与 pnl_service 口径一致）
        assert c['realized_pnl'] == 5000.0
        assert c['pnl_pct'] == 14.29  # 5000 / 35000
        assert c['pnl_known'] is True
        assert data['summary']['cycle_count'] == 1
        assert data['summary']['win_rate'] == 100.0
        assert data['summary']['realized_pnl_total'] == 5000.0
        # 产品数（#2774）：1 只标的、1 轮周期 → 两个数都是 1
        assert data['summary']['product_count'] == 1

    def _seed_cleared_cycle(self, client) -> None:
        """买 100 股 → 全部卖出，造一轮已完结周期（末卖日 2026-06-01）。"""
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
        pos_id = client.get('/api/positions/').get_json()['data'][0]['id']
        _post(
            client,
            '/api/positions/',
            {
                'position_id': pos_id,
                'op_type': 'sell',
                'symbol': '00700.HK',
                'quantity': 100,
                'avg_price': 400,
                'trade_date': '2026-06-01',
            },
        )

    def test_start_date_filters_by_last_sell_date(self, client):
        """start_date 含端点：末卖日 == start_date 的周期保留，晚一天则被裁掉（#2774）。"""
        self._seed_cleared_cycle(client)

        inside = client.get('/api/summary/cleared-cycles/?start_date=2026-06-01')
        assert inside.status_code == 200
        assert len(inside.get_json()['data']['cycles']) == 1

        outside = client.get('/api/summary/cleared-cycles/?start_date=2026-06-02')
        assert outside.status_code == 200
        data = outside.get_json()['data']
        assert data['cycles'] == []
        # 窗口内无周期时汇总归零（不是沿用全量结果）
        assert data['summary']['cycle_count'] == 0
        assert data['summary']['product_count'] == 0
        assert data['summary']['win_rate'] is None

    def test_range_keeps_cycle_crossing_window(self, client):
        """跨窗口周期仍可算：首买在窗口外、末卖在窗口内（先聚合后裁剪的口径保证）。"""
        self._seed_cleared_cycle(client)
        resp = client.get('/api/summary/cleared-cycles/?start_date=2026-06-01&end_date=2026-06-30')
        data = resp.get_json()['data']
        assert len(data['cycles']) == 1
        assert data['cycles'][0]['pnl_known'] is True
        assert data['cycles'][0]['realized_pnl'] == 5000.0

    def test_invalid_date_returns_400(self, client):
        """格式错 400，不静默当成「不过滤」——静默降级会让用户以为筛选生效了。"""
        resp = client.get('/api/summary/cleared-cycles/?start_date=2026/06/01')
        assert resp.status_code == 400
        assert resp.get_json()['error_code'] == 1001

    def test_start_after_end_returns_400(self, client):
        resp = client.get('/api/summary/cleared-cycles/?start_date=2026-07-01&end_date=2026-06-01')
        assert resp.status_code == 400

    # ── 清仓后涨跌幅 + 浮亏标的数（#2773）────────────────────────────

    def _seed_otc_cycle(self, client, code='004369', sell_date='2026-06-01') -> None:
        """场外基金一轮完整周期：买 1000 份 @1.0 → 卖 1000 份 @1.1。

        **卖出请求故意不带 ``type``**：导入器/脚本/老客户端都不带，而缺失时若兜底成
        ``'stock'``，卖出流水与买入会分属两个身份键（``EXCHANGE:`` vs ``OTC:``），
        清仓周期永远闭合不上。这条同时守住 `_get_asset_type(fallback=持仓品种)`。

        代码取 ``004369`` 而非 ``000001``：后者与平安银行同码，后端成交价区间校验
        会按股票的真实区间把 1.1 拦下来（`_validate_price_within_range`）。
        """
        buy = _post(
            client,
            '/api/positions/',
            {
                'symbol': code,
                'name': '测试场外基',
                'type': 'fund',
                'asset_type': 'fund',
                'market': 'CN_A',
                'account_name': '天天基金',
                'quantity': 1000,
                'avg_price': 1.0,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
                'op_type': 'buy',
            },
        )
        assert buy.status_code == 200, buy.get_json()
        pos_id = client.get('/api/positions/').get_json()['data'][0]['id']
        sell = _post(
            client,
            '/api/positions/',
            {
                'position_id': pos_id,
                'op_type': 'sell',
                'symbol': code,
                'quantity': 1000,
                'avg_price': 1.1,
                'trade_date': sell_date,
            },
        )
        assert sell.status_code == 200, sell.get_json()

    def test_post_clear_fields_absent_by_default(self, client):
        """不传 include_post_clear → 周期里没有 post_clear_* 字段（老调用方零改动）。"""
        self._seed_cleared_cycle(client)

        data = client.get('/api/summary/cleared-cycles/').get_json()['data']

        assert 'post_clear_pct' not in data['cycles'][0]
        assert 'post_clear_status' not in data['cycles'][0]

    def test_include_post_clear_computes_pct_with_as_of_and_basis(self, client, db):
        """场外周期：给出涨跌幅 + **截至日** + **口径**（三者缺一，这个数就会被误读）。"""
        from datetime import date

        from app.domains.funds.models import DailyWorth

        self._seed_otc_cycle(client)
        db.add_all(
            [
                # 锚点：卖出日当日净值
                DailyWorth(fund_code='004369', date=date(2026, 6, 1), unit_nav=1.2, acc_nav=1.2),
                # 最新：卖出之后
                DailyWorth(fund_code='004369', date=date(2026, 9, 30), unit_nav=1.4, acc_nav=1.5),
            ]
        )
        db.commit()

        data = client.get('/api/summary/cleared-cycles/?include_post_clear=1').get_json()['data']
        c = data['cycles'][0]

        assert c['post_clear_status'] == 'ok'
        assert c['post_clear_pct'] == 25.0  # 1.5 / 1.2 − 1，用 acc 口径
        assert c['post_clear_as_of'] == '2026-09-30'
        assert c['post_clear_basis'] == 'acc_nav'

    def test_include_post_clear_without_nav_reports_reason_not_zero(self, client):
        """无净值可算时回 null + 状态码，**绝不回 0**（0 的含义是「没涨没跌」）。"""
        self._seed_otc_cycle(client)

        data = client.get('/api/summary/cleared-cycles/?include_post_clear=1').get_json()['data']
        c = data['cycles'][0]

        assert c['post_clear_pct'] is None
        assert c['post_clear_status'] == 'no_nav_at_sell'
        assert c['post_clear_as_of'] is None

    def test_unrealized_count_lists_underwater_holdings(self, client, db, make_position):
        """浮亏标的数与胜率并列下发，且**不随**时间窗口变化（它是当前持仓的点位事实）。"""
        from datetime import date

        from app.domains.funds.models import DailyWorth

        self._seed_cleared_cycle(client)
        make_position(
            symbol='000002', asset_type='fund', name='浮亏基', quantity=1000, avg_price=1.0
        )
        db.add(DailyWorth(fund_code='000002', date=date(2026, 9, 30), unit_nav=0.9, acc_nav=0.9))
        db.commit()

        data = client.get('/api/summary/cleared-cycles/').get_json()['data']
        assert data['summary']['unrealized_count'] == 1
        assert data['summary']['cycle_count'] == 1

        # 把窗口推到未来：周期被裁掉，但浮亏数不变（不许随筛选一起归零）
        windowed = client.get('/api/summary/cleared-cycles/?start_date=2030-01-01').get_json()['data']
        assert windowed['summary']['cycle_count'] == 0
        assert windowed['summary']['unrealized_count'] == 1

    def test_unrealized_count_is_zero_not_none_when_no_holdings(self, client):
        """算了但没有持仓 → 0；不是 null（null 表示「没算」，两者不能混）。"""
        data = client.get('/api/summary/cleared-cycles/').get_json()['data']

        assert data['summary']['unrealized_count'] == 0
