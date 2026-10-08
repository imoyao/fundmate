# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/7
# File : pnl_snapshot_store.py
"""收益日历物化快照的**存 / 取 / 删**（#1926）。

本模块只搬数据，一个数字都不算
------------------------------
算口径的唯一出口仍是 ``pnl_calendar.build_daily_pnl_series``。物化读与现算读
**逐位相等**由 ``tests/services/test_pnl_snapshot_store.py`` 的等价性用例钉住：
一旦分叉，就退化回 #1812 那种「静默错数字」——那正是 `asset_snapshots` 被否的原因。

为什么要物化（#1925 的边界）
----------------------------
#1925 只做**读路径**优化（按 fund_code 过滤 + 聚合下推 + 日/月/年三视图），
`build_pnl_series` 仍是每次请求 as-of 现算：整月亚秒，但 1 年 ≈1.3s、5 年 ≈3.6s
（151 持仓实测），成本随天数线性增长。物化后读路径退化成一条索引扫描。

三道失效（与 `asset_snapshots` 的根本区别）
------------------------------------------
`asset_snapshots` 的 `snapshot_date` 只是**标签**：取数链无日期过滤、全仓无
失效/重算钩子，回填等于把今天的值贴到历史日期（#1812 docstring 详述）。本表：

1. **口径版本** ``CALIBER_VERSION`` —— 读时发现区间内有旧版本行即整表清一次，
   之后再无旧版本行（自愈，无需迁移脚本）。
2. **用户编辑** —— ``_before_flush`` 事件（见下）。
3. **价格数据** —— ``purge_all`` 由 sync 编排器在 ``full_sync`` 回填后调用。
   日常增量同步**不需要钩子**：见 `pnl_calendar.PRICE_FRESH_DAYS`。

为什么用 ``before_flush`` 事件而不是逐个写入口打补丁
----------------------------------------------------
本仓写流水/持仓的入口有十余处（`trading.TransactionService.create` /
`ledger_write_service.update_ledger_transaction` / 各导入提交 / 级联删除…），
漏掉任何一处就是静默错数字——`asset_snapshots` 正是这么烂掉的。事件挂在
``Session`` 上，**写入路径无论怎么绕都会经过**，与 `positions/models.py:173`
先例同源（那段 docstring 讲的就是同一个理由）。

只有 ``Query.update() / .delete()`` 这类 bulk 语句**不进 session 状态**
（mapper 事件同样抓不到），必须显式补调。当前落点：

- ``ledger_migration_service.migrate_orphan_data``（bulk update Position.ledger_id）
- ``ledger_migration_service.delete_orphan_data``（bulk delete Transaction/Position）

而 ``delete_position`` / ``delete_ledger_position`` 之后都跟了 ``db.delete(position)``
（ORM 删除 → 事件抓得到），``delete_ledger`` 则靠「Ledger 被删 ⇒ 整族失效」覆盖。
"""

from datetime import date as _date
from typing import Dict, Iterable, List, Optional, Tuple

from loguru import logger
from sqlalchemy import delete as _sa_delete
from sqlalchemy import event
from sqlalchemy import inspect as _sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.summary.models import PnlDailySnapshot
from app.domains.transactions.models import Transaction

# ── 口径版本号 ────────────────────────────────────────────────────────────────
# `pnl_calendar.py` 的**任何**输出改动（状态判定、差分口径、四态、精度）都必须
# 把它 +1：旧版本行一旦与新口径混在同一条序列里，就再也说不清哪个数字是对的。
# 读路径按版本过滤，不符即整表清，新值随下次读取回填——不需要迁移脚本。
CALIBER_VERSION = 1

# 日历关心的模型全集。`Asset` 不在其内：`pnl_calendar` 的 `net_worth` 只累加
# 持仓市值（见其值循环），静态资产增减**不影响**日历的任何一个数字。
_WATCHED = (Position, Transaction, Ledger)

