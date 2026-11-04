# -*- coding: utf-8 -*-
"""探市大类资产「长历史日线」读写层（#1460 P2）。

职责边界：本模块是 ``market_asset_history`` 的**唯一读写口**，只做持久化，不含取数。
取数编排（何时回填、失败如何兜底）在 ``services/market_history_service.py``，两者分层
是为了避免 ``market_service`` 与历史存储互相 import 成环。

为什么单独一张表而不是复用 ``market_asset_daily.close``：见 ``domains/market/models.py``
模块 docstring（历史行会顶掉快照表「最新日期覆盖全部品种」的判据）。

写入语义：**只补缺失日期**（唯一键 asset_key + trade_date），重复回填幂等；
已有日期不回写——历史收盘价一经发布不会变，回写只会把 upsert 成本摊到每次调用。
"""

from datetime import date as date_cls
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.market.models import MarketAssetHistory


def _parse_date(value: object) -> Optional[date_cls]:
    """把源侧日期（'2026-09-23' / '2026-09-23 00:00:00' / date / datetime）解析成 date。

    解析不出来的点直接跳过：历史序列允许缺点，但不允许写入一个「今天的假日期」——
    那会污染后续的增量补数判据（末日期的准确性决定要不要再取数）。
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if value is None:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def load_series(db: Session, asset_key: str, limit: Optional[int] = None) -> Tuple[List[str], List[float]]:
    """读某资产的历史序列（**升序**返回 dates / closes）。

    limit 取**尾部** N 条（近 N 个交易日），与分位 / σ 的窗口口径一致。
    """
    query = db.query(MarketAssetHistory.trade_date, MarketAssetHistory.close).filter(
        MarketAssetHistory.asset_key == asset_key
    )
    if limit:
        rows = query.order_by(MarketAssetHistory.trade_date.desc()).limit(limit).all()
        rows.reverse()
    else:
        rows = query.order_by(MarketAssetHistory.trade_date.asc()).all()
    dates = [r.trade_date.strftime('%Y-%m-%d') for r in rows]
    closes = [float(r.close) for r in rows]
    return dates, closes


def coverage(db: Session, asset_key: str) -> Tuple[int, Optional[date_cls]]:
    """返回 (行数, 最新交易日)。用于判断「库内是否已有可用历史」与「是否需要补数」。

    单条聚合查询（count + max），避免请求路径上先 count 再排序取尾（两次往返）。
    """
    count, last_date = (
        db.query(func.count(MarketAssetHistory.id), func.max(MarketAssetHistory.trade_date))
        .filter(MarketAssetHistory.asset_key == asset_key)
        .one()
    )
    return int(count or 0), last_date


def save_series(
    db: Session,
    asset_key: str,
    dates: Sequence[object],
    closes: Sequence[float],
    source: str = 'akshare',
) -> int:
    """把一次取数结果落库，**只写库内缺失的日期**，返回新增行数。

    只 flush、不 commit：请求上下文由 teardown_request_session 统一提交，
    job / CLI 这类非请求上下文由调用方自行 commit（与 market_snapshot_store 同约定）。
    """
    if not dates or len(dates) != len(closes):
        return 0

    existing = {
        r.trade_date
        for r in db.query(MarketAssetHistory.trade_date).filter(MarketAssetHistory.asset_key == asset_key).all()
    }

    added = 0
    seen = set()
    for raw_date, close in zip(dates, closes):
        trade_date = _parse_date(raw_date)
        if trade_date is None or close is None:
            continue
        # 同一批数据里可能重复出现同一交易日，先按批内去重，避免撞唯一键
        if trade_date in existing or trade_date in seen:
            continue
        seen.add(trade_date)
        db.add(
            MarketAssetHistory(
                asset_key=asset_key,
                trade_date=trade_date,
                close=float(close),
                source=source,
            )
        )
        added += 1

    if added:
        db.flush()
    return added
