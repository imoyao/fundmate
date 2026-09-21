# -*- coding: utf-8 -*-
"""数据库连接与基础仓储类."""

import os
import sys
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
from app.core.migrations import (
    migrate_advisor_portfolio_metadata,
    migrate_advisor_portfolio_metrics,
    migrate_advisor_portfolio_provenance,
    migrate_channel_link_indexes,
    migrate_watchlist_family_scoped_unique_key,
    migrate_watchlist_name_snapshot,
    migrate_watchlist_unique_key,
    migrate_watchlist_venue_not_null,
)

# 保留历史符号：部分模块（如 sync/orchestrator 备份路径）仍引用，
# 指向当前应用运行库的 URL，供文件库路径推断使用。
SQLALCHEMY_DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./invest.db')

# ⚠️ engine / user_engine **不再在导入期构造**（#1513）。
#
# 旧写法是模块级 `engine = DatabaseFactory.create(DOMAIN_APP)`——`create_engine()` 会
# 立刻解析方言并 import 对应 DBAPI，于是「缺一个域的驱动/连接串」被放大成「整个后端
# 不可导入」：CI 只想跑 market 域调度，却因 user 域缺 psycopg2 在 import 阶段崩溃，
# 且栈顶看着像「模型导入失败」，报错点离真因极远（#1434 / #1514）。
#
# 现改为 PEP 562 模块级 __getattr__ 惰性构造：首次访问 `database.engine` /
# `database.user_engine` 时才建引擎，对外名字与语义不变，conftest 的 monkeypatch
# 重定向照旧生效（setattr 会写进模块 __dict__，之后查找不再走 __getattr__）。
# 模块内部一律经 _engine_for(domain) 取值，不要直接写裸 `engine`。
#
# 域语义：
# - engine（DOMAIN_APP）：应用运行库（市场域/非敏感数据），按 APP_ENV 自动切换，
#   dev -> 本地 SQLite；prod -> Turso（回退 DATABASE_URL）。见 db_factory。
# - user_engine（DOMAIN_USER）：配了 SUPABASE_DATABASE_URL 即真 Supabase；
#   **development 默认与 market 同库**（DEV_DATABASE_URL，缺省 invest.db）——单库，
#   本地既有数据零迁移；只有显式配 DEV_USER_DATABASE_URL 才拆独立文件（双库模拟）。
#   prod/staging 未配 Supabase 时回退 USER_DATABASE_URL（缺省与 DATABASE_URL 同库）。


def _engine_for(domain: str) -> Engine:
    """取指定域的当前引擎（惰性，且尊重测试的 monkeypatch）。

    取值顺序：
    1. 模块属性 `engine` / `user_engine` —— conftest 会把它们重定向到内存库，必须优先；
       这里只读 `__dict__` 而不触发 `__getattr__`，避免「取值」反过来把引擎造出来；
    2. 否则走 `DatabaseFactory.create()`（内部有缓存，重复调用不重复建引擎）。
    """
    module = sys.modules[__name__]
    attr = 'user_engine' if domain == DOMAIN_USER else 'engine'
    eng = vars(module).get(attr)
    return eng if eng is not None else DatabaseFactory.create(domain)


def __getattr__(name: str):
    """PEP 562：惰性构造 `engine` / `user_engine`（首次访问才 create_engine，见 #1513）。"""
    if name == 'engine':
        return DatabaseFactory.create(DOMAIN_APP)
    if name == 'user_engine':
        return DatabaseFactory.create(DOMAIN_USER)
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# 按表路由的会话：单一 session 即可跨域查询（如持仓页同时读 positions + daily_worth），
# 每张表按需落到其数据域引擎（user 表→user_engine，market 表→engine）。
# 这是 #1085 的核心：业务层无需改动调用点，user 域数据自动路由到 user 引擎。
def _build_routing_binds():
    from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER

    binds = {}
    for table in Base.metadata.tables.values():
        domain = DATA_DOMAIN_REGISTRY.get(table.name)
        binds[table] = _engine_for(DOMAIN_USER if domain == DOMAIN_USER else DOMAIN_APP)
    return binds


_ROUTING_BINDS = None


def _get_routing_binds():
    global _ROUTING_BINDS
    if _ROUTING_BINDS is None:
        _ROUTING_BINDS = _build_routing_binds()
    return _ROUTING_BINDS


def reset_routing_binds() -> None:
    """使已缓存的域路由 binds 失效，下次 ``SessionLocal()`` 时按当前引擎重建。

    测试替换引擎（conftest 重定向 ``engine`` / ``user_engine``）或运行时切换引擎后必须
    调用，否则 ``_ROUTING_BINDS`` 仍指向旧引擎，导致会话偷偷连到旧库（#1608）。
    """
    global _ROUTING_BINDS
    _ROUTING_BINDS = None


