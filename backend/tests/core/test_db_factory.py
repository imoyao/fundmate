# -*- coding: utf-8 -*-
"""db_factory 单元测试：验证 APP_ENV 驱动的运行库切换与多域引擎。

通过 mock 环境变量 + 重置工厂缓存，确保不依赖真实数据库即可验证切换逻辑。
注：Turso(libsql/https) 与 Postgres(psycopg2) 驱动仅在生产 Linux 机可用，
本机 Windows 开发机不可装，故对这两类仅校验「配置解析出的 URL 正确」，
并对 create_engine 打桩，避免尝试真实建连。
"""

from unittest import mock

from app.core import db_factory
from app.core.db_factory import (
    DOMAIN_APP,
    DOMAIN_USER,
    DatabaseConfig,
    DatabaseFactory,
    get_app_env,
)


def _reset_and_set(monkeypatch, env_vars: dict):
    """设置环境变量并清空工厂缓存。"""
    for k, v in env_vars.items():
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
    fake_engine = object()
    with mock.patch.object(db_factory, 'create_engine', return_value=fake_engine) as m:
        eng = DatabaseFactory.create(DOMAIN_USER)
    assert eng is fake_engine
    # 确认 create_engine 收到的是 supabase 的 postgres URL
    called_url = m.call_args.args[0]
    assert str(called_url).startswith('postgresql://')
    # 与应用库（此处未配 turso，回退 sqlite）应为不同实例
    app_eng = DatabaseFactory.create(DOMAIN_APP)
    assert app_eng is not eng
    DatabaseFactory.reset()
