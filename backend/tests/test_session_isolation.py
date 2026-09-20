# -*- coding: utf-8 -*-
"""#1608 回归：测试隔离不再依赖「模块名清单」式补丁。

核心修复：conftest 不再替换 ``SessionLocal`` maker，而是重定向 ``engine`` / ``user_engine``；
``SessionLocal``（路由 maker）在调用时经 ``_engine_for`` 解析到当前引擎，因此即使服务在
导入期早绑定了 ``SessionLocal``，也会自动走内存库。本文件锁定这一行为，以及
``reset_routing_binds()`` 的失效路径。
"""
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


def test_early_bound_session_resolves_to_redirected_engine(app):
    """导入期早绑定 ``SessionLocal`` 的服务（thermometer.service）在测试里必须连到内存库，
    且不需要 conftest 再为其打补丁（#1608 删除 ``_patch_thermo_session`` 的前提）。

    若 revert 回「换 maker + 逐模块补丁」，早绑定的 maker 仍解析到真实引擎，断言失败。
    """
    import app.core.database as db
    import app.services.thermometer.service as thermo_service

    session = thermo_service.SessionLocal()
    try:
        # db.engine 已被 conftest 重定向为内存引擎；早绑定的 maker 必须解析到它
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
