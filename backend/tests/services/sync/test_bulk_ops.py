# -*- coding: utf-8 -*-
"""批量写库与阶段计时的判据（#2522）。

## 为什么这些用例必须存在

Turso/Hrana 上的「逐行 HTTP 往返」在**本地 SQLite 上不可复现**（毫秒级），
所以任何「跑一遍很快 ⇒ 没问题」的本地验证都是假绿。能本地钉住的只有**语句形状**：

- 一条 INSERT 里必须有多组 VALUES（否则退回逐行往返）；
- 单条语句的绑定参数不得超过 `MAX_PARAMS_PER_STATEMENT`（SQLite 变量上限）；
- `in_` 去重查询必须分批（28k 个参数的单条 SQL 就是 52 分钟静默的嫌疑）。

这三条都是「编译出来的 SQL 长什么样」，用 `before_cursor_execute` 抓下来断言即可，
不依赖远端、也不依赖时间。
"""

import math

import pytest
from loguru import logger
from sqlalchemy import event

from app.domains.funds.models import Fund
from app.domains.securities.models import Security
from app.services.job_base import IN_CHUNK_SIZE, JobStatus, SyncJob
from app.services.sync.bulk_ops import (
    MAX_CHUNK_ROWS,
    MAX_PARAMS_PER_STATEMENT,
    bulk_insert_rows,
    chunk_row_count,
    chunked,
)
from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob


def _capture(db):
    """收集本 session 引擎上执行过的 (SQL, 参数个数)。

    `before_cursor_execute` 是 SQLAlchemy 的公开事件钩子；参数在 SQLite 驱动上是
    位置参数元组，`len(parameters)` 即该语句的绑定参数个数。
    """
    statements = []
    engine = db.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if isinstance(parameters, (list, tuple)):
            count = len(parameters)
        elif isinstance(parameters, dict):
            count = len(parameters)
        else:
            count = 0
        statements.append({'sql': ' '.join(statement.split()), 'params': count})

    event.listen(engine, 'before_cursor_execute', before)
    return statements, lambda: event.remove(engine, 'before_cursor_execute', before)


def _inserts(statements):
    return [s for s in statements if s['sql'].upper().startswith('INSERT')]


# ── 助手本身 ──


def test_multi_row_values_is_one_statement(db):
    rows = [{'symbol': f'6000{i:02d}.SH', 'name': f'n{i}', 'market': 'CN_A', 'type': 'stock'} for i in range(3)]
    statements, stop = _capture(db)
    try:
        count = bulk_insert_rows(db, Security, rows)
    finally:
        stop()

    inserts = _inserts(statements)
    assert count == 3
    assert len(inserts) == 1, f'3 行必须压成 1 条语句，实际 {len(inserts)} 条'
    # 3 组 VALUES ⇒ SQL 里出现 2 个 "), (" 分隔
    assert inserts[0]['sql'].count('), (') == 2


