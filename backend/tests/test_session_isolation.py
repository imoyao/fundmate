# -*- coding: utf-8 -*-
"""#1608 回归：测试隔离不再依赖「模块名清单」式补丁。

核心修复：conftest 不再替换 ``SessionLocal`` maker，而是重定向 ``engine`` / ``user_engine``；
``SessionLocal``（路由 maker）在调用时经 ``_engine_for`` 解析到当前引擎，因此消费方**不需要**
被逐个打补丁，引擎重定向一处即自动落到内存库。本文件锁定这一行为，以及
「引擎被替换后，路由**自动**跟随当前引擎」（#1608 起改为查询期解析，已无引擎缓存）。

与 #1626 的关系：本文件原先还顺带锁定了「服务在导入期早绑定的 ``SessionLocal`` 仍能解析到
重定向引擎」。``thermometer.service`` 现已改为经 ``database.get_session()`` 晚绑定访问（不再
在模块级持有会话工厂名字），该断言改落在单一入口本身；语义等价，见下方用例 docstring。
"""

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool


def test_single_entry_session_resolves_to_redirected_engine(app):
    """会话**单一入口** ``get_session()`` 必须解析到 conftest 重定向后的内存引擎。

    这是 conftest 能删掉 ``_patch_thermo_session``（#1608 要消除的「模块名清单」式补丁）的
    前提：引擎重定向生效后，消费方无论经哪条路径开会话，都自动落到内存库。

    演进说明（#1626）：原用例断言的是「服务在导入期早绑定的 ``thermo_service.SessionLocal``
    仍能解析到重定向引擎」。``thermometer.service`` 现已改为经 ``database.get_session()``
    晚绑定访问，服务侧不再持有 ``SessionLocal`` 名字，故断言改落在单一入口本身上；
    断言强度不变（同样是「经路由 maker 解析到重定向引擎」）。

    若 ``get_session()`` 被改成绕过路由 maker（例如直接绑定固定 engine），本用例失败。
    """
    import app.core.database as db

    session = db.get_session()
    try:
        # db.engine 已被 conftest 重定向为内存引擎；单一入口必须解析到它
        assert session.bind is db.engine
    finally:
        session.close()


def test_routing_follows_current_engine_without_any_reset(app, monkeypatch):
    """引擎被替换后，路由**自动**跟随当前引擎 —— 不需要任何「让缓存失效」的调用（#1608）。

    演进说明：旧实现的域路由 binds 在首次开会话时把「表 → 引擎」缓存了下来，故必须显式
    ``reset_routing_binds()``，否则残留旧引擎（原用例断言的就是这条失效路径）。现改为
    **查询期解析**（``database._domain_for_statement`` + ``_RoutingSession.get_bind``），
    已无引擎缓存可残留 ⇒ 断言升级为「**不调用任何 reset** 即跟随当前引擎」——
    比「reset 之后能重建」更强：把旧实现换回来、删掉 reset，本用例即红。
    """
    import app.core.database as db
    from app.core.database import Base

    eng_a = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    eng_b = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    user_table = Base.metadata.tables['users']  # user 域表：必须落 user 引擎

    monkeypatch.setattr(db, 'engine', eng_a)
    monkeypatch.setattr(db, 'user_engine', eng_a)
    session_a = db.SessionLocal()
    assert session_a.bind is eng_a
    assert session_a.get_bind(clause=select(user_table)) is eng_a
    session_a.close()

    # 切换两个域的引擎：**不**调用任何失效函数
    monkeypatch.setattr(db, 'engine', eng_b)
    monkeypatch.setattr(db, 'user_engine', eng_b)
    session_b = db.SessionLocal()
    assert session_b.bind is eng_b
    assert session_b.get_bind(clause=select(user_table)) is eng_b
    session_b.close()
