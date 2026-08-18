# -*- coding: utf-8 -*-
"""跨域联合查询工具（应用层两步法，可复用基础设施）。

背景：market 域（Turso）与 user 域（Supabase）是独立引擎，SQL 层无法 JOIN。
需要"用户自选 + 市场净值"这类联合视图时，必须走"先取键 → 批量取 → 应用层拼装"，
禁止幻想 SQL join、禁止各 service 手写 N+1。

本模块提供：
- CrossDomainQuery.enrich_by_rows：通用两步法骨架，任何"user 记录 → market 数据"
  的联合查询都复用它，集中防 N+1。
- enrich_watchlist_with_market：自选 + 基金资料/净值的具体复用方法。

设计原则（见 docs/dev/db-data-domain.md 第 4 节）：
- 不持有全局引擎；session 工厂通过构造注入，便于测试与双库落地后切换。
- market 域为冗余键权威来源；user 域只存 symbol/market 字符串，不存外键。
- 所有跨域读取经此一处，杜绝散落各 service 的重复/错误实现。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, TypeVar

T = TypeVar('T')
K = TypeVar('K')


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

        market_columns：预留，限定 market 侧取回的字段（避免每次取全表）；
        当前实现取基础资料实体，后续可按需裁剪。
        """
        from app.domains.watchlist.models import WatchlistItem

        def _user_fetch(db, _fid=family_id):
            return db.query(WatchlistItem).filter(WatchlistItem.family_id == _fid).all()

        def _market_fetch(db, _keys):
            # 批量按 (market, code) 取 market 侧资料（funds 优先，回退 securities）
            from app.domains.funds.models import Fund
            from app.domains.securities.models import Security

            m: Dict[Any, Any] = {}
            for f in db.query(Fund).all():
                m[('FUND', f.fund_code)] = f
            for s in db.query(Security).all():
                m[(s.market, s.symbol)] = s
            return m

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