def test_chunk_width_respects_param_limit(db):
    table_columns = len(Security.__table__.columns)
    per_stmt = chunk_row_count(table_columns)
    assert per_stmt == max(1, min(MAX_CHUNK_ROWS, MAX_PARAMS_PER_STATEMENT // table_columns))

    total = per_stmt * 3 + 5  # 跨 4 条语句
    rows = [{'symbol': f'7000{i:04d}.SH', 'name': f'n{i}', 'market': 'CN_A', 'type': 'stock'} for i in range(total)]
    statements, stop = _capture(db)
    try:
        bulk_insert_rows(db, Security, rows)
    finally:
        stop()

    inserts = _inserts(statements)
    assert len(inserts) == math.ceil(total / per_stmt)
    assert all(s['params'] <= MAX_PARAMS_PER_STATEMENT for s in inserts), [s['params'] for s in inserts]


def test_heterogeneous_rows_rejected_not_silently_truncated(db):
    """键集不一致必须当场报错。

    旧路径 `bulk_insert_mappings` 的实现行为（SQLAlchemy 2.0.52 实测）是**按最后一行的
    键集截断**：第 1 行独有的 `market` 被静默丢掉，随后以一条毫不相关的
    `NOT NULL constraint failed: securities.market` 收场。
    """
    rows = [
        {'symbol': 'A1', 'name': 'n1', 'market': 'CN_A', 'type': 'stock'},
        {'symbol': 'A2', 'name': 'n2', 'type': 'etf'},
    ]
    with pytest.raises(ValueError, match='键集一致'):
        bulk_insert_rows(db, Security, rows)


def test_empty_rows_emit_nothing(db):
    statements, stop = _capture(db)
    try:
        assert bulk_insert_rows(db, Security, []) == 0
    finally:
        stop()
    assert statements == []


def test_chunked_covers_all_items():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(chunked([], 10)) == []


# ── job 级：stock_list / fund_list 真的走到了批量路径 ──


def test_stock_list_save_uses_multi_row_insert(db):
    job = StockListSyncJob(adapter=None, db=db)
    total = 260
    data = [{'symbol': f'6000{i:03d}.SH', 'name': f'n{i}', 'market': 'CN_A', 'type': 'stock'} for i in range(total)]

    statements, stop = _capture(db)
    try:
        job._save_data(data)
    finally:
        stop()

    inserts = _inserts(statements)
    per_stmt = chunk_row_count(len(Security.__table__.columns))
    assert len(inserts) == math.ceil(total / per_stmt), f'{total} 行应压成 {math.ceil(total / per_stmt)} 条语句'
    assert all(s['sql'].count('), (') >= 1 for s in inserts), '每条 INSERT 都必须是多组 VALUES'
    assert db.query(Security).count() == total


def test_stock_list_save_only_writes_changed_rows(db):
    """存量行 name/market/type 都没变 ⇒ 只查不写（避免每日全量 UPDATE 往返）。"""
    job = StockListSyncJob(adapter=None, db=db)
    data = [{'symbol': '600100.SH', 'name': 'n', 'market': 'CN_A', 'type': 'stock'}]
    job._save_data(data)
    statements, stop = _capture(db)
    try:
        job._save_data(data)
    finally:
        stop()

    writes = [s for s in statements if s['sql'].upper().startswith(('INSERT', 'UPDATE'))]
    assert writes == []


def test_fund_list_save_chunks_existing_code_query(db):
    """28149 只基金 ⇒ `in_` 必须分批，且每批 ≤ IN_CHUNK_SIZE 个参数。"""
    bulk_insert_rows(
        db,
        Fund,
        [{'fund_code': f'{i:06d}', 'name': f'f{i}'} for i in range(IN_CHUNK_SIZE + 400)],
    )
    db.commit()

    total = IN_CHUNK_SIZE + 800
    new_data = [{'fund_code': f'{i:06d}', 'name': f'f{i}', 'company_name': ''} for i in range(total)]

    job = FundListSyncJob(adapter=None, db=db)
    statements, stop = _capture(db)
    try:
        job._save_data(new_data)
    finally:
        stop()

    selects = [s for s in statements if s['sql'].upper().startswith('SELECT') and 'fund_code IN' in s['sql']]
    assert len(selects) >= 2, f'`in_` 未分批：只发了 {len(selects)} 条查询'
    assert max(s['params'] for s in selects) <= IN_CHUNK_SIZE, [s['params'] for s in selects]

    inserts = _inserts(statements)
    assert inserts, '新增基金必须走批量插入'
    assert all(s['sql'].count('), (') >= 1 for s in inserts)


# ── 阶段计时：真机日志里必须能分开「抓取 / 去重 / 写库」 ──


class _TimedJob(SyncJob):
    """最小实现：只用于验证 `run()` 的阶段计时接线。"""

    def get_name(self) -> str:
        return 'timed_probe'

    def _fetch_data(self, full_sync, targets):
        return [{'symbol': 'probe', 'name': 'probe', 'market': 'CN_A', 'type': 'stock'}]

    def _validate_data(self, raw_data):
        return raw_data

    def _deduplicate(self, data):
        return data

    def _save_data(self, new_data):
        bulk_insert_rows(self.db, Security, new_data, log_scope='probe')
        self.db.commit()


def test_run_logs_phase_costs(db):
    messages = []
    handler_id = logger.add(lambda message: messages.append(message.record['message']), level='INFO')
    try:
        result = _TimedJob(adapter=None, db=db).run()
    finally:
        logger.remove(handler_id)

    assert result['status'] == JobStatus.SUCCESS.value
    phase_lines = [m for m in messages if m.startswith('阶段耗时：')]
    assert phase_lines, 'run() 必须输出「阶段耗时：…」一行'
    for phase in ('抓取', '校验', '去重', '写库'):
        assert phase in phase_lines[0], phase_lines[0]
