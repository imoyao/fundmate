# -*- coding: utf-8 -*-
"""验证 #1085 的按表路由映射：user 域表落到 user_engine，market 域表落到 engine。

无需真实 session，直接校验 database._build_routing_binds() 的表→引擎映射；
真正的跨引擎落库断言由 tests/core/test_db_data_domain.py 覆盖。
"""

from sqlalchemy import create_engine

from app.core import database
from app.domains.families.models import Family
from app.domains.funds.models import Fund


def test_routing_binds_maps_user_tables_to_user_engine(monkeypatch):
    app_eng = create_engine('sqlite:///:memory:')
    user_eng = create_engine('sqlite:///:memory:')
    monkeypatch.setattr(database, 'engine', app_eng)
    monkeypatch.setattr(database, 'user_engine', user_eng)
    database._ROUTING_BINDS = None  # 强制用 patched 引擎重建

    binds = database._get_routing_binds()
    assert binds[Family.__table__] is user_eng
    assert binds[Fund.__table__] is app_eng
    # 映射应已缓存（非空）
    assert database._ROUTING_BINDS is not None
