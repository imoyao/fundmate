# -*- coding: utf-8 -*-
"""数据库连接与基础仓储类."""

import os
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Column, DateTime, Engine, Integer, func, inspect
from sqlalchemy import exc as sa_exc
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.sql import visitors

from app.core.db_factory import (
    DATA_DOMAIN_REGISTRY,
    DOMAIN_APP,
    DOMAIN_USER,
    DatabaseFactory,
)
from app.core.migrations import (
    migrate_advisor_portfolio_metadata,
    migrate_advisor_portfolio_metrics,
    migrate_advisor_portfolio_provenance,
    migrate_channel_link_indexes,
    migrate_positions_money_fund_flag,
    migrate_positions_symbol_norm,
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
# 每张表落到其数据域引擎（user 表→user_engine，market 表→engine）。
# 这是 #1085 的核心：业务层无需改动调用点，user 域数据自动路由到 user 引擎。
#
# **解析时机（#1608，对齐 D-2026-09-15 的「binds 下沉到首次路由时解析」）**：
# 不用 ``Session(binds=...)``，改为**查询期按语句解析**。原因是 SQLAlchemy 在
# ``Session.__init__`` 里就 ``for key, bind in binds.items()`` 把「表 → 引擎」**全量
# 物化**（2.0.52 源码实证）——注入 binds 的那一刻必然构造两个域的引擎，于是 #1513 为
# 「不限域入口不因缺驱动崩溃」做的惰性构造，会在**第一次 ``SessionLocal()``** 时被抵消
# （实测：user 域驱动缺 pg8000 时，只调一次 ``SessionLocal()`` 即 ModuleNotFoundError，
# 且被请求的域恰是 user）。改为查询期解析后，只有语句真正涉及 user 域表时才碰 user 引擎。
def _domain_for_statement(mapper, clause) -> Optional[str]:
    """判定语句涉及哪个数据域；无法判定时返回 ``None``（调用方按应用域兜底）。

    **查找顺序与 SQLAlchemy 2.0 ``Session.get_bind`` 对 ``binds`` 的查找逐条对齐**：
    先由 mapper 落到 ``persist_selectable``，再遍历 clause 里的表；命中的第一张
    **已登记模型表**决定域。只认 identity 属于 ``Base.metadata`` 的表——与旧实现
    「binds 以 Table 对象为键命中」等价，别的 MetaData 上的同名表不参与路由。
    """
    if mapper is not None:
        try:
            inspected = inspect(mapper)
        except sa_exc.NoInspectionAvailable as err:
            # 与 SQLAlchemy 一致：不可映射的类显式报错，不静默回落默认 bind
            if isinstance(mapper, type):
                raise sa_exc.UnmappedClassError(mapper) from err
            raise
        if clause is None:
            clause = inspected.persist_selectable

    if clause is None:
        return None

    for obj in visitors.iterate(clause):
        name = getattr(obj, 'name', None)
        if not isinstance(name, str) or Base.metadata.tables.get(name) is not obj:
            continue
        domain = DATA_DOMAIN_REGISTRY.get(name)
        if domain is not None:
            return DOMAIN_USER if domain == DOMAIN_USER else DOMAIN_APP
    return None


class _RoutingSession(Session):
    """域路由 Session：bind 在**查询期**解析（见 :func:`_domain_for_statement`）。

    未命中任何已登记表（裸 ``text()`` 语句、ad-hoc 表）与无法判定时回落**应用域**，
    与旧实现「默认 bind = 应用引擎」一致。
    """

    def get_bind(self, mapper=None, *, clause=None, bind=None, **kw):
        if bind is None:
            bind = _engine_for(_domain_for_statement(mapper, clause) or DOMAIN_APP)
        return super().get_bind(mapper, clause=clause, bind=bind, **kw)


class _RoutingSessionMaker(sessionmaker):
    """sessionmaker 子类：**不注入 binds**（那会在开会话时全量构造两域引擎，见上文）。

    ``bind`` 仍惰性注入（#1513）：构造时不写死 bind，避免
    `SessionLocal = ...(bind=engine)` 在导入期就把引擎造出来；默认 bind 首次开 session
    时才解析，具体语句属于哪个域由 :class:`_RoutingSession` 逐句判定。
    """

    def __call__(self, **kw):
        kw.setdefault('bind', _engine_for(DOMAIN_APP))
        return super().__call__(**kw)


SessionLocal = _RoutingSessionMaker(class_=_RoutingSession, autocommit=False, autoflush=False)

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


def _request_scope():
    """返回当前请求的 ``flask.g``（请求上下文）；非请求上下文返回 ``None``。

    只有请求上下文才启用「请求级单会话」（#1632）；job / CLI / scheduler 走各自独立会话。
    """
    try:
        from flask import g, has_request_context
    except Exception:  # pragma: no cover - flask 缺失时按非请求上下文处理
        return None
    return g if has_request_context() else None


# 请求级会话槽位（挂在 ``flask.g`` 上，彼此独立）：应用会话（#1632）、user / market 域会话（#1640）
_SESSION_SLOTS = ('_db_session', '_user_db_session', '_market_db_session')


@contextmanager
def _scoped_session(slot: str, factory):
    """请求级单会话的通用实现（#1632 应用会话；#1640 扩展到 user / market 域会话）。

    - **请求上下文**：按 ``slot`` 首次创建 Session，此后同一请求内**顺序或嵌套**进入都复用
      同一个 Session；提交 / 回滚由 :func:`teardown_request_session` 在请求结束时统一执行
      ——本函数不提交、不关闭。
    - **非请求上下文**（job / CLI / scheduler）：每次独立会话，只关闭；提交时机由调用方决定。
    - **槽位彼此独立**：``get_db()`` / ``user_session()`` / ``market_session()`` 在同一请求内
      是互不干扰的 Session，不会互相提交或回滚（各自回到自己的引擎 / 路由）。
    """
    scope = _request_scope()
    if scope is None:
        db = factory()
        try:
            yield db
        finally:
            db.close()
        return

    session = getattr(scope, slot, None)
    if session is None:
        session = factory()
        setattr(scope, slot, session)
    yield session


@contextmanager
def get_db():
    """应用运行库会话上下文（请求级单会话，事务边界在请求 teardown，#1632）。

    请求上下文：同一请求内**顺序或嵌套**的多次 ``get_db()`` 都复用同一个 Session，
    因此「一个请求一个事务」成立；提交 / 回滚由
    :func:`teardown_request_session` 在请求结束时统一执行，本函数不提交、不关闭。

    非请求上下文（job / CLI / scheduler）：保持原语义——每次独立会话、只关闭，
    提交时机由调用方自行决定。

    服务方法 / ``BaseRepository`` 内不应再 ``commit()``：它们只 ``flush()``
    （conventions §2.13 方案 A）。
    """
    with _scoped_session('_db_session', get_session) as db:
        yield db


def teardown_request_session(exc=None):
    """请求收尾：统一提交（成功）/ 回滚（异常）并关闭**全部**请求级会话（#1632 / #1640）。

    这是「一个请求一个事务」的**真正边界**：``get_db()`` / ``user_session()`` /
    ``market_session()`` 都只复用（不提交、不关闭），由本函数在请求结束时统一
    commit / rollback，保证同一请求内顺序 / 嵌套的多次会话获取都落在同一事务里
    （否则先后两个 ``with get_db()`` 块会在第一块退出时提前提交，并令首块对象
    detach+expire，触发 ``DetachedInstanceError``）。

    ``flask.g`` 上的三个槽位都会被收尾；任一会话提交失败都会被回滚并**在收尾完其余会话后**
    上抛（保证不留未关闭的连接）。非请求上下文（未挂 ``flask.g``）为空操作；无会话亦为空操作（幂等）。
    """
    scope = _request_scope()
    if scope is None:
        return

    pending: list[Session] = []
    for slot in _SESSION_SLOTS:
        session = getattr(scope, slot, None)
        if session is not None:
            setattr(scope, slot, None)
            pending.append(session)
    if not pending:
        return

    failure: Optional[BaseException] = None
    for session in pending:
        try:
            if exc is not None:
                session.rollback()
            else:
                session.commit()
        except Exception as err:  # noqa: BLE001 - 提交失败需先回滚，收尾其余会话后再上抛
            failure = failure or err
            try:
                session.rollback()
            except Exception:  # pragma: no cover - 回滚都失败时无法再补救
                pass
        finally:
            session.close()
    if failure is not None:
        raise failure


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
    # positions.symbol_norm 归一身份列 + 唯一索引（#1662 后续）：同上须先于结构校验
    migrate_positions_symbol_norm(user_eng)
    # positions.is_money_fund 存量重算（#1661 收尾）：读写路径已修，历史标记不会自己变；
    # 与 symbol_norm 同处 user 域、同样须先于结构校验（幂等，名录不可达时保持原值）
    migrate_positions_money_fund_flag(user_eng)
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
        # positions.symbol_norm 归一身份列 + 唯一索引（#1662 后续）：create_all 不替存量表加列，
        # 迁移须先于结构校验（否则「模型有列、库没列」直接拒绝启动）
        migrate_positions_symbol_norm(user_eng)
        # positions.is_money_fund 存量重算（#1661 收尾）：同上，先于结构校验、幂等
        migrate_positions_money_fund_flag(user_eng)
        _validate_schema(user_eng, user_meta, label='user')
        # 存量库回归迁移（#1286 / #1362 评审 #3）：watchlist 唯一键回归基线，
        # 双库模式同样按 user 域引擎自动执行，幂等。
        migrate_watchlist_venue_not_null(user_eng)
        migrate_watchlist_unique_key(user_eng)
        migrate_watchlist_family_scoped_unique_key(user_eng)


def _new_market_session() -> Session:
    """market 域会话工厂（**晚绑定**：测试会 monkeypatch ``db_factory.market_session_factory``）。"""
    from app.core.db_factory import market_session_factory

    return market_session_factory()()


def _new_user_session() -> Session:
    """user 域会话工厂（**晚绑定**：测试会 monkeypatch ``db_factory.user_session_factory``）。"""
    from app.core.db_factory import user_session_factory

    return user_session_factory()()


@contextmanager
def market_session():
    """market 域会话上下文（读取净值 / 行情 / 温度 / 基金资料等；请求级单会话，#1640）。

    规则与 :func:`get_db` 一致：请求内顺序 / 嵌套进入复用同一 Session，提交 / 回滚由
    :func:`teardown_request_session` 统一执行（视图无需显式 ``commit()``）；
    非请求上下文每次独立会话、只关闭。

    注：当前仓库内**无调用方**（保留 API）；将来若在请求里经它写入，请依赖本请求级边界，
    不要再逐视图显式 ``commit()``。
    """
    with _scoped_session('_market_db_session', _new_market_session) as db:
        yield db


@contextmanager
def user_session():
    """user 域会话上下文（读写账户 / 持仓 / 交易 / 自选 / 审计等；请求级单会话，#1640）。

    规则与 :func:`get_db` 一致（即 #1632 的 user 域版本）：请求上下文内**顺序或嵌套**的多次
    ``user_session()`` 复用同一 Session，提交 / 回滚由 :func:`teardown_request_session` 统一执行
    —— 因此**视图层无需再显式 ``commit()``**；非请求上下文（job / CLI / scheduler）每次独立会话、
    只关闭，提交时机由调用方决定。

    历史教训（#1640）：本函数原先只 ``yield`` + ``close()``、**既不提交也不回滚**，导致使用它的视图
    必须逐个显式 ``commit()``，否则写入随连接关闭**静默丢失**（实测：把
    ``domains/reconciliation/views.py`` 的 commit 去掉后 6 个用例转红）。
    """
    with _scoped_session('_user_db_session', _new_user_session) as db:
        yield db


# 注：默认家庭 / 默认用户种子（原 `_seed_default_identity`）已移至
# `app.domains.users.seed.seed_default_identity()`——core 不 import 领域层（#1607），
# 「种子业务数据」属 user 域职责，由组合根在建表后调用。
