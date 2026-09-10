# -*- coding: utf-8 -*-
"""测试且慢 MCP 客户端重构（#1392）：通用 _call_tool + fetch_strategy_composition 容错解析。

不依赖真实 QIEMAN_API_KEY / 组合代码：直接 monkeypatch `_call_tool` 返回各类 JSON 形状，
覆盖 list / dict.result / dict.data 三种且慢返回结构。
"""

import json

from app.services.thermometer.fetchers import QiemanFetcher


def _make_fetcher(monkeypatch, payload) -> QiemanFetcher:
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', lambda api_key, tool, args: payload)
    return f


def test_fetch_strategy_composition_list_shape(monkeypatch):
    # 且慢直接返回持仓数组
    payload = json.dumps(
        [
            {'code': '110011', 'name': '易方达中小盘', 'ratio': 32.5},
            {'code': '161725', 'name': '招商中证白酒', 'weight': 18.0},
        ]
    )
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZH008005')
    assert len(out) == 2
    assert out[0] == {'code': '110011', 'name': '易方达中小盘', 'ratio': 32.5}
    assert out[1]['code'] == '161725'
    assert out[1]['ratio'] == 18.0


def test_fetch_strategy_composition_dict_result_shape(monkeypatch):
    # 且慢返回 {result: [...]} 形状
    payload = json.dumps({'result': [{'fundCode': '000001', 'fundName': '华夏成长', 'ratio': 10.0}]})
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZH006678')
    assert out == [{'code': '000001', 'name': '华夏成长', 'ratio': 10.0}]


def test_fetch_strategy_composition_empty(monkeypatch):
    f = _make_fetcher(monkeypatch, json.dumps({'result': []}))
    assert f.fetch_strategy_composition('ZHX') == []


def test_fetch_strategy_composition_skips_non_dict(monkeypatch):
    payload = json.dumps(['not-an-object', {'code': '110011', 'ratio': 5.0}])
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZHX')
    assert out == [{'code': '110011', 'name': '', 'ratio': 5.0}]


def test_fetch_temperature_still_works(monkeypatch):
    """重构后温度主链路不能回归：_call_tool 返回温度列表，fetch() 取 000985 为主。"""
    payload = json.dumps(
        [
            {'temperatureIndexCode': '000985', 'indexName': '中证全A', 'temperature': 42.0, 'ratingText': '正常'},
            {'temperatureIndexCode': '000300', 'indexName': '沪深300', 'temperature': 50.0, 'ratingText': '偏高'},
        ]
    )
    f = _make_fetcher(monkeypatch, payload)
    rec = f.fetch()
    assert rec is not None
    assert rec['value'] == 42.0  # 主指数 000985
