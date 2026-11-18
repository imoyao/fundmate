# -*- coding: utf-8 -*-
"""目标池接线判据（#3073）。

## 为什么需要这组测试

`JobBase.run(targets=None)` 会以 ``_fetch_data(full_sync, [])`` 调用子类——这是给
「全量列表类 job」准备的分支。但**按标的逐只抓**的 job 收到空列表就一次都不循环，
返回空数据，再被 ``_allow_empty_data`` 记成 SUCCESS + ``total=0``。于是「调用方忘了给
目标池」和「今天真的没活干」在日志与看板上完全同形，没有任何地方会红。

真库实测（2026-11-12，811 条 sync_logs）：``dividend_split`` 27 次执行 27 次
``total=0``，一次都没抓过分红/送股；``securities_backfill`` 10 次全零（#3070）。

## 判据为什么挂在「两份清单对账」上

系统里早有 ``SYMBOL_BACKFILL_JOBS``（orchestrator，逐标的 job 的登记册，`dividend_split`
本来就在里面），而调度器 ``_JOB_TEMPLATES`` 的 ``target_kind`` 是另一份独立清单。
两份清单**各写各的、没有对账**，正是这次漏接线的土壤。把它变成断言，两边一旦分叉就红。
"""

import pytest

from app.services import daily_scheduler as ds
from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob
from app.services.sync.jobs.securities_backfill_job import SecuritiesBackfillJob
from app.services.sync.target_guard import require_targets

#: 已声明「`_fetch_data` 依赖调用方给目标池」的 job。新增同类 job 时加到这里 ——
#: 清单本身就是判据：漏加会被 `TestSchedulerWiring` 之外的用例挡住（各自类里断言）。
_DECLARED_JOBS = {
    'dividend_split': DividendSplitSyncJob,
    'securities_backfill': SecuritiesBackfillJob,
}


class TestRequireTargets:
    def test_missing_targets_is_rejected(self):
        """声明了 requires_targets 的 job 拿到 None ⇒ 报接线错误，不许静默空跑。"""
        with pytest.raises(ValueError, match='需要目标池'):
            require_targets('dividend_split', True, None)

    def test_empty_list_is_allowed(self):
        """空列表放行：那是「持仓 + 自选里确实没有标的」的计算结果，不是配置错。

        两者必须分开——把 [] 也判成错，会让没有持仓的账户每天调度都红。
        """
        require_targets('dividend_split', True, [])

    def test_job_without_declaration_ignores_none(self):
        """全量列表类 job（自己取全市场）不受影响。"""
        require_targets('fund_list', False, None)


class TestSchedulerWiring:
    def test_declared_jobs_get_target_pool(self):
        """声明了 `requires_targets` 且参与调度的 job，调度器必须给它配 target_kind。

        2026-11-12 实测：`dividend_split` 在 `SYMBOL_BACKFILL_JOBS` 登记册里（裸
        --full-sync 会被 `require_full_sync_scope` 拒），但 `_JOB_TEMPLATES` 的
        target_kind 是 None ⇒ 调度器走「不给目标池」分支 ⇒ `_fetch_data(full_sync, [])`
        ⇒ 27 次执行 27 次 total=0。

        判据按**声明**查而不是按 `SYMBOL_BACKFILL_JOBS` 查：该登记册里 `position_price`
        没有 target_kind，但它的 `_fetch_data` 是空实现（覆写 `run()` 自己干活，
        真库实测 total=171 正常）——属于「登记册为 full-sync 范围校验而收，与目标池无关」，
        套用登记册会造出误报。
        """
        kinds = {t[0]: t[4] for t in ds._JOB_TEMPLATES}
        for name, cls in _DECLARED_JOBS.items():
            if name not in kinds:
                continue  # 未被调度器调度（如 securities_backfill 只由导入路径触发）
            assert cls.requires_targets is True, f'{name} 的声明被人改掉了'
            assert kinds[name] is not None, f'{name} 声明了 requires_targets，但调度器没配 target_kind'

    def test_dividend_split_gets_fund_and_stock_pool(self):
        """分红对象既有场外基金（裸 6 位）也有场内股票/ETF（带前缀），两池都要。"""
        kind = next(t[4] for t in ds._JOB_TEMPLATES if t[0] == 'dividend_split')
        assert kind == ('fund', 'stock')


class TestRequiresTargetsDeclaration:
    def test_dividend_split_declares(self):
        assert DividendSplitSyncJob.requires_targets is True

    def test_securities_backfill_declares(self):
        """缺口清单只能由调用方给，本 job 不兜底成全量（#3070 的教训）。"""
        assert SecuritiesBackfillJob.requires_targets is True

    def test_stock_list_does_not_declare(self):
        """父类 `stock_list` 是全市场 job，不能被 `securities_backfill` 的声明带偏。"""
        from app.services.sync.jobs.stock_list_job import StockListSyncJob

        assert StockListSyncJob.requires_targets is False
