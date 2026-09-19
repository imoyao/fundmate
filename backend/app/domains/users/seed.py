# -*- coding: utf-8 -*-
"""默认家庭 / 默认用户种子（#1607：从 `app/core/database.py` 移出）。

`families` / `users` 属 user 域业务数据（D1 家庭共享层），而 core 是业务无关的基础设施层，
把种子业务数据硬编码在 core 会让基础设施层反向依赖领域模型（此前只能靠函数内延迟 import
掩盖，见 `docs/working-notes/backend-architecture-audit-2026-09-19.md` §4.2）。因此种子实现移到
本模块，由组合根在 `init_db()` 建表之后调用。

写入目标固定为 **user 域引擎**（`get_user_sessionmaker()` 的 bind）：单库模式下与 market 同库，
双库模式下必须落 user 引擎——此前用 market 引擎写 user 域表，真双库分离时会落错库（#1219）。
"""

from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import MetaData

from app.core.database import Base, get_user_sessionmaker
from app.core.db_factory import DOMAIN_USER, DatabaseFactory
from app.domains.families.models import Family
from app.domains.users.models import ROLE_ADMIN, User


def _ensure_user_tables(bind) -> None:
    """确保 user 域表存在于目标引擎。

    调用方（组合根）通常刚跑过 `init_db()`，表已就绪；但双库下 user 域可能落在独立
    文件 / Supabase 上，且本函数也可能被单独调用，故保留这层幂等兜底
    （`create_all` 对已存在的表是空操作）。
    """
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    user_meta = MetaData()
    for table in grouped[DOMAIN_USER]:
        table.to_metadata(user_meta)
    user_meta.create_all(bind=bind)


def seed_default_identity() -> None:
    """幂等写入默认家庭 1 与默认用户 1，保证无鉴权模式下查询可用。

    默认用户 1 是 `AUTH_ENABLED` 未启用时的回退身份，也是既有单用户数据的归属。
    """
    target_bind = get_user_sessionmaker().kw['bind']
    _ensure_user_tables(target_bind)

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
