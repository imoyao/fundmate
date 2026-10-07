# app/services/sync/jobs/orphan_backfill_job.py
"""孤儿交易回填任务：把 `position_id IS NULL` 的交易按**身份**挂回既有持仓（不联网）。

## 为什么需要它（tech-debt.md §1「孤儿交易无自动回填机制」）

交易流水与持仓是两条独立写入路径，而**导入顺序不保证**——先导流水、后建持仓（或
反之）时，早先那批流水就成了孤儿。写入层只在**建仓那一刻**做货基 / 逆回购的挂回
（`position_service._reattach_orphan_flows`，#863 口径 A），因此：

- 货基 / 逆回购：建仓时顺带挂回（早已实现）；
- **其余全部标的**：建仓时不挂回、写入层也不管 ⇒ 孤儿永久滞留。后果是持仓的
  「交易历史」凭空缺一段，金额口径与持仓市值对不上（`transactions` 有买入、
  `positions` 没有对应持仓行，二者对账必然不平）。

本 job 补的就是这个缺口：定时扫描 `position_id IS NULL`，按 symbol 身份挂回既有持仓。

## 匹配口径：按身份（`symbol_norm`），不按字面量

`positions.symbol_norm`（`{VENUE}:{code}`，由 `symbol_identity()` 计算、落库前由
`_fill_position_symbol_norm` 事件钩子强制填充）是 #1662 为「同一标的的写法变体」
建立的**唯一身份键**：`SZ004369` / `sz004369` / ` SZ004369 ` / `SH.004369` 在 SQLite
里是四个不同字符串却同一只基金。若按字面量匹配，同一只基金会同时产生「挂不上」
与「挂错持仓」两类错误。所以本 job 一律先算身份键再匹配，与那个唯一约束**同源**，
不存在两处口径漂移（这正是 #1657 复审栽过的坑：脚本按字面量相等，跨形态组合被静默漏挂）。

## 三条硬约束

1. **只补 `position_id`**：不改写 `amount` / `confirm_date` / `trade_date`。
   回填是「补链接」而非「修数据」，否则就成了数据污染源（验收标准第 2 条）。
2. **幂等**：只捞 `position_id IS NULL` 的行，挂过即离开候选集，重跑不重复关联
   （验收标准第 3 条）。不依赖任何「上次跑到哪」的记账。
3. **宁可不挂，也不挂错**：同 `(family_id, ledger_id, symbol_norm)` 命中多个持仓时
   跳过并计入 `ambiguous`。`ledger_id` 可为 NULL（未归档持仓 / 探市迁移），
   这种情况下同一身份可能对应多行，静默取第一条等于随机挂错。

## 为什么排除收益行

`is_income` 为真的行不参与回填，与 #863 `find_orphan_cash_flows` 的既有口径一致：
收益行属于「孤儿净额」桶的语义（income 而非本金流动），挂到持仓上会与那条口径
打架。收益归属是另一件事，不属于「补 `position_id`」的最小范围。
"""

from typing import Any, Dict, List, Optional, Tuple

from app.core.symbol_utils import symbol_identity
from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.job_base import IN_CHUNK_SIZE, JobStatus, SyncJob

# ledger_id 可为 NULL，而 `NULL == NULL` 在 SQL 里为假——索引键统一用哨兵 -1，
# 与 `transactions` 上那个 `COALESCE(ledger_id, -1)` 函数式唯一索引同一套约定。
_NULL_LEDGER = -1


