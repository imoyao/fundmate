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
    """创建所有数据库表."""
    Base.metadata.create_all(bind=engine)
