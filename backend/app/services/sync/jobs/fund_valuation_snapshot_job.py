# app/services/sync/jobs/fund_valuation_snapshot_job.py
"""
场外基金收盘估值定格（#2141）

收盘后按固定时点（daily_scheduler 的 cron `15 15,19,21 * * mon-fri`，
即工作日 15:15 / 19:15 / 21:15）抓取天天基金 `FundValuationLast` 估值
快照，落市场域 `fund_valuation_daily`，供收盘估值展示与收益日历
「今日预估」回退（`pnl_calendar`）。

设计要点（简报 §2）：
- 目标池 = `orchestrator.resolve_targets()`（持仓 ∪ 自选），空池 → 跳过，
  禁止静默全库（`_allow_empty_data=True` 兜底）。
- 仅场外基金入表：场内 ETF / 股票 / 转债按 venue 排除；QDII 等场外基金
  保留——估值源对 QDII 覆盖差，拉不到即缺行，诚实降级。
- 单源：天天基金。基类按 batch_size=50 切批，恰好对齐接口 FCODES 上限，
  一批一次 HTTP；单批失败记 warning、继续下一批，整 job 成功条件 =
  至少一批成功或目标池为空跳过。
- 幂等：按 (fund_code, est_date) INSERT OR REPLACE 覆盖——估值是时点数据，
  同一日多次重跑以后写入的时点为准（源端净值公布后即清空 GSZ）。
- GSZ 为空字符串/缺失的基金不写行（缺行即降级信号）。
- 休市判断在调度层：估值随行情走，`skip_non_trading_day` 统一跳过，
  本 job 不另判交易日。
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import List

import requests
from loguru import logger

from app.core.db_utils import bulk_upsert_replace
from app.core.exceptions import ErrorCode, SBException
from app.core.time_utils import now_shanghai
from app.core.venues import EXCHANGE, venue_of_row
from app.domains.funds.models import FundValuationDaily
from app.domains.positions.models import Position
from app.domains.watchlist.models import WatchlistItem
from app.services.job_base import IN_CHUNK_SIZE, SyncJob

# 天天基金实时估值接口（字段用法与前端 realtimeDataSources.ts 一带一致：
# GSZ 估算净值 / GSZZL 估算涨跌幅 / GZTIME 估值时间 / FCODE 基金代码 / PDATE 净值日期）
TIANTIAN_VALUATION_URL = 'https://fundcomapi.tiantianfunds.com/mm/newCore/FundValuationLast'
VALUATION_FIELDS = 'FCODE,SHORTNAME,GSZZL,GZTIME,GSZ,NAV,PDATE'
REQUEST_TIMEOUT = 30


class FundValuationSnapshotJob(SyncJob):
    """场外基金收盘估值定格（单源、多时点幂等覆盖）"""

    def get_name(self) -> str:
        return 'fund_valuation_snapshot'

    @property
    def _allow_empty_data(self) -> bool:
        return True  # 空池 / 源端无数据时正常跳过

    # ── 分批编排 ──

    def _execute_batches(self, targets: List[str]) -> int:
        # 整 job 成功条件（简报 §2）：至少一批成功。基类流程里每批的抓取
        # 异常已在 _fetch_data 内收敛为「空批 + errors 记录」，这里以
        # _any_batch_ok 判定——全部失败时抛业务异常，run() 直接置 FAILED
        # （不重试：单源瞬时失败由下一个 cron 时点自然补齐）。
        self._any_batch_ok = False
        total_saved = super()._execute_batches(targets)
        if targets and not self._any_batch_ok:
            raise SBException(
                code=ErrorCode.DATA_SOURCE_ERROR.code,
                message=f'全部批次估值抓取失败: {self.get_name()}',
                status_code=503,
            )
        return total_saved

    # ── 数据获取 ──

    def _filter_otc_funds(self, targets: List[str]) -> List[str]:
        """从目标池筛出场外基金：场内 ETF / 股票 / 转债排除。

        判据用 `venue_of_row`（显式声明 > 场内货基特例 > asset_type 缺省），
        场所信号来自持仓与自选两张表——目标池本来就由它们产生，
        查不到场所信息的裸码按「非场内」保留（估值源对非基金码自然缺行，
        由 _validate_data 的 GSZ 缺失检查兜底丢弃）。
        """
        if not targets:
            return []
        venue_map: dict = {}
        for i in range(0, len(targets), IN_CHUNK_SIZE):
            chunk = targets[i : i + IN_CHUNK_SIZE]
            for symbol, asset_type in (
                self.db.query(Position.symbol, Position.asset_type).filter(Position.symbol.in_(chunk)).all()
            ):
                venue_map[symbol] = venue_of_row(symbol, asset_type)
            for symbol, asset_type, venue in (
                self.db.query(WatchlistItem.symbol, WatchlistItem.asset_type, WatchlistItem.venue)
                .filter(WatchlistItem.symbol.in_(chunk))
                .all()
            ):
                venue_map[symbol] = venue_of_row(symbol, asset_type, venue)
        return [c for c in targets if venue_map.get(c) != EXCHANGE]

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """一批（基类已按 batch_size=50 切好）一次 HTTP 抓取。"""
        otc_codes = self._filter_otc_funds(targets)
        if not otc_codes:
            # 合法空批：本批无场外基金（如池内全是股票/ETF），不算失败
            self._any_batch_ok = True
            return []
        try:
            # requests_patch 已全局生效（TLS impersonate），不要自加 UA 硬修
            resp = requests.get(
                TIANTIAN_VALUATION_URL,
                params={'FCODES': ','.join(otc_codes), 'FIELDS': VALUATION_FIELDS},
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            self._any_batch_ok = True
            return payload.get('data') or []
        except Exception as e:
            # 单批失败：记 warning、继续下一批（对齐邻近 job 的容错惯例）
            logger.warning(f'估值批次抓取失败（{len(otc_codes)} 只）: {e}')
            self.stats.setdefault('errors', []).append({'batch_size': len(otc_codes), 'error': str(e)})
            return []

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """源端字段（FCODE/GSZ/GSZZL/GZTIME/PDATE）→ 落库形态。

        GSZ 为空字符串/缺失的基金不写行——净值公布后源端会清空估值，
        缺行即降级信号。PDATE 缺失/非法/未来日期同样跳过；GZTIME 原样
        存字符串（源端格式稳定且仅展示用，解析成 DateTime 无额外收益）。
        """
        validated: List[dict] = []
        seen: set = set()
        today = date.today()
        for item in raw_data:
            code = str(item.get('FCODE') or '').strip()
            if not code or code in seen:
                continue
            gsz = item.get('GSZ')
            if gsz is None or str(gsz).strip() == '':
                continue
            pdate = str(item.get('PDATE') or '').strip()
            if not pdate:
                continue
            try:
                est_date = date.fromisoformat(pdate)
            except ValueError:
                continue
            if est_date > today:
                continue  # 未来日期的估值尚未成立，不落库
            try:
                estimated_nav = Decimal(str(gsz).strip())
            except (InvalidOperation, ValueError):
                continue
            change_pct = None
            gszzl = item.get('GSZZL')
            if gszzl is not None and str(gszzl).strip() != '':
                try:
                    change_pct = Decimal(str(gszzl).strip())
                except (InvalidOperation, ValueError):
                    change_pct = None
            seen.add(code)
            validated.append(
                {
                    'fund_code': code,
                    'est_date': est_date,
                    'estimated_nav': estimated_nav,
                    'change_pct': change_pct,
                    'source_time': str(item.get('GZTIME') or '').strip() or None,
                    'source': 'tiantian_gsz',
                    'status': 'estimated',
                }
            )
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """不去重：写入层是 REPLACE 语义，重复键直接覆盖（幂等收敛）。"""
        return data

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """REPLACE 覆盖写入：同一 (fund_code, est_date) 以最后写入的时点为准。"""
        if not new_data:
            return
        now = now_shanghai()
        records = [
            {
                'fund_code': item['fund_code'],
                'est_date': item['est_date'],
                'estimated_nav': item['estimated_nav'],
                'change_pct': item['change_pct'],
                'source_time': item['source_time'],
                'source': item['source'],
                'status': item['status'],
                'created_at': now,
                'updated_at': now,
            }
            for item in new_data
        ]
        bulk_upsert_replace(self.db, FundValuationDaily, records, unique_columns=['fund_code', 'est_date'])
