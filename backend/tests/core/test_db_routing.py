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


def _registered_entities() -> list:
    """(实体类, 域)：已登记表对应的 ORM 实体类。

    与 `_ROUTED` 同源（`DATA_DOMAIN_REGISTRY` ∩ `Base.metadata`），但走 **实体** 而非
    裸表——`select(Entity)` 的 FROM 是 `AnnotatedTable` 注解包装，与 `select(Table)`
    不是同一条代码路径，必须单独立保护（见下方 entity 路由用例的教训）。
    """
    return sorted(
        (
            (mapper.class_, DATA_DOMAIN_REGISTRY[mapper.local_table.name])
            for mapper in database.Base.registry.mappers
            if mapper.local_table.name in DATA_DOMAIN_REGISTRY
        ),
        key=lambda pair: pair[0].__name__,
    )


_ENTITIES = _registered_entities()


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


def test_entity_registry_is_not_empty():
    """防假绿：实体矩阵空转时下面的参数化会静默通过。"""
    assert len(_ENTITIES) >= 20, f'实体矩阵只有 {len(_ENTITIES)} 个，疑似模型未 import'


@pytest.mark.parametrize('entity,domain', _ENTITIES, ids=[cls.__name__ for cls, _ in _ENTITIES])
def test_orm_entity_select_routes_to_its_domain_engine(routed_engines, entity, domain):
    """**clause 路径的真实形态**：`select(Entity)` / `db.query(Entity)` → 本域引擎。

    线上 500 的根因用例（2026-10-12 AI 批量导入自选全 500）：ORM 实体 select 的 FROM
    节点是 `AnnotatedTable` 注解包装，**不是** `Base.metadata` 里的裸 Table，旧实现按
    identity 比对必然落空 → 返回 None → 误回落 APP 引擎。dev 单库下 flush（走 mapper
    正确落 user 引擎）与 refresh 的 SELECT（误落 app 引擎、另一条连接）分属两条连接，
    app 侧读不到 user 事务里**未提交**的行 → `Could not refresh instance`。
    裸表矩阵（上方用例）覆盖不到这条路径，故单独立保护。
    """
    app_eng, user_eng = routed_engines
    expected = user_eng if domain == DOMAIN_USER else app_eng
    session = database.SessionLocal()
    try:
        assert session.get_bind(clause=select(entity)) is expected
    finally:
        session.close()


def test_flush_then_refresh_reads_own_uncommitted_row(tmp_path):
    """端到端复现线上 500：同文件双引擎（dev 单库双引擎形态）下，add+flush 后 refresh
    必须读到**自己事务里刚写入的行**（读己之写）。

    两个独立 Engine 连同一个 SQLite 文件、各自持有独立连接——修复前 INSERT 走 user
    引擎、refresh 的 SELECT 因 AnnotatedTable 误回落 app 引擎（另一连接、看不到未提交
    行）→ `sqlalchemy.exc.InvalidRequestError: Could not refresh instance`，
    即 `watchlist.views.create_item` 的 500（logs/fundmate_2026-10-12.log:1138-1149）。

    ⚠️ 用**局部** MonkeyPatch（不用函数级 monkeypatch 夹具）：autouse 的 `clean_db`
    teardown 与本测试共享同一个函数级 monkeypatch 实例，若用共享实例，清理会在
    patch 仍生效时把被测引擎当库去清表（实测 database is locked）。局部实例在
    finally 里 undo，clean_db 之后看到的是 app 夹具的正常引擎。
    """
    from app.domains.watchlist.models import WatchlistItem

    url = f'sqlite:///{tmp_path / "routing.db"}'
    app_eng = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30})
    user_eng = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30})
    mp = pytest.MonkeyPatch()
    session = None
    try:
        mp.setattr(database, 'engine', app_eng)
        mp.setattr(database, 'user_engine', user_eng)
        database.Base.metadata.create_all(user_eng)

        session = database.SessionLocal()
        item = WatchlistItem(
            symbol='__ROUTING_PROBE__',
            market='CN_A',
            venue='OTC',
            asset_type='fund',
            status='WATCHING',
            family_id=1,
        )
        session.add(item)
        session.flush()
        session.refresh(item)  # 修复前在此抛 InvalidRequestError: Could not refresh instance
        assert item.id is not None
        assert session.get_bind(clause=select(WatchlistItem)) is user_eng
    finally:
        if session is not None:
            session.rollback()
            session.close()
        # Windows 下 tmp_path 清理要求文件句柄已释放：引擎池不 dispose 会留下
        # 未关闭连接 → teardown PermissionError
        app_eng.dispose()
        user_eng.dispose()
        mp.undo()