class OrphanBackfillJob(SyncJob):
    """把孤儿交易挂回持仓的本地维护任务（不联网、无外部依赖）。"""

    def __init__(self, adapter, db):
        # adapter 是 SyncJob 的构造签名要求；本 job 不取数，NullAdapter 占位即可
        super().__init__(adapter, db)

    def get_name(self) -> str:
        return 'orphan_backfill'

    @property
    def _allow_empty_data(self) -> bool:
        # 「没有孤儿」是常态而非失败：绝大多数交易日库里不该有任何待回填的行
        return True

    # 以下四个方法是基类抽象方法的占位实现（本 Job 使用自定义 run 流程，
    # 同 FundCompanyBackfillJob / FundDetailEnrichJob）

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return []

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return []

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: Optional[List[str]] = None) -> Dict[str, Any]:
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.stats = {
            'scanned': 0,
            'attached': 0,
            'no_identity': 0,
            'no_position': 0,
            'ambiguous': 0,
            'errors': [],
        }
        self.logger.info('开始回填孤儿交易（position_id IS NULL → 按身份挂回持仓）')

        try:
            self._backfill()
        except Exception as e:
            self.db.rollback()
            self.logger.exception(f'孤儿交易回填失败: {e}')
            self.stats['errors'].append({'error': str(e)})
            self.status = JobStatus.FAILED
            return self._build_result()

        self._post_run()
        self.status = JobStatus.SUCCESS
        self.logger.info(
            f'孤儿交易回填完成: 扫描 {self.stats["scanned"]},挂回 {self.stats["attached"]}, '
            f'无身份 {self.stats["no_identity"]}, 无匹配持仓 {self.stats["no_position"]}, '
            f'候选歧义跳过 {self.stats["ambiguous"]}'
        )
        return self._build_result()

    # ── 主逻辑 ──

    def _backfill(self) -> None:
        orphans = (
            self.db.query(Transaction)
            .filter(
                Transaction.position_id.is_(None),
                # 收益行属「孤儿净额」桶语义，不参与回填（见模块 docstring）
                (Transaction.is_income.is_(None)) | (Transaction.is_income.is_(False)),
            )
            .all()
        )
        self.stats['scanned'] = len(orphans)
        if not orphans:
            self.logger.info('无孤儿交易')
            return

        # 第一步：逐行算身份键。symbol 为空的行算不出身份（symbol_identity 返回空串），
        # 直接计入 no_identity而不是拿空串去匹配——那会把所有无代码的流水挂到同一个持仓上。
        pending: List[Tuple[Transaction, str]] = []
        for txn in orphans:
            identity = symbol_identity(txn.symbol, txn.asset_type)
            if not identity:
                self.stats['no_identity'] += 1
                continue
            pending.append((txn, identity))

        # 第二步：一次性取出候选持仓，按 (family_id, ledger_id, 身份) 建索引。
        # 不用 SQL JOIN：孤儿可能上千行，JOIN 会把整表拉进内存；分批 in_ 只取需要的身份。
        families = {txn.family_id for txn, _identity in pending}
        index = self._load_position_index({identity for _txn, identity in pending}, families)

        # 第三步：逐条挂回，只写 position_id
        for txn, identity in pending:
            key = (
                txn.family_id,
                txn.ledger_id if txn.ledger_id is not None else _NULL_LEDGER,
                identity,
            )
            candidates = index.get(key, ())
            if not candidates:
                self.stats['no_position'] += 1
                continue
            if len(candidates) > 1:
                # 同一身份命中多个持仓：无法判断该挂哪一个，跳过而不是随机取第一条
                self.stats['ambiguous'] += 1
                continue
            txn.position_id = candidates[0]
            self.stats['attached'] += 1

        self.db.commit()

    def _load_position_index(
        self, identities: set, families: set
    ) -> Dict[tuple, Tuple[int, ...]]:
        """按身份批量取持仓，建 `(family_id, ledger_id, symbol_norm) -> (position_id, ...)` 索引。

        值用元组而非单个 id：同一身份理论上被 `uq_positions_ledger_symbol_norm` 唯一
        约束挡住，但 `ledger_id IS NULL` 时该约束失效（NULL互不冲突），仍可能出现多行——
        这种情况要交给调用方判歧义，而不是在这里悄悄取第一条。
        """
        index: Dict[tuple, List[int]] = {}
        identity_list = list(identities)
        for start in range(0, len(identity_list), IN_CHUNK_SIZE):
            chunk = identity_list[start:start + IN_CHUNK_SIZE]
            rows = (
                self.db.query(Position)
                .filter(Position.symbol_norm.in_(chunk), Position.family_id.in_(families))
                .all()
            )
            for pos in rows:
                key = (
                    pos.family_id,
                    pos.ledger_id if pos.ledger_id is not None else _NULL_LEDGER,
                    pos.symbol_norm,
                )
                index.setdefault(key, []).append(pos.id)
        return {k: tuple(v) for k, v in index.items()}
