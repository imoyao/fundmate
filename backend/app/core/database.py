# -*- coding: utf-8 -*-
"""数据库连接与基础仓储类."""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Engine, Integer, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.db_factory import (
    DOMAIN_APP,
    DOMAIN_USER,
    DatabaseFactory,
)

# 保留历史符号：部分模块（如 sync/orchestrator 备份路径）仍引用，
# 指向当前应用运行库的 URL，供文件库路径推断使用。
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')

# 默认 engine = 应用运行库（市场域/非敏感数据），按 APP_ENV 自动切换
# dev -> 本地 SQLite；prod -> Turso（回退 DATABASE_URL）。见 db_factory。
engine: Engine = DatabaseFactory.create(DOMAIN_APP)

# user 域引擎：配置了 SUPABASE_DATABASE_URL 即真 Supabase；未配置自动回退本地
# SQLite 文件（invest.user.dev.db），与 market 域物理分离但零网络依赖。
# 单库模式下 user_engine 与 engine 指向同一库（如生产未配 Supabase 时回退到
# 通用 DATABASE_URL 同库），此时双域表落在同一引擎，行为等价于旧单库。
# 注意：user_engine 是模块级全局，测试可经 monkeypatch 重定向到内存库（见 conftest）。
user_engine: Engine = DatabaseFactory.create(DOMAIN_USER)


# 按表路由的会话：单一 session 即可跨域查询（如持仓页同时读 positions + daily_worth），
# 每张表按需落到其数据域引擎（user 表→user_engine，market 表→engine）。
# 这是 #1085 的核心：业务层无需改动调用点，user 域数据自动路由到 user 引擎。
def _build_routing_binds():
    from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER

    binds = {}
    for table in Base.metadata.tables.values():
        domain = DATA_DOMAIN_REGISTRY.get(table.name)
        binds[table] = user_engine if domain == DOMAIN_USER else engine
    return binds


_ROUTING_BINDS = None


def _get_routing_binds():
    global _ROUTING_BINDS
    if _ROUTING_BINDS is None:
        _ROUTING_BINDS = _build_routing_binds()
    return _ROUTING_BINDS


class _RoutingSessionMaker(sessionmaker):
    """sessionmaker 子类：每次创建 session 时按表注入域路由 binds（懒构建一次）。"""

    def __call__(self, **kw):
        if 'binds' not in kw:
            kw['binds'] = _get_routing_binds()
        return super().__call__(**kw)


SessionLocal = _RoutingSessionMaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class BaseRepository:
    """为所有模型提供基础数据库操作的混入类."""

    def save(self, db: Session):
        """保存实例到数据库."""
        db.add(self)
        db.commit()
        db.refresh(self)
        return self

    def delete(self, db: Session):
        """从数据库删除实例."""
        db.delete(self)
        db.commit()


class PrimaryKeyMixin:
    """为模型提供自增 id 主键"""

    id = Column(Integer, primary_key=True, autoincrement=True)


class FamilyScopedMixin:
    """家庭隔离列（D1 家庭共享层）。

    核心账本表（账户/持仓/交易/组合/自选/策略标签等）混入本类，
    按 `family_id` 归属家庭；默认家庭 1 兼容既有单用户数据。
    查询侧一律经 `app.core.auth.get_family_id()` 过滤，禁止绕过。
    """

    family_id = Column(
        Integer,
        nullable=False,
        default=1,
        index=True,
        comment='归属家庭 ID（家庭共享层隔离键）',
    )


class TimestampMixin:
    """为模型提供中国标准时间（东八区）的创建和更新时间戳"""

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(ZoneInfo('Asia/Shanghai')),
        server_default=func.now(),  # 保持数据库层面也有默认值，若系统时区正确则一致
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(ZoneInfo('Asia/Shanghai')),
        onupdate=lambda: datetime.now(ZoneInfo('Asia/Shanghai')),
        server_default=func.now(),
    )