class _RoutingSessionMaker(sessionmaker):
    """sessionmaker 子类：每次创建 session 时按表注入域路由 binds（懒构建一次）。

    bind 同样惰性注入（#1513）：构造时不传 bind，避免 `SessionLocal = ...(bind=engine)`
    在导入期就把引擎造出来；默认 bind 推迟到首次开 session 时才解析。
    """

    def __call__(self, **kw):
        if 'binds' not in kw:
            kw['binds'] = _get_routing_binds()
        kw.setdefault('bind', _engine_for(DOMAIN_APP))
        return super().__call__(**kw)


SessionLocal = _RoutingSessionMaker(autocommit=False, autoflush=False)

Base = declarative_base()


class BaseRepository:
    """为所有模型提供基础数据库操作的混入类（#1609：只 flush，不 commit）。

    事务边界由调用方持有（视图 / 用例编排层 / ``with_db`` 请求级 unit-of-work）：
    本类只把变更刷进当前事务（``flush()``），提交 / 回滚由边界统一决定（conventions §2.13 方案 A）。
    """

    def save(self, db: Session):
        """保存实例到当前事务（flush，不提交）."""
        db.add(self)
        db.flush()
        db.refresh(self)
        return self

    def delete(self, db: Session):
        """从当前事务删除实例（flush，不提交）."""
        db.delete(self)
        db.flush()


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


def get_session() -> Session:
    """应用运行库会话（单一入口，#1608）。

    业务层一律经本函数开会话，不要在模块里 ``from app.core.database import SessionLocal``
    后直接 ``SessionLocal()``——统一入口便于测试重定向与未来会话生命周期治理（#1609）。
    ``SessionLocal`` 仍是底层路由工厂，仅供本函数与测试夹具使用。
    """
    return SessionLocal()


@contextmanager
def get_db():
    """上下文管理器形式的数据库会话（应用运行库），自动关闭连接."""
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_engine(domain: str = DOMAIN_APP) -> Optional[Engine]:
    """按数据域取已缓存 engine（接缝：业务层后续按域路由）。

    - DOMAIN_APP：应用运行库（默认，市场域/非敏感数据）。
    - DOMAIN_USER：用户核心账本库。**永不返回 None**——未配 Supabase 时按
      development 回退（默认与 market 同库，显式配 DEV_USER_DATABASE_URL 才独立），
      其余环境回退 USER_DATABASE_URL。调用方无需判空。
    """
    return DatabaseFactory.create(domain)


def get_user_sessionmaker() -> sessionmaker:
    """用户库 SessionLocal（未配 Supabase 时本地回退，永不返回 None）。

    单库/双库统一可用：配置了 SUPABASE_DATABASE_URL 即真 Supabase；
    未配置则 development 下**默认与 market 同库**（缺省 invest.db，即单库），
    显式配 DEV_USER_DATABASE_URL 才落到独立文件（双库模拟）。调用方无需判断空值。
    """
    return sessionmaker(autocommit=False, autoflush=False, bind=_engine_for(DOMAIN_USER))


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
    """创建所有表（按数据域分建）——只做「结构」，不写业务种子数据。

    双库就绪（#1085）：按数据域把表分别建到对应引擎——
    market 域 → engine（应用运行库），user 域 → user_engine（Supabase / 本地回退）。
    单库模式下两引擎指向同一库，等价于旧单库建表；双库模式下自然分离。

    边界（#1607）：core 是业务无关的基础设施层，**不 import 领域层**，故
    「默认家庭 1 + 默认用户 1」这类 user 域业务数据的播种已移到
    `app.domains.users.seed.seed_default_identity()`，由调用方（应用组合根 / CLI 入口）
    在建表之后自行调用。同理，表集合取决于**调用方已 import 的模型**：本函数不再代为
    导入顶层模型（`app.models.sync_log`），入口须自行保证模型注册齐全，否则缺表。
    """
    from sqlalchemy.schema import MetaData

    from app.core.db_factory import (
        DOMAIN_MARKET,
        DOMAIN_USER,
        DatabaseFactory,
    )

    DatabaseFactory.validate_domain_labels(Base.metadata)
    grouped = DatabaseFactory.tables_by_domain(Base.metadata)
    # 引擎在此才真正构造（#1513）：导入期不建，故只跑 market 域的入口不受 user 域驱动缺失牵连
    app_eng = _engine_for(DOMAIN_APP)
    user_eng = _engine_for(DOMAIN_USER)
    # market 域表 → 应用引擎
    market_meta = MetaData()
    for t in grouped[DOMAIN_MARKET]:
        t.to_metadata(market_meta)
    market_meta.create_all(bind=app_eng)
    # 投顾组合指标列（#1392）：create_all 不替存量表加列，迁移须在结构校验前补齐，
    # 否则 _validate_schema 会因模型列多于库表而报错阻断启动
    migrate_advisor_portfolio_metrics(app_eng)
    # 投顾组合策展元数据列（#1468）：波动率/夏普/配置目标/产品类型，同上须先于结构校验
    migrate_advisor_portfolio_metadata(app_eng)
    # 投顾组合来历列（#1392）：source 来源标记 + extra 平台特有字段，同上须先于结构校验
    migrate_advisor_portfolio_provenance(app_eng)
    # channel_links.to_symbol 索引（#1491 评审）：create_all 只建新表、不给存量表加索引
    migrate_channel_link_indexes(app_eng)
    _validate_schema(app_eng, market_meta, label='market')
    # user 域表 → 用户引擎
    user_meta = MetaData()
    for t in grouped[DOMAIN_USER]:
        t.to_metadata(user_meta)
    user_meta.create_all(bind=user_eng)
    # watchlist.name 名称快照列（#1508）：create_all 不替存量表加列，迁移须先于结构校验，
    # 否则 _validate_schema 会因模型列多于库表而报错阻断启动（与下方投顾列同因）。
    migrate_watchlist_name_snapshot(user_eng)
    _validate_schema(user_eng, user_meta, label='user')
    # 存量库回归迁移（#1286 / #1362 评审 #3）：watchlist 唯一键 (symbol, venue)
    # → (symbol, market, venue) 防跨市场同码冲突。create_all 只增表不改表，旧库
    # 仍停留旧约束会静默失效，故启动期按 user 域自动执行，幂等可重复跑。
    # 先回填历史 NULL venue（否则唯一键对存量行失效），再迁唯一键；
    # 最后补 family_id（#1491 评审阻断项：唯一键不含 family_id 会让其他家庭再也无法关注同一标的）
    migrate_watchlist_venue_not_null(user_eng)
    migrate_watchlist_unique_key(user_eng)
    migrate_watchlist_family_scoped_unique_key(user_eng)


