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
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

# 项目根目录：从 app 包的物理路径推导
import app
from app.core.config import SYNC__FUND_LIST_SOURCE
from app.core.database import SQLALCHEMY_DATABASE_URL as DB_URL

# 文件锁实现已抽到 core（#1467）：进程内每日调度器与应用启动路径都要用它，
# 留在本模块会让它们为了借锁而连带加载 akshare。此处保留同名导入以兼容既有
# 调用方与测试的 monkeypatch 目标（`app.services.sync.orchestrator.acquire_lock`）。
from app.core.file_lock import acquire_lock
from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.models.sync_log import SyncLog
from app.services.sync.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.adapters.eastmoney_adapter import EastmoneyAdapter
from app.services.sync.adapters.jiucaishuo_adapter import JiucaishuoAdapter
from app.services.sync.adapters.null_adapter import NullAdapter
from app.services.sync.adapters.tiantian_advisor_adapter import TiantianAdvisorAdapter
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter
from app.services.sync.jobs.advisor_portfolio_job import AdvisorPortfolioSyncJob
from app.services.sync.jobs.amac_institution_job import AmacInstitutionJob
from app.services.sync.jobs.asset_snapshot_job import AssetSnapshotJob
from app.services.sync.jobs.channel_link_job import ChannelLinkSyncJob
from app.services.sync.jobs.convertible_bond_job import ConvertibleBondSyncJob
from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob
from app.services.sync.jobs.fund_company_backfill_job import FundCompanyBackfillJob
from app.services.sync.jobs.fund_detail_enrich_job import FundDetailEnrichJob
from app.services.sync.jobs.fund_list_job import FundListSyncJob
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob
from app.services.sync.jobs.fund_nav_job import FundNavSyncJob
from app.services.sync.jobs.fund_position_job import FundPositionSyncJob
from app.services.sync.jobs.fund_scale_job import FundScaleSyncJob
from app.services.sync.jobs.fund_type_job import FundTypeSyncJob
from app.services.sync.jobs.index_catalog_job import IndexCatalogSyncJob
from app.services.sync.jobs.index_constituent_job import INDEX_TARGETS, IndexConstituentSyncJob
from app.services.sync.jobs.index_daily_job import IndexDailySyncJob
from app.services.sync.jobs.index_valuation_job import IndexValuationSyncJob
from app.services.sync.jobs.market_snapshot_job import MarketSnapshotSyncJob
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob
from app.services.sync.jobs.stock_list_job import StockListSyncJob
from app.services.thermometer.jobs import TemperatureJob

