# -*- coding: utf-8 -*-
"""跨域联合查询工具（应用层两步法，可复用基础设施）。

合并说明（2026-09-09）：原位于 ``services/common/`` 包内且该包**无 ``__init__.py``**、
仅此一个模块（113 行），属「为分层而分层」的空壳包，已上提为
``app.services.cross_domain``；对外符号与行为不变。

背景：market 域（Turso）与 user 域（Supabase）是独立引擎，SQL 层无法 JOIN。
需要"用户自选 + 市场净值"这类联合视图时，必须走"先取键 → 批量取 → 应用层拼装"，
禁止幻想 SQL join、禁止各 service 手写 N+1。

本模块提供：
- CrossDomainQuery.enrich_by_rows：通用两步法骨架，任何"user 记录 → market 数据"
  的联合查询都复用它，集中防 N+1。
- enrich_watchlist_with_market：自选 + 基金资料/净值的具体复用方法。
- fetch_market_records_by_keys：第 2 步「按冗余键批量取 market 侧」的集中实现
  （funds / securities 两个命名空间），独立成函数以便测试。

设计原则（见 docs/dev/db-data-domain.md 第 4 节）：
- 不持有全局引擎；session 工厂通过构造注入，便于测试与双库落地后切换。
- market 域为冗余键权威来源；user 域只存 symbol/market 字符串，不存外键。
- 所有跨域读取经此一处，杜绝散落各 service 的重复/错误实现。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, TypeVar

T = TypeVar('T')
K = TypeVar('K')

# SQLite in_ 变量上限防御（部分构建为 999，与 sync/jobs/base.py 的 IN_CHUNK_SIZE 同因）
_IN_CHUNK_SIZE = 900


def _chunked(values, size: int = _IN_CHUNK_SIZE):
    """把键集合分批，规避 SQLite in_ 变量上限。"""
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i : i + size]


def fetch_market_records_by_keys(db, keys) -> Dict[Any, Any]:
    """按 (market, code) 冗余键**批量**取 market 侧资料（funds 优先，回退 securities）。

    这是「应用层两步法」第 2 步的集中实现，独立成函数以便复用与测试。

    2026-09-11 修复（#1404）：此前该逻辑内联在
    `CrossDomainQuery.enrich_watchlist_with_market._market_fetch` 里，且**完全忽略传入的
    keys**——`for f in db.query(Fund).all()` 无条件全表加载。这与同函数上方
    「避免每次取全表」的注释意图**正好相反**：自选列表每打开一次，就把全库约 2.7 万只
    基金 + 全部证券载入 ORM 实体。现改为按 keys 分组后 `in_` 过滤。

    命名空间约定：`market == 'FUND'` 的键落 `funds` 表；其余（如 `'SH'`）落 `securities`
    表。两边 market 命名空间的映射由调用方保证（如 watchlist.market 与 Security.market）。

    Args:
        db: market 域 Session。
        keys: 可迭代的 `(market, code)` 二元组。

    Returns:
        `{(market, code): 实体}`。**只包含命中 keys 的键**——未请求的记录不会被载入。
    """
    from app.domains.funds.models import Fund
    from app.domains.securities.models import Security

    key_set = {(market, code) for market, code in keys}
    if not key_set:
        return {}

    m: Dict[Any, Any] = {}

    fund_codes = {code for market, code in key_set if market == 'FUND'}
    for chunk in _chunked(fund_codes):
        for f in db.query(Fund).filter(Fund.fund_code.in_(chunk)).all():
            m[('FUND', f.fund_code)] = f

    # 非 FUND 命名空间：先按 symbol 收窄（symbol 通常跨市场唯一），
    # 再用 (market, symbol) 精确匹配，避免把不同市场的同名代码错配进来。
    sec_keys = {k for k in key_set if k[0] != 'FUND'}
    for chunk in _chunked({code for _market, code in sec_keys}):
        for s in db.query(Security).filter(Security.symbol.in_(chunk)).all():
            if (s.market, s.symbol) in sec_keys:
                m[(s.market, s.symbol)] = s

    return m


class CrossDomainQuery:
    """跨域联合查询工具。

    参数：
        user_session_factory：返回 user 域 SQLAlchemy Session 的可调用对象。
        market_session_factory：返回 market 域 Session 的可调用对象。
        两者均为无参可调用（如 db_factory.user_session_factory），测试可注入
        内存引擎的 sessionmaker。
    """

    def __init__(self, user_session_factory, market_session_factory):
        self._user_sf = user_session_factory
        self._market_sf = market_session_factory

    def enrich_by_rows(
        self,
        user_rows_provider: Callable[[Any], Sequence[T]],
        market_fetch: Callable[[Any, Sequence[K]], Dict[K, Any]],
        join_key: Callable[[T], K],
    ) -> List[Dict[str, Any]]:
        """通用"应用层两步法"拼装。

        流程：
        1. 用 user 域 session 调 user_rows_provider 取 user 侧记录（一次查询）。
        2. 从记录中用 join_key 抽 keys，用 market 域 session 调 market_fetch
           批量取 market 侧数据（一次 in_ 查询，杜绝 N+1）。
        3. 按 join_key 把 market 数据拼装进每条 user 记录，返回 enriched 列表。

        注意：两步各自独立 session，不在同一事务；跨域本就无法 ACID，符合设计。
        user 侧无记录时直接返回空列表（避免无谓的 market 查询）。
        """
        with self._user_sf() as u_db:
            user_rows = list(user_rows_provider(u_db))
        if not user_rows:
            return []
        keys = [join_key(r) for r in user_rows]
        with self._market_sf() as m_db:
            market_map = market_fetch(m_db, keys)
        enriched: List[Dict[str, Any]] = []
        for row in user_rows:
            item: Dict[str, Any] = dict(row.__dict__) if hasattr(row, '__dict__') else {'_row': row}
            item.pop('_sa_instance_state', None)
            item['market_data'] = market_map.get(join_key(row))
            enriched.append(item)
        return enriched

    def enrich_watchlist_with_market(
        self,
        family_id: int,
        market_columns: Sequence[str] | None = None,
    ) -> List[Dict[str, Any]]:
        """自选 + 基金资料/净值 的具体复用方法。

        取某 family 的全部自选（user 域），按 (market, symbol) 批量取市场侧资料
        （market 域 funds/securities），拼装返回。供前端"自选列表带实时估值"复用。

        market_columns：**预留参数**，用于将来限定 market 侧取回的**字段**；当前实现返回
        基础资料实体（整行）。注意它已与「避免全表」无关——**行**范围的收窄已由
        `fetch_market_records_by_keys` 按 keys 落地（2026-09-11 修复 #1404）。
        """
        from app.domains.watchlist.models import WatchlistItem

        def _user_fetch(db, _fid=family_id):
            return db.query(WatchlistItem).filter(WatchlistItem.family_id == _fid).all()

        def _market_fetch(db, _keys):
            # 批量按 (market, code) 取 market 侧资料；只加载请求到的键，不做全表扫描。
            # 具体实现见模块级 fetch_market_records_by_keys（2026-09-11 修复 #1404）。
            return fetch_market_records_by_keys(db, _keys)

        def _join_key(row):
            # watchlist.(market, symbol) 标准化代码构成跨域冗余键，market 域为权威。
            # 注意：两边 market 命名空间需由调用方约定一致（watchlist.market 如
            # 'FUND'/'SH' 与 Security.market 如 'CN_A' 的映射由上层保证）。
            return (row.market, row.symbol)

        return self.enrich_by_rows(
            user_rows_provider=_user_fetch,
            market_fetch=_market_fetch,
            join_key=_join_key,
        )
