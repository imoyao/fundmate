# app/services/sync/jobs/base.py
"""
同步任务基类 —— 重构版 v2.0

职责：
- 提供统一的 run() 流程（不再区分子类覆盖）
- 内置分批执行：子类只需设置 batch_size 和提供目标列表
- 内置重试与状态机
- 空数据保护由子类属性 _allow_empty_data 控制
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import now_shanghai


class JobStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    RETRYING = 'retrying'
    MANUAL_INTERVENTION = 'manual_intervention'


# 常量
BATCH_SIZE_DEFAULT = 50
BATCH_SIZE_DETAIL_ENRICH = 50  # FundDetailEnrichJob 每批提交的基金数
MAX_RETRIES = 3


class SyncJob(ABC):
    """
    所有同步任务的基类。

    子类必须实现：
        get_name() -> str
        _fetch_data(targets: List[str]) -> List[dict]
        _validate_data(raw_data: List[dict]) -> List[dict]
        _deduplicate(data: List[dict]) -> List[dict]
        _save_data(new_data: List[dict]) -> None

    可选覆盖：
        _allow_empty_data (property, default False) — 是否允许空数据
        batch_size (int, default 50) — 分批大小
    """

    batch_size = BATCH_SIZE_DEFAULT  # 保留类属性作为默认值

    def __init__(self, adapter, db: Session):
        self.adapter = adapter
        self.db = db
        self.logger = logger.bind(job=self.get_name())
        self.status = JobStatus.PENDING
        self.retry_count = 0
        self.stats: Dict[str, Any] = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
        self.snapshot_time: Optional[datetime] = None
        self._full_sync_flag: bool = False
        self.batch_size = BATCH_SIZE_DEFAULT  # 实例属性，可修改

    def _pre_run(self) -> None:
        """前置钩子，子类可重写"""
        pass

    def _post_run(self) -> None:
        """后置钩子，子类可重写"""
        pass

    # ── 子类必须实现 ──

    @abstractmethod
    def get_name(self) -> str:
        """任务名称"""

    @abstractmethod
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """
        获取原始数据。

        Args:
            full_sync: 是否全量同步
            targets: 目标代码列表（由 Orchestrator 注入）
        """

    @abstractmethod
    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """校验并清洗数据"""

    @abstractmethod
    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """去重"""

    @abstractmethod
    def _save_data(self, new_data: List[dict]) -> None:
        """写入数据库并提交"""

    # ── 可选覆盖 ──

    @property
    def _allow_empty_data(self) -> bool:
        """是否允许数据源返回空（如非交易日）"""
        return False

    # ── 通用工具 ──

    def _deduplicate_by_unique_key(self, data: List[dict], model, unique_key: str) -> List[dict]:
        """根据单一唯一键去重"""
        if not data:
            return []
        col = getattr(model, unique_key)
        unique_values = [item[unique_key] for item in data]
        existing = {row[0] for row in self.db.query(col).filter(col.in_(unique_values)).all()}
        return [item for item in data if item[unique_key] not in existing]

    # ── 分批执行核心 ──

    def _execute_batches(self, targets: List[str]) -> int:
        """
        分批抓取、校验、去重、写入，返回成功写入的总记录数。
        """
        if not targets:
            return 0

        total_saved = 0
        for i in range(0, len(targets), self.batch_size):
            batch = targets[i : i + self.batch_size]
            self.logger.info(f'进度: {min(i + self.batch_size, len(targets))}/{len(targets)}')

            # 1. 抓取
            batch_data = self._fetch_data(self._full_sync_flag, batch)

            # 2. 校验
            validated = self._validate_data(batch_data)

            # 3. 去重
            new_data = self._deduplicate(validated)
            self.stats['skipped'] += len(validated) - len(new_data)

            # 4. 写入
            if new_data:
                self._save_data(new_data)
                self.stats['success'] += len(new_data)
                total_saved += len(new_data)

        return total_saved

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()

        while self.status in (JobStatus.PENDING, JobStatus.FAILED, JobStatus.RETRYING):
            try:
                self.status = JobStatus.RUNNING
                self.logger.info(f'开始执行 (全量={full_sync}, 目标数={len(targets) if targets else "全部"})')

                if targets is None:
                    # 无外部目标列表：子类自己获取全部数据（适用于全量列表 Job）
                    raw_data = self._fetch_data(full_sync, [])
                    if not raw_data:
                        if self._allow_empty_data:
                            self.logger.info('数据源返回空数据（已允许），跳过同步')
                            self.status = JobStatus.SUCCESS
                            break
                        else:
                            raise SBException(
                                code=ErrorCode.DATA_SOURCE_ERROR.code,
                                message=f'数据源返回空数据: {self.get_name()}',
                                status_code=503,
                            )
                    validated = self._validate_data(raw_data)
                    new_data = self._deduplicate(validated)
                    self.stats['total'] = len(raw_data)
                    self.stats['skipped'] = len(validated) - len(new_data)
                    if new_data:
                        self._save_data(new_data)
                        self.stats['success'] = len(new_data)
                    self.status = JobStatus.SUCCESS
                    break

                # 有外部目标列表：走分批执行流程
                if len(targets) == 0:
                    if self._allow_empty_data:
                        self.logger.info('目标列表为空，跳过同步')
                        self.status = JobStatus.SUCCESS
                        break
                    else:
                        raise SBException(
                            code=ErrorCode.DATA_SOURCE_ERROR.code,
                            message=f'目标列表为空: {self.get_name()}',
                            status_code=503,
                        )

                self.stats['total'] = len(targets)
                self._execute_batches(targets)
                self.status = JobStatus.SUCCESS
                break

            except SBException as e:
                self.status = JobStatus.FAILED
                self.stats['error'] = e.message
                self.logger.error(f'业务异常: {e.message}')
                break

            except Exception as e:
                self.retry_count += 1
                if self.retry_count < MAX_RETRIES:
                    self.status = JobStatus.RETRYING
                    wait = 2**self.retry_count
                    self.logger.warning(f'临时失败，{wait}s 后重试 ({self.retry_count}/{MAX_RETRIES}): {e}')
                    time.sleep(wait)
                else:
                    self.status = JobStatus.MANUAL_INTERVENTION
                    self.stats['error'] = str(e)
                    self.logger.error('超过最大重试次数，需人工介入')
                    break

        return self._build_result()

    def _build_result(self) -> Dict[str, Any]:
        return {
            'job_name': self.get_name(),
            'status': self.status.value,
            'stats': self.stats,
            'retry_count': self.retry_count,
        }