BASE_DIR = Path(app.__path__[0]).parent


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
        # 消费导入侧观察值（user 域 fund_company_observations）补 funds.company_id：
        # 纯本地解析、不联网，故 NullAdapter 占位（同 amac_institution 的处理）。
        self.jobs['fund_company_backfill'] = FundCompanyBackfillJob(NullAdapter(), self.db)
        self.jobs['fund_scale'] = FundScaleSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_position'] = FundPositionSyncJob(self.data_sources['akshare'], self.db)
        self.jobs['fund_type'] = FundTypeSyncJob(self.data_sources['akshare'], self.db)
        # 投顾组合数据源独立于 akshare/xalpha（天天基金公开接口，自带节流）
        self.jobs['advisor_portfolio'] = AdvisorPortfolioSyncJob(TiantianAdvisorAdapter(), self.db)
        self.jobs['fund_nav'] = FundNavSyncJob(self.data_sources['xalpha'], self.db)
        self.jobs['price_history'] = PriceHistorySyncJob(self.data_sources['akshare'], self.db)
        self.jobs['index_constituents'] = IndexConstituentSyncJob(self.data_sources['akshare'], self.db)
        # #1285/#1394：指数估值（中证官方：市盈率 / 股息率）
        self.jobs['index_valuation'] = IndexValuationSyncJob(self.data_sources['akshare'], self.db)
        # #1285 §3.8：跨渠道关联（指数↔ETF，主流宽基白名单）
        self.jobs['channel_link'] = ChannelLinkSyncJob(self.data_sources['akshare'], self.db)
        # #1285/#1393：可转债条款（强赎状态 + 静态条款，akshare 集思录）
        self.jobs['convertible_bond'] = ConvertibleBondSyncJob(self.data_sources['akshare'], self.db)
        # #1286：指数名录（聚合搜索可搜索的指数条目，与成分互补）
        self.jobs['index_catalog'] = IndexCatalogSyncJob(self.data_sources['akshare'], self.db)
        # #275：指数日线点位（万得全A 经韭圈儿公开接口，独立数据源）
        self.jobs['index_daily'] = IndexDailySyncJob(JiucaishuoAdapter(), self.db)
        self.jobs['temperature'] = TemperatureJob(NullAdapter(), self.db)
        # AMAC 名录为 HTTP JSON 直抓（非 akshare/xalpha 数据源），NullAdapter 占位；
        # 此前仅 invoke grab.* 通道可达，注册后 pdm run sync --job 亦可直达（#1081 策展应用入口）
        self.jobs['amac_institution'] = AmacInstitutionJob(NullAdapter(), self.db)
        # #1179：分红 / 送股自动抓取（akshare），落库复用 ImportOrchestrator 路径
        self.jobs['dividend_split'] = DividendSplitSyncJob(self.data_sources['akshare'], self.db)
        # #1182：资产快照每日落账（家庭/账户两级，含货基每日收益），无外部数据源
        self.jobs['asset_snapshot'] = AssetSnapshotJob(self.db)
        # #1460：探市 20 大类资产每日快照落库（只落算好的结果，不落收盘序列），
        # 供 /api/market/overview 读库；无外部适配器，取数在 market_service 内直连 akshare
        self.jobs['market_snapshot'] = MarketSnapshotSyncJob(self.db)

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
            # 异常路径同样落一条审计行（#1402）。
            # run_job 只在 job.run **正常返回**之后才调 _save_sync_log；一旦抛异常，
            # sync_logs 全链路无记录，「某 job 到底跑没跑过、失败在哪一步」无法回答。
            self._save_error_sync_log(job_name, full_sync, e)
            return {'job_name': job_name, 'status': 'error', 'error': str(e)}

    def run_all_jobs(self, full_sync: bool = False, target_file: Optional[str] = None) -> Dict[str, Any]:
        """
        按依赖顺序执行所有同步任务（顺序见下方 `execution_plan`）。

        计划内的每一项都必须是在 `_register_jobs()` 里注册过的 job —— 「注册了却不在计划里」
        会让 `grab.all` 静默漏跑（#1460 修复：`temperature` / `index_valuation` /
        `convertible_bond` / `amac_institution` / `channel_link` 5 个此前从未进过计划）。
        `tests/services/sync/test_orchestrator.py` 有断言钉死这一不变量。

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
                # #1286 数据底座：拆成两条成本量级不同的链路（原 fund_meta 一条全干，见 #1403）
                #   fund_scale —— 单次 HTTP 返回全市场列表，§4.3.3 允许全量
                #   fund_position —— 逐只 HTTP（≈1.8s/只），§4.3.3 强制按目标池限量
                ('fund_scale', ['__full__']),
                ('fund_position', fund_targets),  # 空 targets 显式跳过，不退化为全库
                ('fund_manager', fund_targets),  # 回填基金经理并关联基金公司（核心池）
                # 导入侧观察值 → funds.company_id（不联网、幂等、只填空缺）：
                # 紧跟基金公司相关任务，且 funds 已由 fund_list 建好
                ('fund_company_backfill', []),
                ('fund_nav', fund_targets),  # 净值增量同步（核心池）
                ('price_history', stock_targets),  # 行情增量同步（核心池）
                ('index_constituents', INDEX_TARGETS),  # 指数成分回填（#1286 数据底座）
                ('index_catalog', ['__full__']),  # 指数名录重建（#1286 聚合搜索底座）
                ('index_daily', ['__full__']),  # 指数日线（万得全A 全量 10 年，#275）
                # #1460：探市 20 大类资产快照落库（只落算好的结果，不落收盘序列）。
                # 不依赖净值/行情，放在这里即可；页面读取只认「库里有今天的行」。
                ('market_snapshot', None),
                ('dividend_split', stock_targets + fund_targets),  # 分红/送股抓取（#1179）
                ('advisor_portfolio', ['__full__']),  # 投顾组合持仓/调仓回填（#1167，组合数少且自带节流）
                # ── 以下 5 个此前**注册了却从未进过本计划**（#1460 顺带修复）──
                # 后果：`grab.all` / `pdm run sync --all` / CI 的 `pdm run scheduler` 都
                # 不刷新温度计（连带 bias 乖离率、industry_crowding 拥挤度——它们跑在
                # TemperatureJob 内部），也不刷新可转债条款、指数估值、AMAC 主数据、
                # 跨渠道关联；而 backend/tasks.py 与 tools/sync_cli.py 的文案都写着
                # 「全部同步任务（元数据 + 温度）」，文案与实现不一致。
                #
                # ⚠️ 这 5 个一律传 `None`（不是 `[]`、也不是 `['__full__']`）：
                #   - `[]` 会被基类 `SyncJob.run()` 当成「空目标池」→ 直接跳过（这些 job
                #     的 `_allow_empty_data=True`），**静默空跑**；
                #   - `['__full__']` 只对显式过滤该哨兵值的 job 安全。`IndexValuationSyncJob`
                #     是 `codes = targets if targets else INDEX_VALUATION_TARGETS`，传
                #     `['__full__']` 会真去抓一个字面代码 `'__full__'`；
                #   - `None` 才会走基类的「无外部目标列表」分支，调 `_fetch_data()` 抓自身全量。
                #
                # 本次只修「漏」，不重构分组：按频率拆「每日/每周/每月/每季」会改变
                # 「全量同步」的语义、需同步改文案，见 data-refresh-scheduling-plan
                # §8-D2 与 §10-PR3，单独 PR 处理。
                ('temperature', None),  # 温度计（含乖离率 / 拥挤度）+ 顺带清理 1 年前的多维列表
                ('convertible_bond', None),  # 可转债条款（东财 + 集思录双源合并）
                ('index_valuation', None),  # 指数估值（中证官方，12 指数 ≈2 分钟）
                ('channel_link', None),  # 跨渠道关联（指数↔ETF，台账建议每月）
                ('amac_institution', None),  # AMAC 基金管理人主数据（台账建议每季）
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

    def _save_error_sync_log(self, job_name: str, full_sync: bool, error: Exception) -> None:
        """异常路径的审计落库（#1402）。

        与 `_save_sync_log` 的关键差别：本方法必须在「job 没跑完」时也安全，因此
        全程防御式取值：

        - `job.snapshot_time` 可能仍是 `None`（未进入 `run()` 就炸），而 `started_at`
          列是 NOT NULL，照抄 `_save_sync_log` 会再抛一次；
        - `self.jobs[job_name]` 可能根本不存在（`run_job` 对未知任务名抛 ValueError），
          用下标访问会把原始异常替换成 KeyError；
        - 审计写入本身失败绝不能向上抛——本方法存在的意义是「让失败可见」，
          若它自己炸掉，调用方正在冒泡的原始异常就被掩盖了。
        """
        job = self.jobs.get(job_name)
        now = now_shanghai()
        started_at = getattr(job, 'snapshot_time', None) or now
        try:
            log_entry = SyncLog(
                job_name=job_name,
                status='error',
                full_sync=full_sync,
                stats=None,
                error_detail=str(error),
                data_source=(job.adapter.get_name() if job is not None else None),
                data_source_version=(job.adapter.get_version() if job is not None else None),
                started_at=started_at,
                finished_at=now,
                duration_seconds=(now - started_at).total_seconds(),
            )
            self.db.add(log_entry)
            self.db.commit()
            logger.info(f'已为异常任务 {job_name} 写入 sync_logs（status=error）')
        except Exception:
            # 回滚并把自身异常降级为日志，保住调用方正在冒泡的原始异常
            self.db.rollback()
            logger.exception(f'写入 {job_name} 失败审计日志时出错（已忽略，不影响主流程）')
