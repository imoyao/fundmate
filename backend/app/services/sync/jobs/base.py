# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:25
# File : base.py
# -*- coding: utf-8 -*-
# app/services/sync/jobs/base.py

import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import now_shanghai

# 批次大小常量
BATCH_SIZE_FULL_SYNC = 50  # 全量同步每批处理标的数
BATCH_SIZE_DETAIL_ENRICH = 50  # 详情填充每批提交数
MAX_RETRIES = 3  # 最大重试次数
DEFAULT_INCREMENTAL_DAYS = 30  # 增量同步默认回溯天数


# 费率类型枚举
class FeeType:
    SUBSCRIBE = 'subscribe'  # 认购
    PURCHASE = 'purchase'  # 申购
    REDEEM = 'redeem'  # 赎回
    MANAGEMENT = 'management'  # 管理费


class JobStatus(Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCESS = 'success'
    FAILED = 'failed'
    RETRYING = 'retrying'
    MANUAL_INTERVENTION = 'manual_intervention'


class SyncJob(ABC):
    """元数据同步任务基类"""

    def __init__(self, adapter, db: Session):
        self._full_sync_flag = None
        self.adapter = adapter
        self.db = db
        self.logger = logger.bind(job=self.get_name())
        self.status = JobStatus.PENDING
        self.retry_count = 0
        self.max_retries = 3
        self.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
        # 增量同步基准时间（任务开始时拍快照）
        self.snapshot_time = None
        self.target_file_codes = None  # 用于 CSV 文件导入模式

    @property
    def _allow_empty_data(self) -> bool:
        """增量同步在非交易日或未添加标时返回空数据是正常的"""
        return False

    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def _fetch_data(self, full_sync: bool) -> List[dict]:
        """从数据源获取原始数据"""
        pass

    @abstractmethod
    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """数据校验与格式转换"""
        pass

    @abstractmethod
    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """去重：过滤已存在的记录"""
        pass

    @abstractmethod
    def _save_data(self, new_data: List[dict]) -> None:
        """批量写入数据库（单事务）"""
        pass

    def _validate_integrity(self) -> None:
        """完整性校验（子类可重写）"""
        pass

    def _pre_run(self) -> None:
        """前置钩子"""
        pass

    def _post_run(self) -> None:
        """后置钩子"""
        pass

    def _deduplicate_by_unique_key(self, data: List[dict], model, unique_key: str) -> List[dict]:
        """通用去重：根据唯一键过滤已存在的记录"""
        if not data:
            return []
        unique_values = [item[unique_key] for item in data]
        existing = set(
            row[0]
            for row in self.db.query(getattr(model, unique_key))
            .filter(getattr(model, unique_key).in_(unique_values))
            .all()
        )
        return [item for item in data if item[unique_key] not in existing]

    def _build_result(self) -> Dict[str, Any]:
        return {
            'job_name': self.get_name(),
            'status': self.status.value,
            'stats': self.stats,
            'retry_count': self.retry_count,
        }

    def run(self, full_sync: bool = False) -> Dict[str, Any]:
        """主执行循环，使用 while 状态机替代递归重试"""
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()

        while self.status in (JobStatus.PENDING, JobStatus.FAILED, JobStatus.RETRYING):
            try:
                self.status = JobStatus.RUNNING
                self._pre_run()
                self.logger.info(f'开始执行任务 {self.get_name()} (全量同步: {full_sync})')

                # 1. 获取数据
                raw_data = self._fetch_data(full_sync)
                if not raw_data:
                    if getattr(self, '_allow_empty_data', False):
                        self.logger.info('数据源返回空数据（已允许），跳过本次同步')
                        self.status = JobStatus.SUCCESS
                        break
                    else:
                        raise SBException(
                            code=ErrorCode.DATA_SOURCE_ERROR.code,
                            message=f'数据源返回空数据: {self.get_name()}',
                            status_code=503,
                        )
                self.stats['total'] = len(raw_data)

                # 2. 校验
                validated = self._validate_data(raw_data)

                # 3. 去重
                new_data = self._deduplicate(validated)
                self.stats['skipped'] = len(validated) - len(new_data)

                # 4. 保存
                if new_data:
                    self._save_data(new_data)
                    self.stats['success'] = len(new_data)
                else:
                    self.logger.info('无新数据需要保存')

                # 5. 完整性校验
                self._validate_integrity()

                self._post_run()
                self.status = JobStatus.SUCCESS
                self.logger.info(
                    f"任务 {self.get_name()} 执行成功: 总数={self.stats['total']}, "
                    f"新增={self.stats['success']}, 跳过={self.stats['skipped']}"
                )
                break  # 成功退出循环

            except SBException as e:
                self.status = JobStatus.FAILED
                self.stats['error'] = e.message
                self.logger.error(f'任务 {self.get_name()} 执行失败: {e.message}')
                break

            except Exception as e:
                self.retry_count += 1
                if self.retry_count < self.max_retries:
                    self.status = JobStatus.RETRYING
                    wait_time = 2**self.retry_count
                    self.logger.warning(
                        f'任务临时失败，{wait_time}秒后重试 (第{self.retry_count}/{self.max_retries}次): {e}'
                    )
                    time.sleep(wait_time)
                else:
                    self.status = JobStatus.MANUAL_INTERVENTION
                    self.stats['error'] = str(e)
                    self.logger.error(f'任务 {self.get_name()} 超过最大重试次数，需要人工介入')
                    break

        return self._build_result()
