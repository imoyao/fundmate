# -*- coding: utf-8 -*-
"""#1431：行业拥挤度「申万官网单源」路径与降级闭环的离线用例（不打网络）。

覆盖两件事：
1. `_sw_share_records()` 的产出形状（申万代码 / 占比分位 / BIASn / crowding_pct 为空 / note）；
2. `fetch_industry_crowding()` 在 PB 源不可用时**先降级到申万路径**、两者都不可用才整组标灰。
"""

from app.services.thermometer import industry_crowding as ic
from app.services.thermometer import sw_industry_source as sw


def _fake_metrics():
    return {
        '801010': {
            'amount_pct': 12.5,
            'amount_pct_rank': 88.0,
            'history_days': 2000,
            'bias6': 1.2,
            'bias20': -0.5,
            'bias60': -3.0,
        },
        '801030': {
            'amount_pct': 3.0,
            'amount_pct_rank': 15.0,
            'history_days': 2000,
            'bias6': 0.1,
            'bias20': 0.2,
            'bias60': 0.3,
        },
    }


class TestSwShareRecords:
    def test_shapes_and_fields(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {'801010': '农林牧渔', '801030': '化工'})
        monkeypatch.setattr(sw, 'fetch_sw_metrics', lambda *a, **k: _fake_metrics())

        recs = ic._sw_share_records()
        assert len(recs) == 2
        by_code = {r['item_code']: r for r in recs}
        r = by_code['801010']
        assert r['item_name'] == '农林牧渔'
        assert r['source'] == 'industry_crowding'
        assert r['item_type'] == 'industry'
        assert r['stale'] is False
        assert r['data']['amount_pct'] == 12.5
        assert r['data']['amount_pct_rank'] == 88.0
        assert r['data']['bias6'] == 1.2
        assert r['data']['bias20'] == -0.5
        assert r['data']['bias60'] == -3.0
        # 本路径无 PB 源：估值维为空、换手率维为空（东财不可用即空，决策 B 保留列）
        assert r['data']['crowding_pct'] is None
        assert r['data']['turnover'] is None
        assert r['data']['amount_src'] == 'sw_industry_official'
        assert '申万宏源官网' in r['data']['note']

    def test_empty_when_no_industries(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {})
        assert ic._sw_share_records() == []

    def test_empty_when_no_metrics(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {'801010': '农林牧渔'})
        monkeypatch.setattr(sw, 'fetch_sw_metrics', lambda *a, **k: {})
        assert ic._sw_share_records() == []

    def test_skips_rows_without_rank(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {'801010': '农林牧渔', '801030': '化工'})
        monkeypatch.setattr(
            sw,
            'fetch_sw_metrics',
            lambda *a, **k: {'801010': {'amount_pct': 1.0, 'amount_pct_rank': 10.0}, '801030': {'amount_pct': 2.0}},
        )
        recs = ic._sw_share_records()
        assert [r['item_code'] for r in recs] == ['801010']

    def test_never_raises(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        assert ic._sw_share_records() == []


class TestFetchIndustryCrowdingFallback:
    def test_falls_back_to_sw_path_when_pb_unavailable(self, monkeypatch):
        monkeypatch.setattr(ic, 'market_pb_series', lambda: (None, {'src': 'unavailable'}))
        monkeypatch.setattr(ic, '_sw_share_records', lambda: [{'item_code': '801010', 'source': 'industry_crowding'}])
        out = ic.fetch_industry_crowding()
        assert len(out) == 1
        assert out[0]['item_code'] == '801010'

    def test_placeholder_when_both_sources_unavailable(self, monkeypatch):
        monkeypatch.setattr(ic, 'market_pb_series', lambda: (None, {'src': 'unavailable'}))
        monkeypatch.setattr(ic, '_sw_share_records', lambda: [])
        out = ic.fetch_industry_crowding()
        assert len(out) == 1
        assert out[0]['item_code'] == '__NA__'
        assert out[0]['stale'] is True
        assert '申万官网源均不可用' in out[0]['data']['note']


class TestSwIndustryListAligned:
    def test_sw_industry_dict_matches_current_31(self):
        """决策 D：清单对齐申万现行 31 个——剔除过时 801020，补入 2021 版新增 4 个。"""
        codes = {c.split('.')[0] for c in ic.SW_INDUSTRY.values()}
        assert len(codes) == sw.EXPECTED_INDUSTRY_COUNT
        assert '801020' not in codes
        assert {'801950', '801960', '801970', '801980'} <= codes
