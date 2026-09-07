# -*- coding: utf-8 -*-
"""#1354：投资理财大类收敛。

银行理财 / 投顾 / 信托 / 私募 / 理财型保险 不再作为平级大类：
- 盘点页标签栏只保留 6 个主类；
- 新增记录写入 minor_category（细分），major_category 统一 investment；
- 读取 / 聚合口径把历史 5 个大类归一为 investment，存量数据零迁移但不丢。
"""

from app.core.asset_types import (
    INVESTMENT_CATEGORIES,
    INVESTMENT_MINOR_CATEGORIES,
    get_investment_minor_label,
    normalize_major_category,
)

# 由常量生成，避免与 INVESTMENT_CATEGORIES 手工重复维护（#1355 AI review）
ALL_INVESTMENT_KEYS = ','.join(INVESTMENT_CATEGORIES)


class TestNormalizeMajorCategory:
    def test_sub_categories_normalized_to_investment(self):
        for key in INVESTMENT_MINOR_CATEGORIES:
            assert normalize_major_category(key) == 'investment'

    def test_other_categories_unchanged(self):
        assert normalize_major_category('cash') == 'cash'
        assert normalize_major_category('liability') == 'liability'
        assert normalize_major_category('insurance') == 'insurance'
        assert normalize_major_category(None) is None

    def test_investment_categories_set(self):
        assert INVESTMENT_CATEGORIES == {'investment', *INVESTMENT_MINOR_CATEGORIES}

    def test_investment_minor_label(self):
        assert get_investment_minor_label('bank_wealth') == '银行理财'
        assert get_investment_minor_label('private_fund') == '私募'
        assert get_investment_minor_label('') == ''
        assert get_investment_minor_label('未知细分') == '未知细分'


class TestAssetListMultiMajorCategory:
    def test_filter_by_comma_separated_major_category(self, client):
        client.post('/api/assets/', json={'major_category': 'investment', 'name': '定期', 'amount': 100})
        # 存量历史数据：直接写了平级大类 bank_wealth（未被迁移），查询时仍应被 investment 筛选命中
        client.post('/api/assets/', json={'major_category': 'bank_wealth', 'name': '银行理财', 'amount': 200})
        client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期', 'amount': 50})

        resp = client.get('/api/assets/', query_string={'major_category': ALL_INVESTMENT_KEYS})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        names = {a['name'] for a in data}
        assert names == {'定期', '银行理财'}

    def test_new_record_writes_investment_major_with_minor(self, client):
        """新增记录写入收敛：投资理财细分走 minor_category，major_category 统一 investment。

        注意：列表明细展示保留写入时的 major_category（存量可追溯），故此处断言写入后即
        investment，而非在 list 响应里被归一（归一只发生在聚合 / 汇总口径，见
        TestSummaryMergesInvestment / TestDistributionsMergesInvestment）。
        """
        resp = client.post(
            '/api/assets/',
            json={'major_category': 'investment', 'minor_category': 'bank_wealth', 'name': '某银行理财', 'amount': 100},
        )
        assert resp.status_code == 200
        body = resp.get_json()['data']
        assert body['major_category'] == 'investment'
        assert body['minor_category'] == 'bank_wealth'

        list_resp = client.get('/api/assets/', query_string={'major_category': 'investment'})
        listed = [a for a in list_resp.get_json()['data'] if a['name'] == '某银行理财']
        assert listed and listed[0]['major_category'] == 'investment'

    def test_single_major_category_still_works(self, client):
        client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期', 'amount': 50})
        client.post('/api/assets/', json={'major_category': 'fixed', 'name': '房产', 'amount': 500})

        resp = client.get('/api/assets/', query_string={'major_category': 'cash'})
        assert resp.status_code == 200
        names = {a['name'] for a in resp.get_json()['data']}
        assert names == {'活期'}

    def test_filter_by_minor_category(self, client):
        client.post(
            '/api/assets/',
            json={
                'major_category': 'investment',
                'minor_category': 'trust',
                'name': '某信托',
                'amount': 100,
            },
        )
        client.post(
            '/api/assets/',
            json={
                'major_category': 'investment',
                'minor_category': 'private_fund',
                'name': '某私募',
                'amount': 100,
            },
        )

        resp = client.get('/api/assets/', query_string={'minor_category': 'trust'})
        assert resp.status_code == 200
        names = {a['name'] for a in resp.get_json()['data']}
        assert names == {'某信托'}


class TestAssetSummaryMergesInvestment:
    def test_summary_merges_sub_categories_into_investment(self, client):
        client.post('/api/assets/', json={'major_category': 'investment', 'name': '定期', 'amount': 100})
        client.post('/api/assets/', json={'major_category': 'bank_wealth', 'name': '银行理财', 'amount': 200})
        client.post('/api/assets/', json={'major_category': 'trust', 'name': '信托', 'amount': 300})

        resp = client.get('/api/assets/summary/')
        assert resp.status_code == 200
        summary = {item['code']: item['value'] for item in resp.get_json()['data']}
        assert summary['investment'] == 600.0
        # 细分大类不再单独下发，否则盘点页会把投资理财拆成多档
        assert 'bank_wealth' not in summary
        assert 'trust' not in summary

    def test_summary_keeps_other_categories(self, client):
        client.post('/api/assets/', json={'major_category': 'cash', 'name': '活期', 'amount': 100})
        client.post('/api/assets/', json={'major_category': 'liability', 'name': '信用卡', 'amount': 30})

        resp = client.get('/api/assets/summary/')
        summary = {item['code']: item['value'] for item in resp.get_json()['data']}
        assert summary['cash'] == 100.0
        assert summary['liability'] == -30.0


class TestDistributionsMergesInvestment:
    def test_sub_category_asset_merged_into_investment(self, client, make_asset):
        make_asset(major_category='wealth_insurance', name='增额终身寿', amount=1000)

        resp = client.get('/api/summary/distributions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        categories = {item['name']: item['value'] for item in data['category_distribution']}
        assert categories.get('投资理财') == 1000.0
        assert '理财型保险' not in categories

    def test_position_groups_label_normalized(self, client, make_asset):
        """按账户分组的明细里，细分大类要显示为「投资理财」而不是各自为政"""
        make_asset(major_category='advisory', name='投顾组合', amount=500, account_name='某账户')

        resp = client.get('/api/summary/groups/', query_string={'dimension': 'account'})
        assert resp.status_code == 200
        groups = resp.get_json()['data']
        labels = {item['type_label'] for g in groups for item in g['items']}
        assert '投资理财' in labels
        assert '投顾' not in labels
