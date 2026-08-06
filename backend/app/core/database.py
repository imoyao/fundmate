# -*- coding: utf-8 -*-
"""数据库连接与基础仓储类."""

import os
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Engine, Integer, create_engine, event, func
from sqlalchemy.orm import Session, declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={
        'check_same_thread': False,
        'timeout': 30,  # 写锁等待 30 秒，避免立即报 locked
    },
)


@event.listens_for(Engine, 'connect')
def set_sqlite_pragma(dbapi_connection, connection_record):
    """启用 WAL 模式，提升并发读写性能"""
    cursor = dbapi_connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.close()


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
    """上下文管理器形式的数据库会话，自动关闭连接."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有数据库表，并确保默认家庭/用户存在（多用户地基）。

    默认家庭 1 + 默认用户 1 兼容既有单用户数据：模型结构变更后
    需要重建 DB 文件（见 scripts/migrate_family_id.py 的 ALTER 迁移说明）。
    """
    Base.metadata.create_all(bind=engine)
    _seed_default_identity()


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
