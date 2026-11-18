# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 22:01
# File : test_summary.py

from collections import defaultdict

import pytest

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
    # 总资产为 0 时负债率**不可计算**：给 None 而不是 0%。
    # 「负债率 0%」会被读成「一分钱负债都没有」，而真相是分母不存在。
    assert data['liability_ratio'] is None


def test_ratio_pct_统一舍入且分母非正时给None():
    """占比的唯一实现：分母为 0 / None ⇒ None，分子为 0 ⇒ 0.0（两者不可混同）。

    「没有负债」（0/100 = 0%）与「没有资产」（1/0 = 不可计算）在界面上是两句话，
    函数必须能分开表达，否则卡面只能要么撒谎、要么永远显示「--」。
    """
    from app.services.summary_service import ratio_pct

    assert ratio_pct(5000, 132200) == 3.78
    assert ratio_pct(0, 100) == 0.0
    assert ratio_pct(1, 0) is None
    assert ratio_pct(1, None) is None
    assert ratio_pct(None, 100) is None
    assert ratio_pct(10, -5) is None


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
    # 负债率 = 5,000 ÷ 132,200 = 3.78%（后端直出，前端不再除一遍）
    assert data['liability_ratio'] == 3.78
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
    """桑基图端点测试套件（2026-11-09 按 D94「单轴守恒图」契约重写）。

    旧套件把「净资产 → 五笔钱 → 产品类型」钉成期望，其中
    `test_liabilities_isolated_from_net_worth` 断言净资产 1.5 万却能流出
    2 万持仓市值——**守恒破坏被测试固化**。新套件每个用例都过一遍
    `_assert_sankey_conserved()`：桑基图是守恒流量图，一条链只能承载一个
    分类轴（资金来源 → 资产运用），且 A = L + E 必须逐节点成立。

    守卫本身也要自检（AGENTS.md：守门通过 ≠ 守门有效），见
    `test_conservation_guard_is_effective`：故意破坏守恒 / 塞回「未配置资产」
    都必须让守卫转红。
    """

    # 五笔钱配置目标与「未配置资产」属于正交分类轴，绝不能出现在这张图里
    FORBIDDEN_NODES = {
        '未配置资产',
        '活钱',
        '稳健底仓',
        '长期增值',
        '高风险博弈',
        '保险保障',
    }

    @staticmethod
    def _assert_sankey_conserved(data):
        """通用守恒守卫：禁用节点 / 正流量 / 中间节点入=出 / 无孤立节点 / 方向。

        只从 `nodes` 与 `links` 独立判断，不调用被测实现，避免「删掉实现后
        守卫恒绿」这类假绿。返回 `(nodes, links)` 方便用例继续断言。
        """
        nodes = [n['name'] for n in data['nodes']]
        links = data['links']
        node_set = set(nodes)

        assert len(nodes) == len(node_set), '节点名重复（_add_node 去重失效）'
        assert not (node_set & TestSankeyEndpoint.FORBIDDEN_NODES), (
            f'出现了被删除的正交分类轴节点：{node_set & TestSankeyEndpoint.FORBIDDEN_NODES}'
        )
        assert all(lk['value'] > 0 for lk in links), '桑基图不能画非正流量'

        in_sum = defaultdict(float)
        out_sum = defaultdict(float)
        touched = set()
        for lk in links:
            in_sum[lk['target']] += lk['value']
            out_sum[lk['source']] += lk['value']
            touched.add(lk['source'])
            touched.add(lk['target'])
        assert node_set == touched, f'存在孤立节点：{node_set - touched}'

        for name in node_set:
            if in_sum[name] > 0 and out_sum[name] > 0:
                assert abs(in_sum[name] - out_sum[name]) <= 0.02, (
                    f'中间节点「{name}」入边 {in_sum[name]} ≠ 出边 {out_sum[name]}'
                )

        # 方向：资金来源侧只往总资产汇，总资产只往资产运用侧分流
        edge_set = {(lk['source'], lk['target']) for lk in links}
        assert ('总资产', '净资产') not in edge_set, '流向反了（旧拓扑）'
        assert ('总资产', '总负债') not in edge_set, '流向反了（旧拓扑）'
        assert all(lk['target'] == '总资产' for lk in links if lk['source'] == '净资产'), '净资产不能流向五笔钱'
        assert all(lk['target'] == '总资产' for lk in links if lk['source'] == '总负债'), '总负债只能汇入总资产'

        if in_sum['总资产'] > 0:
            assert abs(in_sum['总资产'] - out_sum['总资产']) <= 0.02, '总资产入边 ≠ 出边'
        return nodes, links

    def test_empty_data_returns_empty(self, client):
        """空数据库返回空 nodes 和 links，不报错"""
        resp = client.get('/api/summary/sankey/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['nodes'] == []
        assert data['links'] == []

    def test_only_positions_no_assets(self, client, db):
        """仅有持仓：无负债分支，产品类型作为资产明细挂在「投资理财」下"""
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

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        edges = {(lk['source'], lk['target']) for lk in links}
        assert {'净资产', '总资产', '投资理财', '股票'} <= set(nodes)
        assert '总负债' not in nodes
        assert ('净资产', '总资产') in edges
        assert ('总资产', '投资理财') in edges
        assert ('投资理财', '股票') in edges

    def test_only_assets_no_positions(self, client, db):
        """仅有通用资产：负债明细在左侧汇入总负债，资产明细在右侧展开"""
        db.add_all(
            [
                Asset(
                    user_id=1,
                    major_category='fixed',
                    name='阳光花园',
                    amount=Money.yuan_to_cents(5_000_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='招商银行信用卡',
                    amount=Money.yuan_to_cents(5000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        edges = {(lk['source'], lk['target']) for lk in links}
        assert {'招商银行信用卡', '总负债', '净资产', '总资产', '固定资产', '阳光花园'} <= set(nodes)
        assert ('招商银行信用卡', '总负债') in edges
        assert ('总负债', '总资产') in edges
        assert ('总资产', '固定资产') in edges
        assert ('固定资产', '阳光花园') in edges

    def test_full_data_with_allocation(self, client, db):
        """混合数据：五笔钱配置目标完全不进图，负债只在资金来源侧出现一次"""
        db.add_all(
            [
                Position(
                    symbol='SH600519',
                    name='茅台',
                    market='SH',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(50),
                    avg_price=Money.yuan_to_price_units(1600),
                    current_price=Money.yuan_to_price_units(1800),
                    currency='CNY',
                    allocation='longterm',
                ),
                Position(
                    symbol='000001',
                    name='某基金',
                    market='SZ',
                    asset_type='fund',
                    quantity=Money.shares_to_min_unit(1000),
                    avg_price=Money.yuan_to_price_units(1.5),
                    current_price=Money.yuan_to_price_units(1.8),
                    currency='CNY',
                    allocation='stable',
                ),
                Asset(
                    user_id=1,
                    major_category='cash',
                    name='活期存款',
                    amount=Money.yuan_to_cents(200_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='房屋贷款',
                    amount=Money.yuan_to_cents(100_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        edges = {(lk['source'], lk['target']) for lk in links}
        assert {'流动资金', '投资理财', '总资产', '净资产', '总负债', '房屋贷款'} <= set(nodes)
        assert {'活期存款', '股票', '基金'} <= set(nodes)
        assert ('房屋贷款', '总负债') in edges
        assert ('总资产', '流动资金') in edges
        assert ('总资产', '投资理财') in edges
        assert ('投资理财', '股票') in edges
        assert ('投资理财', '基金') in edges
        assert not (set(nodes) & {'长期增值', '稳健底仓', '活钱', '高风险博弈', '保险保障'})

    def test_currency_conversion(self, client, db):
        """外币持仓正确换算为 CNY，体现在 总资产 → 投资理财 的链接中"""
        db.add(
            Position(
                symbol='HK00700',
                name='腾讯控股',
                market='HK',
                asset_type='stock',
                quantity=Money.shares_to_min_unit(100),
                avg_price=Money.yuan_to_price_units(300),
                current_price=Money.yuan_to_price_units(350),
                currency='HKD',
            )
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        _nodes, links = self._assert_sankey_conserved(data)
        # 市值 = 100 * 350 * 0.92 = 32200.0
        invest_link = next(lk for lk in links if lk['source'] == '总资产' and lk['target'] == '投资理财')
        assert invest_link['value'] == 32200.0

    def test_node_deduplication(self, client, db):
        """同产品类型的多笔持仓聚合成一个明细节点"""
        db.add_all(
            [
                Position(
                    symbol='A',
                    name='股A',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(1),
                    current_price=Money.yuan_to_price_units(10),
                ),
                Position(
                    symbol='B',
                    name='股B',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(1),
                    current_price=Money.yuan_to_price_units(20),
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, _links = self._assert_sankey_conserved(data)
        assert nodes.count('股票') == 1

    def test_aggregation_by_category(self, client, db):
        """同一大类多条资产聚合成一个大类节点，明细逐项展开"""
        db.add_all(
            [
                Asset(
                    user_id=1, major_category='cash', name='银行卡A', amount=Money.yuan_to_cents(10000), currency='CNY'
                ),
                Asset(
                    user_id=1, major_category='cash', name='银行卡B', amount=Money.yuan_to_cents(20000), currency='CNY'
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        assert nodes.count('流动资金') == 1
        assert {'银行卡A', '银行卡B'} <= set(nodes)
        cat_link = next(lk for lk in links if lk['source'] == '总资产' and lk['target'] == '流动资金')
        assert cat_link['value'] == 30000.0

    def test_liabilities_isolated_from_net_worth(self, client, db):
        """负债不影响资产运用侧，且净资产本身就是 A − L（不再配平出「未配置资产」）。

        旧用例断言「净资产(1.5万) → 高风险博弈 = 持仓市值(2万)」，等于把
        入边 1.5 万 / 出边 2 万的守恒破坏钉成期望行为。现在净资产出边
        只有「总资产」，持仓市值走 总资产 → 投资理财 → 股票。
        """
        db.add_all(
            [
                Position(
                    symbol='SH600519',
                    name='茅台',
                    market='SH',
                    asset_type='stock',
                    quantity=Money.shares_to_min_unit(10),
                    avg_price=Money.yuan_to_price_units(1000),
                    current_price=Money.yuan_to_price_units(2000),
                    currency='CNY',
                    allocation='speculative',
                ),
                Asset(
                    user_id=1, major_category='liability', name='花呗', amount=Money.yuan_to_cents(5000), currency='CNY'
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        _nodes, links = self._assert_sankey_conserved(data)
        by_edge = {(lk['source'], lk['target']): lk['value'] for lk in links}
        assert by_edge[('净资产', '总资产')] == 15000.0
        assert by_edge[('花呗', '总负债')] == 5000.0
        assert by_edge[('总负债', '总资产')] == 5000.0
        assert by_edge[('总资产', '投资理财')] == 20000.0
        assert by_edge[('投资理财', '股票')] == 20000.0
        assert ('净资产', '高风险博弈') not in by_edge

    def test_house_and_loan_no_unconfigured_asset(self, client, db):
        """用户原案例：零持仓 + 房 220万 + 房贷 176万，不得凭空造「未配置资产」。

        旧版 `unconfigured = net_worth − Σ持仓市值` 在这里给出 44 万，
        它其实是「非持仓资产净额」被错配到权益下面。
        """
        db.add_all(
            [
                Asset(
                    user_id=1,
                    major_category='fixed',
                    name='自住房',
                    amount=Money.yuan_to_cents(2_200_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='房贷',
                    amount=Money.yuan_to_cents(1_760_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        assert '未配置资产' not in nodes
        by_edge = {(lk['source'], lk['target']): lk['value'] for lk in links}
        assert by_edge[('净资产', '总资产')] == 440000.0
        assert by_edge[('总资产', '固定资产')] == 2_200_000.0
        assert by_edge[('固定资产', '自住房')] == 2_200_000.0

    def test_allocation_does_not_change_graph(self, client, db):
        """改五笔钱配置目标不改变图的任何金额：这条正交轴已被彻底移除"""
        pos = Position(
            symbol='FUND',
            name='一支基金',
            asset_type='fund',
            quantity=Money.shares_to_min_unit(1),
            current_price=Money.yuan_to_price_units(1000),
            currency='CNY',
            allocation='longterm',
        )
        db.add_all(
            [
                pos,
                Asset(
                    user_id=1,
                    major_category='fixed',
                    name='自住房',
                    amount=Money.yuan_to_cents(2_200_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        first = client.get('/api/summary/sankey/').get_json()['data']
        pos.allocation = 'liquid'
        db.commit()
        second = client.get('/api/summary/sankey/').get_json()['data']

        self._assert_sankey_conserved(first)
        self._assert_sankey_conserved(second)
        assert first == second

    def test_negative_net_worth_degrades_to_single_axis(self, client, db):
        """资不抵债时 E ≤ 0 不能画成正流量：退化为「总资产 → 大类 → 明细」单轴图"""
        db.add_all(
            [
                Asset(
                    user_id=1,
                    major_category='fixed',
                    name='自住房',
                    amount=Money.yuan_to_cents(2_200_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='房贷',
                    amount=Money.yuan_to_cents(4_000_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        assert '净资产' not in nodes
        assert '总负债' not in nodes
        assert '房贷' not in nodes
        assert nodes == ['总资产', '固定资产', '自住房']
        assert {(lk['source'], lk['target']) for lk in links} == {('总资产', '固定资产'), ('固定资产', '自住房')}

    def test_zero_value_assets_ignored(self, client, db):
        """金额为 0 的资产不参与桑基图"""
        db.add(Asset(user_id=1, major_category='cash', name='空账户', amount=Money.yuan_to_cents(0), currency='CNY'))
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, _links = self._assert_sankey_conserved(data)
        assert '空账户' not in nodes

    def test_duplicate_liability_names_merged(self, client, db):
        """同名负债（不同账户）合并成一条带，不产生两条同源同目标的边

        桑基图以节点 name 为唯一键。同名明细若不聚合，会出现两条
        source/target 完全相同的边，前端算重心时父节点被数两次。
        """
        db.add_all(
            [
                # 一笔正资产让净资产 > 0，资金来源侧才会绘制（否则触发资不抵债退化，
                # 整个负债分支被跳过，合并边根本不会出现）
                Asset(
                    user_id=1,
                    major_category='cash',
                    name='活期存款',
                    amount=Money.yuan_to_cents(3_000_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='房贷',
                    account_name='A',
                    amount=Money.yuan_to_cents(1_000_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='liability',
                    name='房贷',
                    account_name='B',
                    amount=Money.yuan_to_cents(500_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        edges = [lk for lk in links if lk['source'] == '房贷']
        assert len(edges) == 1, f'同名负债应合并成一条边，实得 {edges}'
        assert edges[0]['target'] == '总负债'
        assert edges[0]['value'] == 1_500_000.0

    def test_detail_name_colliding_with_category_has_no_self_loop(self, client, db):
        """明细名撞大类名时不生成自环边（ECharts 判非 DAG 会让整图白屏）

        用户完全可以把资产命名为「投资理财」「流动资金」。旧实现明细名取自
        asset_type（股票/基金…）不会撞；改成用户自填资产名后必须显式去重。
        """
        db.add_all(
            [
                Asset(
                    user_id=1,
                    major_category='investment',
                    name='投资理财',
                    amount=Money.yuan_to_cents(300_000),
                    currency='CNY',
                ),
                Asset(
                    user_id=1,
                    major_category='cash',
                    name='流动资金',
                    amount=Money.yuan_to_cents(100_000),
                    currency='CNY',
                ),
            ]
        )
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        assert not [lk for lk in links if lk['source'] == lk['target']], '出现了自环边'
        # 大类节点仍是唯一的那个，撞名的明细被改名让开
        assert nodes.count('投资理财') == 1
        assert nodes.count('流动资金') == 1
        assert '投资理财·2' in nodes
        assert '流动资金·2' in nodes
        assert len(set(nodes)) == len(nodes), '节点名必须全局唯一'

    def test_unnamed_asset_falls_back_to_other_asset(self, client, db):
        """无名的通用资产归到「其他资产」，不产生空名节点或空名边"""
        db.add(Asset(user_id=1, major_category='cash', name=None, amount=Money.yuan_to_cents(80_000), currency='CNY'))
        db.commit()

        data = client.get('/api/summary/sankey/').get_json()['data']
        nodes, links = self._assert_sankey_conserved(data)
        assert '其他资产' in nodes
        assert '' not in nodes
        assert all(lk['source'] and lk['target'] for lk in links)

    def test_conservation_guard_is_effective(self):
        """守卫灵敏度探针：破坏守恒 / 孤立节点 / 禁用节点 / 反转方向 / 零流量都转红。

        AGENTS.md：守门通过 ≠ 守门有效。若有人删掉守恒实现，这条探针
        必须能证明守卫不是恒绿。
        """
        base = {
            'nodes': [
                {'name': '净资产'},
                {'name': '总资产'},
                {'name': '固定资产'},
                {'name': '自住房'},
            ],
            'links': [
                {'source': '净资产', 'target': '总资产', 'value': 100},
                {'source': '总资产', 'target': '固定资产', 'value': 100},
                {'source': '固定资产', 'target': '自住房', 'value': 100},
            ],
        }
        self._assert_sankey_conserved(base)  # 基线先绿

        def must_fail(mutate):
            broken = {
                'nodes': [dict(n) for n in base['nodes']],
                'links': [dict(lk) for lk in base['links']],
            }
            mutate(broken)
            with pytest.raises(AssertionError):
                self._assert_sankey_conserved(broken)

        must_fail(lambda d: d['links'][1].update(value=200))  # 入 100 / 出 200
        must_fail(lambda d: d['nodes'].append({'name': '孤立节点'}))  # 无边的节点
        must_fail(lambda d: d['nodes'].append({'name': '未配置资产'}))  # 禁用节点
        must_fail(
            lambda d: d['links'][0].update(  # 方向反转
                source='总资产', target='净资产'
            )
        )
        must_fail(lambda d: d['links'][2].update(value=0))  # 非正流量


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

        代码沿用 ``004369``：历史上取它而非 ``000001`` 是为了绕开场外基金与平安银行
        ``SZ000001`` 同码导致的误拦。该误拦已于 2026-11-04 修复（写路径区间校验按
        venue 过滤，见 `validate_trade_price_within_range`），这里保留原代码只为用例稳定。
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
        make_position(symbol='000002', asset_type='fund', name='浮亏基', quantity=1000, avg_price=1.0)
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

    def test_exchange_cycle_uses_adj_close(self, client, db):
        """场内周期用**前复权**收盘价：除权日 close 会跳台阶，adj_close 不会。

        造一组跨分红的数据：close 10.0 → 9.5（−5%），adj_close 10.0 → 10.55（+5.5%）。
        接口必须给出 +5.5% 且 basis 标 adj_close —— 用 close 会把分红记成亏损，
        方向都反了。这条就是 #2773 验收里「能挡住随手取 close」的那条。
        """
        from datetime import date

        from app.domains.price_history.models import PriceHistory

        db.add_all(
            [
                # 买入日之前：同样给出区间，否则后端价格校验会去拉真实行情
                PriceHistory(
                    security_id=1,
                    symbol='SZ000001',
                    trade_date=date(2026, 5, 5),
                    open=10.0,
                    high=10.2,
                    low=9.8,
                    close=10.0,
                    adj_close=10.0,
                ),
                # 卖出日之前：价格区间 9.8~10.2，让 10.0 的成交价通过区间校验
                PriceHistory(
                    security_id=1,
                    symbol='SZ000001',
                    trade_date=date(2026, 5, 29),
                    open=10.0,
                    high=10.2,
                    low=9.8,
                    close=10.0,
                    adj_close=10.0,
                ),
                # 除权日：close 下跳，adj_close 连续
                PriceHistory(
                    security_id=1,
                    symbol='SZ000001',
                    trade_date=date(2026, 7, 15),
                    open=9.0,
                    high=9.1,
                    low=8.9,
                    close=9.0,
                    adj_close=10.0,
                ),
                PriceHistory(
                    security_id=1,
                    symbol='SZ000001',
                    trade_date=date(2026, 10, 30),
                    open=9.5,
                    high=9.6,
                    low=9.4,
                    close=9.5,
                    adj_close=10.55,
                ),
            ]
        )
        db.commit()

        _post(
            client,
            '/api/positions/',
            {
                'symbol': '000001',
                'name': '平安银行',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商',
                'quantity': 100,
                'avg_price': 10.0,
                'currency': 'CNY',
                'trade_date': '2026-05-06',
                'op_type': 'buy',
            },
        )
        pos_id = client.get('/api/positions/').get_json()['data'][0]['id']
        sell = _post(
            client,
            '/api/positions/',
            {
                'position_id': pos_id,
                'op_type': 'sell',
                'symbol': '000001',
                'quantity': 100,
                'avg_price': 10.0,
                'trade_date': '2026-06-01',
            },
        )
        assert sell.status_code == 200, sell.get_json()

        data = client.get('/api/summary/cleared-cycles/?include_post_clear=1').get_json()['data']
        c = data['cycles'][0]

        assert c['post_clear_status'] == 'ok'
        assert c['post_clear_pct'] == 5.5  # 10.55 / 10.0 − 1，而非 close 口径的 −5%
        assert c['post_clear_basis'] == 'adj_close'
        assert c['post_clear_as_of'] == '2026-10-30'


def test_cross_ledger_duplicates_display_name(db):
    """跨账本重复组带 display_name：组内任一行 position_name 非空即取，全空给 None。

    域 D 卡片此前只拿到裸编码（SH515250），名称其实一直在 ``transactions.position_name``
    里——本用例钉住 payload 里必须真的带上它，且空时是 None 而不是报错。
    """
    from datetime import date, datetime

    from app.domains.ledgers.models import Ledger
    from app.domains.transactions.models import Transaction
    from app.services.summary_service import scan_cross_ledger_duplicates

    a = Ledger(name='券商A', ledger_type='stock', family_id=1)
    b = Ledger(name='券商B', ledger_type='stock', family_id=1)
    db.add_all([a, b])
    db.flush()

    def mk(ledger_id, symbol, position_name=None, amount=100000):
        t = Transaction(
            ledger_id=ledger_id,
            family_id=1,
            account_name='券商',
            symbol=symbol,
            txn_type='buy',
            quantity=100,
            price=100000,
            fee=0,
            amount=amount,
            confirm_date=date(2026, 8, 1),
            trade_date=datetime(2026, 8, 1),
            import_hash=f'dn-{ledger_id}-{symbol}-{amount}',
            status='success',
            position_name=position_name,
        )
        db.add(t)
        return t

    mk(a.id, '000001', position_name='平安银行')
    mk(b.id, '000001')
    mk(a.id, '600000')
    mk(b.id, '600000')
    db.commit()

    groups = {g['symbol']: g for g in scan_cross_ledger_duplicates(db, 1)}
    assert groups['000001']['display_name'] == '平安银行'
    assert groups['600000']['display_name'] is None
