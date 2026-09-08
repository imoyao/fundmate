# -*- coding: utf-8 -*-
"""统一聚合搜索 /api/search/assets/ 测试（#1286）。

覆盖五类 Provider 命中、空查询、统一信封形状与无市场实体空串约定。
"""

from app.domains.funds.models import AdvisorPortfolio, Fund, FundCompany, Manager
from app.domains.indices.models import IndexCatalog
from app.domains.securities.models import Security


def _seed(db):
    db.add(Security(symbol='SH600519', name='贵州茅台', market='CN_A', type='stock'))
    db.add(Fund(fund_code='110011', name='易方达优质精选混合'))
    db.add(IndexCatalog(index_code='000300', name='沪深300', exchange='SH', source='sina'))
    db.add(AdvisorPortfolio(platform='TIANTIAN', code='XCOVSEX', name='越海', is_active=True))
    company = FundCompany(code='80000235', name='易方达基金')
    db.add(company)
    db.flush()
    db.add(Manager(mgr_code='abc123def456', name='张坤', company_id=company.id))
    db.commit()


class TestSearchAssets:
    def test_empty_q_returns_empty(self, client, db):
        resp = client.get('/api/search/assets/', query_string={'q': ''})
        assert resp.status_code == 200
        assert resp.get_json()['data'] == []

    def test_securities_hit(self, client, db):
        _seed(db)
        resp = client.get('/api/search/assets/', query_string={'q': '600519'})
        data = resp.get_json()['data']
        hit = next(i for i in data if i['code'] == 'SH600519')
        assert hit['asset_type'] == 'stock'
        assert hit['market'] == 'CN_A'
        assert hit['venue'] == 'EXCHANGE'

    def test_fund_hit(self, client, db):
        _seed(db)
        resp = client.get('/api/search/assets/', query_string={'q': '110011'})
        hit = next(i for i in resp.get_json()['data'] if i['code'] == '110011')
        assert hit['asset_type'] == 'fund'
        assert hit['venue'] == 'OTC'

    def test_index_hit_normalized_code(self, client, db):
        _seed(db)
        resp = client.get('/api/search/assets/', query_string={'q': '沪深300'})
        hit = next(i for i in resp.get_json()['data'] if i['code'] == 'SH000300')
        assert hit['asset_type'] == 'index'
        assert hit['extra']['exchange'] == 'SH'

    def test_index_csi_prefix(self, client, db):
        """中证专属代码（三源合并 #1365）：code 带 CSI 命名空间前缀。"""
        _seed(db)
        db.add(IndexCatalog(index_code='930950', name='中证偏股基金指数', exchange='CSI', source='csindex'))
        db.commit()
        resp = client.get('/api/search/assets/', query_string={'q': '偏股基金'})
        hit = next(i for i in resp.get_json()['data'] if i['code'] == 'CSI930950')
        assert hit['asset_type'] == 'index'
        assert hit['market'] == 'CSI'
        assert hit['venue'] == ''

    def test_index_core_whitelist_ordering(self, client, db):
        """核心白名单置顶（is_core/core_rank，#1365）：核心排前、extra 携带标记。"""
        _seed(db)
        # _seed 已含 000300（非核心），直接升格为核心
        seeded_300 = db.query(IndexCatalog).filter_by(index_code='000300').one()
        seeded_300.is_core = True
        seeded_300.core_rank = 1
        db.add_all(
            [
                IndexCatalog(
                    index_code='000905', name='中证500', exchange='SH', source='sina', is_core=True, core_rank=2
                ),
                IndexCatalog(index_code='399001', name='深证成指', exchange='SZ', source='sina'),
            ]
        )
        db.commit()
        resp = client.get('/api/search/assets/', query_string={'q': '000'})
        index_hits = [
            i for i in resp.get_json()['data'] if i['asset_type'] == 'index' and i['extra'].get('is_core') is not None
        ]
        core_first = [i['code'] for i in index_hits if i['extra']['is_core']]
        # 核心按 core_rank 升序置顶：沪深300(1) 先于 中证500(2)
        assert core_first[:2] == ['SH000300', 'SH000905']

    def test_portfolio_hit_with_platform(self, client, db):
        _seed(db)
        resp = client.get('/api/search/assets/', query_string={'q': '越海'})
        hit = next(i for i in resp.get_json()['data'] if i['code'] == 'XCOVSEX')
        assert hit['asset_type'] == 'portfolio'
        # 无市场实体：market/venue 空串（#1286 约定）
        assert hit['market'] == ''
        assert hit['venue'] == ''
        assert hit['extra']['platform'] == 'TIANTIAN'

    def test_manager_hit_with_prefix(self, client, db):
        _seed(db)
        resp = client.get('/api/search/assets/', query_string={'q': '张坤'})
        hit = next(i for i in resp.get_json()['data'] if i['code'] == 'MGR_abc123def456')
        assert hit['asset_type'] == 'manager'
        assert hit['market'] == ''
        assert hit['extra']['company'] == '易方达基金'

    def test_single_source_failure_does_not_block(self, client, db, monkeypatch):
        """单源抛错不阻断其他品种（Partial failure 容忍）。"""
        _seed(db)
        import app.services.asset_search as mod

        def _boom(db, q):
            raise RuntimeError('boom')

        original = mod.SEARCH_PROVIDERS[0]
        mod.SEARCH_PROVIDERS[0] = _boom
        try:
            resp = client.get('/api/search/assets/', query_string={'q': '110011'})
            assert resp.status_code == 200
            assert any(i['code'] == '110011' for i in resp.get_json()['data'])
        finally:
            mod.SEARCH_PROVIDERS[0] = original
