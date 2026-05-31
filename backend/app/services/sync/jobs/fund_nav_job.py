# app/services/sync/jobs/fund_nav_job.py
"""
基金净值同步任务。
全量同步直接分批拉取所有历史净值，增量同步仅拉取最近 N 天。
目标代码由 Orchestrator 传入。
"""

from datetime import date, timedelta
from typing import List

from loguru import logger

from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth
from app.models.sync_log import SyncLog
from app.services.sync.jobs.base import SyncJob


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
        if not data:
            return []
        codes = list({item['fund_code'] for item in data})
        existing = set(
            (row.fund_code, row.date)
            for row in self.db.query(DailyWorth.fund_code, DailyWorth.date)
            .filter(DailyWorth.fund_code.in_(codes))
            .all()
        )
        return [item for item in data if (item['fund_code'], item['date']) not in existing]

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        if new_data:
            self.db.bulk_insert_mappings(DailyWorth, new_data)
            self.db.commit()
