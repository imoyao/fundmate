# -*- coding: utf-8 -*-
"""投顾组合净值序列：目标池解析、落库、按需补拉（详情页走势图底数）。

## 这个模块回答的问题

详情页 `/api/products/trend/?asset_type=portfolio&symbol=ZH012926` 此前恒为「无序列」，
原因是 ``product_trend._NO_SERIES_TYPES`` 把 ``portfolio`` 直接判死。事实并非没有数据源
——且慢 MCP 的 ``GetPortfolioNavHistory`` 一次调用就能返回该组合成立至今的日频净值
（实测 ZH012926 = 2250 行）。缺的是「取 → 存 → 读」这条链。

## 三条边界（都是被既有教训逼出来的）

1. **抓取目标池必须显式**（`docs/spec/data-strategy.md` 数据准入第 3 问）：
   只抓**用户触达**的组合（自选 ∪ 持仓，见 :func:`tracked_codes`），
   **不做**「库里 114 个组合全量刷」的静默退化——那正是数据策略明令禁止的形态。
   首次查看某个不在池内的组合时按需补拉一次并落库，之后它自然进入后续日更的判断依据。
2. **「没有该数据面」与「这次没调成」必须分开**：
   平台不提供序列 ⇒ ``fetch_nav_history`` 返回 ``[]``（这是事实，不算错）；
   调不通（Token 缺失 / 传输失败）⇒ 抛错，由本模块**显式降级并记日志**，
   绝不把异常吞成空列表——空列表会被上层读成「这组合没有净值」。
3. **按需补拉要节流**：详情页是 GET，不能每刷一次就打一次 MCP。
   判据是「库里最新一行太旧」+「进程内 6 小时内没试过」，两者**同时**成立才拉。
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.funds.models import AdvisorPortfolio, AdvisorPortfolioNav
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.services.mcp.errors import McpError

#: 快照「够新」的判据（自然日）。组合净值 T+1 发布，3 天容差覆盖周末与节假日。
FRESH_DAYS = 3
#: 进程内节流：同一组合两次补拉尝试的最小间隔（秒）。失败也计时，
#: 否则 MCP 抖动时每刷一次页面就重试一次，把「失败」放大成请求风暴。
RETRY_INTERVAL_SECONDS = 6 * 3600

#: 落库来源码（与 ``advisor_holdings.source`` 同口径；平台名小写）
SOURCE_BY_PLATFORM = {'QIEMAN': 'qieman'}

#: 组合代码在 positions / watchlist 里的形态可能是 ``NO_VENUE:ZH012926``
_VENUE_PREFIXES = ('NO_VENUE:', 'OTC:', 'EXCHANGE:')

_lock_guard = threading.Lock()
_code_locks: Dict[str, threading.Lock] = {}
#: code → 上次补拉尝试的时间戳（monotonic）
_last_attempt: Dict[str, float] = {}


def _code_lock(code: str) -> threading.Lock:
    """按组合取一把进程内锁（同一组合并发首访只让一个线程去打 MCP）。"""
    with _lock_guard:
        lock = _code_locks.get(code)
        if lock is None:
            lock = threading.Lock()
            _code_locks[code] = lock
        return lock


def normalize_code(raw: Any) -> str:
    """把自选 / 持仓里的组合标识归一成 ``advisor_portfolios.code`` 形态。

    只做三件事：去空白、大写、剥场地前缀。**不猜平台**——且慢码含
    ``LONG_WIN`` / ``J7`` / ``WALLET`` / ``SIxxxx`` 等非 ``ZH`` 命名空间，
    按前缀判平台会把它们误送进天天适配器（``advisor_portfolio_job._infer_platform`` 的教训）。
    """
    code = str(raw or '').strip().upper()
    for prefix in _VENUE_PREFIXES:
        if code.startswith(prefix):
            code = code[len(prefix) :]
            break
    return code


def tracked_codes(db: Session) -> List[str]:
    """用户触达的投顾组合代码（自选 ∪ 持仓），升序去重。

    Args:
        db: 会话。单库模式下 user / market 同库，直接可用；双库模式下本函数
            与 ``orchestrator._load_codes_from_database`` 同口径（那边也只读同一个
            session），保持一致性而不是在这里另造一套跨域机制。

    Returns:
        组合代码列表；用户一个都没关注时返回 ``[]``（**合法状态**，不是故障）。
    """
    codes: set[str] = set()

    for (symbol,) in db.query(WatchlistItem.symbol).filter(WatchlistItem.asset_type == 'portfolio').all():
        code = normalize_code(symbol)
        if code:
            codes.add(code)

    # 清仓行仍留在表里（#2343「清仓不删行」），故不加 ownership_status 过滤——
    # 清仓后用户回看详情页同样需要走势。
    for (symbol,) in db.query(Position.symbol).filter(Position.asset_type == 'portfolio').all():
        code = normalize_code(symbol)
        if code:
            codes.add(code)

    return sorted(codes)


def tracked_portfolios(db: Session) -> List[AdvisorPortfolio]:
    """把 :func:`tracked_codes` 映射成库内组合实体（未建档的代码自然缺席）。"""
    codes = tracked_codes(db)
    if not codes:
        return []
    rows = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code.in_(codes)).all()
    # 保持 tracked_codes 的稳定顺序，便于日志与测试断言
    by_code = {r.code: r for r in rows}
    return [by_code[c] for c in codes if c in by_code]


def source_of(portfolio: AdvisorPortfolio) -> str:
    """组合的净值来源码（落库用）。未登记平台回退平台名小写。"""
    platform = str(portfolio.platform or '').strip().upper()
    return SOURCE_BY_PLATFORM.get(platform, platform.lower() or 'unknown')


def latest_nav_date(db: Session, portfolio_id: int) -> Optional[dt.date]:
    """该组合库里最新一条净值的日期；无序列时 ``None``。"""
    row = (
        db.query(AdvisorPortfolioNav.nav_date)
        .filter(AdvisorPortfolioNav.portfolio_id == portfolio_id)
        .order_by(AdvisorPortfolioNav.nav_date.desc())
        .first()
    )
    return row[0] if row else None


def save_nav_rows(
    db: Session,
    portfolio_id: int,
    rows: Sequence[Dict[str, Any]],
    source: str,
) -> int:
    """把适配器给的净值序列写入库（幂等）。

    - 新日期 ⇒ 插入；
    - 已存在的日期但净值变了 ⇒ 更新（上游偶尔会修正当日净值，静默忽略会让曲线与
      组合页的「最新净值」对不上）；
    - 解析不出的行 ⇒ 丢弃（**不补 0**：净值 0 会在图上造出一根假暴跌）。

    Returns:
        实际写入（插入 + 更新）的行数。
    """
    parsed: Dict[dt.date, float] = {}
    for raw in rows or []:
        if not isinstance(raw, dict):
            continue
        day = _parse_date(raw.get('nav_date'))
        nav = _to_float(raw.get('nav'))
        if day is None or nav is None or nav <= 0:
            continue
        parsed[day] = nav
    if not parsed:
        return 0

    existing = {
        day: (nav, pk)
        for pk, day, nav in db.query(
            AdvisorPortfolioNav.id, AdvisorPortfolioNav.nav_date, AdvisorPortfolioNav.nav
        ).filter(AdvisorPortfolioNav.portfolio_id == portfolio_id)
    }

    written = 0
    for day, nav in parsed.items():
        hit = existing.get(day)
        if hit is None:
            db.add(AdvisorPortfolioNav(portfolio_id=portfolio_id, nav_date=day, nav=nav, source=source))
            written += 1
        elif _to_float(hit[0]) != nav:
            obj = db.get(AdvisorPortfolioNav, hit[1])
            if obj is not None:
                obj.nav = nav
                obj.source = source
                written += 1

    if written:
        db.commit()
    return written


def refresh_series(
    db: Session,
    portfolio: AdvisorPortfolio,
    *,
    force: bool = False,
) -> int:
    """拉取该组合的净值序列并落库；返回写入行数（0 表示没拉或没变化）。

    失败**不抛给调用方**（详情页不该因为上游抖动整块 500），但会记日志——
    「降级」与「静默」的区别就在这条日志上。
    """
    code = portfolio.code
    if not force and not _needs_refresh(db, portfolio):
        return 0

    lock = _code_lock(code)
    if not lock.acquire(blocking=False):
        # 已有线程在拉同一只：本次直接放弃，返回库里现有数据（不排队阻塞请求）
        return 0
    try:
        if not force and not _needs_refresh(db, portfolio):
            return 0  # 双检：等锁期间别人已经拉完了
        _mark_attempt(code)
        from app.services.adapters.advisor_source import (
            UnknownAdvisorPlatform,
            get_advisor_source,
        )

        try:
            source = get_advisor_source(portfolio.platform)
            rows = source.fetch_nav_history(code)
        except UnknownAdvisorPlatform as exc:
            logger.warning(f'投顾组合 {code} 无可用数据源，跳过错值序列：{exc}')
            return 0
        except McpError as exc:
            logger.warning(f'投顾组合 {code} 净值序列抓取失败（本次降级）：{exc}')
            return 0

        if not rows:
            # 有数据面的平台返回空 ⇒ 上游确实没有这条序列（计划型 / 钱包类组合实测如此）。
            # 这是事实，不是故障，故只记 info。
            logger.info(f'投顾组合 {code} 上游未提供净值序列，跳过')
            return 0

        written = save_nav_rows(db, portfolio.id, rows, source_of(portfolio))
        logger.info(f'投顾组合 {code} 净值序列落库 {written} 行（共 {len(rows)} 条）')
        return written
    finally:
        lock.release()


def ensure_series(db: Session, portfolio: AdvisorPortfolio, *, force: bool = False) -> None:
    """详情页读路径的唯一入口：需要时补拉，否则什么都不做。"""
    refresh_series(db, portfolio, force=force)


def load_series(db: Session, portfolio_id: int, start: dt.date) -> List[Tuple[dt.date, float]]:
    """读库内序列（``start`` 起，升序）。"""
    rows = (
        db.query(AdvisorPortfolioNav.nav_date, AdvisorPortfolioNav.nav)
        .filter(
            AdvisorPortfolioNav.portfolio_id == portfolio_id,
            AdvisorPortfolioNav.nav_date >= start,
        )
        .order_by(AdvisorPortfolioNav.nav_date)
        .all()
    )
    out: List[Tuple[dt.date, float]] = []
    for day, nav in rows:
        value = _to_float(nav)
        if day is None or value is None:
            continue
        out.append((day, round(value, 6)))
    return out


def series_source_code(db: Session, portfolio_id: int) -> str:
    """该组合序列的**来源码**（取最近一条非空 ``source``）。

    刻意返回内部码（``qieman``）而不是站点名：映射成「且慢」是**展示层**的事，
    与 ``price_history.source`` / ``index_daily.source`` 同口径——上游给码、
    ``product_trend`` 统一调 :func:`app.core.data_sources.data_source_label`。
    在数据层先映射一次、上层再映射一次的话，映射表以后改了容易出现「一处生效一处不生效」。
    """
    row = (
        db.query(AdvisorPortfolioNav.source)
        .filter(AdvisorPortfolioNav.portfolio_id == portfolio_id)
        .order_by(AdvisorPortfolioNav.nav_date.desc())
        .first()
    )
    return str(row[0]) if row and row[0] else ''


# ── 内部 ──


def _needs_refresh(db: Session, portfolio: AdvisorPortfolio) -> bool:
    """「库里太旧」且「进程内近期没试过」——两者同时成立才值得再打一次 MCP。"""
    last_day = latest_nav_date(db, portfolio.id)
    if last_day is not None and (dt.date.today() - last_day).days <= FRESH_DAYS:
        return False
    last_try = _last_attempt.get(portfolio.code)
    if last_try is not None and (_once_now() - last_try) < RETRY_INTERVAL_SECONDS:
        return False
    return True


def _once_now() -> float:
    """单调时钟（节流用；不随系统时间跳变而失真）。"""
    return time.monotonic()


def _mark_attempt(code: str) -> None:
    _last_attempt[code] = _once_now()


def _parse_date(raw: Any) -> Optional[dt.date]:
    """``YYYY-MM-DD`` / ``YYYY-MM-DD HH:MM:SS`` → date；解析不了返回 ``None``。

    不在适配器里做转换（与 ``fetch_holdings`` 的 ``as_of_date`` 同口径：日期解析统一
    收口在落库层）。只取前 10 位即可同时覆盖「纯日期」与「日期 + 时间」两种形态，
    比按格式串逐个 try 更不容易写错。
    """
    text = str(raw or '').strip().replace('/', '-')
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        return None


def _to_float(raw: Any) -> Optional[float]:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
