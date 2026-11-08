# -*- coding: utf-8 -*-
# app/services/sync/jobs/securities_backfill_job.py
"""证券名录**定向补录**（只补缺的，不重拉全量）。

## 与 `stock_list` 的分工

| | `stock_list` | `securities_backfill`（本 job） |
|---|---|---|
| 范围 | 全市场（A 股 + ETF + 可转债） | 只补「流水里有、名录里没有」的那几只 |
| 成本 | 11.67s（仅 A 股段）～ 29.4 分钟（三源合并） | 0.04~0.25s/只 |
| 频率 | 月度 / 手动 | 导入后自动触发，也可手动 |
| 作用 | 灾备重建、首次部署 | 日常让缺口自愈 |

不把补录塞进 `stock_list` 的原因：那个 job 的耗时全在「换全市场」，而补录只需要
几只 —— 为了补 3 只跑 29 分钟，是把月度任务当日常任务用。两者目标正交，各留各的。

## 为什么继承 `StockListSyncJob`

`_validate_data` / `_deduplicate` / `_save_data` 三个方法的语义与名录写入**完全一致**
（upsert：新增缺失 + 更新 name/market/type）。复制一份等于给自己留两套口径，
下次改 upsert（比如 #2522 那次为了 Turso 换 `bulk_insert_rows`）时必然漏改一处。
本 job 与它的唯一差别就是「数据从哪来」，所以只覆写 `get_name` 与 `_fetch_data`。

## 缺口必须进 `errors`，否则会显示成「全成功」

`_execute_batches` 只累加 `success`；`failed` 由基类尾部按 `len(errors)` 收口
（`job_base.py` #2475）。也就是说**只有 `errors` 能表达失败** —— 查不到的标的
若只是 `continue` 掉，「10 个缺口补上 3 个」会显示成「3/3」，剩下 7 个无声消失。

补录的价值恰恰在于**让缺口可见**（与 `price_history_job.unlisted` 同一条纪律：
不修名录可以，但必须让人看见），故逐只写进 `stats['errors']`，不另行维护 `failed`。
"""

from typing import List

from app.services.sync.jobs.stock_list_job import StockListSyncJob


class SecuritiesBackfillJob(StockListSyncJob):
    """按缺口逐只补录名录；查不到的标的记进 `stats['failed']` 并保留为缺口。"""

    def get_name(self) -> str:
        return 'securities_backfill'

    @property
    def _allow_empty_data(self) -> bool:
        # 缺口为空是**正常**状态（名录已齐全），不是故障
        return True

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """逐只查上游，返回可直接喂 `_save_data` 的记录。

        `targets` 由调用方给出缺口清单（见 `securities_catalog.missing_catalog_symbols`）；
        为空时不自行兜底成「全量」—— 那会把一个 0.1s 的补录变成 29 分钟的全量刷新，
        而调用方以为自己只是「顺手补一下」。
        """
        records: List[dict] = []
        for symbol in targets:
            record = self.adapter.fetch_security_by_symbol(symbol)
            if record:
                records.append(record)
                continue
            # 未上市 / 已退市 / 代码不存在：上游明确没有，保留缺口并让它可见。
            # 只写 errors、**不自己加 failed** —— 基类尾部按
            # `max(stats['failed'], len(errors))` 收口（#2475），两处各记一次
            # 会得到两种口径，且哪一处漏改都不会报错，只会静默少算。
            self.stats['errors'].append(
                {
                    'symbol': symbol,
                    'error': '名录查不到（未上市 / 已退市 / 代码不存在），缺口保留',
                }
            )
        return records
