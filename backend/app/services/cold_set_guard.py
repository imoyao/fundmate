# -*- coding: utf-8 -*-
"""冷集膨胀守卫（#2123 · P2）。

## 为什么需要它

`data-strategy.md` §4.3 的范围强制（`require_full_sync_scope`）只防「误跑全量」（裸
`--full-sync` 无目标池时 CLI 直接拒绝），防不住「反复小批量灌」：每次给 50 只冷集基金
补一次历史，单看合法，累起来把清理掉的 800 万行灌回来。而膨胀不会报错、不会失败、
不会有人投诉（同文档 §0）。

## 监测什么

**冷集在保留窗口之外的行数**（`stale_rows`）——该清却没清掉的量。清理到位后它应等于
floor 保护行数（实测 28 行）；P0-2 的按需取会合法地把它提上来，故阈值放得足够宽。

## 为什么用 sync_logs 存时序

判定需要上一次的数据，项目已有每跑一次就落一行的审计表（`stats` 存 JSON）——复用它
不用新表、不用迁移；代价是不保证按时间严格排序，故取最近一条而不做时间匹配。

## 不进每日调度，但进周频本地巡检

`_JOB_TEMPLATES` 的准入判据是「数据日变化 + 用户直接看得见」，守卫两条都不满足；它走
并列的**本地巡检**通道（`local_checks`，周一 04:10 周频，#3078），判定流程在 `cold_set_check`。
"""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

# 守卫的 job 名（写进 sync_logs，与真实同步 job 区分）
GUARD_JOB_NAME = 'cold_set_bloat_guard'
# 默认保留窗口（与清理脚本同口径）
RETENTION_DAYS = 365
# 单次巡检允许的 stale 行增量。取 5000 的取舍：P0-2 的按需取是「30 分钟防抖 + 3 秒
# 全局节流」的慢速路径，正常浏览一天也就补只数到数十只；而「误跑全量 / 反复小批量灌」
# 是万行级，两者差 2~3 个数量级，阈值放在中间不会误报。
DEFAULT_MAX_GROWTH = 5000
# 监控的表（与清理脚本覆盖范围一致）
TABLES = ('daily_worth', 'money_fund_daily_worth')


@dataclass
class TableSnapshot:
    """单张表的快照：总量 / 冷集量 / 过期量。"""

    table: str
    total_rows: int
    cold_rows: int
    stale_rows: int
    cold_funds: int


@dataclass
class GuardReport:
    """一次巡检的结果（含上次对比与判定）。"""

    cutoff: str
    tables: List[TableSnapshot] = field(default_factory=list)
    total_stale: int = 0
    prev_stale: Optional[int] = None
    growth: Optional[int] = None
    max_growth: int = DEFAULT_MAX_GROWTH
    bloated: bool = False

    def to_stats(self) -> Dict[str, Any]:
        """落库的 stats 字典（写进 sync_logs.stats，下次巡检读回来做对比）。"""
        return {
            'cutoff': self.cutoff,
            'tables': [
                {
                    'table': t.table,
                    'total_rows': t.total_rows,
                    'cold_rows': t.cold_rows,
                    'stale_rows': t.stale_rows,
                    'cold_funds': t.cold_funds,
                }
                for t in self.tables
            ],
            'total_stale': self.total_stale,
            'prev_stale': self.prev_stale,
            'growth': self.growth,
            'max_growth': self.max_growth,
            'bloated': self.bloated,
        }


def _table_exists(db: Session, table: str) -> bool:
    row = db.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"), {'n': table}).fetchone()
    return row is not None


def _hot_codes(db: Session) -> set:
    """热集口径：持仓 ∪ 自选 ∪ 流水的 6 位数字代码。

    与清理脚本同口径（`watchlist` 而非 `watchlist_items`——后者是 #2145 事故里的错表名）；
    缺表直接报错：少算任一来源都会把「仅自选」的基金误判为冷集。用原生 SQL 而非 ORM：
    只需三张表的 `symbol` 列，为它把所有域模型拉进 mapper 会触发 `Ledger→Fund` 的关系
    解析顺序问题（实测 `InvalidRequestError`）。
    """
    parts = []
    for table in ('positions', 'watchlist', 'transactions'):
        if not _table_exists(db, table):
            raise SystemExit(
                '热集来源表缺失: %s\n热集口径 = 持仓 ∪ 自选 ∪ 流水，少算任一来源都会把'
                '「仅自选、未持有」的基金误判为冷集。若表名变更请同步修正。' % table
            )
        parts.append("SELECT DISTINCT symbol FROM %s WHERE LENGTH(symbol)=6 AND symbol NOT GLOB '*[^0-9]*'" % table)
    return {r[0] for r in db.execute(text(' UNION '.join(parts))).fetchall()}


