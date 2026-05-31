# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:35
# File : fund_nav_job.py
# -*- coding: utf-8 -*-
# app/services/sync/jobs/fund_nav_job.py
import random
import time
from datetime import date, timedelta
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth, Fund
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.models.sync_log import SyncLog
from app.services.sync.jobs.base import JobStatus, SyncJob


class FundNavSyncJob(SyncJob):
    def __init__(self, adapter, db: Session):
        super().__init__(adapter, db)
        # 允许增量同步返回空数据（部分基金无新净值或失败是正常的）
        self._get_fund_codes = None

    @property
    def _allow_empty_data(self) -> bool:
        """增量同步在部分基金无数据或失败时允许返回空"""
        return True

    def get_name(self) -> str:
        return 'fund_nav'

    # ── 辅助方法：获取需同步的基金代码（含复活逻辑） ──
    def _get_fund_codes(self) -> tuple[List[str], Dict[str, int]]:
        """
        返回 (待处理代码列表, 统计计数)
        统计计数包含: active, sampled_inactive
        """
        # 活跃基金
        active_rows = self.db.query(Fund.fund_code).filter(Fund.is_active).all()
        active_codes = [row[0] for row in active_rows]

        # 非活跃基金随机复活
        inactive_rows = self.db.query(Fund.fund_code).filter(~Fund.is_active).all()
        inactive_codes = [row[0] for row in inactive_rows]

        revival_codes = []
        sampled = 0
        if inactive_codes:
            sample_size = max(1, int(len(inactive_codes) * 0.05))
            sampled = min(sample_size, len(inactive_codes))
            revival_codes = random.sample(inactive_codes, sampled)
            logger.info(f'随机抽取 {sampled} 只非活跃基金进行复活探测')

        total_codes = active_codes + revival_codes
        counts = {'active': len(active_codes), 'sampled_inactive': sampled, 'total_funds': self._get_total_funds()}
        return total_codes, counts

    def _get_total_funds(self) -> int:
        return self.db.query(Fund).count()

    # ── 增量同步使用基类标准流程，这里只需覆盖 _fetch_data ──
    def _fetch_data(self, full_sync: bool) -> List[dict]:
        """
        增量模式：获取所有活跃基金最近一段时间的净值。
        全量模式：本方法不会被调用（由自定义 run 接管）。
        """
        if not full_sync:
            codes, _ = self._get_fund_codes()
            if not codes:
                return []
            last = SyncLog.get_last_sync_time(self.db, self.get_name())
            start_date = (last.date() - timedelta(days=1)) if last else (date.today() - timedelta(days=30))
            records = []
            for code in codes:
                try:
                    nav_data = self.adapter.fetch_fund_nav(code, start_date=start_date)
                except Exception as e:
                    logger.warning(f'获取基金 {code} 净值时适配器抛异常: {e}')
                    self.stats.setdefault('skipped_no_data', 0)
                    self.stats['skipped_no_data'] += 1
                    self._update_fund_fail_count(code, is_empty=True)
                    continue

                if not isinstance(nav_data, list):
                    logger.warning(f'基金 {code} 返回值异常 (类型:{type(nav_data)})，已跳过')
                    self.stats.setdefault('skipped_no_data', 0)
                    self.stats['skipped_no_data'] += 1
                    self._update_fund_fail_count(code, is_empty=True)
                    continue

                records.extend(nav_data)
            return records
        return []

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

    def _save_data(self, new_data: List[dict]) -> None:
        if new_data:
            self.db.bulk_insert_mappings(DailyWorth, new_data)
            self.db.commit()

    # ── 全量同步（分批 + 过滤 + 统计） ──
    def run(self, full_sync: bool = False) -> Dict[str, Any]:
        if not full_sync:
            # 增量：使用目标代码列表
            codes = self._get_target_codes()
            if not codes:
                self.logger.info('无持仓/自选基金，跳过净值同步')
                self.snapshot_time = now_shanghai()
                self.status = JobStatus.SUCCESS
                return self._build_result()
            # 保存原 _get_fund_codes，替换为目标版本
            self._get_fund_codes = lambda: (codes, {})
            try:
                return super().run(full_sync)
            finally:
                del self._get_fund_codes

        self._full_sync_flag = True
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()

        # 初始化统计字段
        self.stats = {
            'total': 0,
            'active': 0,
            'sampled_inactive': 0,
            'success': 0,
            'skipped_inactive': 0,
            'skipped_no_data': 0,
            'failed_network': 0,
            'failed_timeout': 0,
            'failed_other': 0,
            'errors': [],
        }

        codes, counts = self._get_fund_codes()
        self.stats['total'] = len(codes)
        self.stats['active'] = counts['active']
        self.stats['sampled_inactive'] = counts['sampled_inactive']
        # 跳过的无效基金数 = 总基金数 - 活跃数 - 复活样本数
        self.stats['skipped_inactive'] = counts['total_funds'] - counts['active'] - counts['sampled_inactive']

        if not codes:
            logger.info('无基金需要同步')
            self.status = JobStatus.SUCCESS
            return self._build_result()

        total = len(codes)
        batch_size = getattr(self, 'batch_size', 50)
        failed_funds = []
        success_funds = []  # 记录本批次成功获取到净值的基金代码

        for i in range(0, total, batch_size):
            batch = codes[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size
            logger.info(f'净值进度: 批次 {batch_num}/{total_batches} (本批 {len(batch)} 只基金)')

            batch_data = []
            for code in batch:
                try:
                    records = self.adapter.fetch_fund_nav(code, start_date=None)  # 全量拉取
                    if records:
                        batch_data.extend(records)
                        success_funds.append(code)
                    else:
                        # 返回空但未抛异常 → 标记为无数据（临时）
                        self.stats['skipped_no_data'] += 1
                        self._update_fund_fail_count(code, is_empty=True)
                except Exception as e:
                    logger.warning(f'获取基金 {code} 净值失败: {e}')
                    failed_funds.append(code)
                    self._update_fund_fail_count(code, is_empty=False, error=e)
                    # 根据异常类型分类统计
                    self._classify_error(e)

            # 校验、去重、写入
            if batch_data:
                validated = self._validate_data(batch_data)
                new_data = self._deduplicate(validated)
                if new_data:
                    self._save_data(new_data)
                    self.stats['success'] += len(new_data)
                else:
                    logger.info('本批无新净值数据')
            else:
                logger.info('本批未获取到任何净值数据')

            # 批次间延迟，防止请求过密
            time.sleep(1.0)

        # 处理成功的基金：重置失败计数及复活
        for code in set(success_funds):
            self._reset_fund_status(code)

        if failed_funds:
            logger.warning(f"以下基金净值获取失败: {', '.join(failed_funds[:20])}...（共 {len(failed_funds)} 只）")

        # 输出摘要日志
        self._print_summary()

        self._validate_integrity()
        self._post_run()
        self.status = JobStatus.SUCCESS
        return self._build_result()

    # ── 辅助方法：更新基金失败计数 ──
    def _update_fund_fail_count(self, code: str, is_empty: bool, error: Exception = None):
        fund = self.db.query(Fund).filter_by(fund_code=code).first()
        if not fund:
            return
        fund.nav_fail_count = (fund.nav_fail_count or 0) + 1
        fund.last_nav_check = now_shanghai()
        if fund.nav_fail_count >= 3 and fund.is_active:
            fund.is_active = False
            logger.info(f'基金 {code} 连续失败 {fund.nav_fail_count} 次，标记为无效')
        self.db.commit()

    def _reset_fund_status(self, code: str):
        fund = self.db.query(Fund).filter_by(fund_code=code).first()
        if not fund:
            return
        fund.nav_fail_count = 0
        fund.last_nav_check = now_shanghai()
        if not fund.is_active:
            fund.is_active = True
            logger.info(f'基金 {code} 已复活')
        self.db.commit()

    def _classify_error(self, error: Exception):
        msg = str(error).lower()
        if 'timeout' in msg or 'timed out' in msg:
            self.stats['failed_timeout'] += 1
        elif 'connection' in msg or 'network' in msg:
            self.stats['failed_network'] += 1
        else:
            self.stats['failed_other'] += 1
        self.stats['errors'].append({'fund_code': '', 'error': str(error)})  # 具体code已在循环中记录

    def _print_summary(self):
        total_funds = self.stats.get('total_funds', self._get_total_funds())
        active = self.stats.get('active', 0)
        sampled = self.stats.get('sampled_inactive', 0)
        success = self.stats.get('success', 0)
        skipped_inactive = self.stats.get('skipped_inactive', total_funds - active - sampled)
        no_data = self.stats.get('skipped_no_data', 0)
        net_err = self.stats.get('failed_network', 0)
        timeout_err = self.stats.get('failed_timeout', 0)
        other_err = self.stats.get('failed_other', 0)
        duration = (now_shanghai() - self.snapshot_time).total_seconds()

        summary = (
            f'\n[INFO] 基金净值同步完成\n'
            f'  总基金数: {total_funds}\n'
            f'  活跃基金: {active}\n'
            f'  探测非活跃: {sampled}\n'
            f'  成功获取: {success}\n'
            f'  跳过无效: {skipped_inactive}\n'
            f'  无数据: {no_data}\n'
            f'  网络错误: {net_err}\n'
            f'  超时错误: {timeout_err}\n'
            f'  其他错误: {other_err}\n'
            f'  耗时: {duration:.2f}秒'
        )
        logger.info(summary)

    def _get_all_active_fund_codes(self) -> List[str]:
        """获取所有活跃基金代码（全量同步用）"""
        return [row[0] for row in self.db.query(Fund.fund_code).filter(Fund.is_active).all()]

    def _get_target_codes(self) -> List[str]:
        """获取本次应同步的基金代码（持仓 + 自选 + 系统）"""
        # 如果有 target_file_codes 属性，则直接使用文件中的代码（过滤出6位数字）
        if hasattr(self, 'target_file_codes') and self.target_file_codes:
            # 这里要确保 self.target_file_codes 是列表
            self.logger.info(f'使用文件代码列表: {len(self.target_file_codes)} 个')
            return [c for c in self.target_file_codes if c.isdigit() and len(c) == 6]

        codes = set()

        # 1. 持仓中的基金
        position_rows = self.db.query(Position.symbol).filter(Position.asset_type == 'fund').distinct().all()
        codes.update(row[0] for row in position_rows if row[0])

        # 2. 自选中的基金（6位纯数字）
        watchlist_rows = self.db.query(WatchlistItem.symbol).distinct().all()
        for row in watchlist_rows:
            code = row[0]
            if code and code.isdigit() and len(code) == 6:
                codes.add(code)

        # 3. 系统强制列表（暂无）
        return list(codes)
