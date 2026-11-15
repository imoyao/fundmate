# -*- coding: utf-8 -*-
"""对账的**理论持仓口径**（域 B/C 共用的唯一一份派生实现）。

`reconciliation_service` 原先自带 6 个小函数（`_txn_type` / `_txn_quantity` /
`_txn_net_quantity` / `_txn_confirm_date` / `_theoretical_qty` / `_find_holding`），
域 B 的「理论持仓 vs 实际持仓」和孤儿判定全靠它们。抽出来的原因只有一个：
新增的补录闸门（`reconciliation_integrity`）要判「这笔补录会不会与已有流水重复」，
必须用**同一口径**把 payload 折成份额——若各写一份折算，闸门与本体的差异会被读成
「闸门误报」而不是「代码有两份口径」。

## 两个口径同时存在，不是历史包袱

- **锚点口径**（`theoretical_qty`，持仓有 `snapshot_quantity`+`snapshot_date` 时）：
  快照是独立绝对值，不是流水的推导结果，故理论持仓 = 快照基线 + 快照日之后的流水净额；
- **全量口径**（`net_quantity`，无锚点份额时）：迁移只回填了 `snapshot_date`，
  `snapshot_quantity` 留空（历史份额已丢失，盲猜会改坏另一半账户），这类持仓退回
  「全量流水净额」，与加锚点之前行为一致，不制造新红。

`_theoretical_qty` 的原 docstring 已在此处保留完整版（含为何不能只用全量净额的推导）。
"""

_ADD_TYPES = ('buy', 'deposit', 'split')
_SELL_TYPES = ('sell', 'withdraw')


def txn_type(t) -> str:
    """兼容 Transaction 对象与 dict 两种流水表示。"""
    return t.txn_type if not isinstance(t, dict) else t['txn_type']


def txn_quantity(t) -> int:
    """兼容 Transaction 对象与 dict 两种流水表示。"""
    return t.quantity if not isinstance(t, dict) else t['quantity']


def txn_confirm_date(t):
    return t.confirm_date if not isinstance(t, dict) else t.get('confirm_date')


def net_quantity(txns) -> int:
    """从流水计算净份额（最小单位）：Σ买入/存入/送股 − Σ卖出/取出。"""
    buy_qty = sum(txn_quantity(t) for t in txns if txn_type(t) in _ADD_TYPES)
    sell_qty = sum(txn_quantity(t) for t in txns if txn_type(t) in _SELL_TYPES)
    return buy_qty - sell_qty


def has_anchor(position) -> bool:
    """持仓是否带**份额锚点**（快照绝对值 + 快照日俱全）。

    这个判据必须只有一个来源：`theoretical_qty` 用它选口径，域 B 用它区分
    「数量差异」与「缺基准」（#3125）。两处各写一遍条件的话，一旦一边漏判，
    就会出现「理论值走了锚点分支、差异类型却报缺基准」的口径分裂——那比错报
    更难查，因为两个数各自都算得通。

    注意「有 `snapshot_date`、无 `snapshot_quantity`」是迁移的合法常态
    （历史快照份额已丢失，见 `migrate_positions_snapshot_anchor`），不算锚点。
    """
    return position is not None and position.snapshot_quantity is not None and position.snapshot_date is not None


def theoretical_qty(txns, position) -> int:
    """锚点口径的理论持仓（**快照基线 + 快照日之后的流水净额**）。

    ## 为什么不能只用「全量流水净额」

    快照是独立绝对值，不是流水的推导结果。加入锚点后
    `positions.quantity = snapshot_quantity + Σ(confirm_date > snapshot_date)`，
    若这里仍拿全量流水去比，只要「快照值 ≠ 快照前流水净额」（有分红、有漏录、
    有手续费尾差都会发生），就会**恒报数量差异**——修复上线即制造一批假红。
    """
    if has_anchor(position):
        total = int(position.snapshot_quantity)
        for t in txns:
            d = txn_confirm_date(t)
            if d is None or d <= position.snapshot_date:
                continue
            if txn_type(t) in _ADD_TYPES:
                total += txn_quantity(t)
            elif txn_type(t) in _SELL_TYPES:
                total -= txn_quantity(t)
        return total
    return net_quantity(txns)


def find_holding(txns) -> bool:
    """从流水推断理论持仓是否存在：净份额 > 0 即存在（对齐孤儿检测）。"""
    return net_quantity(txns) > 0


def group_by_business_key(rows) -> dict[tuple, list]:
    """把 `(ledger_id, symbol, txn_type, quantity, confirm_date)` 结果集折成
    `{(ledger_id, symbol): [流水 dict]}`（域 B/C 的检测单位）。

    缺账本或缺标的的流水直接跳过：域 B 的业务键就是这两列，`None` 键会把不同账本
    的无关流水并成一个桶（并在差异表里落一条 NULL 差异）。`confirm_date` 带上是因为
    锚点口径要过滤「快照日之前」的流水。
    """
    grouped: dict[tuple, list] = {}
    for ledger_id, symbol, txn_type, quantity, confirm_date in rows:
        if ledger_id is None or not symbol:
            continue
        grouped.setdefault((ledger_id, symbol), []).append(
            {'txn_type': txn_type, 'quantity': quantity or 0, 'confirm_date': confirm_date}
        )
    return grouped