# 影响日历口径的持仓字段。`current_price` / `market_value` / `name` 刻意不在内——
# `position_price` 每天 22:15 都在回写现价，纳入即等于「每天全族作废」，
# 物化就白做了（日历读的是历史价格序列，不是 `positions.current_price`）。
_POSITION_CALIBER_ATTRS = frozenset(
    {
        'symbol',  # 场所判定 + 价格序列键
        'asset_type',  # 同上
        'ownership_status',  # `_positions` 只取 active
        'ledger_id',  # 账户级作用域的归属
        'avg_price',  # 成本基数
        'currency',  # 汇率换算
        'family_id',  # 隔离键
    }
)


# ────────────────────────────── 存 / 取 ──────────────────────────────


def _scope(query, family_id: int, ledger_id: Optional[int]):
    """按作用域收窄：`ledger_id is None` = 家庭级（行上该列为 NULL）。"""
    query = query.filter(PnlDailySnapshot.family_id == family_id)
    if ledger_id is None:
        return query.filter(PnlDailySnapshot.ledger_id.is_(None))
    return query.filter(PnlDailySnapshot.ledger_id == ledger_id)


def load_days(
    db: Session,
    family_id: int,
    ledger_id: Optional[int],
    start: _date,
    end: _date,
) -> Dict[_date, PnlDailySnapshot]:
    """取 `[start, end]` 的物化行；只回**当前口径版本**的行。

    发现区间内有旧版本行 ⇒ 先 `purge_all` 再回 `{}`（口径换版自愈）。
    这一步刻意**不做**「按版本过滤就完事」：不清理的话，从未被重新读到的日期
    会永远留着旧版本行占盘，且下次换版又要重新判一次。
    """
    rows = _scope(db.query(PnlDailySnapshot), family_id, ledger_id).filter(
        PnlDailySnapshot.date >= start,
        PnlDailySnapshot.date <= end,
    ).all()
    stale = [r for r in rows if r.caliber_version != CALIBER_VERSION]
    if stale:
        purged = purge_all(db)
        logger.info(
            '收益日历快照口径换版（现存 {} 行为旧版 {}），已作废全表 {} 行，将在下次读取时按新口径回填',
            len(stale),
            sorted({r.caliber_version for r in stale}),
            purged,
        )
        return {}
    return {r.date: r for r in rows}


def save_days(
    db: Session,
    family_id: int,
    ledger_id: Optional[int],
    entries: Iterable[dict],
    max_date: Optional[_date] = None,
) -> int:
    """按 `(family_id, ledger_id, date)` upsert 逐日行，返回落库条数。

    `entries` 每项须含 `date / daily_pnl_cents / net_worth_cents / rate_bp /
    state`（缺 `daily_pnl_cents` 时按 NULL 落，语义是「算不出来」）。

    `max_date`：**永不落库晚于该日**的行——物化新鲜窗（`pnl_calendar.PRICE_FRESH_DAYS`）。
    传了它，日常价格同步就完全不需要失效钩子：新鲜窗内的日期读时恒现算，
    永远不会有一行「带着过期价格的快照」被读出去。
    """
    # `entries` 的 `date` 是 ISO 字符串（`_compute_days` 的输出形态）；统一成 `date`
    # 再比较——字符串与 `date` 直接比会 TypeError，而一旦有人顺手改成字符串比较，
    # 字典序与日期序的差异会让**极少数日期**静默落错位，比报错更难查。
    normalized: List[Tuple[_date, dict]] = []
    for e in entries:
        d = e['date']
        normalized.append((_date.fromisoformat(d) if isinstance(d, str) else d, e))

    rows = [(d, e) for d, e in normalized if max_date is None or d <= max_date]
    if not rows:
        return 0
    dates = [d for d, _ in rows]
    existing = {r.date: r for r in _scope(db.query(PnlDailySnapshot), family_id, ledger_id).filter(
        PnlDailySnapshot.date.in_(dates)
    ).all()}

    touched = 0
    for d, e in rows:
        row = existing.get(d)
        if row is None:
            row = PnlDailySnapshot(
                family_id=family_id,
                ledger_id=ledger_id,
                date=d,
                caliber_version=CALIBER_VERSION,
            )
            db.add(row)
        row.daily_pnl_cents = e.get('daily_pnl_cents')
        row.net_worth_cents = e['net_worth_cents']
        row.rate_bp = e.get('rate_bp')
        row.state = e['state']
        touched += 1

    # 只 flush 不 commit（`BaseRepository` 同款约定）：事务边界归调用方。
    # flush 还让同一会话内后续的 `load_days` 看得见本次写入——`SessionLocal`
    # 是 `autoflush=False`，不显式 flush 会读到自己的旧结果。
    db.flush()
    return touched


