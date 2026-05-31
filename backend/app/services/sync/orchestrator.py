# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:26
# File : orchestrator.py
# -*- coding: utf-8 -*-
# app/services/sync/orchestrator.py
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

import app
from app.core.database import SQLALCHEMY_DATABASE_URL
from app.core.time_utils import now_shanghai
from app.models.sync_log import SyncLog
from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter
from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob

BASE_DIR = Path(app.__path__[0]).parent


def acquire_lock(lock_file: Path):
    """
    尝试获取原子文件锁。
    返回 (成功标志, 文件描述符或None)。
    """
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR)
        if sys.platform == 'win32':
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True, fd
    except (OSError, IOError):
        if 'fd' in locals():
            os.close(fd)
        return False, None


class DataSyncOrchestrator:
    def __init__(self, db: Session, target_file_codes: Optional[List[str]] = None):
        self.db = db
        self.data_sources = {}
        self.target_file_codes = target_file_codes
        self.jobs: Dict[str, Any] = {}
        self._register_data_sources()
        self._register_jobs()

    def _register_data_sources(self):
        self.data_sources['xalpha'] = XalphaAdapter()
        self.data_sources['akshare'] = AkshareAdapter()

    def _register_jobs(self):
        self.jobs['stock_list'] = StockListSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_list'] = FundListSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_manager'] = FundManagerSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_nav'] = FundNavSyncJob(self.data_sources['xalpha'], self.db)
        self.jobs['price_history'] = PriceHistorySyncJob(self.data_sources['akshare'], self.db)

    def _backup_database(self):
        """根据 DATABASE_URL 自动选择备份方式"""
        backup_dir = BASE_DIR / 'data/backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now_shanghai().strftime('%Y%m%d_%H%M%S')
        db_url = SQLALCHEMY_DATABASE_URL

        if db_url.startswith('sqlite'):
            self._backup_sqlite(db_url, backup_dir, timestamp)
        elif db_url.startswith('postgresql'):
            self._backup_postgresql(db_url, backup_dir, timestamp)
        elif db_url.startswith('mysql'):
            self._backup_mysql(db_url, backup_dir, timestamp)
        else:
            logger.warning(f"不支持的数据库类型，跳过备份: {db_url.split(':')[0]}")

    def _backup_sqlite(self, db_url, backup_dir, timestamp):
        # 提取文件路径 (去掉 sqlite:/// 前缀)
        if db_url.startswith('sqlite:///'):
            db_path = Path(db_url[10:])  # 使用 Path 自动处理分隔符
            if not db_path.is_absolute():
                db_path = BASE_DIR / db_path  # 相对路径转为绝对路径
        else:
            db_path = Path(db_url)

        if not db_path.exists():
            logger.warning(f'SQLite 数据库文件不存在: {db_path}')
            return

        backup_path = backup_dir / f'showbuy_backup_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        logger.info(f'SQLite 备份完成: {backup_path}')
        self._rotate_backups(backup_dir, 'showbuy_backup_*.db')

    def _backup_postgresql(self, db_url, backup_dir, timestamp):
        if not shutil.which('pg_dump'):
            logger.warning('pg_dump 未安装，跳过备份')
            return
        backup_path = backup_dir / f'showbuy_backup_{timestamp}.sql'
        try:
            subprocess.run(['pg_dump', db_url, '-f', str(backup_path)], check=True, capture_output=True, timeout=300)
            logger.info(f'PostgreSQL 备份完成: {backup_path}')
            self._rotate_backups(backup_dir, 'showbuy_backup_*.sql')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f'pg_dump 备份失败: {e}')

    def _backup_mysql(self, db_url, backup_dir, timestamp):
        if not shutil.which('mysqldump'):
            logger.warning('mysqldump 未安装，跳过备份')
            return
        backup_path = backup_dir / f'showbuy_backup_{timestamp}.sql'
        try:
            subprocess.run(
                ['mysqldump', f'--result-file={backup_path}', db_url], check=True, capture_output=True, timeout=300
            )
            logger.info(f'MySQL 备份完成: {backup_path}')
            self._rotate_backups(backup_dir, 'showbuy_backup_*.sql')
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f'mysqldump 备份失败: {e}')

    @staticmethod
    def _rotate_backups(backup_dir: Path, pattern: str, keep: int = 7):
        backups = sorted(backup_dir.glob(pattern))
        for old in backups[:-keep]:
            old.unlink()

    def _save_sync_log(self, job_name, result, full_sync):
        log_entry = SyncLog(
            job_name=job_name,
            status=result['status'],
            full_sync=full_sync,
            stats=str(result.get('stats', {})),
            error_detail=str(result.get('stats', {}).get('errors', [])),
            data_source=self.jobs[job_name].adapter.get_name(),
            data_source_version=self.jobs[job_name].adapter.get_version(),
            started_at=self.jobs[job_name].snapshot_time,
            finished_at=now_shanghai(),
            duration_seconds=result.get('duration', 0),
        )
        self.db.add(log_entry)
        self.db.commit()

    def _execute_job(self, job_name: str, full_sync: bool) -> Dict[str, Any]:
        """执行单个 Job，处理异常并返回结果字典"""
        try:
            result = self.run_job(job_name, full_sync)
            if result['status'] != 'success':
                logger.error(f"任务 {job_name} 失败（状态：{result['status']}），继续执行下一个任务")
            else:
                logger.info(f'任务 {job_name} 完成')
            return result
        except Exception as e:
            logger.exception(f'任务 {job_name} 异常: {e}，继续执行下一个任务')
            return {'job_name': job_name, 'status': 'error', 'error': str(e)}

    def run_all_jobs(self, full_sync: bool = False) -> Dict[str, Any]:
        lock_file = BASE_DIR / 'data/sync.lock'
        locked, fd = acquire_lock(lock_file)
        if not locked:
            raise RuntimeError('另一个同步进程正在运行')

        try:
            self._backup_database()

            order = ['stock_list', 'fund_list', 'fund_nav', 'price_history']
            results = {}
            for name in order:
                if name in self.jobs:
                    results[name] = self._execute_job(name, full_sync)
            return results
        finally:
            if fd is not None:
                os.close(fd)
            lock_file.unlink(missing_ok=True)

    def run_job(self, job_name: str, full_sync: bool = False) -> Dict[str, Any]:
        if job_name not in self.jobs:
            raise ValueError(f'未知任务: {job_name}')
        logger.info(f'开始执行 {job_name} (全量={full_sync})')

        job = self.jobs[job_name]
        # 注入从 CSV 文件读取的目标代码列表（如果存在）
        if self.target_file_codes and hasattr(job, 'target_file_codes'):
            job.target_file_codes = self.target_file_codes

        result = job.run(full_sync)
        result['duration'] = (now_shanghai() - job.snapshot_time).total_seconds()
        self._save_sync_log(job_name, result, full_sync)
        return result
