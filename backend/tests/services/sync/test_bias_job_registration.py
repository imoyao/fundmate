# -*- coding: utf-8 -*-
"""#2494：BiasJob 注册进编排器（只注册、不调度）的判据。

为什么要一整批用例钉「加一行字典」：它连着两个**已经发生过**的形态，且两者都静默。

1. **只注册、不设定目标池口径** ⇒ 若哪天有人把它挂进每日调度并声明 `target_kind='fund'`，
   编排器会按 `batch_size`（默认 50）分批、每批调一次 `_fetch_data`；而
   `BiasJob._fetch_data` 不消费 `targets`、每次都算全量 37 个品种
   ⇒ N 批 × 37 次外部请求（东财限流/封禁风险）。
2. **注册后顺手挂进每日调度** ⇒ 与 `TemperatureJob._fetch_data` 的内联调用同一天算两遍
   （每遍 37 × request_interval 3s）。

故下面的用例分别钉住：注册了 / 没有被调度 / 无目标池时只取一次全量 / 自己落 sync_logs /
全部标的失败必须落 failed（不能静默 success）。
"""

from app.models.sync_log import SyncLog
from app.services import daily_scheduler
from app.services.bias.job import BiasJob
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestBiasJobRegistered:
    def test_orchestrator_registers_bias_job(self, db):
        """注册是「能单独补跑」的前提：run_job 只认 self.jobs 这个字典。"""
        orch = DataSyncOrchestrator(db)

        assert 'bias' in orch.jobs
        assert isinstance(orch.jobs['bias'], BiasJob)
        assert orch.jobs['bias'].get_name() == 'bias'

    def test_bias_job_is_not_daily_scheduled(self):
        """只注册、不调度：日常仍由 TemperatureJob 内联跑一次（#2494 方案 a）。

        这条不是「防止功能缺失」，而是**防止重复计算**：bias 一旦进了调度模板，
        同一天就会被算两遍，且两遍都成功、日志全绿——只有外部请求数翻倍能看出来。
        """
        config = daily_scheduler.load_config({})
        scheduled = {spec.job_name for spec in config.jobs}

        assert 'bias' not in scheduled
        # 连模板都不许出现：只看 config 的话，「默认关闭的模板」能绕过这条判据
        assert 'bias' not in {template[0] for template in daily_scheduler._JOB_TEMPLATES}

    def test_bias_fetch_runs_once_without_target_pool(self, db, monkeypatch):
        """targets=None ⇒ 只取一次全量清单。

        反证同一件事：若被按目标池分批，`_collect` 会随批次数增加——本用例把「1 次」
        钉住，等于把「不要给它设 target_kind」这条口径变成了可执行的判据。
        """
        orch = DataSyncOrchestrator(db)
        job = orch.jobs['bias']
        calls = []

        def fake_collect():
            calls.append(1)
            return [], []

        monkeypatch.setattr(job, '_collect', fake_collect)

        result = job.run(full_sync=False, targets=None)

        assert len(calls) == 1
        # 清单为空是合法状态（「今天没有品种要算」），不是失败
        assert result['status'] == 'success'


class TestBiasJobAuditVisible:
    def test_run_job_writes_its_own_sync_log(self, db, monkeypatch):
        """跑一次必须留一行 `job_name='bias'` 的审计——这正是本卡要修的第一件事。"""
        orch = DataSyncOrchestrator(db)
        monkeypatch.setattr(orch.jobs['bias'], '_collect', lambda: ([], []))

        result = orch.run_job('bias')

        assert result['status'] == 'success'
        db.expire_all()
        rows = db.query(SyncLog).filter_by(job_name='bias').all()
        assert len(rows) == 1
        assert rows[0].status == 'success'
        assert rows[0].started_at is not None

    def test_all_targets_failed_is_reported_as_failed(self, db, monkeypatch):
        """全部标的抓取失败 ⇒ 必须落 failed。

        断网 / 上游整体不可用是这条 job 最常见的故障形态；若它记成 success，
        「bias 跑过了」与「bias 一条都没拿到」在看板上长得一样（#2475 同族）。
        """
        orch = DataSyncOrchestrator(db)
        failures = [{'item_code': '801010', 'item_name': '农林牧渔', 'error': '连接超时'}]
        monkeypatch.setattr(orch.jobs['bias'], '_collect', lambda: ([], failures))

        result = orch.run_job('bias')

        assert result['status'] == 'failed'
        assert result['stats']['total'] == 1
        assert result['stats']['success'] == 0
        db.expire_all()
        row = db.query(SyncLog).filter_by(job_name='bias').one()
        assert row.status == 'failed'