# ────────────────────────────── 删 ──────────────────────────────


def purge_family(db: Session, family_id: int) -> int:
    """作废某家庭的**全部**快照（持仓结构变化 / 账户级联删除用）。"""
    result = db.execute(_sa_delete(PnlDailySnapshot).where(PnlDailySnapshot.family_id == family_id))
    return result.rowcount or 0


def purge_from(db: Session, family_id: int, from_date: _date) -> int:
    """作废某家庭 `[from_date, ∞)` 的快照——流水编辑的精确失效。

    为什么精确到日期而不是整族：编辑今天的交易后读「近 30 天」，精确失效只
    重算 1 天，整族失效要重算 30 天；编辑越靠近区间末端，收益越大。
    """
    result = db.execute(
        _sa_delete(PnlDailySnapshot).where(
            PnlDailySnapshot.family_id == family_id,
            PnlDailySnapshot.date >= from_date,
        )
    )
    return result.rowcount or 0


def purge_all(db: Session) -> int:
    """作废**全表**快照（口径换版 / 价格历史回填用）。

    价格数据不属于任何家庭，`full_sync` 回填改的是历史区间里的行，
    每个家庭的每个作用域都会受影响 ⇒ 没有比全表更精确且更简单的单位。
    """
    result = db.execute(_sa_delete(PnlDailySnapshot))
    return result.rowcount or 0


# ────────────────────────── 失效钩子（before_flush） ──────────────────────────


def _old_attr(obj, name: str):
    """某属性**改动前**的值。dirty 集合里的对象属性已被覆写，只能问 history。

    用 `orm.attributes.get_history` 而非 `Session.get_history`——后者在
    SQLAlchemy 2.0 已不存在，2.0 的取历史入口只在 attributes 模块。
    """
    history = get_history(obj, name)
    if history.deleted:
        return history.deleted[0]
    if history.unchanged:
        return history.unchanged[0]
    return getattr(obj, name)


def _old_effective_date(txn: Transaction) -> Optional[_date]:
    """编辑前的流水生效日（`confirm_date` 优先，缺失回退 `trade_date`）。

    与 `pnl_calendar._effective_date` 同一套规则——口径不许有第二份。
    """
    confirm = _old_attr(txn, 'confirm_date')
    if confirm:
        return confirm
    trade = _old_attr(txn, 'trade_date')
    if trade:
        return trade.date() if hasattr(trade, 'date') else trade
    return None


def _txn_invalid_from(txn: Transaction, kind: str) -> Optional[_date]:
    """该流水变更影响的**起始日期**；回 `None` 表示定不了位（调用方须整族失效）。

    - 新增 / 删除：影响自其生效日起；
    - 编辑：新旧生效日都可能被影响过（改日期 = 老日期要撤、新日期要补）
      ⇒ 取两者较小者，保证 `[D, ∞)` 覆盖并集。
    """
    # 惰性导入：`pnl_calendar` 模块级 import 了本模块，此处再顶层导入即成环。
    from app.services.pnl_calendar import _effective_date

    dates: List[Optional[_date]] = [_effective_date(txn)]
    if kind == 'dirty':
        dates.append(_old_effective_date(txn))
    known = [d for d in dates if d is not None]
    if not known:
        # 生效日缺失 ⇒ `_as_of_shares` 本就取不到它，但不敢替它下结论，
        # 宁可整族作废（代价是一次现算，不是错数字）。
        return None
    return min(known)


def _position_caliber_changed(pos: Position) -> bool:
    """该持仓是否改到了**影响日历口径**的字段。"""
    return any(get_history(pos, attr).has_changes() for attr in _POSITION_CALIBER_ATTRS)


