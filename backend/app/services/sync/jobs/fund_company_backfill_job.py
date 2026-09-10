# app/services/sync/jobs/fund_company_backfill_job.py
"""基金公司回填任务：消费导入侧观察值，回填 `funds.company_id`（不联网）。

## 为什么需要它

`funds.company_id` 覆盖率长期偏低（实测本库 3034/26938 ≈ 11%，由 `fund_list`/
`fund_detail_enrich` 按目标池增量填写），导致聚合页「基金管理人」大量为空。
基金 E 账户导出文件里的「基金管理人」是**中国结算给出的法人全称**，比我们自己的
任何来源都权威，是补这个覆盖率的最好材料。

## 为什么绕一道观察表

导入路径属 user 域（`position_import_meta` / `fund_company_observations`），
而 `funds` 属 market 域——双库部署下是两套独立引擎（AGENTS.md「数据域架构」）。
因此导入侧**只落观察值**，由本 Job 作为 market 域唯一消费者把它写进 `funds.company_id`，
保证该字段仍然只有一个写者，杜绝「导入写一遍、同步再写一遍」的来回写。

## 实现要点

- **不联网**：公司名 → 公司行的解析走 `company_resolver.get_or_create_fund_company`
  （本地归一化规则 + 东财公司名录内存缓存），不调 akshare / 东财接口，可离线重跑。
- **幂等**：只填空缺（`company_id IS NULL`）。已有公司归属的基金一律不动，
  既避免覆盖同步 job 的成果，也让本 Job 可以随便重跑。
- **跨域两步法**（AGENTS.md 规则 3）：先取键列表（user 域观察表），再用 `in_`
  批量查 `funds`（market 域）；不做跨域 SQL JOIN——双库下必然失败。
- **忽略 targets**：消费全量待补观察值（观察值规模由导入量决定，量级小），
  避免编排器传入的 `['__full__']` 之类哨兵值被误当基金代码过滤掉全部候选。
"""

from typing import Any, Dict, List

from sqlalchemy import func

from app.core.time_utils import now_shanghai
from app.domains.funds.models import Fund, FundCompany
from app.domains.positions.models import FundCompanyObservation
from app.services.sync.company_resolver import get_or_create_fund_company
from app.services.sync.jobs.base import IN_CHUNK_SIZE, JobStatus, SyncJob


class FundCompanyBackfillJob(SyncJob):
    def __init__(self, adapter, db):
        super().__init__(adapter, db)

    def get_name(self) -> str:
        return 'fund_company_backfill'

    # 以下四个方法是基类抽象方法的占位实现（本 Job 使用自定义 run 流程，同 FundDetailEnrichJob）
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return []

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return []

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: List[str] = None) -> Dict[str, Any]:
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.logger.info('开始回填基金公司（消费导入侧观察值）')
        self.stats = {
            'observations': 0,
            'filled': 0,
            'companies_created': 0,
            'skipped': 0,
            'errors': [],
        }

        try:
            observed = self._load_observations()
            self.stats['observations'] = len(observed)
            if not observed:
                self.logger.info('无待消费的导入侧观察值')
                return self._finish()

            # 公司名 → 公司行（唯一写入口，带缓存避免同一公司反复查库）
            companies_before = self._count_companies()
            name_to_id: Dict[str, int] = {}
            cache: Dict[str, int] = {}
            for name in dict.fromkeys(observed.values()):
                company_id = get_or_create_fund_company(self.db, name, cache=cache)
                if company_id:
                    name_to_id[name] = company_id
            self.db.flush()
            self.stats['companies_created'] = self._count_companies() - companies_before

            self._fill_funds(observed, name_to_id)
        except Exception as e:
            self.db.rollback()
            self.logger.exception(f'基金公司回填失败: {e}')
            self.stats['errors'].append({'error': str(e)})
            self.status = JobStatus.FAILED
            return self._build_result()

        return self._finish()

    def _finish(self) -> Dict[str, Any]:
        self._post_run()
        self.status = JobStatus.SUCCESS
        self.logger.info(
            f'基金公司回填完成: 观察值 {self.stats["observations"]}, 回填 {self.stats["filled"]}, '
            f'新建公司 {self.stats["companies_created"]}, 跳过 {self.stats["skipped"]}'
        )
        return self._build_result()

    # ── 数据读取与写入 ──

    def _load_observations(self) -> Dict[str, str]:
        """读取导入侧观察值（user 域）→ {fund_code: company_name}。

        同一 fund_code 有多条观察值时取 id 最大者（末次观察）；这一步只取键与名，
        不 join 任何 market 域表（跨域两步法的第一步）。
        """
        rows = (
            self.db.query(FundCompanyObservation.fund_code, FundCompanyObservation.company_name)
            .filter(FundCompanyObservation.company_name.isnot(None))
            .order_by(FundCompanyObservation.id)
            .all()
        )
        observed: Dict[str, str] = {}
        for code, name in rows:
            code = (code or '').strip()
            name = (name or '').strip()
            if code and name:
                observed[code] = name
        return observed

    def _fill_funds(self, observed: Dict[str, str], name_to_id: Dict[str, int]) -> None:
        """第二步：用 in_ 批量查 funds（market 域），只填空缺的公司归属。"""
        codes = list(observed)
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            chunk = codes[i : i + IN_CHUNK_SIZE]
            funds = self.db.query(Fund).filter(Fund.fund_code.in_(chunk), Fund.company_id.is_(None)).all()
            for fund in funds:
                company_id = name_to_id.get(observed.get(fund.fund_code, ''))
                if company_id:
                    fund.company_id = company_id
                    self.stats['filled'] += 1
                else:
                    self.stats['skipped'] += 1
            self.db.commit()
        # 观察值命中但库里无对应 fund 的（基金主数据缺失）单独计数，便于排查
        self.stats['skipped'] += max(len(observed) - self.stats['filled'] - self.stats['skipped'], 0)

    def _count_companies(self) -> int:
        return self.db.query(func.count(FundCompany.id)).scalar() or 0
