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
from sqlalchemy.orm import sessionmaker

# --------------------------------------------------------------------------- #
# 数据域标识：应用运行库 vs 用户核心账本库
# --------------------------------------------------------------------------- #
DOMAIN_APP = 'app'  # 应用运行库（市场域/非敏感数据：净值、指数、温度计、自选种子等）
DOMAIN_USER = 'user'  # 用户核心账本库（Supabase，隐私数据，独立权威）

# 域的「引擎来源」语义别名：market 域对应 DOMAIN_APP 引擎，user 域对应 DOMAIN_USER 引擎。
# 文档与代码统一用 'market' / 'user' 描述数据归属，用 DOMAIN_APP / DOMAIN_USER 描述引擎。
DOMAIN_MARKET = 'market'

_DEFAULT_APP_DB = 'sqlite:///./invest.db'
_DEFAULT_DEV_DB = 'sqlite:///./invest.dev.db'
# user 域本地回退文件：与 market 的 invest.dev.db 物理分离，模拟「双库」，
# 但无需任何网络/云连接，纯本地最快。仅在未配置 SUPABASE_DATABASE_URL 时启用。
_DEFAULT_DEV_USER_DB = 'sqlite:///./invest.user.dev.db'


# --------------------------------------------------------------------------- #
# 表 → 数据域归属注册表（单一事实来源，与 docs/dev/db-data-domain.md 同步）
# --------------------------------------------------------------------------- #
# 规则：每个 ORM 模型对应的 __tablename__ 必须在此登记，且只能归 market / user 之一。
# 未登记的表在 init_db 启动校验时直接 fail（防漏声明导致建错库 / 读错库）。
# 归属判定见 AGENTS.md「多引擎数据域约束」决策树。
#
# 边界先例（已固化，勿凭"公开=Turso"一刀切）：
#  - sales_institutions / fund_management_companies：公开名录，但被 user 域表
#    (ledgers/positions) 外键引用 → 随 user 域，避反向跨域 FK。
#  - managers / fund_managers：被 market 域表 (funds) 外键引用 → 随 market 域。
DATA_DOMAIN_REGISTRY: Dict[str, str] = {
    # ── market 域（Turso）：公开、读多写少、无限膨胀的市场数据 ──
    'funds': DOMAIN_MARKET,
    'fund_companies': DOMAIN_MARKET,
    'fund_varieties': DOMAIN_MARKET,
    'fund_types': DOMAIN_MARKET,
    'fund_sales_orgs': DOMAIN_MARKET,  # 基金维度销售机构（funds 域内）
    'managers': DOMAIN_MARKET,  # 基金管理人（被 funds 引用）
    'fund_managers': DOMAIN_MARKET,  # 基金-经理关联（被 funds 引用）
    'daily_worth': DOMAIN_MARKET,  # 基金净值（最大体积表）
    'money_fund_daily_worth': DOMAIN_MARKET,  # 货基净值
    'purchase_rules': DOMAIN_MARKET,
    'redeem_rules': DOMAIN_MARKET,
    'fee_ratios': DOMAIN_MARKET,
    'price_history': DOMAIN_MARKET,  # 历史行情（最大体积表）
    'securities': DOMAIN_MARKET,
    'market_single_values': DOMAIN_MARKET,
    'market_composites': DOMAIN_MARKET,
    'market_multi_items': DOMAIN_MARKET,
    'sync_logs': DOMAIN_MARKET,  # 系统同步审计（随市场同步任务）
    # ── user 域（Supabase）：含 family_id/user_id 的用户私有数据 ──
    'families': DOMAIN_USER,
    'users': DOMAIN_USER,
    'ledgers': DOMAIN_USER,
    'portfolios': DOMAIN_USER,
    'positions': DOMAIN_USER,
    'transactions': DOMAIN_USER,
    'position_import_meta': DOMAIN_USER,  # 导入溯源（含 family_id）
    'assets': DOMAIN_USER,  # 静态资产（含 family_id）
    'sales_institutions': DOMAIN_USER,  # 销售机构名录（被 ledgers 引用，随 user 域）
    'fund_management_companies': DOMAIN_USER,  # 基金公司名录（被 positions 引用，随 user 域）
    'watchlist': DOMAIN_USER,
    'watchlist_groups': DOMAIN_USER,
    'watchlist_item_group': DOMAIN_USER,
    'watchlist_tag_defs': DOMAIN_USER,
    'watchlist_item_tags': DOMAIN_USER,
    'watchlist_alerts': DOMAIN_USER,
    'cleared_positions': DOMAIN_USER,
    'strategy_tags': DOMAIN_USER,
    'position_strategy_tags': DOMAIN_USER,
    'asset_snapshots': DOMAIN_USER,
    'user_usage': DOMAIN_USER,
}

