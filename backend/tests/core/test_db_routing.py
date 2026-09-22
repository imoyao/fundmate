# -*- coding: utf-8 -*-
"""按表域路由回归（#1085 的结论 / #1608 的查询期解析）：user 域表 → user_engine，其余 → engine。

#1608 把路由从「会话构造期注入全表 binds」改为**查询期按语句解析**
（`database._domain_for_statement` + `_RoutingSession.get_bind`），故本文件由
「检查内部映射字典」改为**行为断言**：给一条语句，看解析到哪个引擎。

覆盖按 `DATA_DOMAIN_REGISTRY`（唯一事实源）与 `Base.metadata` 的**全部交集**遍历，
不挑代表表——漏判一张 user 表的后果是**静默读错库**（跨库约束见 `decisions.md` D34），
只断言 Family / Fund 两张时，此后新增的表完全不在保护范围内。真实落库的跨引擎断言见
`tests/core/test_db_data_domain.py`。

**不覆盖**（与旧实现一致，非本卡引入）：经辅助函数的间接拼装、跨函数传递后再拼装、
字符串原始 SQL（`text()`）—— 后者无法判定域，按旧实现的默认 bind 落**应用域**。
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select, text
from sqlalchemy.pool import StaticPool

from app.core import database
from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER


def _registered_tables() -> list:
    """(表名, 域)：既已登记、又随模型 import 进了 ``Base.metadata`` 的表。"""
    return [
        (name, DATA_DOMAIN_REGISTRY[name])
        for name in sorted(database.Base.metadata.tables)
        if name in DATA_DOMAIN_REGISTRY
    ]


_ROUTED = _registered_tables()


@pytest.fixture
def routed_engines(app, monkeypatch):
    """两个域引擎各换成独立内存引擎（**依赖 app**：确保在 conftest 的重定向之后生效）。"""
    app_eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    user_eng = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    monkeypatch.setattr(database, 'engine', app_eng)
    monkeypatch.setattr(database, 'user_engine', user_eng)
    return app_eng, user_eng


def test_routing_matrix_is_not_empty():
    """防假绿：模型未 import（metadata 空）时下面的参数化会**空转通过**，此处显式兜底。"""
    assert len(_ROUTED) >= 20, f'路由矩阵只有 {len(_ROUTED)} 张表，疑似模型未 import'


@pytest.mark.parametrize('table_name,domain', _ROUTED, ids=[name for name, _ in _ROUTED])
def test_statement_routes_to_its_domain_engine(routed_engines, table_name, domain):
    """每张已登记表：以表为 clause 的语句必须解析到本域引擎。"""
    app_eng, user_eng = routed_engines
    expected = user_eng if domain == DOMAIN_USER else app_eng
    session = database.SessionLocal()
    try:
        assert session.get_bind(clause=select(database.Base.metadata.tables[table_name])) is expected
    finally:
        session.close()


def test_orm_mapper_routes_by_persist_selectable(routed_engines):
    """ORM 路径（有 mapper、无 clause）：按 ``persist_selectable`` 定域。"""
    from app.domains.watchlist.models import WatchlistItem

    _, user_eng = routed_engines
    session = database.SessionLocal()
    try:
        assert session.get_bind(mapper=WatchlistItem) is user_eng
    finally:
        session.close()


def test_bindless_call_falls_back_to_app_engine(routed_engines):
    """无 mapper、无 clause（如 ``session.connection()``）→ 应用域，与旧默认 bind 一致。"""
    app_eng, _ = routed_engines
    session = database.SessionLocal()
    try:
        assert session.get_bind() is app_eng
    finally:
        session.close()


def test_raw_text_sql_falls_back_to_app_engine(routed_engines):
    """字符串原始 SQL 无法判定域 → 应用域（与旧实现「未命中 binds」一致）。"""
    app_eng, _ = routed_engines
    session = database.SessionLocal()
    try:
        assert session.get_bind(clause=text('SELECT 1')) is app_eng
    finally:
        session.close()


def test_ad_hoc_table_with_same_name_is_not_routed(routed_engines):
    """**身份**判据：别的 ``MetaData`` 上的同名表不参与路由。

    旧实现以 ``Table`` **对象**为 binds 的键，故同样不命中；本用例把这个语义钉住，
    防「按名字匹配」的实现把 ad-hoc 表误路由到 user 域（那会静默连到另一个库）。
    """
    app_eng, _ = routed_engines
    ad_hoc = Table('users', MetaData(), Column('id', Integer, primary_key=True))
    session = database.SessionLocal()
    try:
        assert session.get_bind(clause=select(ad_hoc)) is app_eng
    finally:
        session.close()
