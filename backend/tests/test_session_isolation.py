# -*- coding: utf-8 -*-
"""#1608 回归：测试隔离不再依赖「模块名清单」式补丁。

核心修复：conftest 不再替换 ``SessionLocal`` maker，而是重定向 ``engine`` / ``user_engine``；
``SessionLocal``（路由 maker）在调用时经 ``_engine_for`` 解析到当前引擎，因此消费方**不需要**
被逐个打补丁，引擎重定向一处即自动落到内存库。本文件锁定这一行为，以及
``reset_routing_binds()`` 的失效路径。

与 #1626 的关系：本文件原先还顺带锁定了「服务在导入期早绑定的 ``SessionLocal`` 仍能解析到
重定向引擎」。``thermometer.service`` 现已改为经 ``database.get_session()`` 晚绑定访问（不再
在模块级持有会话工厂名字），该断言改落在单一入口本身；语义等价，见下方用例 docstring。
"""

from sqlalchemy import create_engine
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


def test_reset_routing_binds_rebuilds_with_current_engine(monkeypatch):
    """``reset_routing_binds()`` 必须让已缓存的域路由 binds 失效，下次 ``SessionLocal()``
    按当前引擎重建（#1608：引擎被替换后旧 binds 不应残留）。"""
    import app.core.database as db
    from app.core.database import Base

    eng_a = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    eng_b = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)

    # 同时重定向两个域引擎，避免 _build_routing_binds 触发真实引擎构造
    monkeypatch.setattr(db, 'engine', eng_a)
    monkeypatch.setattr(db, 'user_engine', eng_a)
    db.reset_routing_binds()
    Base.metadata.create_all(bind=eng_a)
    session_a = db.SessionLocal()
    assert session_a.bind is eng_a
    session_a.close()

    # 切换引擎并失效缓存后，新会话必须解析到新引擎
    monkeypatch.setattr(db, 'engine', eng_b)
    monkeypatch.setattr(db, 'user_engine', eng_b)
    db.reset_routing_binds()
    Base.metadata.create_all(bind=eng_b)
    session_b = db.SessionLocal()
    assert session_b.bind is eng_b
    session_b.close()

    # 清空缓存，避免陈旧 binds 泄漏到后续用例
    db.reset_routing_binds()