@contextmanager
def get_db():
    """上下文管理器形式的数据库会话（应用运行库），自动关闭连接."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine(domain: str = DOMAIN_APP) -> Optional[Engine]:
    """按数据域取已缓存 engine（接缝：业务层后续按域路由）。

    - DOMAIN_APP：应用运行库（默认，市场域/非敏感数据）。
    - DOMAIN_USER：用户核心账本库（Supabase，未配置返回 None，
      表示仍走应用库兼容既有单库模式）。
    """
    return DatabaseFactory.create(domain)


def get_user_sessionmaker() -> sessionmaker:
    """用户库 SessionLocal（未配置 Supabase 时自动回退本地 SQLite 文件）。

    单库/双库统一可用：配置了 SUPABASE_DATABASE_URL 即真 Supabase；
    未配置则落本地 invest.user.dev.db，与 market 域物理隔离但零网络依赖。
    调用方无需判断 None。
    """
    user_engine = DatabaseFactory.create(DOMAIN_USER)
    return sessionmaker(autocommit=False, autoflush=False, bind=user_engine)


def _validate_schema(bind, metadata, label: str = 'app') -> None:
    """启动期数据库结构校验守卫（issue #1036）。

    背景：create_all 只增表不改表——模型加了字段而存量 DB 未跟上时，
    错误要等到第一条 SQL 触发才以晦涩的 OperationalError 暴露，排查成本高；
    #1020 约束降级等迁移批次落地前，更需要一道「模型 vs 库结构」显式比对兜底。

    规则（首版从轻，聚焦最高频漂移）：
    - DB 中已存在的表：逐列比对 ORM 定义，缺列即收集；
    - DB 中不存在的表：交给 create_all 补建，跳过不误报；
    - 列类型/索引/约束差异：SQLite 反射信息有限且历史库存在合理漂移，
      首版不做强校验（避免误报阻断启动），后续按需加严。

    任一缺列 → RuntimeError 一次性列出全部漂移 + 修复路径
    （dev 重建 DB 文件 / 生产补迁移脚本），不允许带病启动。
    """
    from sqlalchemy import inspect

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    drifts: list[str] = []

    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # 新表由 create_all 负责
        db_cols = {c['name'] for c in inspector.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in db_cols]
        if missing:
            drifts.append(f'  - 表 {table.name} 缺列: {", ".join(missing)}')

    if drifts:
        raise RuntimeError(
            f'[{label}] 数据库结构与模型不一致（{len(drifts)} 处漂移），拒绝启动：\n'
            + '\n'.join(drifts)
            + '\n修复路径：开发环境重建 DB 文件；生产环境补迁移脚本后再启动。'
        )


def init_db():
    """创建所有表并写入默认家庭/用户（多用户地基）。

    双库就绪（#1085）：按数据域把表分别建到对应引擎——
    market 域 → engine（应用运行库），user 域 → user_engine（Supabase / 本地回退）。
    单库模式下两引擎指向同一库，等价于旧单库建表；双库模式下自然分离。
    默认家庭 1 + 默认用户 1 兼容既有单用户数据。
    """
    # 确保顶层模型已注册到 Base.metadata（否则 DATA_DOMAIN_REGISTRY 会因
    # 模型未导入而报孤儿表告警）。sync_log 仅在 services/sync 被加载时才导入，
    # 启动路径未必触达，故此处显式导入（与 sync_metadata 的防御式导入一致）。
    from sqlalchemy.schema import MetaData

    import app.models.sync_log  # noqa: F401
    from app.core.db_factory import (
        DOMAIN_MARKET,
        DOMAIN_USER,
        DatabaseFactory,
    )

    DatabaseFactory.validate_domain_labels(Base.metadata)
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    # market 域表 → 应用引擎
    market_meta = MetaData()
    for t in grouped[DOMAIN_MARKET]:
        t.to_metadata(market_meta)
    market_meta.create_all(bind=engine)
    _validate_schema(engine, market_meta, label='market')
    # user 域表 → 用户引擎
    user_meta = MetaData()
    for t in grouped[DOMAIN_USER]:
        t.to_metadata(user_meta)
    user_meta.create_all(bind=user_engine)
    _validate_schema(user_engine, user_meta, label='user')
    _seed_default_identity()


def init_db_split():
    """双库模式：按数据域分别 create_all 到对应 engine。

    - market 引擎必配（本地 dev 为 invest.dev.db，生产为 Turso）。
    - user 引擎：配了 SUPABASE_DATABASE_URL 即 Supabase；本地 development 下
      显式配置 DEV_USER_DATABASE_URL 才是独立文件（本地双库模拟），未配置时
      与 market 共用同一本地库（默认单库，本地既有数据立即可见）。显式拆分时
      user 表才落到「与 market 不同的引擎」，域边界成立。

    启动校验保证"声明域 == 实际建到的 engine"，不一致直接 fail。
    注：用户库（Supabase）生产建表建议由 Supabase 迁移工具独立负责，此方法
    主要用于开发期本地双库验证 / CI 校验，不强制生产路径。本地需要模拟双库时，
    请先显式设置 DEV_USER_DATABASE_URL 再调用本方法。
    """
    import app.models.sync_log  # noqa: F401
    from app.core.db_factory import (
        DOMAIN_APP,
        DOMAIN_MARKET,
        DOMAIN_USER,
        DatabaseFactory,
    )

    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    app_eng = DatabaseFactory.create(DOMAIN_APP)
    user_eng = DatabaseFactory.create(DOMAIN_USER)
    if app_eng is None:
        raise RuntimeError('market 域引擎未配置，init_db_split 终止。')
    # market 域表 → 应用引擎
    from sqlalchemy.schema import MetaData

    market_meta = MetaData()
    for t in grouped[DOMAIN_MARKET]:
        t.to_metadata(market_meta)
    market_meta.create_all(bind=app_eng)
    _validate_schema(app_eng, market_meta, label='market')
    # user 域表 → 用户引擎（若已配置）
    if user_eng is not None:
        user_meta = MetaData()
        for t in grouped[DOMAIN_USER]:
            t.to_metadata(user_meta)
        user_meta.create_all(bind=user_eng)
        _validate_schema(user_eng, user_meta, label='user')
    # 双库模式：种子必须落到 user 引擎（修复跨域 bug），bind 传 user_eng；
    # 未配 Supabase 时 user_eng 为本地回退文件，仍与 market 域隔离。
    _seed_default_identity(bind=user_eng)


@contextmanager
def market_session():
    """market 域会话上下文（读取净值/行情/温度/基金资料等）。"""
    from app.core.db_factory import market_session_factory

    db = market_session_factory()()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def user_session():
    """user 域会话上下文（读写账户/持仓/交易/自选/审计等）。"""
    from app.core.db_factory import user_session_factory

    db = user_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _seed_default_identity(bind=None):
    """幂等写入默认家庭 1 与默认用户 1，保证无鉴权模式下查询可用。

    Family / User 属于 user 域。写入目标引擎由调用方决定，避免跨域错写：
    - 单库模式 init_db()：所有表建在 app 引擎，bind 默认取 app 引擎
      （即 SessionLocal 的 bind），保证单库内数据自洽。
    - 双库模式 init_db_split()：必须传 user 引擎作为 bind，使家庭/用户落到
      user 域库（Supabase / 本地回退文件），与 market 域物理隔离；此前的 bug
      是用 market 引擎的 SessionLocal 写入 user 域表，真双库分离时落错库。
    """
    from app.core.db_factory import DOMAIN_USER, DatabaseFactory
    from app.domains.families.models import Family
    from app.domains.users.models import ROLE_ADMIN, User

    # 默认落到 user 引擎（Family/User 属于 user 域）；单库模式下 user_engine == engine。
    target_bind = bind if bind is not None else user_engine

    # 双库模式（bind 即 user 引擎）下，确保 user 域表已存在再写入；
    # 单库模式表已由 init_db 的 create_all 建好，无需重复。
    if bind is not None and bind is not SessionLocal.kw['bind']:
        grouped = DatabaseFactory.tables_by_domain(Base.metadata)
        from sqlalchemy.schema import MetaData

        user_meta = MetaData()
        for t in grouped[DOMAIN_USER]:
            t.to_metadata(user_meta)
        user_meta.create_all(bind=bind)

    UserSession = sessionmaker(autocommit=False, autoflush=False, bind=target_bind)
    with UserSession() as db:
        if not db.query(Family).filter_by(id=1).first():
            db.add(Family(id=1, name='默认家庭'))
        if not db.query(User).filter_by(id=1).first():
            db.add(
                User(
                    id=1,
                    family_id=1,
                    username='local',
                    nickname='本地用户',
                    role=ROLE_ADMIN,
                    is_active=1,
                )
            )
        db.commit()
