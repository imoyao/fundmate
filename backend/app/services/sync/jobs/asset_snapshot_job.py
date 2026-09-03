# app/services/sync/jobs/asset_snapshot_job.py
"""资产快照每日落账任务（#1182）。

封装 summary_service.write_asset_snapshot，遍历全部 family 幂等 upsert 当日快照
（含 #863 P1-5 货基每日收益 money_fund_income_cents）。

无外部数据源，用 NullAdapter 占位（与 temperature / amac_institution 一致）。
失败告警经 Orchestrator._save_sync_log 写入 SyncLog；单 job 异常不中断 run_all_jobs
（Orchestrator._execute_job 已捕获并继续下一个 job）。

注意：本 Job 在 Orchestrator 的会话（run_all_jobs 用 get_db()）中运行，读写同库。
单库开发态下 user 域（持仓/交易/账户）与 market 域（货基净值）同库，无跨域问题；
双库生产态下若 user/market 拆分，需在部署侧保证快照写入指向正确的会话（已知限制，见 #1182）。
"""

from typing import Any, Dict, List, Optional

from app.core.time_utils import now_shanghai
from app.services.summary_service import write_asset_snapshot
from app.services.sync.adapters.null_adapter import NullAdapter
from app.services.sync.jobs.base import JobStatus, SyncJob


class AssetSnapshotJob(SyncJob):
    """资产快照每日落账（家庭/账户两级）"""

    def __init__(self, db):
        # 无外部数据源，NullAdapter 占位
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'asset_snapshot'

    # run() 已重写，以下抽象方法仅满足 ABC 要求、运行期不被调用
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return raw_data

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return data

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    def _family_ids(self) -> List[int]:
        """枚举全部 family_id（从 user 域 Ledger 表去重）。"""
        from app.domains.ledgers.models import Ledger

        rows = self.db.query(Ledger.family_id).distinct().all()
        return sorted({r[0] for r in rows if r[0] is not None})

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self._full_sync_flag = full_sync
        self.snapshot_time = now_shanghai()
        self.logger.info('开始资产快照每日落账')
        family_ids = self._family_ids()
        total = len(family_ids)
        written = 0
        failed = 0
        errors: List[str] = []
        for fid in family_ids:
            try:
                # write_asset_snapshot 内部已幂等 upsert + commit；逐 family 落账
                write_asset_snapshot(self.db, family_id=fid)
                written += 1
            except Exception as e:  # noqa: BLE001
                # 单家庭失败不中断其余家庭：记录失败数，回滚本家庭未提交事务后继续
                failed += 1
                errors.append(f'family_id={fid}: {e}')
                self.logger.exception(f'资产快照落账失败（family_id={fid}）: {e}')
                self.db.rollback()
        self.status = JobStatus.SUCCESS if failed == 0 else JobStatus.FAILED
        self.stats = {
            'total': total,
            'success': written,
            'skipped': 0,
            'failed': failed,
            'errors': errors,
        }
        self.logger.info(f'资产快照落账完成，覆盖 {written}/{total} 个家庭，失败 {failed}')
        return self._build_result()
