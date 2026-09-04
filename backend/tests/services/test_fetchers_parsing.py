# -*- coding: utf-8 -*-
"""fetchers 解析鲁棒性测试（离线，不触网）。

固化两类线上「运行时才暴露」的崩溃：
  1. 集思录估值指标 fetch 在字段改版为字符串时，label_temp 不应抛 str-vs-int 比较错误，
     且应正常产出 median_pb_level / median_pe_level。
  2. 自算估值分位 SelfCalcFetcher._producer 在 akshare 接口返回 None / 空 DataFrame
     （限流 / 被拦 / 返回空响应）时应安全返回 None，而非抛出 JSONDecodeError 之类异常。
"""

from unittest.mock import MagicMock

import pandas as pd

from app.services.thermometer.fetchers import JisiluIndicatorFetcher, SelfCalcFetcher


class _FakeResp:
    """极简 requests.Response 替身，仅实现 .json()。"""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _patch_jisilu(monkeypatch, payload):
    fetcher = JisiluIndicatorFetcher()
    monkeypatch.setattr(fetcher, '_get', lambda *a, **k: _FakeResp(payload))
    return fetcher


def test_jisilu_valuation_string_fields_do_not_crash(monkeypatch):
    # 集思录改版：温度字段变为字符串（线上崩溃根因的复现输入）
    payload = {
        'price_dt': '2026-08-02',
        'median_pb': '1.62',
        'median_pb_temperature': '22.75',
        'median_pe': '15.3',
        'median_pe_temperature': '48.2',
        'stock_count': '5000',
        'IPO_count': '0',
        'st_count': '120',
        'index_point': '3200.5',
    }
    fetcher = _patch_jisilu(monkeypatch, payload)
    result = fetcher.fetch()
    assert result is not None
    data = result['data']
    # 字段应被成功解析为数值，level 不应因字符串比较而缺失
    assert data['median_pb_temperature'] == 22.75
    assert data['median_pb_level'] == '偏低'
    assert data['median_pe_level'] == '适中'


def test_jisilu_valuation_dirty_fields_return_unknown_level(monkeypatch):
    # 脏值字段：解析失败应落到 '未知'，而非崩溃
    payload = {
        'price_dt': '2026-08-02',
        'median_pb_temperature': '--',
        'median_pe_temperature': 'N/A',
    }
    fetcher = _patch_jisilu(monkeypatch, payload)
    result = fetcher.fetch()
    assert result is not None
    assert result['data']['median_pb_level'] == '未知'
    assert result['data']['median_pe_level'] == '未知'


def test_self_calc_handles_none_dataframe(monkeypatch):
    # akshare 接口返回 None（限流 / 异常）→ fetch 应优雅返回 None，不抛异常
    fetcher = SelfCalcFetcher()
    fake_ak = MagicMock()
    fake_ak.stock_index_pe_lg.return_value = None  # 模拟 stock_index_pe_lg 返回 None
    monkeypatch.setattr('app.core.akshare_lazy._AKSHARE', fake_ak)
    assert fetcher.fetch() is None


def test_self_calc_handles_empty_dataframe(monkeypatch):
    # akshare 接口返回空 DataFrame（被拦 / 空响应）→ fetch 应优雅返回 None
    fetcher = SelfCalcFetcher()
    fake_ak = MagicMock()
    fake_ak.stock_index_pe_lg.return_value = pd.DataFrame()  # 空表
    monkeypatch.setattr('app.core.akshare_lazy._AKSHARE', fake_ak)
    assert fetcher.fetch() is None


def test_self_calc_handles_json_decode_error(monkeypatch):
    # 线上真实场景：akshare 内部 requests.json() 拿到空响应，抛 JSONDecodeError。
    # fetch 的外层 try 必须兜底，返回 None（stale），而非让同步任务崩溃。
    from requests.exceptions import JSONDecodeError

    fetcher = SelfCalcFetcher()
    fake_ak = MagicMock()
    fake_ak.stock_index_pe_lg.side_effect = JSONDecodeError('Expecting value', '', 0)
    monkeypatch.setattr('app.core.akshare_lazy._AKSHARE', fake_ak)
    assert fetcher.fetch() is None
