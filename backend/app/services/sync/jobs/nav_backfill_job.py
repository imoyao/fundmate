# app/services/sync/jobs/nav_backfill_job.py
"""
净值缺失流水回填（pending_nav → 官方净值到位后重算份额/成本）

记一笔基金买入时，当日净值可能尚未发布或数据源临时故障。为了不把用户挡在
记账之外，`process_buy_or_deposit` 用「库内最近净值」当占位价放行提交，并把
流水标成 `entry_status='pending_nav'`（元数据在 extra JSON：nav_date /
shares_manual）。本 job 在官方净值（`daily_worth`）落库后完成回填：

- 份额自动型（shares_manual=False）：`份额 = round(流水金额 / 官方净值, 4)`，
  金额 = 价格×份额（净投入 ≈ 买入金额−手续费，回填前后近似不变）；
- 份额手动型（shares_manual=True）：份额是用户录入的权威值，**只校正净值与成本**；
- 更新流水后按 position_id 调 `recompute_position_from_transactions` 从流水
  重建持仓（天然兼容合并仓），最后清 pending 标记；
- 手动编辑优先：用户在编辑弹窗手改过份额的流水，pending 已被
  `ledger_write_service.update_ledger_transaction` 清掉，本 job 天然跳过。

## 时序（T-1 硬护栏，#824）

`fund_nav_job` 丢弃 `date >= today` 的记录：day-D 官方净值**最早 D+1 21:30**
的 fund_nav 增量才落进 daily_worth。故本 job 的 cron 排在其后
（daily_scheduler：`35 8,22 * * *`），与 fund_valuation_reconcile 同节奏：
晚班消费当晚 21:30 刚落库的昨日净值，晨班兜底（休市日 catch-up、源延迟恢复）。
未命中官方净值的流水保持 pending，等下一轮自然收敛（晚到 N 天最终都会回填）。

## 硬边界

- **不改写 daily_worth**：官方值唯一权威，本 job 只读。
- **纯 DB 零外部请求**：target_kind=None 全量路径（targets 忽略），
  不入 SYMBOL_BACKFILL_JOBS；量级 = 用户池 pending 行，天然有界。
- **幂等**：只处理 entry_status='pending_nav' 行；清标后重跑零副作用。
"""

import json
from datetime import date, datetime
from typing import Dict, List, Tuple

from app.core.money import Money
from app.core.symbol_utils import strip_exchange_prefix
from app.core.time_utils import now_shanghai
from app.domains.funds.models import DailyWorth
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.adapters.null_adapter import NullAdapter
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.position_service import PositionService


