# app/services/sync/jobs/fund_nav_job.py
"""
基金净值同步任务。
全量同步直接分批拉取所有历史净值，增量同步仅拉取最近 N 天。
目标代码由 Orchestrator 传入。
"""

from datetime import date, timedelta
from typing import List

from loguru import logger

from app.core.constants import SOURCE_VERSION_V2_RECALC
from app.core.db_utils import bulk_insert_if_not_exists
from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth, MoneyFundDailyWorth
from app.models.sync_log import SyncLog
from app.services.job_base import IN_CHUNK_SIZE, SyncJob


class FundNavSyncJob(SyncJob):
    """基金净值同步"""

    def get_name(self) -> str:
        return 'fund_nav'

    @property
    def _allow_empty_data(self) -> bool:
        return True  # 允许无新净值时正常退出

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """逐只基金拉取净值，单只失败不影响整体"""
        if not full_sync:
            last = SyncLog.get_last_sync_time(self.db, self.get_name())
            start_date = (last.date() - timedelta(days=1)) if last else (date.today() - timedelta(days=30))
        else:
            start_date = None  # 全量不限日期

        records = []
        for code in targets:
            try:
                nav_list = self.adapter.fetch_fund_nav(code, start_date=start_date)
                if isinstance(nav_list, list):
                    records.extend(nav_list)
            except Exception as e:
                logger.warning(f'基金 {code} 净值获取跳过: {e}')
                self.stats.setdefault('errors', []).append({'fund_code': code, 'error': str(e)})

        return records

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        validated = []
        for item in raw_data:
            if not item.get('fund_code') or not item.get('date') or item.get('unit_nav') is None:
                continue
            if isinstance(item['date'], str):
                try:
                    item['date'] = date.fromisoformat(item['date'])
                except ValueError:
                    continue
            item.setdefault('created_at', now_shanghai())
            item.setdefault('updated_at', now_shanghai())
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按「记录将要落的那张表」分别去重（#1550）。

        货基与普通基金落的是**两张不同的表**：普通基金 → `daily_worth`，
        货基 → `money_fund_daily_worth`（各自一条 (fund_code, date) 唯一约束）。
        旧实现只查 `DailyWorth`，对货基记录而言等于「没去重」——只要
        `money_fund_daily_worth` 里已有该 (fund_code, date)，
        `bulk_insert_mappings` 就必然撞 `uq_money_fund_daily_worth_code_date`。

        2026-09-16 实测案发形态：026029（银河水星现金添利货币）存量止于 08-14，
        增量起点 = 上次 successful 同步日 − 1 = 08-13，每天都会把 08-13/08-14
        再插一遍；旧逻辑「查 daily_worth 没这两行」→ 放行 → UNIQUE 冲突，
        整批 50 只基金一起回滚。
        """
        if not data:
            return []
        money_records = [item for item in data if item.get('is_money_fund')]
        normal_records = [item for item in data if not item.get('is_money_fund')]
        return self._drop_existing(normal_records, DailyWorth) + self._drop_existing(money_records, MoneyFundDailyWorth)

    def _drop_existing(self, data: List[dict], model) -> List[dict]:
        """剔除在 `model` 表中已存在 (fund_code, date) 的记录"""
        if not data:
            return []
        codes = list({item['fund_code'] for item in data})
        existing: set = set()
        # 分批 in_ 查询：与基类 _deduplicate_by_unique_key 同口径防 SQLite 变量上限
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            chunk = codes[i : i + IN_CHUNK_SIZE]
            existing.update(
                (row[0], row[1])
                for row in self.db.query(model.fund_code, model.date).filter(model.fund_code.in_(chunk)).all()
            )
        return [item for item in data if (item['fund_code'], item['date']) not in existing]

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        if not new_data:
            return

        now = now_shanghai()
        money_records = []
        normal_records = []
        for item in new_data:
            if item.pop('is_money_fund', False):
                money_records.append(
                    {
                        'fund_code': item['fund_code'],
                        'date': item['date'],
                        'nav_per_10k': item['unit_nav'],
                        'annual_return_7d': None,  # 暂不计算
                        # #863 P0-4：新写入显式标记重算来源，与存量 legacy_dirty 旧数据区分
                        'source_version': SOURCE_VERSION_V2_RECALC,
                        'created_at': item.get('created_at') or now,
                        'updated_at': item.get('updated_at') or now,
                    }
                )
            else:
                # 显式挑列：Core insert 对未映射的键比 ORM bulk_insert_mappings 更严格，
                # 适配器将来多带一个字段就会直接炸在 SQL 编译期（#1550）
                normal_records.append(
                    {
                        'fund_code': item['fund_code'],
                        'date': item['date'],
                        'unit_nav': item['unit_nav'],
                        'acc_nav': item.get('acc_nav'),
                        'created_at': item.get('created_at') or now,
                        'updated_at': item.get('updated_at') or now,
                    }
                )

        # #1550：改用「冲突忽略」写入。去重虽已按表分流，但库里仍可能有本进程
        # 看不到的并发写入（异步回填线程 / 调度器补跑），一条重复不该让整批
        # （batch_size=50 只基金）一起回滚、连带丢掉当天所有新净值。
        if normal_records:
            inserted = bulk_insert_if_not_exists(
                self.db,
                DailyWorth,
                normal_records,
                unique_key='fund_code',  # 兼容旧参数
                unique_columns=['fund_code', 'date'],  # 实际使用的联合键
            )
            self._warn_if_skipped('daily_worth', inserted, len(normal_records), normal_records)
        if money_records:
            inserted = bulk_insert_if_not_exists(
                self.db,
                MoneyFundDailyWorth,
                money_records,
                unique_key='fund_code',
                unique_columns=['fund_code', 'date'],
            )
            self._warn_if_skipped('money_fund_daily_worth', inserted, len(money_records), money_records)

    def _warn_if_skipped(self, table: str, inserted, expected: int, records: List[dict]) -> None:
        """DB 端跳过的条数 > 0 时留痕（去重漏判 / 并发写的早期信号）"""
        if not isinstance(inserted, int) or inserted < 0 or inserted >= expected:
            return
        skipped = [(r['fund_code'], str(r['date'])) for r in records]
        logger.warning(f'{table} 冲突忽略 {expected - inserted} 条（去重未覆盖，已按已存在跳过）: {skipped[:10]}')