def init_db_split():
    """双库模式：按数据域分别 create_all 到对应 engine（只做结构，不播种子）。

    - market 引擎必配（本地 dev 为 invest.db，生产为 Turso）。
    - user 引擎：配了 SUPABASE_DATABASE_URL 即 Supabase；本地 development 下
      显式配置 DEV_USER_DATABASE_URL 才是独立文件（本地双库模拟），未配置时
      与 market 共用同一本地库（默认单库，本地既有数据立即可见）。显式拆分时
      user 表才落到「与 market 不同的引擎」，域边界成立。

    启动校验保证"声明域 == 实际建到的 engine"，不一致直接 fail。
    注：用户库（Supabase）生产建表建议由 Supabase 迁移工具独立负责，此方法
    主要用于开发期本地双库验证 / CI 校验，不强制生产路径。本地需要模拟双库时，
    请先显式设置 DEV_USER_DATABASE_URL 再调用本方法。

    边界（#1607）：默认家庭 / 默认用户种子已移到
    `app.domains.users.seed.seed_default_identity()`，需要时由调用方在本方法之后调用。
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
    # 投顾组合指标列（#1392）：迁移须在结构校验前补齐，否则 _validate_schema 报错阻断启动
    migrate_advisor_portfolio_metrics(app_eng)
    # 投顾组合策展元数据列（#1468）：波动率/夏普/配置目标/产品类型，同上须先于结构校验
    migrate_advisor_portfolio_metadata(app_eng)
    # 投顾组合来历列（#1392）：source 来源标记 + extra 平台特有字段，同上须先于结构校验
    migrate_advisor_portfolio_provenance(app_eng)
    # channel_links.to_symbol 索引（#1491 评审）
    migrate_channel_link_indexes(app_eng)
    _validate_schema(app_eng, market_meta, label='market')
    # user 域表 → 用户引擎（若已配置）
    if user_eng is not None:
        user_meta = MetaData()
        for t in grouped[DOMAIN_USER]:
            t.to_metadata(user_meta)
        user_meta.create_all(bind=user_eng)
        # watchlist.name 名称快照列（#1508）：同上，须先于结构校验
        migrate_watchlist_name_snapshot(user_eng)
        _validate_schema(user_eng, user_meta, label='user')
        # 存量库回归迁移（#1286 / #1362 评审 #3）：watchlist 唯一键回归基线，
        # 双库模式同样按 user 域引擎自动执行，幂等。
        migrate_watchlist_venue_not_null(user_eng)
        migrate_watchlist_unique_key(user_eng)
        migrate_watchlist_family_scoped_unique_key(user_eng)


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


# 注：默认家庭 / 默认用户种子（原 `_seed_default_identity`）已移至
# `app.domains.users.seed.seed_default_identity()`——core 不 import 领域层（#1607），
# 「种子业务数据」属 user 域职责，由组合根在建表后调用。
