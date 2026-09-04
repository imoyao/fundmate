# app/services/sync/orchestrator.py
"""
元数据同步调度器。

职责：
- 注册和管理所有 SyncJob 实例
- 解析同步目标代码列表（CSV / 持仓+自选 / 全量）
- 按依赖顺序执行多个 Job
- 同步前自动备份数据库
- 记录审计日志
"""

import csv
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

# 项目根目录：从 app 包的物理路径推导
import app
from app.core.config import SYNC__FUND_LIST_SOURCE
from app.core.database import SQLALCHEMY_DATABASE_URL as DB_URL
from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.models.sync_log import SyncLog
from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.eastmoney_adapter import EastmoneyAdapter
from app.services.sync.adapters.null_adapter import NullAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter
from app.services.sync.jobs.amac_institution_job import AmacInstitutionJob
from app.services.sync.jobs.asset_snapshot_job import AssetSnapshotJob
from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob
from app.services.sync.jobs.fund_detail_enrich_job import FundDetailEnrichJob
from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.fund_type_job import FundTypeSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob
from app.services.thermometer.jobs import TemperatureJob

BASE_DIR = Path(app.__path__[0]).parent


# ============================================================
# 跨平台原子文件锁
# ============================================================


def acquire_lock(lock_file: Path) -> tuple:
    """
    尝试获取原子文件锁。

    返回:
        (成功标志, 文件描述符)。
        如果获取失败，返回 (False, None)。
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


# ============================================================
# 调度器主体
# ============================================================


class DataSyncOrchestrator:
    """
    元数据同步调度器。

    用法:
        with get_db() as db:
            orch = DataSyncOrchestrator(db)
            orch.run_all_jobs(full_sync=False)
    """

    def __init__(self, db: Session):
        self.db = db
        self.data_sources: Dict[str, Any] = {}
        self.jobs: Dict[str, Any] = {}
        self._register_data_sources()
        self._register_jobs()

    # ── 初始化 ──

    def _register_data_sources(self) -> None:
        """注册数据源适配器（硬编码，避免过度配置）"""
        self.data_sources['xalpha'] = XalphaAdapter()
        self.data_sources['akshare'] = AkshareAdapter()
        # #1168：天天基金/东财一等数据源（组合 akshare + xalpha）
        self.data_sources['eastmoney'] = EastmoneyAdapter()

    def _register_jobs(self) -> None:
        """注册所有同步任务，明确指定每个 Job 使用的数据源"""
        self.jobs['stock_list'] = StockListSyncJob(self.data_sources['akshare'], self.db)
        # #1168：fund_list 选源可配置（默认 eastmoney），其余 Job 不变
        fund_list_src = SYNC__FUND_LIST_SOURCE
        if fund_list_src not in self.data_sources:
            logger.warning(f'配置的数据源 {fund_list_src} 未注册，回退 akshare')
            fund_list_src = 'akshare'
        self.jobs['fund_list'] = FundListSyncJob(self.data_sources[fund_list_src], self.db)
        # FundDetailEnrichJob 需要两个适配器：akshare 获取详情，xalpha 获取费率
        self.jobs['fund_detail_enrich'] = FundDetailEnrichJob(
            self.data_sources['akshare'], self.data_sources['xalpha'], self.db
        )
        self.jobs['fund_manager'] = FundManagerSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_type'] = FundTypeSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_nav'] = FundNavSyncJob(self.data_sources['xalpha'], self.db)
        self.jobs['price_history'] = PriceHistorySyncJob(self.data_sources['akshare'], self.db)
        self.jobs['temperature'] = TemperatureJob(NullAdapter(), self.db)
        # AMAC 名录为 HTTP JSON 直抓（非 akshare/xalpha 数据源），NullAdapter 占位；
        # 此前仅 invoke grab.* 通道可达，注册后 pdm run sync --job 亦可直达（#1081 策展应用入口）
        self.jobs['amac_institution'] = AmacInstitutionJob(NullAdapter(), self.db)
        # #1179：分红 / 送股自动抓取（akshare），落库复用 ImportOrchestrator 路径
        self.jobs['dividend_split'] = DividendSplitSyncJob(self.data_sources['akshare'], self.db)
        # #1182：资产快照每日落账（家庭/账户两级，含货基每日收益），无外部数据源
        self.jobs['asset_snapshot'] = AssetSnapshotJob(self.db)

    # ── 目标代码解析 ──

    def resolve_targets(self, target_file: Optional[str] = None) -> Dict[str, List[str]]:
        """
        解析本次同步的目标代码列表，按类型分为 'fund' 和 'stock'。

        优先级:
            1. 命令行传入的 --target-file CSV 文件
            2. 数据库中的持仓 + 自选标的
            3. 空列表（增量同步在无持仓时会跳过）

        Returns:
            {"fund": [...], "stock": [...]}
        """
        if target_file:
            codes = self._load_codes_from_csv(target_file)
        else:
            codes = self._load_codes_from_database()

        # 按类型分类：6 位纯数字为基金代码，其余为股票代码
        fund_codes = [c for c in codes if c.isdigit() and len(c) == 6]
        stock_codes = [c for c in codes if not (c.isdigit() and len(c) == 6)]
        return {'fund': fund_codes, 'stock': stock_codes}

    def _load_codes_from_csv(self, filepath: str) -> List[str]:
        """
        从 CSV 文件读取目标代码列表。

        CSV 格式要求:
            - 每行一个代码，第一列有效
            - 支持表头行（自动跳过 "code", "代码", "symbol"）
            - 使用 utf-8-sig 编码，兼容 Excel 导出的 BOM 头
        """
        codes = list()
        with open(filepath, encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                code = row[0].strip().strip('"')
                if not code:
                    continue
                # 跳过表头行
                if code in ('code', '代码', 'symbol'):
                    continue
                codes.append(code)
        logger.info(f'从 CSV 文件读取到 {len(codes)} 个代码')
        return codes

    def _load_codes_from_database(self) -> List[str]:
        """
        从数据库的持仓表和自选表中提取所有需要同步的代码。
        合并去重后返回。

        数据来源:
            - positions 表：用户实际持有的基金/股票
            - watchlist_items 表：用户关注但未持有的标的
        """

        codes = set()

        # 持仓标的
        positions = self.db.query(Position.symbol).distinct().all()
        for (symbol,) in positions:
            if symbol:
                codes.add(symbol)

        # 自选标的
        watchlist = self.db.query(WatchlistItem.symbol).distinct().all()
        for (symbol,) in watchlist:
            if symbol:
                codes.add(symbol)

        logger.info(f'从数据库提取到 {len(codes)} 个目标代码')
        return list(codes)

    # ── 数据库备份 ──

    def _backup_database(self) -> None:
        """
        同步前自动备份数据库。
        根据 DB_URL 自动选择备份方式：
            - SQLite: 复制 .db 文件
            - PostgreSQL: 调用 pg_dump
            - MySQL: 调用 mysqldump
        备份保留最近 7 个。
        """
        backup_dir = BASE_DIR / 'data' / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now_shanghai().strftime('%Y%m%d_%H%M%S')
        db_url = DB_URL

        if db_url.startswith('sqlite'):
            self._backup_sqlite(db_url, backup_dir, timestamp)
        elif db_url.startswith('postgresql'):
            self._backup_postgresql(db_url, backup_dir, timestamp)
        elif db_url.startswith('mysql'):
            self._backup_mysql(db_url, backup_dir, timestamp)
        else:
            logger.warning(f'不支持的数据库类型，跳过备份: {db_url.split(":")[0]}')

    def _backup_sqlite(self, db_url: str, backup_dir: Path, timestamp: str) -> None:
        """SQLite 文件级备份"""
        # 去掉 "sqlite:///" 前缀，得到文件路径
        if db_url.startswith('sqlite:///'):
            db_path = Path(db_url[10:])
            if not db_path.is_absolute():
                db_path = BASE_DIR / db_path
        else:
            db_path = Path(db_url)

        if not db_path.exists():
            logger.warning(f'SQLite 数据库文件不存在: {db_path}')
            return

        backup_path = backup_dir / f'showbuy_backup_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        logger.info(f'SQLite 备份完成: {backup_path}')
        self._rotate_backups(backup_dir, 'showbuy_backup_*.db')

    def _backup_postgresql(self, db_url: str, backup_dir: Path, timestamp: str) -> None:
        """PostgreSQL 逻辑备份"""
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

    def _backup_mysql(self, db_url: str, backup_dir: Path, timestamp: str) -> None:
        """MySQL 逻辑备份"""
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
    def _rotate_backups(backup_dir: Path, pattern: str, keep: int = 7) -> None:
        """清理旧备份，只保留最近 keep 个"""
        backups = sorted(backup_dir.glob(pattern))
        for old in backups[:-keep]:
            old.unlink()

    # ── Job 执行 ──

    def run_job(self, job_name: str, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        执行单个同步任务。

        Args:
            job_name: 任务名（如 'fund_nav'）
            full_sync: 是否全量同步
            targets: 目标代码列表（可选，用于分层同步）

        Returns:
            包含 status 和 stats 的结果字典
        """
        if job_name not in self.jobs:
            raise ValueError(f'未知任务: {job_name}')

        job = self.jobs[job_name]
        logger.info(f'开始执行 {job_name} (全量={full_sync}, 目标数={len(targets) if targets else "全部"})')

        # 注入目标代码列表
        if targets:
            job.target_file_codes = targets

        result = job.run(full_sync, targets=targets)
        result['duration'] = (now_shanghai() - job.snapshot_time).total_seconds()
        self._save_sync_log(job_name, result, full_sync)
        return result

    def _execute_job(self, job_name: str, full_sync: bool, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        执行单个 Job 并处理异常。
        单个 Job 失败不中断后续 Job。

        Returns:
            结果字典。如果失败，status 为 'error'。
        """
        try:
            result = self.run_job(job_name, full_sync, targets=targets)
            if result['status'] != 'success':
                logger.error(f'任务 {job_name} 失败（状态：{result["status"]}），继续执行下一个任务')
            else:
                logger.info(f'任务 {job_name} 完成')
            return result
        except Exception as e:
            logger.exception(f'任务 {job_name} 异常: {e}，继续执行下一个任务')
            return {'job_name': job_name, 'status': 'error', 'error': str(e)}

    def run_all_jobs(self, full_sync: bool = False, target_file: Optional[str] = None) -> Dict[str, Any]:
        """
        按依赖顺序执行所有同步任务。

        执行顺序:
            stock_list → fund_list → fund_detail_enrich → fund_nav → price_history

        单实例锁保证同时只有一个同步进程运行。
        """
        lock_file = BASE_DIR / 'data' / 'sync.lock'
        locked, fd = acquire_lock(lock_file)
        if not locked:
            raise RuntimeError('另一个同步进程正在运行')

        try:
            self._backup_database()

            # 解析目标代码列表
            targets = self.resolve_targets(target_file)
            fund_targets = targets.get('fund', [])
            stock_targets = targets.get('stock', [])

            # 执行顺序：列表类 Job 不需要目标列表，净值/行情需要
            execution_plan = [
                ('stock_list', ['__full__']),  # 全量刷新股票列表，不需要目标列表
                ('fund_list', ['__full__']),  # 全量刷新基金列表
                ('fund_detail_enrich', fund_targets),  # 补充基金详情（核心池）
                ('fund_type', fund_targets),  # 回填基金类型（核心池，#1155 根治项）
                ('fund_manager', fund_targets),  # 回填基金经理并关联基金公司（核心池）
                ('fund_nav', fund_targets),  # 净值增量同步（核心池）
                ('price_history', stock_targets),  # 行情增量同步（核心池）
                ('dividend_split', stock_targets + fund_targets),  # 分红/送股抓取（#1179）
                # #1182：资产快照落账放最后，确保前面的净值/行情已刷新，快照取到最新值
                ('asset_snapshot', []),
            ]

            results = {}
            for job_name, job_targets in execution_plan:
                if job_name in self.jobs:
                    results[job_name] = self._execute_job(job_name, full_sync, job_targets)
            return results
        finally:
            if fd is not None:
                os.close(fd)
            lock_file.unlink(missing_ok=True)

    # ── 审计日志 ──

    def _save_sync_log(self, job_name: str, result: Dict[str, Any], full_sync: bool) -> None:
        """将同步结果写入 sync_logs 表"""
        job = self.jobs[job_name]
        log_entry = SyncLog(
            job_name=job_name,
            status=result.get('status', 'unknown'),
            full_sync=full_sync,
            stats=str(result.get('stats', {})),
            error_detail=str(result.get('stats', {}).get('errors', [])),
            data_source=job.adapter.get_name(),
            data_source_version=job.adapter.get_version(),
            started_at=job.snapshot_time,
            finished_at=now_shanghai(),
            duration_seconds=result.get('duration', 0),
        )
        self.db.add(log_entry)
        self.db.commit()
