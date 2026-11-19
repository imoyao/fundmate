# -*- coding: utf-8 -*-
"""#3182 回归：巡检审计行的绑定参数必须能被 libsql 驱动接受。

## 为什么「本地写进去了」不算数

本地 SQLite 带一条**已废弃**的 datetime 适配器：把 `datetime` 直接交给 `cursor.execute`，
它会悄悄转成字符串，于是坏代码在本地永远绿。生产走 Turso（libsql），驱动只认
int / float / str / bytes / None，同一个参数直接抛
`ValueError: Unsupported parameter type`——2026-11-18 的巡检卡实测，冷集膨胀巡检与份额
反证巡检**同时**失效，而会话里的行一条都没写进去。

⇒ 判据落在**交给驱动的参数类型**上（`before_cursor_execute` 抓），不落在「有没有行」上。

## 为什么断言打在两个调用点，而不只是 helper

出问题的是「调用点自己拼 INSERT」这件事本身。现在两条巡检都走 `insert_audit_row`，
这两条用例钉住的是**接线**：谁再把裸 SQL 抄回来（多传一个 datetime 参数），这里立刻转红。
"""

import json
from datetime import datetime

from sqlalchemy import event

from app.models.sync_log import SyncLog, insert_audit_row
from app.services import cold_set_guard, position_share_audit
from app.services.cold_set_guard import GuardReport

#: libsql 驱动能绑定的标量类型；`bool` 刻意不在内（它是 int 子类，但不该靠子类过关）。
_ALLOWED_TYPES = (str, int, float, bytes, type(None))


def _capture(db, action):
    """执行 `action`，收集写入 `sync_logs` 的绑定参数（值，不是个数）。"""
    captured = []
    engine = db.get_bind()

    def before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if 'INSERT INTO sync_logs' in statement:
            captured.append(parameters)

    event.listen(engine, 'before_cursor_execute', before)
    try:
        action()
    finally:
        event.remove(engine, 'before_cursor_execute', before)
    return captured


def _values(parameters):
    return list(parameters.values()) if isinstance(parameters, dict) else list(parameters)


def _assert_driver_safe(captured):
    assert captured, '没有抓到审计写入——调用点可能绕过了 insert_audit_row'
    for parameters in captured:
        for value in _values(parameters):
            assert type(value) in _ALLOWED_TYPES, f'libsql 不接受的参数类型：{type(value).__name__} = {value!r}'
            assert not isinstance(value, datetime), 'datetime 会原样到达驱动，Turso 上必崩'


def test_helper_binds_scalars_and_time_reads_back_as_datetime(db):
    captured = _capture(db, lambda: insert_audit_row(db, job_name='probe', status='ok', stats={'hits': 1}))
    _assert_driver_safe(captured)
    db.commit()

    row = db.query(SyncLog).filter(SyncLog.job_name == 'probe').one()
    assert row.status == 'ok'
    # 写成字符串后仍能读成 datetime：格式必须与 DateTime 列的存储形态一致，
    # 否则 `local_checks.due_checks` 的 `row.started_at.date()` 会直接炸。
    assert isinstance(row.started_at, datetime)
    assert row.started_at == row.finished_at, '同一行必须用同一个时刻'
    assert json.loads(row.stats)['hits'] == 1


def test_cold_set_guard_record_binds_scalars(db):
    report = GuardReport(cutoff='2025-11-12', total_stale=7)
    captured = _capture(db, lambda: cold_set_guard.record(db, report))
    _assert_driver_safe(captured)

    row = db.query(SyncLog).filter(SyncLog.job_name == cold_set_guard.GUARD_JOB_NAME).one()
    assert row.status == 'ok'
    assert json.loads(row.stats)['total_stale'] == 7


def test_share_integrity_audit_binds_scalars(db):
    captured = _capture(db, lambda: position_share_audit.run_and_record(db))
    _assert_driver_safe(captured)

    row = db.query(SyncLog).filter(SyncLog.job_name == position_share_audit.JOB_NAME).one()
    assert row.status == position_share_audit.STATUS_OK
    assert json.loads(row.stats)['hits'] == 0
