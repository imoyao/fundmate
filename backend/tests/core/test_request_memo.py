# -*- coding: utf-8 -*-
"""`core/request_memo`：请求内家庭级复用的开关语义。

为什么值得单独钉：这个缓存一旦「默认生效」，`Session.info` 会活到会话结束，
写库后复用旧值 ⇒ 批跑与「先算一遍再改数据再算一遍」的回归会拿到过期结果。
故默认必须关，且退出上下文必须清空——两条都是行为契约，不是实现细节。
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.request_memo import memoized, request_memo


@pytest.fixture()
def session():
    engine = create_engine('sqlite://')
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def test_默认不缓存_每次都调用(session):
    calls = []

    def fn():
        calls.append(1)
        return len(calls)

    assert memoized(session, 'k', fn) == 1
    assert memoized(session, 'k', fn) == 2  # 未进上下文 ⇒ 不缓存
    assert len(calls) == 2


def test_上下文内同键只算一次(session):
    calls = []

    def fn():
        calls.append(1)
        return 'v'

    with request_memo(session):
        assert memoized(session, 'k', fn) == 'v'
        assert memoized(session, 'k', fn) == 'v'
    assert len(calls) == 1


def test_不同键互不干扰(session):
    with request_memo(session):
        assert memoized(session, ('a', 1), lambda: 'A') == 'A'
        assert memoized(session, ('a', 2), lambda: 'B') == 'B'


def test_退出上下文后清空_不污染下一次请求(session):
    with request_memo(session):
        memoized(session, 'k', lambda: 'old')
    assert '_family_request_memo' not in session.info
    # 第二遍必须重新计算（同一 session 两次请求：批跑 / 测试常见）
    assert memoized(session, 'k', lambda: 'new') == 'new'


def test_嵌套只由最外层清空(session):
    with request_memo(session):
        memoized(session, 'k', lambda: 'outer')
        with request_memo(session):
            assert memoized(session, 'k', lambda: 'inner') == 'outer'
        assert memoized(session, 'k', lambda: 'x') == 'outer'  # 内层退出不清空
    assert '_family_request_memo' not in session.info
