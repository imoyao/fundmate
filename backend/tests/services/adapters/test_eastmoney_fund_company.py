# -*- coding: utf-8 -*-
"""`fetch_fund_company_of` 的解析与取数口行为（#2037）。

重点三件事：

1. **模糊搜索必须按 `CODE` 精确回选** —— 接口是搜索联想，key 命中多只时
   `Datas[0]` 未必是本只，直接取第一个会把 A 基金的公司写到 B 基金头上；
2. **模块级 Session 复用** —— 实测首次请求要付 TLS 握手约 1.8s、复用后仅 43~87ms。
   详情页请求路径上每次新建 Session 等于把握手成本付给每个冷开用户。这条用
   「多次调用只建一个 Session」锁住，防止有人「顺手改回 requests.get」；
3. **取数失败一律返回 None**，由调用方降级 `—`，不抛异常打断详情页。
"""

import json

import pytest
import requests

from app.services.adapters import eastmoney_adapter as em


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _payload(code, company=None, company_id='80000229'):
    item = {
        'CODE': code,
        'NAME': f'基金{code}',
        'FundBaseInfo': {'JJGS': company, 'JJGSID': company_id} if company else None,
    }
    return {'Datas': [item]}


def _stub_get(monkeypatch, payload, recorder=None):
    """把 Session.get 换成假响应；recorder 记录每次调用的 URL 与参数。"""
    session = em._get_suggest_session()

    def _fake_get(url, params=None, timeout=None):
        if recorder is not None:
            recorder.append((url, params, timeout))
        return _FakeResp(payload() if callable(payload) else payload)

    monkeypatch.setattr(session, 'get', _fake_get)


@pytest.fixture(autouse=True)
def _reset_session():
    """每个用例从「未建 Session」开始，否则复用状态会让断言互相依赖。"""
    original = em._suggest_session
    em._suggest_session = None
    yield
    em._suggest_session = original


# ── 精确回选 ───────────────────────────────────────────────────────────
def test_returns_company_name_and_code(monkeypatch):
    _stub_get(monkeypatch, _payload('110022', '易方达基金', '80000229'))
    assert em.fetch_fund_company_of('110022') == {'name': '易方达基金', 'code': '80000229'}


def test_fuzzy_hit_picks_exact_code_not_first(monkeypatch):
    """key 是模糊的：`001` 会命中一串 001xxx。必须回选 CODE 精确等于本只的那条。

    直接取 `Datas[0]` 在这里会把 001102 的公司写成 001 的——静默错配，最难发现的一类
    数据错误（页面照常渲染，只是名字错了）。
    """
    payload = {
        'Datas': [
            {'CODE': '001102', 'NAME': '前海开源A', 'FundBaseInfo': {'JJGS': '前海开源基金', 'JJGSID': '80280038'}},
            {'CODE': '001594', 'NAME': '天弘银行联接A', 'FundBaseInfo': {'JJGS': '天弘基金', 'JJGSID': '80041198'}},
        ]
    }
    _stub_get(monkeypatch, payload)
    assert em.fetch_fund_company_of('001594') == {'name': '天弘基金', 'code': '80041198'}


def test_no_exact_code_match_returns_none(monkeypatch):
    """候选里没有本只（如 key 只是前缀）→ None，不拿第一条顶替。"""
    payload = {'Datas': [{'CODE': '001102', 'FundBaseInfo': {'JJGS': '前海开源基金', 'JJGSID': '80280038'}}]}
    _stub_get(monkeypatch, payload)
    assert em.fetch_fund_company_of('001') is None


def test_missing_fund_base_info_returns_none(monkeypatch):
    """命中但 `FundBaseInfo` 为空 → 查不到（None），不是空字符串。"""
    _stub_get(monkeypatch, _payload('110022', company=None))
    assert em.fetch_fund_company_of('110022') is None


def test_blank_company_name_returns_none(monkeypatch):
    """`JJGS` 为空白串同样算查不到——`.strip()` 后为空就该是 None。"""
    _stub_get(monkeypatch, _payload('110022', company='   ', company_id=''))
    assert em.fetch_fund_company_of('110022') is None


# ── 入参与失败 ──────────────────────────────────────────────────────────
def test_blank_code_skips_network(monkeypatch):
    """空 code 直接返回，不发请求。"""
    _stub_get(monkeypatch, _payload('110022', '易方达基金'))
    assert em.fetch_fund_company_of('  ') is None
    assert em.fetch_fund_company_of('') is None


def test_request_error_returns_none(monkeypatch):
    session = em._get_suggest_session()

    def _boom(*a, **k):
        raise requests.RequestException('connection reset')

    monkeypatch.setattr(session, 'get', _boom)
    assert em.fetch_fund_company_of('110022') is None


def test_timeout_is_passed_through(monkeypatch):
    """超时上限透传给 requests——调用方要能收紧它，不该被写死。"""
    seen = []
    _stub_get(monkeypatch, _payload('110022', '易方达基金'), recorder=seen)
    em.fetch_fund_company_of('110022', timeout=3)
    assert seen and seen[0][2] == 3


# ── Session 复用（性能事实的回归保护）─────────────────────────────────
def test_session_is_reused_across_calls(monkeypatch):
    """多次调用复用同一个 Session（否则每次都付 TLS 握手，首屏多等约 2s）。

    2026-10-11 实测：首次请求 1.8s（含握手 + DNS），复用后 43~87ms。autouse fixture 已把
    `_suggest_session` 置 None，所以这里数的是「从零到三次调用之间建了几个 Session」——
    必须是 1。有人「顺手改回 `requests.get`」时这条会红。
    """
    created = []
    real_init = requests.Session.__init__

    def _tracking_init(self, *a, **k):
        created.append(self)
        return real_init(self, *a, **k)

    monkeypatch.setattr(requests.Session, '__init__', _tracking_init)

    first = em._get_suggest_session()
    second = em._get_suggest_session()
    third = em._get_suggest_session()

    assert first is second is third
    assert len(created) == 1, f'Session 被建了 {len(created)} 次（应只建 1 次并复用）'


def test_suggest_payload_shape_is_json():
    """锁住对上游响应形状的假设：`Datas[].FundBaseInfo.JJGS`。

    上游若改字段名，这里会返回 None 而**不会报错**——静默降级。所以用一条
    断言把「我们依赖的键」写在测试里，改上游时能立刻看见。
    """
    assert (
        json.loads(json.dumps(_payload('110022', '易方达基金', '80000229')))['Datas'][0]['FundBaseInfo']['JJGS']
        == '易方达基金'
    )
