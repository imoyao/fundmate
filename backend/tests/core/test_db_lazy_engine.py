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


# ── #1608：域路由改为查询期解析后的两条回归 ───────────────────────────────────

# 子进程探针（会话级）：缺 user 域驱动时，「导入 + 首次开会话 + 查 market 域」必须可用，
# 报错点只允许出现在**真正触达 user 域表**的那一刻。
# 旧实现（会话构造期注入全表 binds）在此探针的 `d.SessionLocal()` 即崩。
_SESSION_LAZY_PROBE = """
import app.domains.assets.models  # noqa: F401
import app.domains.families.models  # noqa: F401
import app.domains.funds.models  # noqa: F401
import app.domains.indices.models  # noqa: F401
import app.domains.positions.models  # noqa: F401
import app.domains.price_history.models  # noqa: F401
import app.domains.securities.models  # noqa: F401
import app.domains.summary.models  # noqa: F401
import app.domains.transactions.models  # noqa: F401
import app.domains.users.models  # noqa: F401
import app.domains.watchlist.models  # noqa: F401

from sqlalchemy import select

import app.core.database as d
from app.core.db_factory import DatabaseFactory
from app.domains.funds.models import Fund
from app.domains.watchlist.models import WatchlistItem

session = d.SessionLocal()  # 旧实现：此处即 ModuleNotFoundError（user 域引擎被强制构造）
Fund.__table__.create(bind=DatabaseFactory.create('app'), checkfirst=True)
session.execute(select(Fund.id).limit(1)).first()
session.close()
print('MARKET-OK')

try:
    items = d.SessionLocal()
except Exception as err:  # noqa: BLE001
    raise AssertionError(f'开会话不该崩：{type(err).__name__}: {err}') from err
try:
    items.execute(select(WatchlistItem.id).limit(1)).first()
except ModuleNotFoundError as err:
    print(f'USER-DRIVER-MISSING-AS-EXPECTED: {err}')
else:
    raise AssertionError('user 域查询竟然没触发缺驱动错误——探针口径失效')
finally:
    items.close()
"""


def test_missing_user_driver_survives_session_and_market_query(tmp_path):
    """#1608：缺 user 域驱动时，首次开会话与 market 域查询都必须照常可用。

    与 ``test_import_does_not_build_engines`` 的关系：那条卡的是**导入期**（#1513），
    本条约卡**运行时入口**——旧实现的 binds 全量物化让 #1513 的惰性构造在第一次
    ``SessionLocal()`` 就失效（实测 `ModuleNotFoundError: No module named 'pg8000'`，
    且被请求的域恰是 user）。故本用例在旧实现上**必红**，是本卡的核心回归。
    """
    backend_dir = Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        'APP_ENV': 'production',
        # tmp_path 是绝对路径，避免相对路径在不同 cwd 下落错位置
        'DATABASE_URL': f'sqlite:///{(tmp_path / "session_probe.db").as_posix()}',
        'SUPABASE_DATABASE_URL': 'postgresql+pg8000://user:pwd@host/db',
        'PYTHONPATH': str(backend_dir),
    }
    proc = subprocess.run(
        [sys.executable, '-c', _SESSION_LAZY_PROBE],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f'开会话 / market 域查询因缺 user 域驱动失败：{proc.stderr[-800:]}'
    assert 'MARKET-OK' in proc.stdout
    assert 'USER-DRIVER-MISSING-AS-EXPECTED' in proc.stdout


def test_session_and_market_query_do_not_request_user_engine(app, monkeypatch):
    """#1608：开会话与 market 域语句**不得**请求 user 域引擎；查 user 域表才请求。

    口径说明：conftest 已把两个域引擎重定向到内存库，故「真实引擎是否被构造」在进程内
    **不可观测**；这里观测最邻近的可观测不变量——是否向 `_engine_for` 请求过 user 域
    （旧实现的全量 binds 在第一次 ``SessionLocal()`` 就会请求两个域）。真实缺驱动形态
    由上面的子进程探针锁定，两者互补：本用例给**精确的归因**，探针给**真实后果**。
    """
    from sqlalchemy import select

    from app.core import database as db

    asked = []
    real = db._engine_for

    def _spy(domain):
        asked.append(domain)
        return real(domain)

    monkeypatch.setattr(db, '_engine_for', _spy)

    session = db.SessionLocal()
    try:
        assert 'user' not in asked, f'开会话就请求了 user 域：{asked}'
        session.get_bind(clause=select(db.Base.metadata.tables['funds']))
        assert 'user' not in asked, f'market 域语句请求了 user 域：{asked}'
        session.get_bind(clause=select(db.Base.metadata.tables['users']))
        assert asked.count('user') == 1, f'user 域语句应恰好请求一次 user 域：{asked}'
    finally:
        session.close()
