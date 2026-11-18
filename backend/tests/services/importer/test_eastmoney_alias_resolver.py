# -*- coding: utf-8 -*-
"""EastMoneyAliasResolver 离线单测（不真联网，注入应用 SessionLocal + 假 http）。

覆盖：DB 命中、warm 落库后离线 resolve、跨年复用日期消歧、超窗回落、未知码、
关闭开关、网络失败吞掉、无 session_factory 退化、warm 不重复联网。

DB 由 conftest 的 ``app`` fixture 建好（security_code_aliases 表已随 init_db 落到
路由引擎）；本测试直接复用应用的 ``SessionLocal`` 作为 session_factory——与生产
``cms_stock.py`` 的默认接线完全一致，且共享全局 mapper registry，不会因独立引擎
触发 ``Ledger`` 等跨域关系在配置期找不到 ``Fund`` 的问题。
"""

from datetime import date

import pytest

from app.core.database import SessionLocal
from app.services.importer.eastmoney_alias_resolver import EastMoneyAliasResolver

# 申购码 → [(上市码, 申购日)]。070887 故意造两条不同年份，验证跨年复用消歧。
STORE = {
    '754112': [('113703', '2023-01-05 00:00:00')],
    '370332': [('123092', '2020-12-24 00:00:00')],
    '070887': [
        ('125887', '2011-02-11 00:00:00'),
        ('127119', '2020-10-22 00:00:00'),
    ],
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def make_fake_http(store, call_log=None, fail=False, *, server_cap=None):
    """模拟东财 datacenter 接口。

    关键仿真（2026-11-08 实测行为）：**只认 ``pageNumber`` 参数**——生产踩过的坑是
    resolver 发 ``pageNo``（被服务端忽略，每页都回第一页）+ 以 ``len(data) < page_size``
    判终止（服务端把单页封顶 500，请求 1000 也回 500，第一页后立刻断粮）。fake 故意
    严格：参数名错了就拿不到第 2 页；``server_cap`` 模拟服务端单页封顶。
    """
    rows = [
        {'SECURITY_CODE': listed, 'CORRECODE': apply, 'PUBLIC_START_DATE': issue}
        for apply, pairs in store.items()
        for listed, issue in pairs
    ]

    def fake(url, params=None, headers=None, timeout=None):
        if call_log is not None:
            call_log.append((params or {}).get('pageNumber') if isinstance(params, dict) else 1)
        if fail:
            raise RuntimeError('network down')
        # 故意不认 pageNo/page/pageNum：参数名回归（pageNo）会在拿到 count 前断粮
        page = int((params or {}).get('pageNumber', 1))
        size = int((params or {}).get('pageSize', 500))
        if server_cap is not None:
            size = min(size, server_cap)
        chunk = rows[(page - 1) * size : page * size]
        return _FakeResp({'result': {'data': chunk, 'count': len(rows)}})

    return fake


@pytest.fixture
def factory(app):
    # 复用应用路由会话工厂：与生产 cms_stock.py 接线一致，且表已由 app fixture 建好。
    return SessionLocal


def test_resolve_returns_none_when_disabled(factory):
    r = EastMoneyAliasResolver(session_factory=factory, enabled=False)
    assert r.resolve('754112', date(2023, 1, 10), 'x') is None


def test_warm_then_resolve_offline(factory):
    calls = []
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE, calls))
    r.warm(['754112', '370332'])
    # 落库后离线也能解析
    assert r.resolve('754112', date(2023, 1, 10), '模拟发债') == '113703'
    assert r.resolve('370332', date(2020, 12, 28), '天壕发债') == '123092'
    # 只拉了一页
    assert calls == [1]


def test_warm_does_not_refetch_when_known(factory):
    calls = []
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE, calls))
    r.warm(['754112'])
    r.warm(['754112'])  # 已落库，不应再联网
    assert calls == [1]


def test_cross_year_reuse_picks_nearest(factory):
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE))
    r.warm(['070887'])
    # 2020 中签 → 取 2020 那支
    assert r.resolve('070887', date(2020, 10, 25), 'x') == '127119'
    # 2011 中签 → 取 2011 那支
    assert r.resolve('070887', date(2011, 3, 1), 'x') == '125887'


def test_cross_year_out_of_window_falls_back(factory):
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE))
    r.warm(['070887'])
    # 2026 距两支都 > 5 年 → 无可靠匹配，回落 None（由折叠器走 link_warning）
    assert r.resolve('070887', date(2026, 1, 1), 'x') is None


def test_unknown_code_resolves_none(factory):
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE))
    assert r.resolve('999999', date(2023, 1, 1), 'x') is None


def test_warm_network_failure_is_swallowed(factory):
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(STORE, fail=True))
    # 不应抛异常
    r.warm(['754112'])
    # 库里没数据，回落 None
    assert r.resolve('754112', date(2023, 1, 10), 'x') is None


def test_no_session_factory_degrades_gracefully():
    r = EastMoneyAliasResolver(session_factory=None, http_get=make_fake_http(STORE))
    r.warm(['754112'])  # 无 DB，直接跳过引导
    assert r.resolve('754112', date(2023, 1, 10), 'x') is None


def test_warm_paginates_through_server_capped_pages(factory):
    """回归（2026-11-08 生产事故）：东财单页封顶 500（请求 1000 也只回 500），
    旧实现以 ``len(data) < page_size`` 判终止 → 第一页后断粮，2021 年后发行的
    转债全部缺席；且参数名用了 ``pageNo``（服务端忽略），翻页永远停在第 1 页。
    本用例把两个坑都钉住：server_cap=3 模拟「服务端封顶 < 请求页大小」，
    目标申购码压在第 3 页——参数名或终止条件任一回归，它就拿不到。
    """
    store = {f'0701{i:02d}': [(f'1251{i:02d}', f'2020-05-{i + 1:02d} 00:00:00')] for i in range(7)}
    store['072998'] = [('127078', '2022-12-14 00:00:00')]  # 第 8 行 → 第 3 页
    calls = []
    r = EastMoneyAliasResolver(session_factory=factory, http_get=make_fake_http(store, calls, server_cap=3))
    r.warm(['072998'])
    assert r.resolve('072998', date(2023, 8, 16), '优彩发债') == '127078'
    assert calls == [1, 2, 3]