def _touched(session: Session):
    """本次 flush 中真正被改动、且日历关心的对象。"""
    for obj in session.new:
        if isinstance(obj, _WATCHED):
            yield 'new', obj
    for obj in session.deleted:
        if isinstance(obj, _WATCHED):
            yield 'deleted', obj
    # `session.dirty` 会把「加载过但没改」的对象也放进来（SQLAlchemy 明文行为），
    # 必须 `is_modified` 过滤，否则每次 flush 只要碰过持仓就整族作废。
    for obj in session.dirty:
        if isinstance(obj, (Position, Transaction)) and session.is_modified(obj, include_collections=False):
            yield 'dirty', obj


def _snapshot_table_missing(session: Session) -> bool:
    """该会话绑定的库里**没有**物化快照表 ⇒ 本就没有快照可作废，作废是 no-op。

    事件装在 `Session` 基类上，进程里**每一个** session 都会路过它——包括脚本
    自建的 `sessionmaker(bind=engine)` 与夹具里「只 `__table__.create` 两张表」
    的临时库（见 `tests/scripts/test_fix_orphan_money_fund_reattach.py`）。
    那些库与物化无关，硬删会以 `no such table` 把**别人**的 flush 打断，
    而失败的执行会让整笔事务作废——比不删糟糕得多。

    查「表在不在」只有查一次才知道，故**先查后删**：拿会话自己那条连接查，
    不另开连接，免得与正在进行的写事务争锁。
    """
    return not _sa_inspect(session.connection()).has_table(PnlDailySnapshot.__tablename__)


def _before_flush(session: Session, flush_context, instances) -> None:
    """把「本次 flush 改了什么」翻译成「哪些快照行该作废」。

    **在 flush 内执行删除**：与本次改动同处一个事务，任一失败一起回滚，
    不会出现「改动回滚了、快照却被清了」或反之的中间态。
    """
    if not (session.new or session.dirty or session.deleted):
        return

    purge_all_families = set()
    from_dates: Dict[int, _date] = {}

    for kind, obj in _touched(session):
        if isinstance(obj, Position):
            if kind == 'dirty' and not _position_caliber_changed(obj):
                continue
            # #1916：状态判定恒用**家庭级全量决策集**——任何一笔持仓的增减都会
            # 改变各作用域的丢天集合，账户级快照同样会变，故整族失效。
            purge_all_families.add(obj.family_id)
        elif isinstance(obj, Transaction):
            d = _txn_invalid_from(obj, kind)
            if d is None:
                purge_all_families.add(obj.family_id)
            else:
                cur = from_dates.get(obj.family_id)
                if cur is None or d < cur:
                    from_dates[obj.family_id] = d
        elif kind == 'deleted' and isinstance(obj, Ledger):
            # 删账户走 `Query.delete()` 级联（进不了 session 状态），靠这条兜底。
            purge_all_families.add(obj.family_id)

    if not purge_all_families and not from_dates:
        return
    if _snapshot_table_missing(session):
        return  # 绑定的库里没有物化表 ⇒ 没有快照可作废（见该函数 docstring）

    for fid in purge_all_families:
        from_dates.pop(fid, None)  # 整族优先，免得同一族删两遍

    for fid in sorted(purge_all_families):
        n = purge_family(session, fid)
        if n:
            logger.info('收益日历快照失效：家庭 {} 持仓/账户结构变更，作废 {} 行', fid, n)
    for fid in sorted(from_dates):
        n = purge_from(session, fid, from_dates[fid])
        if n:
            logger.info(
                '收益日历快照失效：家庭 {} 自 {} 起作废 {} 行（流水变更）',
                fid,
                from_dates[fid],
                n,
            )


_installed = False


def install_invalidation() -> None:
    """注册 `before_flush` 失效事件。幂等，挂 `app/__init__.py` 全入口生效。"""
    global _installed
    if _installed:
        return
    event.listen(Session, 'before_flush', _before_flush)
    _installed = True
