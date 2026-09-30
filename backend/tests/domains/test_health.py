# -*- coding: utf-8 -*-
"""`/api/health` 的调度组件健康判定回归测试（#1793）。

背景：`sync_logs.started_at` 落库时写的是 aware（`job.snapshot_time = now_shanghai()`），
而 SQLite 的 DateTime 列不保留时区偏移，**读回来是 naive**。health 端点原先直接拿
`now_shanghai() - last_success`，一旦调度开启且存在成功记录就抛
`TypeError: can't subtract offset-naive and offset-aware datetimes` → 免登录端点 500，
前端「系统状态」页与监控探活同时失效。

本文件的用例专门锁定「naive 落库值 + now_shanghai() 比较」这条路径。
"""

from datetime import datetime, timedelta, timezone

from app.core.time_utils import SHANGHAI_TZ, as_shanghai, now_shanghai
from app.models.sync_log import SyncLog


def _naive_now() -> datetime:
    """模拟 SQLite 读回的 `started_at`：东八区墙钟时间、无 tzinfo。"""
    return now_shanghai().replace(tzinfo=None)


def _insert_success_log(db, started_at: datetime) -> None:
    db.add(
        SyncLog(
            job_name='temperature',
            status='success',
            full_sync=False,
            started_at=started_at,
            finished_at=started_at,
            duration_seconds=1.0,
        )
    )
    db.commit()


def _scheduler_component(client, monkeypatch) -> dict:
    monkeypatch.setenv('SCHEDULER_ENABLED', '1')
    resp = client.get('/api/health')
    assert resp.status_code == 200, f'health 不应 500：{resp.get_data(as_text=True)}'
    return resp.get_json()['components']['scheduler']


def test_as_shanghai_treats_naive_as_shanghai_wall_clock():
    """naive 值按东八区墙钟补齐（**不做 UTC 假设**），aware 值统一转到东八区。"""
    naive = datetime(2026, 9, 30, 17, 34, 25)
    assert as_shanghai(naive) == naive.replace(tzinfo=SHANGHAI_TZ)

    shanghai_aware = datetime(2026, 9, 30, 17, 34, 25, tzinfo=SHANGHAI_TZ)
    assert as_shanghai(shanghai_aware) == shanghai_aware

    # 其他时区的 aware 值按同一时刻换算，而不是照搬墙钟数字
    utc_same_instant = shanghai_aware.astimezone(timezone.utc)
    assert as_shanghai(utc_same_instant) == shanghai_aware

    assert as_shanghai(None) is None


def test_health_tolerates_naive_started_at(client, db, monkeypatch):
    """naive `started_at` 不得让端点 500，且应判为健康（#1793 主回归）。"""
    _insert_success_log(db, _naive_now())

    sched = _scheduler_component(client, monkeypatch)

    assert sched['status'] == 'healthy'
    # 归一后输出带时区偏移的 ISO 串，口径显式（naive 串易被误读成 UTC）
    assert sched['last_success_run'].endswith('+08:00')


def test_health_marks_scheduler_unhealthy_when_naive_record_is_stale(client, db, monkeypatch):
    """超过阈值天数（naive 落库值）应判为 unhealthy，整体降级为 degraded。"""
    _insert_success_log(db, _naive_now() - timedelta(days=5))

    monkeypatch.setenv('SCHEDULER_ENABLED', '1')
    resp = client.get('/api/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['components']['scheduler']['status'] == 'unhealthy'
    assert data['status'] == 'degraded'


def test_health_scheduler_unhealthy_without_any_success(client, monkeypatch):
    """调度开启但无任何成功记录 → unhealthy（防御性，覆盖 last_success 为 None 分支）。"""
    sched = _scheduler_component(client, monkeypatch)

    assert sched['status'] == 'unhealthy'
    assert sched['last_success_run'] is None
