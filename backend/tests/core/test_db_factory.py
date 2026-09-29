# -*- coding: utf-8 -*-
"""db_factory 单元测试：验证 APP_ENV 驱动的运行库切换与多域引擎。

通过 mock 环境变量 + 重置工厂缓存，确保不依赖真实数据库即可验证切换逻辑。
注：Turso(libsql/https) 与 Postgres(psycopg2) 驱动仅在生产 Linux 机可用，
本机 Windows 开发机不可装，故对这两类仅校验「配置解析出的 URL 正确」，
并对 create_engine 打桩，避免尝试真实建连。
"""

import os
from unittest import mock

from app.core import db_factory
from app.core.db_factory import (
    DOMAIN_APP,
    DOMAIN_USER,
    DatabaseConfig,
    DatabaseFactory,
    get_app_env,
)

# #1727：本机 backend/.env 常带真实的 TURSO_DATABASE_URL，且它在 import 期就经
# load_dotenv() 进入 os.environ。用例一旦把 APP_ENV 设为 production，market 域就会路由到
# turso（_normalize_db_url 归一为 sqlite+libsql://），而 Windows 装不了 sqlalchemy-libsql
# （pyproject 的 `sys_platform != "win32"` 平台标记）→ 真实 create_engine 抛
# NoSuchModuleError，且报错点离真因很远。故测试自带中和值，不依赖调用方环境。
_NEUTRAL_TURSO_URL = 'sqlite:///./test.turso-neutralized.db'


def _reset_and_set(monkeypatch, env_vars: dict):
    """设置环境变量并清空工厂缓存。

    默认把 TURSO_DATABASE_URL 中和成本地 SQLite（#1727）：见上方 _NEUTRAL_TURSO_URL。
    显式传入 TURSO_DATABASE_URL 的用例（要验证 turso 归一化的那几条）以传入值为准；
    传 None 表示确实要删掉它（验证「缺 turso 时回退 DATABASE_URL」）。
    """
    for k, v in {'TURSO_DATABASE_URL': _NEUTRAL_TURSO_URL, **env_vars}.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    DatabaseFactory.reset()


def test_get_app_env_default_is_production(monkeypatch):
    """缺省（未设置 APP_ENV）应为 production，安全侧。"""
    monkeypatch.delenv('APP_ENV', raising=False)
    monkeypatch.delenv('FLASK_ENV', raising=False)
    assert get_app_env() == 'production'


def test_get_app_env_dev_variants(monkeypatch):
    for v in ('development', 'dev', 'local'):
        monkeypatch.setenv('APP_ENV', v)
        assert get_app_env() == 'development'


def test_config_for_app_dev_uses_local_sqlite(monkeypatch):
    _reset_and_set(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': 'sqlite:///./test.dev.db'})
    cfg = DatabaseConfig.for_app('development')
    assert str(cfg.url).startswith('sqlite://')
    assert 'test.dev.db' in str(cfg.url)
    assert cfg.pool_pre_ping is False
    assert cfg.connect_args.get('check_same_thread') is False


def test_config_for_app_prod_prefers_turso(monkeypatch):
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': 'https://example.turso.io/?authToken=abc',
            'DATABASE_URL': 'sqlite:///./fallback.db',
        },
    )
    cfg = DatabaseConfig.for_app('production')
    assert 'turso.io' in str(cfg.url)


def test_config_for_app_prod_fallback_to_database_url(monkeypatch):
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': None,
            'DATABASE_URL': 'sqlite:///./prod.db',
        },
    )
    cfg = DatabaseConfig.for_app('production')
    assert 'prod.db' in str(cfg.url)