def measure(db: Session, keep_days: int = RETENTION_DAYS) -> GuardReport:
    """测量当前冷集过期程度（不写库）：每表的总行数 / 冷集行数 / 过期行数。

    过期行（冷集且 date < cutoff）是「该清却没清掉」的量，等于 floor 保护行数时说明清理
    到位；`keep_days` 传「距上次 cutoff 的天数」即回到上次窗口，供同口径比较。
    """
    today = date.today()
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    hot = _hot_codes(db)
    report = GuardReport(cutoff=cutoff)
    codes = tuple(hot)

    for table in TABLES:
        if not _table_exists(db, table):
            continue
        total_rows = db.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
        # 热集行数用一条 SQL 统计，不拿 119 个 code 造 IN 列表。
        # `IN :codes` 必须配 bindparam(expanding=True)，否则 SQLAlchemy 会把它当成单个
        # 参数渲染成 `IN ?`——SQLite 直接语法错误（实测踩过）。
        hot_rows = (
            db.execute(
                text(f'SELECT COUNT(*) FROM {table} WHERE fund_code IN :codes').bindparams(
                    bindparam('codes', expanding=True)
                ),
                {'codes': codes},
            ).scalar()
            if codes
            else 0
        )
        stale_rows = db.execute(
            text(f'SELECT COUNT(*) FROM {table} WHERE date < :cutoff AND fund_code NOT IN :codes').bindparams(
                bindparam('codes', expanding=True)
            ),
            {'cutoff': cutoff, 'codes': codes},
        ).scalar()
        cold_funds = db.execute(
            text(f'SELECT COUNT(DISTINCT fund_code) FROM {table} WHERE fund_code NOT IN :codes').bindparams(
                bindparam('codes', expanding=True)
            ),
            {'codes': codes},
        ).scalar()
        report.tables.append(
            TableSnapshot(
                table=table,
                total_rows=total_rows,
                cold_rows=total_rows - (hot_rows or 0),
                stale_rows=stale_rows or 0,
                cold_funds=cold_funds or 0,
            )
        )
        report.total_stale += stale_rows or 0
    return report


def compare_with_last(
    report: GuardReport, last_stats: Optional[Dict[str, Any]], comparable_stale: Optional[int] = None
) -> GuardReport:
    """与上次巡检的 stats 对比，给出膨胀判定；首轮（无基线）只记录不判定。

    `comparable_stale` 是按上次 cutoff 重算的过期行数：cutoff 随当天前移，直接拿本次值
    比上次值会把时间流逝算成增长（实测 30 天 ≈ 7.9 万行漂移，阈值 5,000 下隔两天必假红）。
    """
    if not last_stats:
        report.prev_stale = None
        report.growth = None
        report.bloated = False
        return report

    prev = last_stats.get('total_stale')
    report.prev_stale = prev
    if prev is None:
        report.growth = None
        report.bloated = False
        return report

    current = report.total_stale if comparable_stale is None else comparable_stale
    report.growth = current - int(prev)
    report.bloated = report.growth > report.max_growth
    return report


def last_guard_stats(db: Session) -> Optional[Dict[str, Any]]:
    """读最近一次守卫巡检落库的 stats（解析失败按没有处理）。

    同样用原生 SQL（`SyncLog` 走 ORM 会触发与 `_hot_codes` 相同的 mapper 解析顺序问题）。
    """
    row = db.execute(
        text('SELECT stats FROM sync_logs WHERE job_name = :n ORDER BY started_at DESC LIMIT 1'),
        {'n': GUARD_JOB_NAME},
    ).fetchone()
    if row is None or not row[0]:
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        logger.warning('冷集膨胀守卫：上一条 stats 解析失败，按首次巡检处理')
        return None


def record(db: Session, report: GuardReport, commit: bool = True) -> None:
    """把本次巡检结果落进 sync_logs（作为下次的基线）。
    status 取 `bloated` / `ok`：前者让它在审计表里一眼可辨，不依赖任何额外通知渠道。
    """
    from app.core.time_utils import now_shanghai

    now = now_shanghai()
    db.execute(
        text(
            'INSERT INTO sync_logs '
            '(job_name, status, full_sync, stats, data_source, started_at, finished_at) '
            'VALUES (:job, :status, :full_sync, :stats, :src, :started, :finished)'
        ),
        {
            'job': GUARD_JOB_NAME,
            'status': 'bloated' if report.bloated else 'ok',
            'full_sync': False,
            'stats': json.dumps(report.to_stats(), ensure_ascii=False),
            'src': 'local',
            'started': now,
            'finished': now,
        },
    )
    if commit:
        db.commit()
