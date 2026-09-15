# -*- coding: utf-8 -*-
"""#1513：`app.core.database` 引擎惰性化回归测试。

背景：旧实现在**导入期**就 `DatabaseFactory.create()` 两个域的引擎，而 `create_engine()`
会立刻解析方言并 import 对应 DBAPI——于是「缺一个域的驱动」被放大成「整个后端不可导入」
（CI 只想跑 market 域调度，却因 user 域缺 psycopg2 在 import 阶段崩溃，#1434 / #1514）。

验证目标：
1. 导入期不构造任何域的引擎；
2. 缺失 user 域驱动时，只用 market 域入口仍可导入并执行；
3. `engine` / `user_engine` 的对外语义不变（首次访问可取到引擎，monkeypatch 仍优先）。
"""

import os
import subprocess
import sys
from pathlib import Path

from app.core import database
from app.core.database import _engine_for
from app.core.db_factory import DOMAIN_APP, DOMAIN_USER

# 子进程探针：只导入 + 取 market 域引擎，不触碰 user 域
_LAZY_PROBE = """
import app.core.database as d

assert 'engine' not in vars(d), '导入期不应构造 engine'
assert 'user_engine' not in vars(d), '导入期不应构造 user_engine'
assert d.get_engine('app') is not None, 'market 域引擎应可取到'
print('LAZY-OK')
"""


def test_import_does_not_build_engines():
    """核心验收：user 域驱动缺失时，导入 + market 域入口仍可用（旧实现在此崩溃）。"""
    backend_dir = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        'APP_ENV': 'production',
        'DATABASE_URL': 'sqlite:///./_lazy_probe.db',
        # 故意指向本环境必然未安装的 DBAPI：改造前 import 即 ModuleNotFoundError
        'SUPABASE_DATABASE_URL': 'postgresql+pg8000://user:pwd@host/db',
        'PYTHONPATH': str(backend_dir),
    }
    proc = subprocess.run(
        [sys.executable, '-c', _LAZY_PROBE],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f'引擎惰性化回归（应在导入期不建引擎）：{proc.stderr[-800:]}'
    assert 'LAZY-OK' in proc.stdout


def test_engine_attr_available_on_access():
    """`database.engine` 语义不变：首次访问即可取到引擎（PEP 562 生效）。"""
    assert database.engine is not None
    assert database.user_engine is not None


def test_engine_for_prefers_monkeypatched_module_attr(monkeypatch):
    """模块内取值必须尊重 monkeypatch——conftest 靠它把引擎重定向到内存库。

    raising=False：避免 monkeypatch 取值时触发 __getattr__ 把真引擎造出来。
    """
    sentinel = object()
    monkeypatch.setattr(database, 'engine', sentinel, raising=False)
    monkeypatch.setattr(database, 'user_engine', sentinel, raising=False)
    assert _engine_for(DOMAIN_APP) is sentinel
    assert _engine_for(DOMAIN_USER) is sentinel
