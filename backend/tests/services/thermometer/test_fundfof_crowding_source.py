# -*- coding: utf-8 -*-
"""fundfof 外部临时源（#1431）的离线用例：开关 / 缓存与降级 / 字段映射 / 主链路优先级。

一律不打网络（HTTP 用 monkeypatch 替身），缓存指向 tmp_path。
"""

import json

import pytest

from app.services.thermometer import fundfof_crowding as fc
from app.services.thermometer import industry_crowding as ic
from app.services.thermometer import sw_industry_source as sw

# 接口真实返回形状（字段名以 2026-09-14 实测为准）
FAKE_ITEMS = [
    {
        'code': '801010.SI',
        'name': '农林牧渔',
        'crowding': 44.4,
        'crowding_pct': 56.95,
        'turnover_ratio': 2.61,
        'turnover_pct': 99.79,
        'turnover_rate': 2.8,
        'turnover_rate_pct': 98.89,
        'ma60_ratio': 9.77,
        'ma60_pct': 4.96,
        'high60_ratio': 33.91,
        'high60_pct': 62.77,
        'margin_ratio': 27.62,
        'margin_pct': 8.11,
        'big_order': 70.57,
        'big_order_pct': None,
    },
    {'code': '801030.SI', 'name': '化工'},  # 缺 crowding 等必需字段：应被跳过
]

FAKE_PAYLOAD = {'success': True, 'trading_day': '2026-09-11', 'data': FAKE_ITEMS}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path, monkeypatch):
    """缓存重定向到 tmp_path：不污染真实 cache 目录，用例互不干扰。"""
    monkeypatch.setattr(fc, 'CACHE_DIR', str(tmp_path))
    monkeypatch.setattr(fc, 'CACHE_FILE', str(tmp_path / 'latest.json'))
    monkeypatch.setenv('FUNDFOF_CROWDING_ENABLED', '1')
    monkeypatch.setenv('FUNDFOF_CROWDING_MERGE_SW_BIAS', '0')  # 默认不触发申万源（另有用例覆盖）


class TestToggle:
    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setenv('FUNDFOF_CROWDING_ENABLED', '0')
        monkeypatch.setattr(fc.requests, 'get', lambda *a, **k: _FakeResp(FAKE_PAYLOAD))
        assert fc.enabled() is False
        assert fc.fetch_fundfof_crowding() == []

    @pytest.mark.parametrize('value', ['0', 'false', 'NO', 'off'])
    def test_off_values(self, monkeypatch, value):
        monkeypatch.setenv('FUNDFOF_CROWDING_ENABLED', value)
        assert fc.enabled() is False

    @pytest.mark.parametrize('value', ['1', 'true', 'yes', ''])
    def test_on_values(self, monkeypatch, value):
        monkeypatch.setenv('FUNDFOF_CROWDING_ENABLED', value)
        assert fc.enabled() is True


class TestMapping:
    def test_fields_and_code_normalization(self):
        recs = fc.to_records({'items': FAKE_ITEMS})
        assert len(recs) == 1  # 缺必需字段的行被跳过
        rec = recs[0]
        assert rec['item_code'] == '801010'  # .SI 后缀归一化，与申万清单口径一致
        assert rec['item_name'] == '农林牧渔'
        assert rec['source'] == 'industry_crowding'
        assert rec['item_type'] == 'industry'
        assert rec['stale'] is False

        data = rec['data']
        assert data['crowding_pct'] == 56.95
        assert data['crowding_value'] == 44.4
        assert data['amount_pct'] == 2.61 and data['amount_pct_rank'] == 99.79
        assert data['turnover'] == 2.8 and data['turnover_rank'] == 98.89
        assert data['ma60_ratio'] == 9.77 and data['ma60_ratio_pct'] == 4.96
        assert data['high60_ratio'] == 33.91 and data['high60_ratio_pct'] == 62.77
        assert data['margin_ratio'] == 27.62 and data['margin_ratio_pct'] == 8.11
        assert data['big_order'] == 70.57
        assert data['big_order_pct'] is None  # 该接口实测为 null，不得用 0 顶替
        assert data['crowd_src'] == 'fundfof'
        assert 'fundfof' in data['note']
        # PB 三列为该接口不提供的维度：必须留空，绝不与其它口径混用
        assert data['multiple'] is None
        assert data['ind_pb'] is None
        assert data['mkt_pb'] is None

    def test_non_numeric_becomes_none(self):
        recs = fc.to_records(
            {'items': [{'code': '801010.SI', 'name': '农林牧渔', 'crowding': 'abc', 'ma60_pct': '--'}]}
        )
        assert recs[0]['data']['crowding_value'] is None
        assert recs[0]['data']['ma60_ratio_pct'] is None

    def test_bool_is_not_a_number(self):
        recs = fc.to_records({'items': [{'code': '801010.SI', 'name': '农林牧渔', 'crowding': True}]})
        assert recs[0]['data']['crowding_value'] is None

    def test_empty_items(self):
        assert fc.to_records({'items': []}) == []
        assert fc.to_records({}) == []


