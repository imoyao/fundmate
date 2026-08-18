# -*- coding: utf-8 -*-
"""数据库连接工厂（多环境 / 多域引擎）。

设计背景（issue #1028 + #894）：
- 前/后端 env 按模式拆分后，后端需要按 APP_ENV 自动切换运行库，避免手动适配。
- 数据库分层（方案 B）：
    * 本地开发：本地 SQLite 运行库（开发用）。
    * 生产运行库：Turso（生产应用读写，市场域/非敏感数据）。
    * 用户核心账本：Supabase Postgres（独立权威库，与运行库各自独立）。
    * Neon：同步 Supabase 数据作灾备/一键切换 —— 延后，此处仅预留接入点。
- 本模块产出「应用运行库」与「用户库」两套独立 engine；业务层后续可按数据域
  经 get_engine(domain) 选库。当前 database.py 的默认 engine 指向应用运行库，
  所有既有调用方（SessionLocal / get_db / init_db）零改动。

切换信号：APP_ENV = development | staging | production，与前端 VITE_APP_ENV 对齐；
FLASK_DEBUG 仅控制调试器，不再混用作环境开关。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Optional

from sqlalchemy import Engine, create_engine, event

# --------------------------------------------------------------------------- #
# 数据域标识：应用运行库 vs 用户核心账本库
# --------------------------------------------------------------------------- #
DOMAIN_APP = 'app'  # 应用运行库（市场域/非敏感数据：净值、指数、温度计、自选种子等）
DOMAIN_USER = 'user'  # 用户核心账本库（Supabase，隐私数据，独立权威）

_DEFAULT_APP_DB = 'sqlite:///./invest.db'
_DEFAULT_DEV_DB = 'sqlite:///./invest.dev.db'


def get_app_env() -> str:
    """解析运行环境，默认 production（安全侧）。"""
    env = (os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or '').strip().lower()
    if env in ('development', 'dev', 'local'):
        return 'development'
    if env in ('staging', 'stage', 'test'):
        return 'staging'
    return 'production'


@dataclass
class DatabaseConfig:
    """单一 engine 的连接配置。

    未来接入 Neon 灾备时，可在此扩展（如 standby_url / failover 策略），
    不必改动工厂主流程。
    """

    name: str  # 数据域：DOMAIN_APP / DOMAIN_USER
    url: str  # SQLAlchemy URL（或待构建的 URL 参数）
    connect_args: Dict = field(default_factory=dict)
    pool_pre_ping: bool = True
    echo: bool = False

    @classmethod
    def for_app(cls, env: str) -> 'DatabaseConfig':
        """应用运行库配置：dev 用本地 SQLite，prod 用 Turso（可回退 DATABASE_URL）。"""
        if env == 'development':
            url = os.getenv('DEV_DATABASE_URL', _DEFAULT_DEV_DB)
            connect_args = {'check_same_thread': False, 'timeout': 30}
            return cls(name=DOMAIN_APP, url=url, connect_args=connect_args, pool_pre_ping=False)

        if env == 'staging':
            url = os.getenv('STAGING_DATABASE_URL') or os.getenv('DATABASE_URL', _DEFAULT_APP_DB)
            connect_args = {'check_same_thread': False, 'timeout': 30}
            return cls(name=DOMAIN_APP, url=url, connect_args=connect_args, pool_pre_ping=False)

        # production：优先 Turso 运行库，回退到通用 DATABASE_URL（便于过渡期）
        url = os.getenv('TURSO_DATABASE_URL') or os.getenv('DATABASE_URL', _DEFAULT_APP_DB)
        # Turso (libsql/https) 通常无需 check_same_thread；保留通用缺省
        connect_args = {'check_same_thread': False, 'timeout': 30}
        return cls(name=DOMAIN_APP, url=url, connect_args=connect_args, pool_pre_ping=True)

    @classmethod
    def for_user(cls, env: str) -> Optional['DatabaseConfig']:
        """用户核心账本库配置：Supabase Postgres（独立）。

        仅在显式配置了 SUPABASE_DATABASE_URL 时返回配置；否则返回 None，
        表示用户库暂未接入（仍走应用库兼容既有单库模式）。
        """
        url = os.getenv('SUPABASE_DATABASE_URL')
        if not url:
            return None
        # Postgres 不需要 SQLite 专用 connect_args
        return cls(name=DOMAIN_USER, url=url, connect_args={}, pool_pre_ping=True)


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """SQLite 专用 PRAGMA：WAL 提升并发、开启外键约束（兜底防悬空引用）。"""

    @event.listens_for(engine, 'connect')
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA foreign_keys=ON;')
        cursor.close()


class DatabaseFactory:
    """按数据域构建并缓存 engine 的工厂。

    用法：
        engine = DatabaseFactory.create(DOMAIN_APP)         # 应用运行库
        user_engine = DatabaseFactory.create(DOMAIN_USER)   # 用户库（未配置则返回 None）
    或经 database.get_engine(domain) 取已缓存实例。
    """

    _engines: Dict[str, Optional[Engine]] = {}

    @classmethod
    def build(cls, domain: str, env: Optional[str] = None) -> Optional[Engine]:
        """构建指定数据域的 engine（不缓存，供测试 mock）。"""
        env = env or get_app_env()
        if domain == DOMAIN_USER:
            cfg = DatabaseConfig.for_user(env)
        else:
            cfg = DatabaseConfig.for_app(env)

        if cfg is None:
            return None

        engine = create_engine(
            cfg.url,
            connect_args=cfg.connect_args,
            pool_pre_ping=cfg.pool_pre_ping,
            echo=cfg.echo,
        )
        # 仅 SQLite 类驱动需要 PRAGMA（按 URL scheme 判断，避免污染 Postgres）
        if str(cfg.url).startswith(('sqlite://', 'sqlite+')):
            _apply_sqlite_pragmas(engine)
        return engine

    @classmethod
    def create(cls, domain: str, env: Optional[str] = None) -> Optional[Engine]:
        """取（或构建并缓存）指定数据域的 engine。"""
        if domain not in cls._engines:
            cls._engines[domain] = cls.build(domain, env)
        return cls._engines[domain]

    @classmethod
    def reset(cls) -> None:
        """清空缓存（测试用）。"""
        cls._engines.clear()
