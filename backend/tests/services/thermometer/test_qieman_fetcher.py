# -*- coding: utf-8 -*-
"""测试且慢 MCP 客户端重构（#1392）：通用 _call_tool + fetch_strategy_composition 解析。

不依赖真实 QIEMAN_API_KEY / 组合代码：
  · monkeypatch ``_call_tool`` 注入各类 JSON 形状；
  · monkeypatch 环境变量 ``QIEMAN_API_KEY``——CI 未配置该 secret，缺 key 会让被测方法
    在调用 ``_call_tool`` **之前**就早退，这正是本文件此前在 CI 全红（返回空列表）的根因。

覆盖三档形状：
  · 真实结构（实测 2026-09）：{strategy_code: {基金类别: {持有成分: [...]}}}，占比为 "4.54%" 字符串；
  · 扁平容器兜底：顶层 list / {result|data: [...]}，字段为英文键；
  · 脏数据：非 dict 元素、缺少基金代码的记录。
"""

import json

import pytest

from app.services.thermometer.fetchers import QiemanFetcher

# 归一化后每条记录的字段集合，用于校验 schema 稳定（新增字段时此处会先失败）
SCHEMA_KEYS = {'code', 'name', 'ratio', 'category', 'nav', 'nav_date', 'adj_time', 'fund_type'}


@pytest.fixture(autouse=True)
def _fake_api_key(monkeypatch):
    """提供假的 QIEMAN_API_KEY，避免未配置分支提前返回。"""
    monkeypatch.setenv('QIEMAN_API_KEY', 'test-key')


def _make_fetcher(monkeypatch, payload) -> QiemanFetcher:
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', lambda api_key, tool, args: payload)
    return f


def _assert_schema(rec: dict) -> None:
    assert isinstance(rec, dict)
    assert set(rec) == SCHEMA_KEYS


def _codes(out):
    return [i['code'] for i in out]


# 真实 MCP 返回结构（实测 2026-09）：按基金类别分桶，占比为带百分号的字符串
REAL_PAYLOAD = json.dumps(
    {
        'ZH008005': {
            '权益类': {
                '持有成分': [
                    {
                        '基金代码': '110011',
                        '基金名称': '易方达中小盘',
                        '持仓占比': '32.5%',
                        '最新净值': '5.1230',
                        '最新净值日期': '2026-09-09',
                        '调仓时间': '2026-06-30',
                        '基金类型': '混合型',
                    },
                    {'基金代码': '161725', '基金名称': '招商中证白酒', '持仓占比': '18.0%'},
                ],
                '分类占比': '50.5%',
            },
            '债券类': {
                '持有成分': [{'基金代码': '000001', '基金名称': '华夏成长', '持仓占比': '10%'}],
                '分类占比': '10%',
            },
        }
    }
)


def test_fetch_strategy_composition_real_bucketed_shape(monkeypatch):
    """主路径：跨类别打平，百分号占比转 float，并保留类别归属。"""
    f = _make_fetcher(monkeypatch, REAL_PAYLOAD)
    out = f.fetch_strategy_composition('ZH008005')

    assert _codes(out) == ['110011', '161725', '000001']
    for rec in out:
        _assert_schema(rec)

    first = out[0]
    assert first['name'] == '易方达中小盘'
    assert first['ratio'] == 32.5  # "32.5%" → 32.5
    assert first['category'] == '权益类'
    assert first['nav'] == 5.123
    assert first['nav_date'] == '2026-09-09'
    assert first['adj_time'] == '2026-06-30'
    assert first['fund_type'] == '混合型'

    # 缺字段的记录补 None / 默认值，不抛异常
    second = out[1]
    assert second['ratio'] == 18.0
    assert second['category'] == '权益类'
    assert second['nav'] is None
    assert second['nav_date'] is None
    assert second['adj_time'] is None
    assert second['fund_type'] is None

    assert out[2]['category'] == '债券类'
    assert out[2]['ratio'] == 10.0


