# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# 注意：更新为你本地的数据库连接，这里沿用你熟悉的 SQLite
SQLALCHEMY_DATABASE_URL = 'sqlite:///./invest.db'

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class BaseRepository:
    """为所有模型提供基础数据库操作的混入类"""

    def save(self, db: Session):
        db.add(self)
        db.commit()
        db.refresh(self)
        return self

    def delete(self, db: Session):
        db.delete(self)
        db.commit()


# 数据库依赖注入函数，每个API请求都会获取独立的会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 初始化数据库，建表
def init_db():
    Base.metadata.create_all(bind=engine)
