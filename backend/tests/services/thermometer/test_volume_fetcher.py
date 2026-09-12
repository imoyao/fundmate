# -*- coding: utf-8 -*-
"""EastmoneyVolumeFetcher：东财 push2 不可用时的新浪兜底（#1431）。"""

import pytest

from app.services.thermometer.fetchers import EastmoneyVolumeFetcher

_SINA_BODY = (
    'var hq_str_s_sh000001="上证指数,3888.1106,-46.2930,-1.18,5791231,95818634";\n'
    'var hq_str_s_sz399001="深证成指,13471.26,-146.413,-1.08,636088924,101371215";\n'
    'var hq_str_s_bj899050="北证50,1023.463,-27.950,-2.658,767839546,15291306142.000";'
)


class _FakeResp:
    def __init__(self, text: str):
        self.text = text
        self.encoding = None

    def raise_for_status(self):
        return None


def test_fetch_sina_volume_parses_three_boards(monkeypatch):
    """新浪三板块成交额解析 + 单位换算（沪/深 万元、北证 元）。"""
    f = EastmoneyVolumeFetcher()
    monkeypatch.setattr(f.session, 'get', lambda *a, **k: _FakeResp(_SINA_BODY))

    out = f._fetch_sina()

    assert out is not None
    assert out['raw']['source'] == 'sina'
    assert out['raw']['parts']['上证'] == pytest.approx(9581.9, abs=0.1)
    assert out['raw']['parts']['深证'] == pytest.approx(10137.1, abs=0.1)
    assert out['raw']['parts']['北证'] == pytest.approx(152.9, abs=0.1)
    assert out['value'] == pytest.approx(19871.9, abs=0.2)


def test_fetch_sina_volume_returns_none_when_board_missing(monkeypatch):
    """某板块字段缺失时整体返回 None（不产出残缺值）。"""
    f = EastmoneyVolumeFetcher()
    body = 'var hq_str_s_sh000001="上证指数,3888.1106,-46.2930,-1.18,5791231,95818634";'
    monkeypatch.setattr(f.session, 'get', lambda *a, **k: _FakeResp(body))

    assert f._fetch_sina() is None


def test_fetch_falls_back_to_sina_when_eastmoney_fails(monkeypatch):
    """东财全失败时 fetch() 自动回退新浪通道。"""
    f = EastmoneyVolumeFetcher()
    monkeypatch.setattr(f, '_fetch_eastmoney', lambda: None)
    monkeypatch.setattr(f.session, 'get', lambda *a, **k: _FakeResp(_SINA_BODY))

    out = f.fetch()

    assert out is not None
    assert out['raw']['source'] == 'sina'
