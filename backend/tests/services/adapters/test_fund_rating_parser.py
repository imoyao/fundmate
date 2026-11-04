# -*- coding: utf-8 -*-
"""测试 AkshareAdapter.fetch_fund_rating 的自写解析与校验（#1440）。

不打网络：构造仿真 `var fundinfos` 响应（字段布局与 2026-10-24 实测一致：
27 字段、pos10/12/14/16 = 招商/上海/晨星/济安 3 年期、pos15 = 晨星 delta、
pos7 = 四家 5 星计数），mock `requests.get` 返回。

覆盖点：正常解析、空评级归一、字段数漂移抛错、评级值越域抛错、delta 越域抛错、
5星家数不自洽抛错、探针缺失抛错、请求异常不吞空。
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.adapters.akshare_adapter import AkshareAdapter

# 27 字段仿真记录。除 pos0/1/2/7/10/12/14/15/16 外其余列填占位值。
_PLACEHOLDER = ['x'] * 27


def _record(code, name, star_count, zs, sh, ms, ms_delta, ja):
    r = list(_PLACEHOLDER)
    r[0], r[1], r[2] = code, name, '混合型-灵活'
    r[3], r[5] = '经理A,经理B', '华夏'
    r[7] = str(star_count)
    r[10], r[12], r[14], r[15], r[16] = zs, sh, ms, ms_delta, ja
    return '|'.join(r)


def _page(*records):
    body = '|_'.join(records)
    return f'<html><script>var fundinfos = "{body}";</script></html>'


# 000001 实测形态（2026-10-24）：四家 0 个 5 星；110011/161725 覆盖另两种类型
_R000001 = _record('000001', '华夏成长混合', 0, '2', '', '3', '-1', '1')
_R110011 = _record('110011', '易方达优质精选混合(QDII)', 0, '4', '2', '1', '0', '3')
_R161725 = _record('161725', '招商中证白酒指数(LOF)A', 0, '4', '1', '1', '0', '1')


@pytest.fixture
def adapter():
    return AkshareAdapter()


class TestFetchFundRating:
    def _run(self, adapter, html, status_ok=True):
        with patch('app.services.adapters.akshare_adapter.requests.get') as g:
            resp = MagicMock()
            resp.text = html
            resp.raise_for_status = MagicMock()
            g.return_value = resp
            return adapter.fetch_fund_rating()

    def test_parses_rating_and_delta(self, adapter):
        rows = self._run(adapter, _page(_R000001, _R110011, _R161725))
        by = {r['fund_code']: r for r in rows}
        assert by['000001'] == {'fund_code': '000001', 'rating': 3, 'delta': -1}
        assert by['110011'] == {'fund_code': '110011', 'rating': 1, 'delta': 0}
        assert by['161725']['rating'] == 1

    def test_empty_rating_normalizes_to_none(self, adapter):
        # 货基/新基金：晨星列空串 → None（不是 0）
        r = _record('000001', '华夏成长混合', 0, '2', '', '', '', '1')
        r2 = _record('110011', '易方达优质精选混合(QDII)', 0, '4', '2', '1', '0', '3')
        r3 = _record('161725', '招商中证白酒指数(LOF)A', 0, '4', '1', '1', '0', '1')
        rows = self._run(adapter, _page(r, r2, r3))
        assert rows[0] == {'fund_code': '000001', 'rating': None, 'delta': None}

    def test_five_star_count_must_be_self_consistent(self, adapter):
        # pos7=1 但四家没有 5 星 → 字段错位信号，抛错
        bad = _record('000001', '华夏成长混合', 1, '2', '', '3', '-1', '1')
        with pytest.raises(ValueError, match='5星评级家数'):
            self._run(adapter, _page(bad, _R110011, _R161725))

    def test_five_star_count_consistent_when_one_five(self, adapter):
        # pos7=1 且晨星=5 → 自洽，正常解析
        r = _record('000001', '华夏成长混合', 1, '2', '', '5', '1', '1')
        rows = self._run(adapter, _page(r, _R110011, _R161725))
        assert rows[0]['rating'] == 5

    def test_field_count_drift_raises(self, adapter):
        short = '|'.join(['x'] * 26)  # 26 字段
        with pytest.raises(ValueError, match='字段数'):
            self._run(adapter, _page(short, _R110011, _R161725))

    def test_rating_out_of_range_raises(self, adapter):
        r = _record('000001', '华夏成长混合', 0, '2', '', '6', '-1', '1')  # 6 星越域
        with pytest.raises(ValueError, match='越域'):
            self._run(adapter, _page(r, _R110011, _R161725))

    def test_delta_out_of_range_raises(self, adapter):
        r = _record('000001', '华夏成长混合', 0, '2', '', '3', '-5', '1')  # |delta|>4
        with pytest.raises(ValueError, match='delta 越域'):
            self._run(adapter, _page(r, _R110011, _R161725))

    def test_probe_missing_raises(self, adapter):
        # 缺 161725 探针 → 上游覆盖异常或结构漂移
        with pytest.raises(ValueError, match='探针缺失'):
            self._run(adapter, _page(_R000001, _R110011))

    def test_no_fundinfos_raises(self, adapter):
        with pytest.raises(ValueError, match='fundinfos'):
            self._run(adapter, '<html>改版了</html>')

    def test_request_error_not_swallowed(self, adapter):
        """网络异常必须上抛（#1179 同族：空 ≠ 没拿到，失败不得吞成 success）。"""
        with patch('app.services.adapters.akshare_adapter.requests.get', side_effect=OSError('conn reset')):
            with pytest.raises(OSError):
                adapter.fetch_fund_rating()