def test_reset_and_set_neutralizes_ambient_turso(monkeypatch):
    """#1727：_reset_and_set 必须中和掉**环境里**的 TURSO_DATABASE_URL（而不仅是不设它）。

    本机 ``backend/.env`` 常带真实 ``turso://``，它在 import 期就进了 ``os.environ``。
    若不中和，凡把 ``APP_ENV`` 设为 production 又真建引擎的用例都会在 Windows 上因缺
    ``sqlalchemy-libsql`` 方言而红，且红在离真因很远的方言加载点——这正是 #1727 的形态。

    为什么这条不变量值得自己可观测：它由测试基础设施承担，而「基础设施级的修复」最容易
    退化成没人能发现、也没人能回归的摆设。这里同时钉住两个方向——默认中和、显式值优先。
    """
    monkeypatch.setenv('TURSO_DATABASE_URL', 'turso://real@example.turso.io/db?authToken=t')
    _reset_and_set(monkeypatch, {'APP_ENV': 'production'})
    assert db_factory._is_local_sqlite(os.environ['TURSO_DATABASE_URL']), (
        f'production 下应中和为本地 SQLite，实际 {os.environ["TURSO_DATABASE_URL"]}'
    )

    # 显式传入者以传入值为准——验证 turso 归一化的那几条用例依赖这条
    _reset_and_set(monkeypatch, {'APP_ENV': 'production', 'TURSO_DATABASE_URL': 'turso://x@y.turso.io/db'})
    assert not db_factory._is_local_sqlite(os.environ['TURSO_DATABASE_URL'])


def test_config_for_user_falls_back_to_local_when_unconfigured(monkeypatch):
    """user 域未配 Supabase 时回退本地 SQLite（AGENTS.md 双库规则 7：
    user_session_factory 不再因缺 Supabase 抛错，本地零配置双库模拟）。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'SUPABASE_DATABASE_URL': None,
        },
    )
    cfg = DatabaseConfig.for_user('production')
    assert cfg is not None
    assert str(cfg.url).startswith('sqlite')


def test_config_for_user_returns_postgres_url(monkeypatch):
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'SUPABASE_DATABASE_URL': 'postgresql://u:p@db.supabase.co:5432/postgres',
        },
    )
    cfg = DatabaseConfig.for_user('production')
    assert cfg is not None
    assert str(cfg.url).startswith('postgresql://')


def test_factory_create_dev_sqlite_real_engine(monkeypatch):
    """dev 用 SQLite，本机可真实建引擎，验证缓存与实例。"""
    _reset_and_set(monkeypatch, {'APP_ENV': 'development', 'DEV_DATABASE_URL': 'sqlite:///./test.dev.db'})
    e1 = DatabaseFactory.create(DOMAIN_APP)
    e2 = DatabaseFactory.create(DOMAIN_APP)
    assert e1 is e2
    assert str(e1.url).startswith('sqlite://')
    DatabaseFactory.reset()


def test_normalize_db_url_turso_rewrites_scheme_and_extracts_auth():
    """裸 turso:// 应归一为 sqlite+libsql://，且 authToken 转入 connect_args。"""
    url, extra = db_factory._normalize_db_url('turso://abc@foo.turso.io/mydb?authToken=secret-token')
    assert url.startswith('sqlite+libsql://')
    assert 'foo.turso.io' in url
    assert 'authToken' not in url  # 已移出 URL
    assert extra.get('auth_token') == 'secret-token'


def test_normalize_db_url_libsql_rewrites_scheme():
    url, extra = db_factory._normalize_db_url('libsql://foo.turso.io/mydb')
    assert url == 'sqlite+libsql://foo.turso.io/mydb'
    assert extra == {}


def test_normalize_db_url_https_turso_rewrites_scheme():
    """https://*.turso.io 也应被归一（Turso 云常用 https 端点）。"""
    url, extra = db_factory._normalize_db_url('https://example.turso.io/?authToken=tk')
    assert url.startswith('sqlite+libsql://')
    assert 'example.turso.io' in url
    assert extra.get('auth_token') == 'tk'


def test_normalize_db_url_non_turso_unchanged():
    for raw in (
        'sqlite:///./invest.db',
        'postgresql://u:p@db.supabase.co:5432/postgres',
        'sqlite+libsql://foo.turso.io/mydb?auth_token=tk',  # 已归一，幂等
    ):
        url, extra = db_factory._normalize_db_url(raw)
        assert url == raw
        assert extra == {}


