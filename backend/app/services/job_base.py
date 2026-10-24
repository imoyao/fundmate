# app/services/job_base.py
"""
跨家族共享的同步任务基类 —— 重构版 v2.0

为什么在 services 顶层，而不是 `services/sync/jobs/`（#1607 批次 3）：
`SyncJob` / `JobStatus` 被 sync、thermometer、bias 三个 job 家族共用，原先"寄生"在 sync
家族包内，导致 thermometer / bias 反向 import `services.sync`——这是包级双向依赖的成因之一
（决策见 `docs/spec/decisions.md` 2026-09-19 D25；`architecture.md` §6「services 内部方向」）。
约定：**跨家族共享件放 `services/` 顶层，家族包内只留该家族独有实现**。

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
# in_ 查询分批大小：SQLite 变量上限防御（部分构建为 999）
IN_CHUNK_SIZE = 900


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

    def _decide_final_status(self) -> JobStatus:
        """终态判定：**每一个目标都失败、且一条都没写成功 ⇒ FAILED**，其余 SUCCESS（#2495）。

        为什么基类要兜这一层：逐标的 job 把单只异常收进 ``stats['errors']`` 后继续
        （一只坏不该拖垮整批，这是对的），但「全部目标都失败」意味着本轮**没有产出
        任何数据**。旧实现一律报 SUCCESS，于是 ``sync_logs.status`` 是绿的，而
        ``success=0 / failed=N`` 只落在另一个字段里——任何按 status 过滤的看板、
        降级与告警都读到假绿（#2495 实测形态）。

        判据为什么是「failed >= total」而不是「failed > 0」或「success == 0」：
        ``stats['success']`` 数的是**落库行数**，不是成功的目标数。分红/送转这类 job
        一个标的抓取成功也可能产出 0 行（确实没分红），只按 success==0 判会把它误判成
        故障（``test_dividend_split_job.py::test_partial_failure_stays_success_but_reports_counts``
        就是这个形态）。故这里用与量纲无关的「试过的目标全都失败」+
        「一条都没写成功」双条件：
        ``total`` 由 ``_count_total`` 给出（试过几个目标），``failed`` 由 errors 对齐，
        两者都不依赖单条 errors 的含义。

        三条刻意不动的语义：

        - **部分失败仍 SUCCESS**：30+ 个目标里偶发单点抖动是常态，「挂一个就红」
          会让红灯常态化，真故障反而被淹没（同族教训 #1179 / #171）。失败明细照旧
          落 ``stats['failed']`` 与 ``errors``，排查时看得见。
        - **``failed == 0`` 的「空」仍 SUCCESS**：那是「今天没有新数据 / 库内已最新 /
          停牌」的合法状态（非交易日等）。真正的「没拿到」由 ``_require_non_empty``
          或 ``errors`` 表达，不在这里猜。
        - **抓到数据但全被去重**：``success=0 / skipped>0 / failed=0``，不受本判据影响
          ——「一条都没新增」不等于「一条都没拿到」。

        子类知道自己分母的口径更细时仍可覆盖（现有：``index_daily``，它把源侧未收录的
        代码算进 ``total`` 却不记 failed，故按自己的「任何失败 + 零写入」判，见 #2475）。
        """
        failed = self.stats.get('failed', 0)
        total = self.stats.get('total', 0)
        if failed and failed >= total and not self.stats.get('success'):
            self.logger.error(f'{failed}/{total} 个目标全部失败，本次没有任何产出 ⇒ FAILED')
            return JobStatus.FAILED
        return JobStatus.SUCCESS

    def _failed_target_count(self) -> int:
        """失败目标数 = errors 条数（基类里 errors 只由子类 `_fetch_data` 写入）。"""
        return len(self.stats.get('errors') or [])

    def _count_total(self, targets: Optional[List[str]], fetched: int) -> int:
        """本轮「试过多少个目标」= `stats['total']` 的分母。

        为什么不能只数「拿到的」：``total`` 若只等于抓取结果条数，失败 / 跳过的目标
        就从分母里消失了 ——「32 个目标里挂 8 个、成功 24 个」会被记成
        total=24 / success=24，看板上是 100% 成功（#2475）。

        默认口径：有外部目标列表就数列表长度；自己取全量则 = 拿到 + 失败。
        子类知道得更多（占位符展开、抓取阶段主动跳过）时必须覆盖。
        """
        if targets is None:
            return fetched + self._failed_target_count()
        return self._count_targets(targets)

    def _count_targets(self, targets: List[str]) -> int:
        """外部目标列表的实际条数（默认即列表长度；支持占位符的子类须展开后再数）。"""
        return len(targets)

    # ── 通用工具 ──

    def _require_non_empty(self, rows: List[dict], *, source: str) -> List[dict]:
        """全市场列表类抓取：**0 条一律当上游异常**（抛错 ⇒ job 失败）。

        为什么需要它：这类 job 的目标是**全市场**（基金上万只、证券数千只），
        「一条都没抓到」只可能是上游结构变更 / 接口异常 / 解析失配，
        绝不可能是「今天没有数据」。

        旧行为是「空 ⇒ success」（``_allow_empty_data=True``），
        于是上游一坏，市场底座就静默停更、且日志一片绿——
        与 #1179（分红 job 把抓取失败吞成空列表）同族：
        **空 ≠ 没拿到**。

        注意区分：「今天没有**新**基金」是**去重之后**的概念（``skipped``），
        与这里的「抓取阶段一条都没有」不是一回事。
        """
        if rows:
            return rows
        raise SBException(
            code=ErrorCode.DATA_SOURCE_ERROR.code,
            message=f'{source} 返回空数据：全市场列表类 job 抓不到任何记录，判定为上游异常',
            status_code=503,
        )

    def _deduplicate_by_unique_key(self, data: List[dict], model, unique_key: str) -> List[dict]:
        """根据单一唯一键去重"""
        if not data:
            return []
        col = getattr(model, unique_key)
        unique_values = [item[unique_key] for item in data]
        existing: set = set()
        # 分批 in_ 查询：全量回填时唯一键可达数千上万（如经理 mgr_code），
        # 单条 in_ 超 SQLite 变量上限直接 OperationalError（#1286 实测踩坑）
        for i in range(0, len(unique_values), IN_CHUNK_SIZE):
            chunk = unique_values[i : i + IN_CHUNK_SIZE]
            existing.update(row[0] for row in self.db.query(col).filter(col.in_(chunk)).all())
        return [item for item in data if item[unique_key] not in existing]

    # ── 分批执行核心 ──

    def _safe_rollback(self) -> None:
        """把 Session 从「flush 失败后的 DEACTIVE」状态拉回来（#1550）。

        SQLAlchemy 在 flush 抛异常（如 UNIQUE 冲突）后会把 Session 标成必须先
        rollback，此后任何操作——包括重试、包括 orchestrator 写 sync_logs——
        都直接抛 PendingRollbackError。旧实现重试分支不 rollback，于是第二次、
        第三次尝试全部以 PendingRollbackError 收场：真实错误被掩盖、重试形同虚设，
        最终异常还会冒泡出去把审计落库一起带崩（sync_logs 全链路无痕）。

        本方法自身绝不向上抛：它出现的场合正是「已有异常待处理」。
        """
        try:
            self.db.rollback()
        except Exception as exc:  # noqa: BLE001 - rollback 失败不得取代原始异常
            self.logger.warning(f'Session rollback 失败（已忽略）: {exc}')

    def _execute_batches(self, targets: List[str]) -> int:
        """
        分批抓取、校验、去重、写入，返回成功写入的总记录数。
        """
        if not targets:
            return 0

        total_saved = 0
        phase_costs: Dict[str, float] = {}
        for i in range(0, len(targets), self.batch_size):
            batch = targets[i : i + self.batch_size]
            self.logger.info(f'进度: {min(i + self.batch_size, len(targets))}/{len(targets)}')

            # 1. 抓取
            started = time.perf_counter()
            batch_data = self._fetch_data(self._full_sync_flag, batch)
            phase_costs['抓取'] = phase_costs.get('抓取', 0.0) + (time.perf_counter() - started)

            # 2. 校验
            started = time.perf_counter()
            validated = self._validate_data(batch_data)
            phase_costs['校验'] = phase_costs.get('校验', 0.0) + (time.perf_counter() - started)

            # 3. 去重
            started = time.perf_counter()
            new_data = self._deduplicate(validated)
            phase_costs['去重'] = phase_costs.get('去重', 0.0) + (time.perf_counter() - started)
            self.stats['skipped'] += len(validated) - len(new_data)

            # 4. 写入
            if new_data:
                started = time.perf_counter()
                self._save_data(new_data)
                phase_costs['写库'] = phase_costs.get('写库', 0.0) + (time.perf_counter() - started)
                self.stats['success'] += len(new_data)
                total_saved += len(new_data)

        self._log_phase_costs(phase_costs)
        return total_saved

    def _log_phase_costs(self, costs: Dict[str, float]) -> None:
        """把各阶段累计耗时打成一行（#2522）。

        为什么必须显式打：瓶颈在**远端写库**（Turso/Hrana 逐行往返），
        本地 SQLite 上是毫秒级 ⇒ 本地测试永远看不到；而真机日志此前只有
        「进入 / 完成」两端，8407 行写 28 分钟、28149 只 52 分钟零输出，
        排查只能靠推断。有了这一行，下一次跑就能直接指出卡在抓取、去重还是写库。
        """
        if not costs:
            return
        text = ' / '.join(f'{name} {secs:.1f}s' for name, secs in costs.items())
        self.logger.info(f'阶段耗时：{text}')

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
                    # #2522：逐阶段计时。写库慢在本地 SQLite 上不可见（毫秒级），
                    # 真机日志此前只有「进入 / 完成」两端，8407 行写 28 分钟、
                    # 28149 只 52 分钟零输出，只能靠推断定位。
                    phase_costs: Dict[str, float] = {}
                    started = time.perf_counter()
                    raw_data = self._fetch_data(full_sync, [])
                    phase_costs['抓取'] = time.perf_counter() - started
                    if not raw_data:
                        self._log_phase_costs(phase_costs)
                        if self._allow_empty_data:
                            # 全挂也走这里：分母取「试过的目标数」，再由 `_decide_final_status`
                            # 决定这是「今天没数据」（errors 为空）还是「全都失败了」（#2475）
                            self.stats['total'] = self._count_total(None, 0)
                            self.logger.info('数据源返回空数据（已允许），跳过同步')
                            self.status = JobStatus.SUCCESS
                            break
                        else:
                            raise SBException(
                                code=ErrorCode.DATA_SOURCE_ERROR.code,
                                message=f'数据源返回空数据: {self.get_name()}',
                                status_code=503,
                            )
                    started = time.perf_counter()
                    validated = self._validate_data(raw_data)
                    phase_costs['校验'] = time.perf_counter() - started
                    started = time.perf_counter()
                    new_data = self._deduplicate(validated)
                    phase_costs['去重'] = time.perf_counter() - started
                    # total 必须含失败目标与主动跳过的目标：否则「32 个目标里 8 个没数据、
                    # 24 个成功」会被记成 total=24/success=24 —— 分母被吃掉，
                    # 看板上 100% 成功（#2475）
                    self.stats['total'] = self._count_total(None, len(raw_data))
                    self.stats['skipped'] = len(validated) - len(new_data)
                    if new_data:
                        started = time.perf_counter()
                        self._save_data(new_data)
                        phase_costs['写库'] = time.perf_counter() - started
                        self.stats['success'] = len(new_data)
                    self._log_phase_costs(phase_costs)
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

                self.stats['total'] = self._count_total(targets, 0)
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
                # #1550：必须先 rollback 再重试。否则 Session 停在 DEACTIVE，
                # 第 2/3 次尝试一定以 PendingRollbackError 失败（真实错误被掩盖），
                # 且这枚「中毒会话」会被 run_all_jobs 里后续 job 继续复用。
                self._safe_rollback()
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

        # failed 以 errors 为准：`_execute_batches` 只累加 success，failed 恒 0，
        # 于是「failed=0 但 errors 有 8 条」长期自相矛盾（#2475）。
        # 用 max 而非赋值：若某 job 自行维护 failed（逐记录失败，与目标数不同量纲），不得被抹掉。
        self.stats['failed'] = max(self.stats.get('failed', 0), self._failed_target_count())

        # 终态收敛：SUCCESS 只是基类默认值，子类可把「确实全挂」升级为 FAILED（#2475）。
        if self.status is JobStatus.SUCCESS:
            self.status = self._decide_final_status()

        if self.status is not JobStatus.SUCCESS:
            # 终态非成功：把 Session 交还给编排器时必须是干净的，
            # 否则 run_job 的审计落库与 run_all_jobs 的后续 job 会连带受害
            self._safe_rollback()

        return self._build_result()

    def _build_result(self) -> Dict[str, Any]:
        return {
            'job_name': self.get_name(),
            'status': self.status.value,
            'stats': self.stats,
            'retry_count': self.retry_count,
        }
