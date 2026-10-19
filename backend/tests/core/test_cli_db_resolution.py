# -*- coding: utf-8 -*-
"""#2344：数据库连接环境变量口径一致性回归网（CLI 与 web 应用同源）。

背景（2026-10-18 实测事故）：使用者在 worktree 里设了 ``DEV_DATABASE_URL`` 跑
``sync --job fund_detail_enrich --target-file``，334 只基金全部静默跳过、
``status=success``。根因是解析面不可解释：环境变量名随 ``APP_ENV`` 切换
（development 认 ``DEV_DATABASE_URL``，production 认 ``TURSO_/DATABASE_URL``），
缺省又是 cwd 相对的 ``./invest.db``，连错库毫无声息。

本文件钉住三件事（对应 #2344 验收标准）：

1. **CLI 与会话单一入口同源**：两个 CLI 入口的 ``get_db`` / ``init_db`` 就是
   ``app.core.database`` 的同两个函数——防止回退成「CLI 自己认一套变量」；
2. **解析可解释且与 web 一致**：``resolve_app_db()`` 报告的「URL + 来源」
   与 web 应用实际使用的 ``DatabaseConfig.for_app()`` 同优先级、同结果；
3. **连错库守卫分级**：``app_db_startup_check()`` 对「不存在的 SQLite 文件库」
   按 strict 分级处置（显式目标 fail-closed，日常增量仅告警）。

注：本文件只测**配置层纯函数**，不创建真实 engine——沿用 test_db_factory.py
的既定姿势（引擎创建会与 conftest 的 autouse ``clean_db`` 夹具相互踩踏）。
"""

import pytest

from app.core.db_factory import (
    DatabaseConfig,
    app_db_startup_check,
    get_app_env,
    resolve_app_db,
)

# 本机 backend/.env 的真实值会在 import 期经 load_dotenv() 进入 os.environ，
# 用例必须显式中和/删除，否则继承出的「环境」不是用例设定的那个。
_BASE_ENV = {
    'APP_ENV': None,
    'FLASK_ENV': None,
    'DEV_DATABASE_URL': None,
    'STAGING_DATABASE_URL': None,
    'TURSO_DATABASE_URL': None,
    'DATABASE_URL': None,
    'USER_DATABASE_URL': None,
    'SUPABASE_DATABASE_URL': None,
}


def _isolate(monkeypatch, env_vars: dict) -> None:
    """先清空全部相关变量，再套用本用例的设定（monkeypatch 自动还原）。"""
    for key, value in {**_BASE_ENV, **env_vars}.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_cli_entries_share_database_entry_points():
    """两个 CLI 入口的 get_db / init_db 就是 app.core.database 的同两个函数。

    #2344 验收 3 的静态面：会话经同一入口 → 同一套工厂解析（for_app），
    CLI 不可能再「只认某一个环境变量」。若有人给 CLI 单开一条读
    ``SQLALCHEMY_DATABASE_URL`` 的会话路径，本测试即红。
    """
    import app.core.database as database
    import app.tools.sync_cli as sync_cli
    import app.tools.sync_metadata as sync_metadata

    for module in (sync_metadata, sync_cli):
        assert module.get_db is database.get_db
        assert module.init_db is database.init_db


def test_get_app_env_default_is_production(monkeypatch):
    """缺省（未设置 APP_ENV / FLASK_ENV）为 production——这正是事故当晚
    「设了 DEV_DATABASE_URL 却被静默忽略」的前提；行为钉住不改，但须可解释。"""
    _isolate(monkeypatch, {})
    assert get_app_env() == 'production'