def test_factory_build_prod_turso_normalizes_scheme_and_auth(monkeypatch):
    """生产环境 turso:// URL 经 build() 后应把归一后的 URL 与 auth_token 传给 create_engine。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': 'turso://abc@foo.turso.io/mydb?authToken=secret-token',
            'DATABASE_URL': None,
        },
    )
    fake_engine = object()
    with mock.patch.object(db_factory, 'create_engine', return_value=fake_engine) as m:
        eng = DatabaseFactory.build(DOMAIN_APP, env='production')
    assert eng is fake_engine
    called_url, called_kwargs = m.call_args.args[0], m.call_args.kwargs
    assert str(called_url).startswith('sqlite+libsql://')
    assert 'turso.io' in str(called_url)
    assert 'authToken' not in str(called_url)
    assert called_kwargs.get('connect_args', {}).get('auth_token') == 'secret-token'


def test_factory_build_dev_sqlite_pragmas_skips_libsql(monkeypatch):
    """本地 SQLite 引擎仍应用 PRAGMA；libsql 引擎不应用（避免向远端发 PRAGMA）。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': 'turso://abc@foo.turso.io/mydb?authToken=tk',
        },
    )
    fake_engine = object()
    with (
        mock.patch.object(db_factory, 'create_engine', return_value=fake_engine),
        mock.patch.object(db_factory, '_apply_sqlite_pragmas') as pragma,
    ):
        DatabaseFactory.build(DOMAIN_APP, env='production')
    # libsql 引擎不应触发本地 PRAGMA
    pragma.assert_not_called()


def test_factory_create_user_mock_engine(monkeypatch):
    """用户库引擎构建：mock create_engine（本机无 psycopg2），验证传入 URL。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'SUPABASE_DATABASE_URL': 'postgresql://u:p@db.supabase.co:5432/postgres',
        },
    )
    # 两个域各给一个**不同**的哨兵：既钉「按域分别缓存」，又不依赖真实引擎。
    # 用 side_effect 列表还有个附带好处——create_engine 若被调用第三次会直接报错。
    user_engine, app_engine = object(), object()
    # 两次建引擎都必须落在 mock 内（#1727）：原实现把 app 域那次留在 with 之外，靠
    # 「环境里恰好没有 turso」这一隐含前提才成立；本机 .env 带真实 TURSO_DATABASE_URL 时，
    # 那次真实 create_engine 会因缺 libsql 方言直接 NoSuchModuleError——即测试假设了调用方环境。
    # 一并 stub _apply_sqlite_pragmas：中和后的 app 域 URL 是本地 SQLite，build() 会对它接
    # PRAGMA，而哨兵不是真 Engine（event.listens_for 会抛 InvalidRequestError）。
    # 本用例只钉「工厂按域分别缓存」，PRAGMA 接线由
    # test_factory_build_dev_sqlite_pragmas_skips_libsql 覆盖。
    with (
        mock.patch.object(db_factory, 'create_engine', side_effect=[user_engine, app_engine]) as m,
        mock.patch.object(db_factory, '_apply_sqlite_pragmas'),
    ):
        eng = DatabaseFactory.create(DOMAIN_USER)
        assert eng is user_engine
        # 确认 create_engine 收到的是 supabase 的 postgres URL。须在第二次建引擎**之前**取，
        # 否则 m.call_args 记录的是后一次调用。
        called_url = m.call_args.args[0]
        assert str(called_url).startswith('postgresql://')
        # 应用库必须**另建**一个实例（不串用 user 域那个）
        app_eng = DatabaseFactory.create(DOMAIN_APP)
        assert app_eng is app_engine
        assert app_eng is not eng
    DatabaseFactory.reset()


# --------------------------------------------------------------------------- #
# #1519：connect_args 必须按方言取值
#
# 历史缺陷：app 域在 staging / production 无条件注入 SQLite 专有的
# `timeout` / `check_same_thread`，而那两个环境默认指向 Turso（libSQL），
# 其 DBAPI 不接受这些关键字 → 建连时 TypeError（CI 定时任务启动即崩）。
# --------------------------------------------------------------------------- #


def test_sqlite_connect_args_only_for_local_sqlite():
    """本地 SQLite 才需要 check_same_thread / timeout；libSQL、Postgres 一律为空。"""
    local = db_factory._sqlite_connect_args('sqlite:///./invest.db')
    assert local == {'check_same_thread': False, 'timeout': 30}
    assert db_factory._sqlite_connect_args('sqlite+pysqlite:///./invest.db') == local

    for remote in (
        'sqlite+libsql://foo.turso.io/mydb',  # 归一后的 Turso
        'turso://abc@foo.turso.io/mydb',  # 归一前的裸 scheme
        'libsql://foo.turso.io/mydb',
        'https://foo.turso.io/',
        'postgresql://u:p@db.supabase.co:5432/postgres',
    ):
        assert db_factory._sqlite_connect_args(remote) == {}, remote


def test_config_for_app_production_turso_has_no_sqlite_args(monkeypatch):
    """生产指向 Turso 时，配置层不得带 SQLite 专有 connect_args（#1519 根因处）。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': 'turso://abc@foo.turso.io/mydb?authToken=tk',
            'DATABASE_URL': None,
        },
    )
    cfg = DatabaseConfig.for_app('production')
    assert cfg.connect_args == {}