# 规划中但尚未建表的域归属（提前登记，防止模型落地时漏声明）。
# 用户操作审计表：含 user_id，按用户数增长，归 user 域，享 RLS，与原操作同引擎。
PENDING_DOMAIN_REGISTRY: Dict[str, str] = {
    'user_audit_log': DOMAIN_USER,
}


def normalize_table_domain(table_name: str) -> Optional[str]:
    """查表名对应的数据域；未登记返回 None（供启动校验拦截）。"""
    return DATA_DOMAIN_REGISTRY.get(table_name)


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
    def for_user(cls, env: str) -> 'DatabaseConfig':
        """用户核心账本库配置：Supabase Postgres（独立）。

        优先级：
        1. 显式配置 SUPABASE_DATABASE_URL → 真 Supabase（生产 / 最终验证）。
        2. 未配置 → **自动回退本地 SQLite 文件** invest.user.dev.db，
           与 market 域的 invest.dev.db 物理分离，模拟「双库」但零网络依赖。
           这样本地 `pdm run python` 默认即可双 SQLite 模拟，测试飞快；
           最终验证时只需配置 SUPABASE_DATABASE_URL 即切换真库，业务零改动。

        设计要点：本方法永不返回 None（除非显式 force_none），因此 user 会话
        入口不再因「未配 Supabase」而抛错——这是单库/双库统一可用的关键。
        """
        url = os.getenv('SUPABASE_DATABASE_URL')
        if url:
            # Postgres 不需要 SQLite 专用 connect_args
            return cls(name=DOMAIN_USER, url=url, connect_args={}, pool_pre_ping=True)

        # 本地回退：dev 用独立 SQLite 文件，prod/staging 回退到通用 DATABASE_URL 同库
        if env == 'development':
            fallback = os.getenv('DEV_USER_DATABASE_URL', _DEFAULT_DEV_USER_DB)
        else:
            fallback = os.getenv('USER_DATABASE_URL', _DEFAULT_APP_DB)
        connect_args = {'check_same_thread': False, 'timeout': 30}
        return cls(name=DOMAIN_USER, url=fallback, connect_args=connect_args, pool_pre_ping=False)


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
    def build(cls, domain: str, env: Optional[str] = None) -> Engine:
        """构建指定数据域的 engine（不缓存，供测试 mock）。

        user 域在未配置 SUPABASE_DATABASE_URL 时自动回退本地 SQLite 文件，
        因此本方法对任一域都保证返回可用引擎（永不返回 None）。
        """
        env = env or get_app_env()
        if domain == DOMAIN_USER:
            cfg = DatabaseConfig.for_user(env)
        else:
            cfg = DatabaseConfig.for_app(env)

        assert cfg is not None, f'数据域 {domain} 无法解析连接配置'

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
    def create(cls, domain: str, env: Optional[str] = None) -> Engine:
        """取（或构建并缓存）指定数据域的 engine。

        任一域都保证返回可用引擎：user 域未配 Supabase 时自动回退本地 SQLite，
        因此本地开发 / 测试零配置即可双库模拟。
        """
        if domain not in cls._engines:
            cls._engines[domain] = cls.build(domain, env)
        return cls._engines[domain]

    @classmethod
    def reset(cls) -> None:
        """清空缓存（测试用）。"""
        cls._engines.clear()

    @classmethod
    def tables_by_domain(cls, metadata) -> Dict[str, list]:
        """按数据域把 metadata 中的表分组。

        返回 {'market': [Table...], 'user': [Table...]}。
        校验：凡 metadata 中的表必须已在 DATA_DOMAIN_REGISTRY 登记，否则抛 ValueError
        （防漏声明导致建错库 / 读错库）。同时校验注册表有无"模型已不存在"的孤儿项，
        打印告警（不致命，但提示文档与代码漂移）。
        """
        from sqlalchemy import MetaData

        if metadata is None:
            metadata = MetaData()
        result = {DOMAIN_MARKET: [], DOMAIN_USER: []}
        registry_keys = set(DATA_DOMAIN_REGISTRY)
        model_tables = set(metadata.tables.keys())

        # 1) 模型表必须全部登记；未登记的立即 fail
        unregistered = sorted(model_tables - registry_keys)
        if unregistered:
            raise ValueError(
                '以下表未在 DATA_DOMAIN_REGISTRY 声明数据域，禁止建库（防建错库）：'
                f' {unregistered}。请在 db_factory.DATA_DOMAIN_REGISTRY 补登记，'
                '判定规则见 AGENTS.md「多引擎数据域约束」。'
            )

        for table in metadata.tables.values():
            domain = DATA_DOMAIN_REGISTRY[table.name]
            result[domain].append(table)
        return result

    @classmethod
    def validate_domain_labels(cls, metadata) -> None:
        """启动期断言：每个表都已声明合法数据域（供 init_db 调用）。

        除致命校验（漏登记）外，额外检查注册表孤儿项（模型已不存在但仍在
        注册表），打印告警提示文档/代码漂移。此告警仅在启动路径触发，
        避免测试期 import 时序造成噪音。
        """
        grouped = cls.tables_by_domain(metadata)
        registry_keys = set(DATA_DOMAIN_REGISTRY)
        model_tables = set(metadata.tables.keys())
        orphan = sorted(registry_keys - model_tables - set(PENDING_DOMAIN_REGISTRY))
        if orphan:
            import logging

            logging.getLogger(__name__).warning(
                'DATA_DOMAIN_REGISTRY 存在孤儿表（模型未定义但已登记）：%s，请同步文档与代码。',
                orphan,
            )
        return grouped


def market_session_factory() -> sessionmaker:
    """market 域会话工厂（Turso / 开发期本地 SQLite 替身）。

    业务层读取市场数据（净值/行情/温度/基金资料）必须且只能经此入口，
    禁止与 user 域会话混用。引擎未配置时抛 RuntimeError（开发期必须配置 APP 库）。
    """
    eng = DatabaseFactory.create(DOMAIN_APP)
    if eng is None:
        raise RuntimeError('market 域引擎未配置，无法创建会话（检查 APP_ENV / DATABASE_URL）。')
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)


def user_session_factory() -> sessionmaker:
    """user 域会话工厂（Supabase / 本地 SQLite 回退）。

    业务层读写用户账本（账户/持仓/交易/自选/审计）必须且只能经此入口，
    禁止与 market 域会话混用。

    单库/双库统一可用：
    - 配置了 SUPABASE_DATABASE_URL → 真 Supabase（最终验证 / 生产）。
    - 未配置 → 自动回退本地 SQLite 文件（invest.user.dev.db），与 market 域
      物理分离但零网络依赖，本地测试飞快。业务代码无需任何分支判断。
    """
    eng = DatabaseFactory.create(DOMAIN_USER)
    return sessionmaker(autocommit=False, autoflush=False, bind=eng)