def _parse_nav_date(item: dict) -> date:
    """流水目标净值日：extra.nav_date 优先，缺失/非法回退 trade_date 当日。"""
    raw = item.get('nav_date')
    if raw:
        try:
            return datetime.strptime(str(raw)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    trade_date = item.get('trade_date')
    if isinstance(trade_date, datetime):
        return trade_date.date()
    if isinstance(trade_date, date):
        return trade_date
    return datetime.strptime(str(trade_date)[:10], '%Y-%m-%d').date()


class NavBackfillJob(SyncJob):
    """净值缺失流水回填：pending_nav 流水按官方净值重算份额/成本（纯 DB）。"""

    def __init__(self, db):
        # 纯本地读写（读 daily_worth / 流水，写流水 + 持仓），NullAdapter 占位
        # ——同 fund_valuation_reconcile / position_price 惯例
        super().__init__(NullAdapter(), db)

    def get_name(self) -> str:
        return 'nav_backfill'

    @property
    def _allow_empty_data(self) -> bool:
        return True  # 无 pending 流水是常态（净值都拉到了）

    # ── 数据获取（targets=None 全量路径：基类单次调用） ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """全部 pending_nav 流水（不限日期——净值晚到 N 天最终都会回填）。

        targets 参数忽略（target_kind=None，调度层不解析目标池）。
        """
        rows = (
            self.db.query(
                Transaction.id,
                Transaction.position_id,
                Transaction.symbol,
                Transaction.quantity,
                Transaction.price,
                Transaction.amount,
                Transaction.trade_date,
                Transaction.extra,
            )
            .filter(Transaction.entry_status == 'pending_nav')
            .all()
        )
        items: List[dict] = []
        for txn_id, position_id, symbol, quantity, price, amount, trade_date, extra_raw in rows:
            try:
                extra = json.loads(extra_raw) if extra_raw else {}
            except (ValueError, TypeError):
                extra = {}
            if not isinstance(extra, dict):
                extra = {}
            items.append(
                {
                    'txn_id': txn_id,
                    'position_id': position_id,
                    'symbol': symbol,
                    'quantity': quantity,
                    'price': price,
                    'amount': amount,
                    'shares_manual': bool(extra.get('shares_manual')),
                    'nav_date': extra.get('nav_date'),
                    'trade_date': trade_date,
                }
            )
        return items

    # ── 数据校验：两步法匹配官方净值，产出回填更新 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """按 (symbol, nav_date) 精确匹配 daily_worth，命中才产出回填更新。

        两步法（同域也保持应用层配对，不做 SQL join）：先收集键，再分批 in_ 取候选。
        未命中 / unit_nav 空 / 自动型金额非正 → 不产出（保持 pending，下轮再试）。
        """
        if not raw_data:
            return []
        for item in raw_data:
            item['nav_date'] = _parse_nav_date(item)

        # daily_worth.fund_code 为裸 6 位码；流水 symbol 可能带场所前缀（ETF），先剥掉再配对
        codes = list({strip_exchange_prefix(r['symbol']) for r in raw_data})
        dates = list({r['nav_date'] for r in raw_data})

        official_map: Dict[Tuple[str, date], float] = {}
        for i in range(0, len(codes), IN_CHUNK_SIZE):
            code_chunk = codes[i : i + IN_CHUNK_SIZE]
            for fund_code, nav_date, unit_nav in (
                self.db.query(DailyWorth.fund_code, DailyWorth.date, DailyWorth.unit_nav)
                .filter(DailyWorth.fund_code.in_(code_chunk), DailyWorth.date.in_(dates))
                .all()
            ):
                if unit_nav is None or unit_nav <= 0:
                    continue
                official_map[(fund_code, nav_date)] = float(unit_nav)

        updates: List[dict] = []
        for item in raw_data:
            nav = official_map.get((strip_exchange_prefix(item['symbol']), item['nav_date']))
            if nav is None:
                continue
            nav_units = Money.yuan_to_price_units(nav)
            if item['shares_manual']:
                # 手动份额是权威值：只校正净值与成本，不动份额
                new_qty_units = item['quantity']
            else:
                net_cents = item['amount'] or 0
                if net_cents <= 0:
                    continue  # 净投入缺失算不出份额：保持 pending，等编辑补
                new_qty_units = Money.shares_to_min_unit(round(net_cents / 100 / nav, 4))
                if new_qty_units <= 0:
                    continue
            updates.append(
                {
                    'txn_id': item['txn_id'],
                    'position_id': item['position_id'],
                    'nav_units': nav_units,
                    'new_qty_units': new_qty_units,
                    'new_amount': Money.multiply_price_quantity(nav_units, new_qty_units),
                }
            )
        return updates

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """不去重：每行独立按 id UPDATE，重复键不可能出现。"""
        return data

    # ── 保存：更新流水 → 重建持仓 → 清标记 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """更新 pending 流水的份额/净值/金额并清标记；随后按持仓重建（兼容合并仓）。

        先批量改流水、再逐个 position 重建，避免同一持仓被中途重算两次；
        再查一次 entry_status 做并发兜底（编辑手改份额刚清过标记就跳过）。
        """
        if not new_data:
            return
        now = now_shanghai()
        touched_positions: Dict[int, int] = {}  # position_id → 官方净值（price units）
        for item in new_data:
            txn = self.db.query(Transaction).filter(Transaction.id == item['txn_id']).first()
            if not txn or txn.entry_status != 'pending_nav':
                continue  # 并发兜底：期间被手动编辑清标 → 以手动结果为准
            txn.quantity = item['new_qty_units']
            txn.price = item['nav_units']
            txn.amount = item['new_amount']
            txn.entry_status = None
            try:
                extra = json.loads(txn.extra) if txn.extra else {}
            except (ValueError, TypeError):
                extra = {}
            if not isinstance(extra, dict):
                extra = {}
            extra['nav_pending'] = False
            extra['backfilled_at'] = now.isoformat()
            txn.extra = json.dumps(extra, ensure_ascii=False)
            if txn.position_id:
                touched_positions[txn.position_id] = item['nav_units']
        for position_id, nav_units in touched_positions.items():
            PositionService.recompute_position_from_transactions(self.db, position_id)
            # recompute 只在 current_price 为 0/None 时填均价；占位期写进 current_price
            # 的旧净值必须刷新为官方值，否则持仓市值停在占位价直到下轮 position_price
            pos = self.db.query(Position).filter(Position.id == position_id).first()
            if pos is not None and pos.current_price != nav_units:
                pos.current_price = nav_units
        self.db.commit()


__all__ = ['NavBackfillJob']