def test_config_for_app_dev_sqlite_keeps_sqlite_args(monkeypatch):
    """回归保护：本地开发仍必须带 SQLite 专有参数（否则并发写会踩 pysqlite 限制）。"""
    _reset_and_set(
        monkeypatch,
        {'APP_ENV': 'development', 'DEV_DATABASE_URL': 'sqlite:///./test.dev.db'},
    )
    cfg = DatabaseConfig.for_app('development')
    assert cfg.connect_args.get('check_same_thread') is False
    assert cfg.connect_args.get('timeout') == 30


def test_factory_build_turso_passes_only_auth_token_as_connect_args(monkeypatch):
    """端到端（打桩 create_engine）：Turso 引擎的 connect_args 只有 auth_token。"""
    _reset_and_set(
        monkeypatch,
        {
            'APP_ENV': 'production',
            'TURSO_DATABASE_URL': 'turso://abc@foo.turso.io/mydb?authToken=secret-token',
            'DATABASE_URL': None,
        },
    )
    fake_engine = object()
    with mock.patch.object(db_factory, 'create_engine', return_value=fake_engine) as m:
        DatabaseFactory.build(DOMAIN_APP, env='production')
    connect_args = m.call_args.kwargs.get('connect_args', {})
    assert connect_args.get('auth_token') == 'secret-token'
    assert 'timeout' not in connect_args
    assert 'check_same_thread' not in connect_args


def test_factory_build_strips_leaked_sqlite_args_for_libsql(monkeypatch):
    """兜底闸门：即使配置层残留 SQLite 参数，build() 也要就地剔除（防将来回归）。"""
    _reset_and_set(
        monkeypatch,
        {'APP_ENV': 'production', 'TURSO_DATABASE_URL': 'turso://abc@foo.turso.io/mydb?authToken=tk'},
    )
    leaked = DatabaseConfig(
        name=DOMAIN_APP,
        url='turso://abc@foo.turso.io/mydb?authToken=tk',
        connect_args={'check_same_thread': False, 'timeout': 30},
    )
    fake_engine = object()
    with (
        mock.patch.object(db_factory.DatabaseConfig, 'for_app', return_value=leaked),
        mock.patch.object(db_factory, 'create_engine', return_value=fake_engine) as m,
    ):
        DatabaseFactory.build(DOMAIN_APP, env='production')
    connect_args = m.call_args.kwargs.get('connect_args', {})
    assert 'timeout' not in connect_args
    assert 'check_same_thread' not in connect_args
    assert connect_args.get('auth_token') == 'tk'
