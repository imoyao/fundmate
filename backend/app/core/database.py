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

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


def get_user_sessionmaker() -> Optional[sessionmaker]:
    """用户库 SessionLocal（未配置返回 None）。

    TODO(数据域拆分 #894)：待 Supabase 云端集成落地后，用户域 service 层
    统一经此注入，与运行库严格隔离（跨库事务无法保证 ACID，必须按域隔离）。
    """
    user_engine = DatabaseFactory.create(DOMAIN_USER)
    if user_engine is None:
        return None
    return sessionmaker(autocommit=False, autoflush=False, bind=user_engine)


def init_db():
    """创建应用运行库所有表，并确保默认家庭/用户存在（多用户地基）。

    默认家庭 1 + 默认用户 1 兼容既有单用户数据：模型结构变更后
    需要重建 DB 文件（见 scripts/migrate_family_id.py 的 ALTER 迁移说明）。

    数据域护栏：建表前先跑启动校验，确保每张表都已在
    db_factory.DATA_DOMAIN_REGISTRY 声明归属域（防漏声明 / 建错库）。
    当前单库兼容模式下仍把所有表建到默认 engine；双库模式请改用
    init_db_split() 按域分别建到各自引擎。
    """
    from app.core.db_factory import DatabaseFactory

    DatabaseFactory.validate_domain_labels(Base.metadata)
    Base.metadata.create_all(bind=engine)
    _seed_default_identity()


def init_db_split():
    """双库模式：按数据域分别 create_all 到对应 engine（Turso / Supabase）。

    仅当 user 引擎已配置（SUPABASE_DATABASE_URL）时可用；market 引擎必配。
    启动校验保证"声明域 == 实际建到的 engine"，不一致直接 fail。
    注：用户库（Supabase）的建表建议由 Supabase 迁移工具独立负责，此方法
    主要用于开发期本地双 SQLite 验证 / CI 校验，不强制生产路径。
    """
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
    # user 域表 → 用户引擎（若已配置）
    if user_eng is not None:
        user_meta = MetaData()
        for t in grouped[DOMAIN_USER]:
            t.to_metadata(user_meta)
        user_meta.create_all(bind=user_eng)
    _seed_default_identity()


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


def _seed_default_identity():
    """幂等写入默认家庭 1 与默认用户 1，保证无鉴权模式下查询可用。"""
    from app.domains.families.models import Family
    from app.domains.users.models import ROLE_ADMIN, User

    with SessionLocal() as db:
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