def test_fetch_strategy_composition_list_shape(monkeypatch):
    """兜底：顶层直接是持仓数组（英文键 + 数值占比）。"""
    payload = json.dumps(
        [
            {'code': '110011', 'name': '易方达中小盘', 'ratio': 32.5},
            {'code': '161725', 'name': '招商中证白酒', 'weight': 18.0},
        ]
    )
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZH008005')

    assert len(out) == 2
    assert out[0]['code'] == '110011'
    assert out[0]['name'] == '易方达中小盘'
    assert out[0]['ratio'] == 32.5
    assert out[0]['category'] is None
    assert out[1]['code'] == '161725'
    assert out[1]['ratio'] == 18.0


def test_fetch_strategy_composition_dict_result_shape(monkeypatch):
    """兜底：{result: [...]} 扁平容器。"""
    payload = json.dumps({'result': [{'fundCode': '000001', 'fundName': '华夏成长', 'ratio': 10.0}]})
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZH006678')

    assert len(out) == 1
    assert out[0]['code'] == '000001'
    assert out[0]['name'] == '华夏成长'
    assert out[0]['ratio'] == 10.0


def test_fetch_strategy_composition_dict_data_shape(monkeypatch):
    """兜底：{data: [...]} 扁平容器（且慢部分版本用 data 承载）。"""
    payload = json.dumps({'data': [{'fundCode': '000002', 'fundName': '华夏大盘', 'ratio': '7.5%'}]})
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZH006678')

    assert len(out) == 1
    assert out[0]['ratio'] == 7.5


def test_fetch_strategy_composition_empty(monkeypatch):
    f = _make_fetcher(monkeypatch, json.dumps({'result': []}))
    assert f.fetch_strategy_composition('ZHX') == []


def test_fetch_strategy_composition_unknown_shape_returns_empty(monkeypatch):
    """结构完全不可识别（既无对应 code 键、也不是扁平容器）时返回空，而不是抛异常。"""
    f = _make_fetcher(monkeypatch, json.dumps({'error': 'invalid strategy'}))
    assert f.fetch_strategy_composition('ZH008005') == []


def test_fetch_strategy_composition_skips_non_dict(monkeypatch):
    payload = json.dumps(['not-an-object', {'code': '110011', 'ratio': 5.0}])
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZHX')

    assert _codes(out) == ['110011']
    assert out[0]['ratio'] == 5.0
    assert out[0]['name'] == ''


def test_fetch_strategy_composition_skips_missing_code(monkeypatch):
    """缺基金代码的持仓记录直接丢弃（无法作为归因主键）。"""
    payload = json.dumps({'result': [{'name': '没有代码', 'ratio': 1.0}, {'code': '110011', 'ratio': 2.0}]})
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZHX')

    assert _codes(out) == ['110011']


def test_fetch_strategy_composition_skips_non_dict_bucket(monkeypatch):
    """分桶值不是对象（如直接是字符串/数字）时跳过该桶，不影响其它桶。"""
    payload = json.dumps({'ZHX': {'坏桶': 'oops', '好桶': {'持有成分': [{'基金代码': '000003'}]}}})
    f = _make_fetcher(monkeypatch, payload)
    out = f.fetch_strategy_composition('ZHX')

    assert _codes(out) == ['000003']


def test_fetch_strategy_composition_without_api_key(monkeypatch):
    """未配置 key 时早退并返回空列表，不发起任何 MCP 调用。"""
    monkeypatch.delenv('QIEMAN_API_KEY', raising=False)
    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', lambda *a, **kw: pytest.fail('未配置 key 时不应调用 MCP'))

    assert f.fetch_strategy_composition('ZH008005') == []


def test_fetch_strategy_composition_call_failure(monkeypatch):
    """MCP 调用抛异常（网络/协议错误）时吞掉并返回空列表，不影响聚合主链路。"""

    def _boom(*_args, **_kwargs):
        raise RuntimeError('MCP 调用返回为空')

    f = QiemanFetcher()
    monkeypatch.setattr(f, '_call_tool', _boom)

    assert f.fetch_strategy_composition('ZH008005') == []


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
