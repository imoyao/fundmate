# app/services/sync/jobs/dividend_split_job.py
"""
分红 / 送股自动抓取任务（#1179）。

数据源：akshare
- 股票：stock_dividend_cninfo（含送股/转增/派息比例与关键日期）
- 基金：fund_announcement_dividend_em（分红公告）

落库：把每只持仓标的最新的分红/送股事件转为 StandardTransactionRecord，
交给 ImportOrchestrator.commit —— 复用手动导入路径（#1213 的送股关联持仓、
import_hash 幂等去重、无持仓时孤儿降级）。
金额/份额按「当前持仓数量 × 比例」测算；找不到持仓则记事件（0 值），
由用户在前端认领补全。
"""

from decimal import Decimal
from typing import List, Optional

from app.core.money import Money
from app.core.symbol_utils import get_normalizer
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.importer.orchestrator import ImportOrchestrator
from app.services.importer.records import StandardTransactionRecord, compute_record_hash
from app.services.sync.jobs.base import SyncJob


class DividendSplitSyncJob(SyncJob):
    """分红 / 送股抓取与落库"""

    def get_name(self) -> str:
        return 'dividend_split'

    @property
    def _allow_empty_data(self) -> bool:
        return True

    # ── 工具 ──

    def _is_stock(self, code: str) -> bool:
        norm, mkt, _ = get_normalizer().normalize(code)
        if mkt:
            return mkt in ('CN_A', 'CN_B', 'CN_A_SH', 'CN_A_SZ', 'CN_B_SH', 'CN_B_SZ')
        return str(code).upper().startswith(('SH', 'SZ', 'BJ'))

    def _holding_shares(self, symbol: str) -> Decimal:
        try:
            rows = self.db.query(Position).filter_by(symbol=symbol, family_id=1).all()
            total = sum(Money.min_unit_to_shares(p.quantity) for p in rows)
            return Decimal(str(total))
        except Exception:
            return Decimal('0')

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        events = []
        for code in targets:
            try:
                if self._is_stock(code):
                    events.extend(self.adapter.fetch_stock_dividend(code))
                else:
                    events.extend(self.adapter.fetch_fund_dividend(code))
            except Exception as e:
                self.logger.warning(f'{code} 分红/送股抓取跳过: {e}')
                self.stats.setdefault('errors', []).append({'code': code, 'error': str(e)})
        return events

    # ── 转换为统一记录 ──

    def _event_to_record(self, ev: dict) -> Optional[StandardTransactionRecord]:
        symbol = ev.get('symbol')
        ex_date = ev.get('ex_date') or ev.get('ann_date')
        if not symbol or not ex_date:
            return None
        bonus = Decimal(str(ev.get('bonus_ratio') or 0))
        transfer = Decimal(str(ev.get('transfer_ratio') or 0))
        cash = Decimal(str(ev.get('cash_ratio') or 0))
        is_split = bonus > 0 or transfer > 0
        business_type = 'split' if is_split else 'dividend'
        held = self._holding_shares(symbol)
        if is_split:
            quantity = held * (bonus + transfer) / Decimal('10')
            amount = Decimal('0')
        else:
            quantity = Decimal('0')
            amount = held * cash / Decimal('10')
        name = ev.get('desc') or ev.get('ann_title') or ''
        rec = StandardTransactionRecord(
            confirm_date=ex_date,
            asset_type='stock' if self._is_stock(symbol) else 'fund',
            symbol=symbol,
            name=name,
            business_type=business_type,
            amount=amount,
            shares=quantity,
            nav=Decimal('0'),
            account_name='',
            source='akshare_dividend',
        )
        rec.import_hash = compute_record_hash(rec.source, rec)
        return rec

    # ── 校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[StandardTransactionRecord]:
        out = []
        for ev in raw_data:
            rec = self._event_to_record(ev)
            if rec is not None:
                out.append(rec)
        return out

    # ── 去重（import_hash 幂等） ──

    def _deduplicate(self, data: List[StandardTransactionRecord]) -> List[StandardTransactionRecord]:
        if not data:
            return []
        seen = set()
        batch_unique = []
        for r in data:
            h = r.import_hash
            if h in seen:
                continue
            seen.add(h)
            batch_unique.append(r)
        hashes = [r.import_hash for r in batch_unique if r.import_hash]
        if not hashes:
            return batch_unique
        existing = set(
            h for (h,) in self.db.query(Transaction.import_hash).filter(Transaction.import_hash.in_(hashes)).all()
        )
        return [r for r in batch_unique if r.import_hash not in existing]

    # ── 落库 ──

    def _save_data(self, new_data: List[StandardTransactionRecord]) -> None:
        if not new_data:
            return
        orch = ImportOrchestrator(self.db, family_id=1)
        result = orch.commit(new_data)
        self.logger.info(f'分红/送股落库: imported={result.get("imported")} orphan={result.get("orphan_count")}')