@pytest.mark.parametrize(
    ('env_vars', 'expected_url_part', 'expected_source'),
    [
        ({'APP_ENV': 'development', 'DEV_DATABASE_URL': 'sqlite:///./a.db'}, 'a.db', 'DEV_DATABASE_URL'),
        ({'APP_ENV': 'development'}, 'invest.db', 'default'),
        ({'APP_ENV': 'staging', 'STAGING_DATABASE_URL': 'sqlite:///./s.db'}, 's.db', 'STAGING_DATABASE_URL'),
        ({'APP_ENV': 'staging', 'DATABASE_URL': 'sqlite:///./st.db'}, 'st.db', 'DATABASE_URL'),
        ({'APP_ENV': 'staging'}, 'invest.db', 'default'),
        ({'APP_ENV': 'production', 'TURSO_DATABASE_URL': 'sqlite:///./t.db'}, 't.db', 'TURSO_DATABASE_URL'),
        ({'APP_ENV': 'production', 'DATABASE_URL': 'sqlite:///./p.db'}, 'p.db', 'DATABASE_URL'),
        ({'APP_ENV': 'production'}, 'invest.db', 'default'),
    ],
)
def test_resolve_app_db_reports_source(monkeypatch, env_vars, expected_url_part, expected_source):
    """resolve_app_db 的「URL + 来源」按 APP_ENV 分流，缺省报 default。"""
    _isolate(monkeypatch, env_vars)
    url, source = resolve_app_db()
    assert expected_url_part in url
    assert source == expected_source


def test_resolve_app_db_agrees_with_for_app(monkeypatch):
    """resolve_app_db 与 DatabaseConfig.for_app 对同一 env 解析出同一 URL。

    两者是「可解释镜像」关系：启动日志/守卫报的库，就是 web 应用实际连的库。
    若哪天 for_app 改了优先级而本函数没跟上，本测试即红（#2344 验收 1 的机器化）。
    """
    for env, vars_ in (
        ('development', {'APP_ENV': 'development', 'DEV_DATABASE_URL': 'sqlite:///./mirror.dev.db'}),
        (
            'production',
            {'APP_ENV': 'production', 'TURSO_DATABASE_URL': None, 'DATABASE_URL': 'sqlite:///./mirror.prod.db'},
        ),
        ('staging', {'APP_ENV': 'staging', 'DATABASE_URL': 'sqlite:///./mirror.staging.db'}),
    ):
        _isolate(monkeypatch, vars_)
        url, _source = resolve_app_db(env)
        assert url == str(DatabaseConfig.for_app(env).url)


def test_startup_check_strict_errors_on_missing_sqlite_file(monkeypatch, tmp_path):
    """strict：解析出的 SQLite 文件不存在 → 错误消息含绝对路径与来源变量。"""
    missing = tmp_path / 'no_such_market.db'
    _isolate(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': f'sqlite:///{missing.as_posix()}'})
    problem = app_db_startup_check(strict=True)
    assert problem is not None
    assert str(missing.resolve()) in problem
    assert 'DEV_DATABASE_URL' in problem


def test_startup_check_non_strict_warns_on_missing_sqlite_file(monkeypatch, tmp_path):
    """非 strict：文件不存在仍返回消息（调用方降级为 WARNING，不阻断建库）。"""
    missing = tmp_path / 'fresh_clone.db'
    _isolate(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': f'sqlite:///{missing.as_posix()}'})
    problem = app_db_startup_check(strict=False)
    assert problem is not None
    assert str(missing.resolve()) in problem


def test_startup_check_passes_when_file_exists(monkeypatch, tmp_path):
    """库文件已存在 → 放行（None），不论 strict。"""
    existing = tmp_path / 'invest.db'
    existing.touch()
    _isolate(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': f'sqlite:///{existing.as_posix()}'})
    assert app_db_startup_check(strict=True) is None
    assert app_db_startup_check(strict=False) is None


@pytest.mark.parametrize(
    'url',
    [
        'sqlite://',
        'sqlite:///:memory:',
        'https://example.turso.io/?authToken=x',
        'postgresql://user:pw@localhost:5432/db',
    ],
)
def test_startup_check_ignores_memory_and_remote(monkeypatch, url):
    """内存库 / 远端库不做本地存在性判定，直接放行。"""
    _isolate(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': url})
    assert app_db_startup_check(strict=True) is None
