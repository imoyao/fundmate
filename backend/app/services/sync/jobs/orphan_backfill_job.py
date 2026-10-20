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

1. **补 `position_id` + 重算派生份额**：挂回后必须对受影响持仓调
   `recompute_position_from_transactions`（份额派生的唯一入口，与 nav_backfill /
   删流水重算同源）。只补链接不重算是本类 bug 的根因——真实库实测（017074
   嘉实清洁能源C）：支付宝先导卖出、后导买入，两笔卖出降级为孤儿，本 job 挂回后
   `position_id` 补上了，份额却从未扣减 ⇒ 账面 2858.29 份 / 市值 2350 元，
   实际早已清仓，对账 quantity 差异白记三个月没人能对平。流水的
   `amount` / `confirm_date` / `trade_date` 仍**一律不改写**——回填是
   「补链接 + 让派生份额跟上」，不是「修流水数据」。
2. **幂等**：只捞 `position_id IS NULL` 的行，挂过即离开候选集，重跑不重复关联
   （验收标准第 3 条）。不依赖任何「上次跑到哪」的记账。重算同样幂等
   （全量流水派生，非增量加减）。
3. **宁可不挂，也不挂错**：同 `(family_id, ledger_id, symbol_norm)` 命中多个持仓时
   跳过并计入 `ambiguous`。`ledger_id` 可为 NULL（未归档持仓 / 探市迁移），
   这种情况下同一身份可能对应多行，静默取第一条等于随机挂错。

## 重算的边界（刻意保守）

- 净额派生出 **0 / 负份额**（超卖）⇒ `recompute` 钳 0 并标记
  `ownership_status='cleared'`（#2343 清仓不删行），负值是脏数据不是持仓。
- 有快照锚点的持仓走锚点口径：归属日 `<= snapshot_date` 的流水视为已被快照
  包含，不重复扣减——重算不会把快照值减穿。
- 单个持仓重算失败（异常）只记 `errors` 不抛出：回填是维护任务，
  一个持仓算错不该让整批挂回的事务回滚。

## 为什么排除收益行

