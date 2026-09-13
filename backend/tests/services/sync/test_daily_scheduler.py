# -*- coding: utf-8 -*-
"""测试每日调度：AssetSnapshotJob 注册与落账（#1182）+ 探市快照与交易日口径（#1460）。"""

from datetime import date

from app.domains.ledgers.models import Ledger
from app.domains.summary.models import AssetSnapshot
from app.services import daily_scheduler as ds
from app.services.daily_scheduler import DailyJobSpec, load_config
from app.services.sync.orchestrator import DataSyncOrchestrator


class TestDailyScheduler:
    def test_asset_snapshot_job_registered(self, db):
        """Orchestrator 必须注册 asset_snapshot job（run_all_jobs 才会在末尾触发）。"""
        orch = DataSyncOrchestrator(db)
        assert 'asset_snapshot' in orch.jobs
        assert orch.jobs['asset_snapshot'].get_name() == 'asset_snapshot'

    def test_run_asset_snapshot_success_on_empty_db(self, db):
        """空库无 family → 幂等 no-op，仍返回 success（不报错、不抛异常）。"""
        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'
        # 幂等 no-op：空库未写入任何快照行
        assert db.query(AssetSnapshot).count() == 0

    def test_run_asset_snapshot_writes_family_snapshot(self, db):
        """有 ledger(family_id=1) 时，应为该家庭落当日快照（家庭级 + 账户级）。"""
        ledger = Ledger(name='测试账户', ledger_type='bank', family_id=1)
        db.add(ledger)
        db.commit()

        orch = DataSyncOrchestrator(db)
        result = orch.run_job('asset_snapshot')
        assert result['status'] == 'success'
        assert result.get('stats', {}).get('success') == 1

        snap = db.query(AssetSnapshot).filter(AssetSnapshot.family_id == 1).first()
        assert snap is not None
        # #863 P1-5：本测试家庭仅有银行台账、无货基持仓，write_asset_snapshot 对无货基
        # 家庭写 None（展示层再按 0.0 处理，见 summary_service._snapshot_payload）。
        assert snap.money_fund_income_cents is None


class TestMarketSnapshotScheduling:
    """#1460：探市 20 资产快照接入本机调度 + 按任务交易日口径。"""

    def test_market_snapshot_in_job_templates(self):
        assert 'market_snapshot' in [t[0] for t in ds._JOB_TEMPLATES]

    def test_market_snapshot_defaults(self):
        """08:00 落库（美股收盘后）、无目标池、日历 none（A 股假期照常跑）。"""
        spec = next(s for s in load_config({}).jobs if s.job_name == 'market_snapshot')
        assert spec.cron == '0 8 * * *'
        assert spec.target_kind is None
        assert spec.calendar == ds.CALENDAR_NONE

    def test_existing_jobs_keep_cn_calendar(self):
        """引入 calendar 字段不得改变既有两任务的行为（仍是 A 股日历）。"""
        by = {s.job_name: s for s in load_config({}).jobs}
        assert by['temperature'].calendar == ds.CALENDAR_CN
        assert by['fund_nav'].calendar == ds.CALENDAR_CN

    def test_market_job_can_be_disabled_by_env(self):
        cfg = load_config({'SCHEDULER_MARKET_ENABLED': 'false'})
        assert 'market_snapshot' not in cfg.job_names()
        # 其余任务不受影响
        assert 'temperature' in cfg.job_names()

    def test_market_cron_can_be_overridden(self):
        cfg = load_config({'SCHEDULER_MARKET_CRON': '15 7 * * *'})
        spec = next(s for s in cfg.jobs if s.job_name == 'market_snapshot')
        assert spec.cron == '15 7 * * *'

    def test_cn_rest_day_skips_cn_jobs_but_not_market(self, monkeypatch):
        """A 股休市只该挡掉 cn 口径的任务。

        探市快照的资产含美股 / 商品 / 汇率，按全局布尔跳过会让它们停更一周（国庆）。
        """
        monkeypatch.setattr(ds, 'is_trading_day', lambda d: False)
        cn_spec = DailyJobSpec('temperature', '0 20 * * *', None, 'x', ds.CALENDAR_CN)
        market_spec = DailyJobSpec('market_snapshot', '0 8 * * *', None, 'x', ds.CALENDAR_NONE)
        holiday = date(2026, 10, 2)  # 国庆假期；显式传日期，测试不依赖「今天」是什么日子

        assert ds.is_job_rest_day(cn_spec, holiday) is True
        assert ds.is_job_rest_day(market_spec, holiday) is False

    def test_is_job_rest_day_defaults_to_shanghai_today(self, monkeypatch):
        """不传 today 时取上海当日（回归：`today_shanghai()` 已是 date，不可再 `.date()`）。"""
        monkeypatch.setattr(ds, 'is_trading_day', lambda d: d == date(2026, 10, 2))
        monkeypatch.setattr(ds, 'today_shanghai', lambda: date(2026, 10, 2))
        cn_spec = DailyJobSpec('temperature', '0 20 * * *', None, 'x', ds.CALENDAR_CN)

        assert ds.is_job_rest_day(cn_spec) is False

    def test_catch_up_includes_market_on_cn_rest_day(self, monkeypatch):
        """启动补跑同样按任务判定：A 股休市当天，探市快照仍应被补跑。"""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        monkeypatch.setattr(ds, 'is_trading_day', lambda d: False)
        cfg = load_config({})
        now = datetime(2026, 10, 2, 9, 0, tzinfo=ZoneInfo(cfg.timezone))  # 国庆假期 09:00

        due = ds.catch_up_targets(cfg, now, {})

        assert 'market_snapshot' in due, 'A 股假期不应挡住探市快照的补跑'
        assert 'temperature' not in due, 'A 股休市应挡住温度计'
