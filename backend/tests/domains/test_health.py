# -*- coding: utf-8 -*-
"""`/api/health` 的调度组件健康判定回归测试（#1793）。

背景：`sync_logs.started_at` 落库时写的是 aware（`job.snapshot_time = now_shanghai()`），
而 SQLite 的 DateTime 列不保留时区偏移，**读回来是 naive**。health 端点原先直接拿
`now_shanghai() - last_success`，一旦调度开启且存在成功记录就抛
`TypeError: can't subtract offset-naive and offset-aware datetimes` → 免登录端点 500，
前端「系统状态」页与监控探活同时失效。

本文件的用例专门锁定「naive 落库值 + now_shanghai() 比较」这条路径，
以及「关闭态必须显式可见、且不被历史成功记录掩盖」（#1720）。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.core.time_utils import SHANGHAI_TZ, as_shanghai, now_shanghai
from app.models.sync_log import SyncLog


def _naive_now() -> datetime:
    """模拟 SQLite 读回的 `started_at`：东八区墙钟时间、无 tzinfo。"""
    return now_shanghai().replace(tzinfo=None)


def _insert_success_log(db, started_at: datetime, job_name: str = 'asset_snapshot') -> None:
    """写一条成功审计行。

    默认写心跳 job（`asset_snapshot`）——#3085 起「调度在跑」只认它；写别的 job
    模拟的是「手动单跑了某一个 job」，那**不该**让停摆显示成正常。
    """
    db.add(
        SyncLog(
            job_name=job_name,
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


# ---------------------------------------------------------------------------
# 调度「未开启」这一状态的可见性（#1720）
#
# 本机每日调度默认关闭（SCHEDULER_ENABLED 未置），此时温度/净值不会自动更新。
# #1720 的定性是「不是抓取失败，而是关闭态对用户不可见」—— 唯一能证明这件事发生了
# 的地方就是 /api/health：它必须显式说 status=disabled，而不是在没有成功记录时
# 报 unhealthy（那是「开了但没跑」的意思，两者混同就会把排查引向错误方向）。
# ---------------------------------------------------------------------------


def _health_scheduler(client, monkeypatch) -> dict:
    resp = client.get('/api/health')
    assert resp.status_code == 200, f'health 不应 500：{resp.get_data(as_text=True)}'
    return resp.get_json()['components']['scheduler']


@pytest.mark.parametrize(
    'env_value',
    [None, '', '0', 'false', 'no', 'off'],
    ids=['unset', 'empty', '0', 'false', 'no', 'off'],
)
def test_health_marks_scheduler_disabled_when_switch_off(client, monkeypatch, env_value):
    """开关未打开 → status=disabled，且 enabled=False。"""
    if env_value is None:
        monkeypatch.delenv('SCHEDULER_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SCHEDULER_ENABLED', env_value)

    sched = _health_scheduler(client, monkeypatch)

    assert sched['enabled'] is False
    assert sched['status'] == 'disabled'
    # message 必须点出「怎么开」，否则维护者看到 disabled 仍不知道要改哪个开关
    assert 'SCHEDULER_ENABLED' in sched['message']


def test_health_keeps_disabled_even_with_recent_success_log(client, db, monkeypatch):
    """**关键回归**：有过成功运行记录也不许把 disabled 判成 healthy。

    判反了会出现最坏组合：用户以为自己在跑调度（页面显示一切正常），
    而实际上抓取早已停止——这正是 #1720 记录的「静默陈旧」形态。

    #3085 起这条更精确：写入的是 `temperature`（非心跳 job）的成功行，
    即「手动单跑过某个 job」——那不能证明每日调度在跑。
    """
    _insert_success_log(db, _naive_now(), job_name='temperature')
    monkeypatch.setenv('SCHEDULER_ENABLED', '0')

    sched = _health_scheduler(client, monkeypatch)

    assert sched['last_success_run'] is not None, '前提：有近期成功记录'
    assert sched['status'] == 'disabled', '开关关闭时不得因有历史成功记录就显示 healthy'


# ---------------------------------------------------------------------------
# 心跳 job 口径与「形态无关」（#3085）
#
# 上一组用例只回答「开关关了要显示出来」。这一组回答的是另一半：**调度停了**也要
# 显示出来，而旧口径两个方向都会漏——手动单跑任何 job 都能续命；部署库（外部 cron
# 驱动、从不设 SCHEDULER_ENABLED）停摆多久都只报 disabled，而 disabled 不拉低整体。
# ---------------------------------------------------------------------------


def test_manual_job_success_does_not_mask_dead_scheduler(client, db, monkeypatch):
    """反向钉：只有非心跳 job 的近期成功，调度仍算停摆。

    旧口径取「任意 success 行的 max」，所以「停摆 10 天 + 今天手动跑了一次 nav_backfill」
    会显示健康——查故障的人第一眼就被这句话劝退。
    """
    _insert_success_log(db, _naive_now() - timedelta(days=10))
    _insert_success_log(db, _naive_now(), job_name='nav_backfill')

    sched = _scheduler_component(client, monkeypatch)

    assert sched['status'] == 'unhealthy', '手动单跑的 success 不得让停摆显示正常'
    assert sched['heartbeat_job'] == 'asset_snapshot'
    assert 'asset_snapshot' in sched['message'], '消息要点名是哪个 heartbeat 没跑'


def test_external_cron_form_is_healthy_without_scheduler_enabled(client, db, monkeypatch):
    """部署形态：本机常驻没开，但库里有近期心跳 ⇒ 外部定时器在跑，判健康。

    旧口径在这里报 `disabled`（"不会自动更新"），把正在跑的部署库说成没启用。
    """
    _insert_success_log(db, _naive_now())
    monkeypatch.delenv('SCHEDULER_ENABLED', raising=False)

    sched = _health_scheduler(client, monkeypatch)

    assert sched['enabled'] is False, '开关本身仍是关的（字段如实反映）'
    assert sched['status'] == 'healthy'
    assert '外部定时器' in sched['message'], '必须说清是谁在驱动它'


def test_external_cron_form_stale_is_degraded(client, db, monkeypatch):
    """部署形态停摆 ⇒ `degraded`：本进程看不到那个定时器，不能下定论，但必须显示。

    报 `disabled` 的后果是「进程全停」这件事在状态页上完全不可见——正是 #3085 要修的。
    """
    _insert_success_log(db, _naive_now() - timedelta(days=10))
    monkeypatch.delenv('SCHEDULER_ENABLED', raising=False)

    sched = _health_scheduler(client, monkeypatch)

    assert sched['status'] == 'degraded'
    assert '外部定时器可能已停' in sched['message']


def test_heartbeat_job_is_daily_scheduled():
    """心跳 job 必须真的在每日调度表里，且 cron 是日频。

    否则这套判定会以「一个从不运行的 job」为基准：它永远没有成功记录，
    或者反过来永远新鲜——两种都会让结论与事实脱钩。
    """
    from app.services.daily_scheduler import _JOB_TEMPLATES

    rows = {t[0]: t for t in _JOB_TEMPLATES}
    assert 'asset_snapshot' in rows, '心跳 job 不在 _JOB_TEMPLATES ⇒ 它不会每日运行'
    cron = rows['asset_snapshot'][3]
    # 五段式 cron 的第 3 段是「日」；写成 `*/2` 或 `1` 就不是每日
    assert cron.split()[2] == '*', f'心跳 job 的 cron 不是日频：{cron}'
