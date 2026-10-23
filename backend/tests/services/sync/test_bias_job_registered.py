# -*- coding: utf-8 -*-
"""#2494：乖离率注册进编排器，但**既不调度、也不进目标池**。

本文件钉的是三条**形态约束**，不是实现细节：

1. `DataSyncOrchestrator().jobs` 含 `'bias'` —— 否则 `sync --job bias` 报「未知任务」，
   裸跑某一天的乖离率只能重跑整个 `temperature`（连带另外 6 个数据源一起打上游）。
2. `'bias'` 不在 `sync_metadata.DB_POOL_JOBS` —— `BiasJob._fetch_data` 不读 `targets`，
   一旦被按目标池分批，就是「每批重算一次全量」（N 批 × 37 次外部请求）。
3. `'bias'` 不在 `daily_scheduler` 的作业模板里 —— 日常仍由 `TemperatureJob` 内联跑；
   两边都调度会让同一批标的每天算两遍。

前两条是「注册方式」的两面：只加进 `self.jobs`、不加进池，CLI 才会传 `targets=None`，
`job_base.run()` 才会走「单次全量」那一支（见 `job_base.py:279`）。
"""

from app.services.bias.job import BiasJob
from app.services.daily_scheduler import _JOB_TEMPLATES, _NOT_SCHEDULED
from app.services.sync.orchestrator import DataSyncOrchestrator
from app.tools.sync_metadata import DB_POOL_JOBS


def test_bias_注册进编排器(db):
    """`jobs` 含 bias —— 这是 `sync --job bias` 能跑起来的前提。"""
    orch = DataSyncOrchestrator(db)

    assert 'bias' in orch.jobs
    job = orch.jobs['bias']
    assert isinstance(job, BiasJob)
    # `sync_logs.job_name` 取自 get_name()，写成别的名字会让审计行落错桶
    assert job.get_name() == 'bias'


def test_bias_不进目标池(db):
    """进了 DB_POOL_JOBS 就会被分批 ⇒ 每批重算全量（东财限流下等于制造封禁）。"""
    assert 'bias' not in DB_POOL_JOBS


def test_bias_不挂每日调度(db):
    """日常由 TemperatureJob 内联跑；再挂一份就是每天算两遍。"""
    scheduled = {tpl[0] for tpl in _JOB_TEMPLATES}
    assert 'bias' not in scheduled
    # 反向锚：模板解析路径没被写坏（否则上面那条「不在」可能只是没解析出来）
    assert 'temperature' in scheduled
    # 「不调度」必须在 daily_scheduler._NOT_SCHEDULED 里有带理由的登记，
    # 否则 scripts/guard_job_schedule_coverage.py 会红（CI 的 layout_guard job）
    assert 'bias' in _NOT_SCHEDULED
    assert _NOT_SCHEDULED['bias'][0].strip(), '登记理由不能为空——空理由等于没登记'


def test_run_job_bias_落自己的审计行(db, monkeypatch):
    """`run_job('bias')` 能跑通，并落一条 `job_name='bias'` 的 sync_logs。

    取数打桩成空清单（`_collect` 返回 `([], [])`）：本用例要验的是**接线**，
    不是抓取；空清单对 `_allow_empty_data=True` 的 job 是合法状态（SUCCESS）。
    """
    from app.models.sync_log import SyncLog

    monkeypatch.setattr(BiasJob, '_collect', lambda self: ([], []))

    orch = DataSyncOrchestrator(db)
    result = orch.run_job('bias', full_sync=False)

    assert result['status'] == 'success'
    db.expire_all()
    rows = db.query(SyncLog).filter_by(job_name='bias').all()
    assert len(rows) == 1
    assert rows[0].status == 'success'


def test_run_job_bias_全部标的失败落_failed_审计行(db, monkeypatch):
    """「上游整体不可用」必须落 `failed`，不得静默成 success（本卡验收第 4 条）。

    打桩成「37 个标的全部抓取失败」——这正是断网时的形态。部分失败仍是 success
    （`_decide_final_status` 的口径，见 #2475），此处验的是全部失败那一支。
    """
    from app.models.sync_log import SyncLog

    failures = [{'item_code': f'8010{i:02d}', 'item_type': 'index', 'error': 'network down'} for i in range(37)]
    monkeypatch.setattr(BiasJob, '_collect', lambda self: ([], failures))

    orch = DataSyncOrchestrator(db)
    result = orch.run_job('bias', full_sync=False)

    assert result['status'] == 'failed'
    db.expire_all()
    rows = db.query(SyncLog).filter_by(job_name='bias').all()
    assert len(rows) == 1
    assert rows[0].status == 'failed'