`is_income` 为真的行不参与回填，与 #863 `find_orphan_cash_flows` 的既有口径一致：
收益行属于「孤儿净额」桶的语义（income 而非本金流动），挂到持仓上会与那条口径
打架。收益归属是另一件事，不属于「补 `position_id`」的最小范围。
"""

from typing import Any, Dict, List, Optional, Tuple

from app.core.symbol_utils import strip_exchange_prefix, symbol_identity
from app.core.time_utils import now_shanghai
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.job_base import IN_CHUNK_SIZE, JobStatus, SyncJob
from app.services.position_service import PositionService

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
            'recomputed': 0,
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
            f'候选歧义跳过 {self.stats["ambiguous"]}, 份额重算 {self.stats["recomputed"]}'
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

        # 第二步：一次性取出候选持仓，建两类索引（同一批数据，避免重复查库）：
        #   index     —— (family_id, ledger_id, symbol_norm)：身份路径，精确匹配
        #   lit_index —— (family_id, ledger_id, 去前缀symbol)：字面量路径，身份未命中时回退
        # 不用 SQL JOIN：孤儿可能上千行，JOIN 会把整表拉进内存；分批 in_ 只取需要的身份。
        families = {txn.family_id for txn, _identity in pending}
        identities = {identity for _txn, identity in pending}
        index = self._load_position_index(identities, families)
        lit_index = self._load_literal_index(identities, families)

        # 第三步：逐条挂回，只写 position_id
        attached_positions: set = set()
        for txn, identity in pending:
            key = (
                txn.family_id,
                txn.ledger_id if txn.ledger_id is not None else _NULL_LEDGER,
                identity,
            )
            candidates = index.get(key, ())
            if len(candidates) == 1:
                txn.position_id = candidates[0]
                self.stats['attached'] += 1
                attached_positions.add(candidates[0])
                continue
            if len(candidates) > 1:
                # 同一身份命中多个持仓：无法判断该挂哪一个，跳过而不是随机取第一条
                self.stats['ambiguous'] += 1
                continue
            # 身份路径未命中 → 字面量回退（见 _try_attach_by_literal）
            pos_id = self._try_attach_by_literal(txn, lit_index)
            if pos_id is not None:
                attached_positions.add(pos_id)

        # 第四步：份额重算。挂回只是补了链接，若不再生份额，被挂回的卖出/取出流水
        # 永远不会扣减持仓数量——「先导卖出、后建持仓」的导入顺序会留下账面有份额、
        # 实际已清仓的幽灵持仓（017074 实测市值虚增 2350 元，见模块 docstring）。
        # 口径与 nav_backfill / 删流水重算完全同源（compute_anchored_state）。
        self._recompute_attached(attached_positions)

        self.db.commit()

    def _recompute_attached(self, attached_positions: set) -> None:
        """对挂回流水涉及的持仓逐个重算份额（第四步，见模块 docstring 硬约束 1）。

        单个持仓失败只记 `errors` 不抛出：回填是维护任务，一个持仓算错
        （典型：锚点与流水互相矛盾的脏数据）不该让整批挂回的事务回滚。
        """
        if not attached_positions:
            return
        # 先把挂回落库再重算：`SessionLocal` 是 autoflush=False（database.py），
        # 循环里 `txn.position_id = ...` 只是内存赋值，recompute 内部的流水查询
        # 看不到未 flush 的挂回——「挂回的卖出」会被当成不存在，份额一点不减
        # （017074 实测形态：recomputed=1 但 quantity 原样）。
        self.db.flush()
        for pos_id in sorted(attached_positions):
            try:
                PositionService.recompute_position_from_transactions(self.db, pos_id)
                self.stats['recomputed'] += 1
            except Exception as e:
                self.logger.exception(f'挂回后份额重算失败: position_id={pos_id}, error={e}')
                self.stats['errors'].append({'position_id': pos_id, 'error': str(e)})

    def _load_position_index(self, identities: set, families: set) -> Dict[tuple, Tuple[int, ...]]:
        """按身份批量取持仓，建 `(family_id, ledger_id, symbol_norm) -> (position_id, ...)` 索引。

        值用元组而非单个 id：同一身份理论上被 `uq_positions_ledger_symbol_norm` 唯一
        约束挡住，但 `ledger_id IS NULL` 时该约束失效（NULL互不冲突），仍可能出现多行——
        这种情况要交给调用方判歧义，而不是在这里悄悄取第一条。
        """
        index: Dict[tuple, List[int]] = {}
        identity_list = list(identities)
        for start in range(0, len(identity_list), IN_CHUNK_SIZE):
            chunk = identity_list[start : start + IN_CHUNK_SIZE]
            rows = (
                self.db.query(Position).filter(Position.symbol_norm.in_(chunk), Position.family_id.in_(families)).all()
            )
            for pos in rows:
                key = (
                    pos.family_id,
                    pos.ledger_id if pos.ledger_id is not None else _NULL_LEDGER,
                    pos.symbol_norm,
                )
                index.setdefault(key, []).append(pos.id)
        return {k: tuple(v) for k, v in index.items()}

    def _load_literal_index(
        self, identities: set, families: set
    ) -> Dict[tuple, Tuple[Tuple[int, Optional[str], str], ...]]:
        """按字面量批量取持仓，建 `(family_id, ledger_id, 去前缀symbol) ->
        (position_id, asset_type, symbol_norm)` 索引。

        用于身份路径未命中时的回退匹配。**不按 `symbol_norm` 过滤**——因为回退要兜的正是
        「孤儿 `asset_type` 缺失 / 与持仓不一致、导致身份键错位」的那类：此时候选持仓的
        `symbol_norm` 并不在孤儿身份集合里，若按 `symbol_norm.in_(identities)` 过滤会直接漏掉它。
        改为按 `family_id` 取该 family 全部持仓（持仓量级远小于流水，可接受），再在内存里按字面量建键。
        """
        index: Dict[tuple, List[tuple]] = {}
        for pos in self.db.query(Position).filter(Position.family_id.in_(families)).all():
            key = (
                pos.family_id,
                pos.ledger_id if pos.ledger_id is not None else _NULL_LEDGER,
                strip_exchange_prefix(pos.symbol or ''),
            )
            index.setdefault(key, []).append((pos.id, pos.asset_type, pos.symbol_norm))
        return {k: tuple(v) for k, v in index.items()}

    def _try_attach_by_literal(
        self, txn: Transaction, lit_index: Dict[tuple, Tuple[Tuple[int, Optional[str], str], ...]]
    ) -> Optional[int]:
        """身份路径未命中时的回退：按去前缀字面量在同一 (family, ledger) 下找持仓。

        只挂「持仓自身 `asset_type` 能让孤儿 `symbol` 复算出该持仓 `symbol_norm`」的那一条——
        用持仓身份反推孤儿身份，校验 `symbol_identity(txn.symbol, pos.asset_type) == pos.symbol_norm`
        通过才挂。这样既不凭空发明身份键，也不会因孤儿 `asset_type` 缺失而漏挂本可挂的持仓
        （真实库实测：大量 legacy 流水 `asset_type` 为 NULL，但同 (family, ledger) 下确有字面量
        相同的持仓；而 `SZ011341` 这类带错前缀的脏 symbol，其真实 venue 只能由持仓侧定）。

        返回挂上的 `position_id`（未挂返回 None），供调用方纳入份额重算集合。
        """
        lk = (
            txn.family_id,
            txn.ledger_id if txn.ledger_id is not None else _NULL_LEDGER,
            strip_exchange_prefix(txn.symbol or ''),
        )
        cands = lit_index.get(lk, ())
        valid = [
            pos_id
            for (pos_id, pos_asset_type, pos_symbol_norm) in cands
            if symbol_identity(txn.symbol, pos_asset_type) == pos_symbol_norm
        ]
        if len(valid) == 1:
            txn.position_id = valid[0]
            self.stats['attached'] += 1
            return valid[0]
        elif len(valid) > 1:
            self.stats['ambiguous'] += 1
        else:
            self.stats['no_position'] += 1
        return None
