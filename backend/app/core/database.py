# -*- coding: utf-8 -*-
"""数据库连接与基础仓储类."""

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = 'sqlite:///./invest.db'

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={'check_same_thread': False},
)
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