class TestCacheAndDegrade:
    def test_second_call_hits_cache(self, monkeypatch):
        calls = {'n': 0}

        def _get(*a, **k):
            calls['n'] += 1
            return _FakeResp(FAKE_PAYLOAD)

        monkeypatch.setattr(fc.requests, 'get', _get)
        first = fc.fetch_latest()
        assert calls['n'] == 1 and len(first['items']) == 2
        second = fc.fetch_latest()
        assert calls['n'] == 1  # 命中缓存，未再请求
        assert second['trading_day'] == '2026-09-11'

    def test_force_bypasses_cache(self, monkeypatch):
        calls = {'n': 0}

        def _get(*a, **k):
            calls['n'] += 1
            return _FakeResp(FAKE_PAYLOAD)

        monkeypatch.setattr(fc.requests, 'get', _get)
        fc.fetch_latest()
        fc.fetch_latest(force=True)
        assert calls['n'] == 2

    def test_falls_back_to_stale_cache_when_unreachable(self, monkeypatch):
        monkeypatch.setattr(fc.requests, 'get', lambda *a, **k: _FakeResp(FAKE_PAYLOAD))
        fc.fetch_latest()

        # 令缓存"过期"（早于 TTL 窗口），再让接口不可达 → 应降级用旧缓存而非返回空
        with open(fc.CACHE_FILE, encoding='utf-8') as fh:
            payload = json.load(fh)
        payload['_cached_at'] = '2020-01-01T00:00:00'
        with open(fc.CACHE_FILE, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)

        def _boom(*a, **k):
            raise RuntimeError('network down')

        monkeypatch.setattr(fc.requests, 'get', _boom)
        out = fc.fetch_latest()
        assert out is not None and len(out['items']) == 2

    def test_empty_when_unreachable_and_no_cache(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError('network down')

        monkeypatch.setattr(fc.requests, 'get', _boom)
        assert fc.fetch_latest() is None
        assert fc.fetch_fundfof_crowding() == []

    def test_bad_shape_does_not_write_cache(self, monkeypatch):
        monkeypatch.setattr(
            fc.requests, 'get', lambda *a, **k: _FakeResp({'success': False, 'message': 'boom'})
        )
        assert fc.fetch_latest() is None
        assert not fc._read_cache_any_age()


class TestMergeBias:
    def test_patches_bias_from_sw_source(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {'801010': '农林牧渔'})
        monkeypatch.setattr(
            sw,
            'fetch_sw_metrics',
            lambda *a, **k: {'801010': {'bias6': 1.5, 'bias20': -2.0, 'bias60': 3.5}},
        )
        recs = fc.to_records({'items': FAKE_ITEMS})
        fc._merge_sw_bias(recs)
        assert recs[0]['data']['bias6'] == 1.5
        assert recs[0]['data']['bias20'] == -2.0
        assert recs[0]['data']['bias60'] == 3.5

    def test_failure_is_silent(self, monkeypatch):
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: (_ for _ in ()).throw(RuntimeError('boom')))
        recs = fc.to_records({'items': FAKE_ITEMS})
        fc._merge_sw_bias(recs)  # 不得抛异常
        assert 'bias6' not in recs[0]['data']

    def test_sw_source_partial_coverage(self, monkeypatch):
        """申万源只覆盖部分行业时：未覆盖的行保持无 BIAS 字段，不影响其它字段。"""
        monkeypatch.setattr(sw, 'list_sw_industries', lambda: {'801010': '农林牧渔', '801030': '化工'})
        monkeypatch.setattr(sw, 'fetch_sw_metrics', lambda *a, **k: {'801030': {'bias6': 9.9}})
        recs = fc.to_records({'items': [FAKE_ITEMS[0], {**FAKE_ITEMS[0], 'code': '801030.SI', 'name': '化工'}]})
        fc._merge_sw_bias(recs)
        by_code = {r['item_code']: r for r in recs}
        assert 'bias6' not in by_code['801010']['data']
        assert by_code['801030']['data']['bias6'] == 9.9
        assert by_code['801010']['data']['crowding_pct'] == 56.95  # 主数据未受影响


class TestMainChainPriority:
    def test_external_source_takes_precedence(self, monkeypatch):
        """外部源有数据时优先返回，且不再走 PB / 申万 / legulegu 路径。"""
        monkeypatch.setattr(ic, 'fetch_fundfof_crowding', lambda: [{'item_code': '801010'}])
        monkeypatch.setattr(ic, 'market_pb_series', lambda: (None, {'src': 'unreachable'}))
        assert ic.fetch_industry_crowding() == [{'item_code': '801010'}]

    def test_falls_through_when_external_empty(self, monkeypatch):
        """外部源为空（关停/不可达）时，行为与接入前一致：回落原三路径。"""
        monkeypatch.setattr(ic, 'fetch_fundfof_crowding', lambda: [])
        monkeypatch.setattr(ic, 'market_pb_series', lambda: (None, {'src': 'unreachable'}))
        monkeypatch.setattr(ic, '_sw_share_records', lambda: [{'item_code': '801030'}])
        assert ic.fetch_industry_crowding() == [{'item_code': '801030'}]
