# -*- coding: utf-8 -*-
"""资金流水分层（#2615）：把 `transactions` 按 L1/L2/L3 分类的**唯一入口**。

## 为什么要有这一层

「钱进出账户」和「资产自己涨跌」是两件事。混在一起就会得出
「总投入 1.68 亿 / 总收益 -1886 万」这种数字（#2610 只修掉了其中的单位错与毛额展示）。
根因不是算术，是**每个页面各自决定「哪些交易算投入」**：

- 组合 XIRR 把买入当投入，完全不看入金 / 出金（= 证券持仓口径）；
- 收益日历按日市值差分（`daily_pnl` 天然免疫资金流，这条是对的）；
- 账户页干脆没有资金流动视图。

三套口径各算一遍，同一个数字在家庭页与账户页就对不上。本模块只做一件事：
**按层分类，让消费方显式声明自己用哪几层**，不再各写一份 if/elif。

## 四层（判据一句话：交易对手方是否跨出「本账户集合」）

| 层 | 交易类型 | 算盈亏 | 算外部现金流 | 进 XIRR（账户口径） |
|---|---|---|---|---|
| L1 外部资金流 | `deposit` / `withdraw`（且未被内部划转配对） | 否 | **是** | 是 |
| L2 资产转换 | `buy` / `sell` / `dividend_reinvest` / `split` | 否 | 否 | 否 |
| L3 收益实现 | `dividend` / `dividend_cash` / `bond_redeem` / `tax` | 是 | 否 | 否 |
| L4 估值变动 | 未实现浮盈浮亏（来自持仓市值，**不是流水**） | 是 | 否 | 终端虚拟卖出 |

家庭内账户互转（同日 / 同额 / 反向 / 跨 ledger）是 L1 的**内部抵消**：
一进一出净额为 0，两笔都不该进账户口径 XIRR——由 :func:`pair_internal_transfers` 判定。

## 单位纪律

`transactions.amount` 存的是**分**，本模块对外一律返回**元**（`Money.cents_to_yuan`）。
消费方不需要、也不应该再做一次换算（#2610 的 100 倍错误就是这么来的）。

## 消费方

- 组合 / 账户 XIRR：`app/services/performance/xirr_engine.py`
- 账户资金流动区块（#2616）：直接读 :func:`build_layers` 的 `l1` / `totals`
- 三级视图聚合（#2595）：按需取 `l2` / `l3` 做结构拆解
"""

import datetime as dt
from typing import Dict, List, Optional, Sequence, Set

from loguru import logger

from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.importer.mappings import BusinessType

#: 资金流水层标识（对外字符串，便于直接进 JSON 响应）
L1_EXTERNAL = 'L1'  # 外部资金流：入金 / 出金（跨出本账户集合）
L2_TRANSFER = 'L2'  # 资产转换：买入 / 卖出 / 红利再投 / 拆分（账户内换形态）
L3_REALIZED = 'L3'  # 收益实现：现金分红 / 兑付 / 税费（计入盈亏，但不是外部现金流）
L4_VALUATION = 'L4'  # 估值变动：未实现浮盈浮亏（来自持仓市值，无对应流水）

#: 交易类型 → 层。未登记的类型一律 `None`（未知层），由调用方显式处理，不猜。
_TXN_LAYER = {
    BusinessType.DEPOSIT.code: L1_EXTERNAL,
    BusinessType.WITHDRAW.code: L1_EXTERNAL,
    BusinessType.BUY.code: L2_TRANSFER,
    BusinessType.SELL.code: L2_TRANSFER,
    BusinessType.DIVIDEND_REINVEST.code: L2_TRANSFER,
    BusinessType.SPLIT.code: L2_TRANSFER,
    BusinessType.DIVIDEND.code: L3_REALIZED,
    BusinessType.DIVIDEND_CASH.code: L3_REALIZED,
    BusinessType.BOND_REDEEM.code: L3_REALIZED,
    BusinessType.TAX.code: L3_REALIZED,
}

#: 投资者视角的现金符号：入金 = 钱从口袋进账户（负），出金 = 回流（正）。
#: XIRR 的约定是「现金流出为负、流入为正」，与 `generate_cashflows` 的买卖符号同向。
_L1_SIGN = {BusinessType.DEPOSIT.code: -1.0, BusinessType.WITHDRAW.code: 1.0}

#: 现金残差公式里「账户现金增加」的类型（+）与「账户现金减少」的类型（-）。
#: 现金 ≈ 入金 − 出金 − 买入 + 卖出 + 现金分红 + 兑付 − 税费（#2615 提案，本卡落地）。
#: 注意方向是**账户现金**视角，不是投资者视角：入金让账户钱变多（+），出金变少（-）。
_ACCOUNT_CASH_IN_TYPES = {
    BusinessType.DEPOSIT.code,
    BusinessType.SELL.code,
    BusinessType.DIVIDEND.code,
    BusinessType.DIVIDEND_CASH.code,
    BusinessType.BOND_REDEEM.code,
}
#: 红利再投 / 拆分**不动现金**（份额变了、钱没进出），故不在任何一侧。
_ACCOUNT_CASH_OUT_TYPES = {
    BusinessType.WITHDRAW.code,
    BusinessType.BUY.code,
    BusinessType.TAX.code,
}


def classify(txn_type: Optional[str]) -> Optional[str]:
    """交易类型 → 资金流水层（L1/L2/L3）；未登记返回 `None`。

    刻意不抛错：历史数据里有 `other` 之类的类型，抛错会让整页 500；
    未知类型由 :func:`build_layers` 单列到 `unknown`，让「有多少笔没被归类」可见。
    """
    return _TXN_LAYER.get(txn_type)


def pair_internal_transfers(flows: Sequence[dict], ledger_ids: Set[int]) -> Set[int]:
    """识别「家庭内账户互转」，返回应剔除的流水**下标集合**。

    配对条件：同日、金额相等（分精度）、方向相反、分属本集合内**不同**账户。
    按 `ledger_id` 判定而不是账户名——同名账户串味是历史 bug（两张卡都叫「主账户」时
    会把外部入金当成内部划转剔掉）。

    配对结果只描述「这两笔互相抵消」，不改变它们的层归属：它们仍是 L1，
    只是**净额为 0**，账户口径 XIRR 与资金流动总额里都不该出现。
    """
    excluded: Set[int] = set()
    deposit_code = BusinessType.DEPOSIT.code
    withdraw_code = BusinessType.WITHDRAW.code

    for i, a in enumerate(flows):
        if i in excluded:
            continue
        for j in range(i + 1, len(flows)):
            b = flows[j]
            if j in excluded:
                continue
            if a['date'] != b['date']:
                continue
            if a['amount_cents'] != b['amount_cents']:
                continue
            # 同一账户内的存取不算内部划转（按 ID 判定）
            if a['ledger_id'] == b['ledger_id']:
                continue
            a_out = a['txn_type'] == deposit_code and b['txn_type'] == withdraw_code
            b_out = b['txn_type'] == deposit_code and a['txn_type'] == withdraw_code
            if not (a_out or b_out):
                continue
            if a['ledger_id'] not in ledger_ids or b['ledger_id'] not in ledger_ids:
                continue
            excluded.update([i, j])
            logger.debug(
                '内部划转已排除: {} ledger#{}↔#{} 金额={:.2f}',
                a['date'],
                a['ledger_id'],
                b['ledger_id'],
                a['amount'],
            )
            break
    return excluded


def collect_flows(
    db_session,
    ledger_ids: Optional[Sequence[int]] = None,
    family_id: int = 1,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
    include_cash_equivalents: bool = False,
    *,
    position_ids: Optional[Sequence[int]] = None,
) -> List[dict]:
    """按账户集合（或持仓集合）读取交易，打上层标签，返回**元**单位的流水列表。

    两种作用域二选一（**都传时 ``position_ids`` 优先**，用于持仓级组合的收益归因）：

    - ``ledger_ids``：账户口径。账户 XIRR / 资金流动视图走这条。
    - ``position_ids``：持仓口径。持仓级组合的 XIRR 走这条——因为组合成员是持仓，
      而账户集合表达不了「同一账户里不同持仓分属不同组合」。

    参数与 `xirr_engine` 同口径：
    - `include_cash_equivalents=False` 时排除货币基金 / 逆回购 / 现金（`EXCLUDED_ASSET_TYPES`），
      与「组合收益不算现金管理工具」的既有约定一致；
    - 日期用 `confirm_date`（确认日），缺失的记录跳过（与现金流构造同口径）。

    每条：`{index, date, layer, txn_type, amount, signed_amount, amount_cents,
    ledger_id, symbol, asset_type}`。`signed_amount` 是投资者视角符号（见 `_L1_SIGN`）：
    L1 入金为负、出金为正；L2 买入为负、卖出为正；L3 一律为正（钱进账户）。
    """
    # 延迟导入：EXCLUDED_ASSET_TYPES 归 xirr_engine 所有（历史位置），避免循环导入
    from app.services.performance.xirr_engine import EXCLUDED_ASSET_TYPES

    if position_ids is not None:
        if not position_ids:
            return []
        scope_filter = Transaction.position_id.in_(list(position_ids))
    else:
        if not ledger_ids:
            return []
        scope_filter = Transaction.ledger_id.in_(list(ledger_ids))

    query = db_session.query(Transaction).filter(
        scope_filter,
        Transaction.family_id == family_id,
    )
    if start_date is not None:
        query = query.filter(Transaction.confirm_date >= start_date)
    if end_date is not None:
        query = query.filter(Transaction.confirm_date <= end_date)

    flows: List[dict] = []
    for txn in query.all():
        txn_date = txn.confirm_date
        if isinstance(txn_date, dt.datetime):
            txn_date = txn_date.date()
        if txn_date is None:
            continue

        asset_type = getattr(txn, 'asset_type', None)
        if not include_cash_equivalents and asset_type in EXCLUDED_ASSET_TYPES:
            continue

        raw_amount = getattr(txn, 'amount', None)
        if raw_amount is None:
            continue
        try:
            amount = Money.cents_to_yuan(int(raw_amount))
        except (TypeError, ValueError):
            continue
        if abs(amount) < 1e-8:
            continue

        txn_type = txn.txn_type
        layer = classify(txn_type)
        if layer == L1_EXTERNAL:
            signed = _L1_SIGN.get(txn_type, 0.0) * amount
        elif txn_type == BusinessType.BUY.code or txn_type == BusinessType.DIVIDEND_REINVEST.code:
            signed = -amount
        elif txn_type == BusinessType.SELL.code:
            signed = amount
        elif txn_type == BusinessType.TAX.code:
            signed = -amount  # 税费是流出，别当成收益
        elif layer == L3_REALIZED:
            signed = amount
        else:  # SPLIT / 未知类型：不动现金
            signed = 0.0

        flows.append(
            {
                'index': len(flows),
                'date': txn_date,
                'layer': layer,
                'txn_type': txn_type,
                'amount': amount,
                'signed_amount': signed,
                'amount_cents': round(amount * 100),
                'ledger_id': txn.ledger_id,
                'symbol': getattr(txn, 'symbol', None),
                'asset_type': asset_type,
            }
        )
    return flows


def build_layers(
    db_session,
    ledger_ids: Sequence[int],
    family_id: int = 1,
    start_date: Optional[dt.date] = None,
    end_date: Optional[dt.date] = None,
    include_cash_equivalents: bool = False,
) -> dict:
    """在 :func:`collect_flows` 之上做分层聚合，返回可直接消费的 dict。

    返回结构::

        {
          'l1': [...], 'l2': [...], 'l3': [...], 'unknown': [...],  # 每条带 internal_transfer 标记
          'internal_transfer_indexes': [...],       # 被内部划转抵消的流水下标（totals 已剔除）
          'totals': {
              'deposit', 'withdraw', 'net_invested',       # L1 汇总（元，已剔除内部互转）
              'buy', 'sell', 'dividend_cash', 'fees',      # 明细口径（元）
              'cash_residual',                             # 推导现金残差（元）
          },
          'basis_by_ledger': {ledger_id: 'account' | 'position'},
        }

    `net_invested = 累计入金 − 累计出金`：这是**用户视角「我一共压进去多少」**。
    刻意不把已实现盈亏混进来——那是收益，不是投入（见 `docs/spec/cashflow-layers.md`）。

    内部互转（#2681）：一次传入多个成员账本时，同日同额反向的两笔被配对并在 totals 中
    剔除（`internal_transfer=True`），但**仍留在 `l1` 桶里**便于诊断；消费方要展示逐笔
    流水时须自行按该标记过滤，否则会出现「列表里有、总额里没有」的对不上。
    """
    flows = collect_flows(
        db_session,
        ledger_ids,
        family_id=family_id,
        start_date=start_date,
        end_date=end_date,
        include_cash_equivalents=include_cash_equivalents,
    )
    ledger_set = set(ledger_ids)
    internal = pair_internal_transfers(flows, ledger_set)

    layers: Dict[str, List[dict]] = {L1_EXTERNAL: [], L2_TRANSFER: [], L3_REALIZED: [], 'unknown': []}
    totals = {
        'deposit': 0.0,
        'withdraw': 0.0,
        'net_invested': 0.0,
        'buy': 0.0,
        'sell': 0.0,
        'dividend_cash': 0.0,
        'fees': 0.0,
        'cash_residual': 0.0,
    }
    for idx, flow in enumerate(flows):
        # 家庭内互转（#2681）：流水仍留在 L1 桶里便于诊断（`internal_transfer_indexes`
        # 与 `internal_transfer` 标记都能定位它），但**不进 totals**——
        # 「我一共投进去多少」不该被 A→B 的搬运抬高：真实外部入金 5 万 + A→B 划转 1 万，
        # 用户看到的累计入金必须是 5 万，不是 6 万。账户级（单账本传入）配不上对，
        # 行为不变；只有一次传入多个成员账本（组合级）才会命中。
        flow['internal_transfer'] = idx in internal
        layer = flow['layer']
        bucket = layers[layer] if layer in (L1_EXTERNAL, L2_TRANSFER, L3_REALIZED) else layers['unknown']
        bucket.append(flow)
        if flow['internal_transfer']:
            continue

        txn_type = flow['txn_type']
        amount = flow['amount']
        if txn_type == BusinessType.DEPOSIT.code:
            totals['deposit'] += amount
        elif txn_type == BusinessType.WITHDRAW.code:
            totals['withdraw'] += amount
        elif txn_type == BusinessType.BUY.code:
            totals['buy'] += amount
        elif txn_type == BusinessType.SELL.code:
            totals['sell'] += amount
        elif txn_type in (BusinessType.DIVIDEND.code, BusinessType.DIVIDEND_CASH.code):
            totals['dividend_cash'] += amount
        elif txn_type == BusinessType.TAX.code:
            totals['fees'] += amount
        if txn_type in _ACCOUNT_CASH_IN_TYPES:
            totals['cash_residual'] += amount
        elif txn_type in _ACCOUNT_CASH_OUT_TYPES:
            totals['cash_residual'] -= amount

    totals['net_invested'] = round(totals['deposit'] - totals['withdraw'], 2)
    for key in ('deposit', 'withdraw', 'buy', 'sell', 'dividend_cash', 'fees', 'cash_residual'):
        totals[key] = round(totals[key], 2)

    return {
        'l1': layers[L1_EXTERNAL],
        'l2': layers[L2_TRANSFER],
        'l3': layers[L3_REALIZED],
        'unknown': layers['unknown'],
        'internal_transfer_indexes': sorted(internal),
        'totals': totals,
        'basis_by_ledger': basis_by_ledger(flows, internal),
    }


def basis_by_ledger(flows: Sequence[dict], internal_indexes: Sequence[int] = ()) -> Dict[int, str]:
    """逐账户判定收益口径：有「真实外部入金/出金」→ `account`，否则 `position`。

    为什么要逐账户判定而不是整组合一刀切：真实数据里常混着两种账户——
    老账户只导过交易（没有入金流水），新账户认真记了入金。整组合按 `account` 算，
    老账户就丢了投入本金（现金流里只剩终端虚拟卖出 → 年化 0%，比原来更糟）。

    `position` = 沿用历史口径（买入当投入），是**缺数据时的降级**，不是等价方案；
    调用方应把 basis 透出到响应里，让页面能写「未记录入金，按买入成本估算」。
    """
    internal = set(internal_indexes)
    basis: Dict[int, str] = {}
    # 先给每个出现过的账户一个降级默认值，再把有真实外部资金流的改成 account——
    # 只写 account 键会让调用方分不清「没这个账户」和「这个账户没入金」。
    for flow in flows:
        basis.setdefault(flow['ledger_id'], 'position')
    for flow in flows:
        if flow['index'] in internal or flow['layer'] != L1_EXTERNAL:
            continue
        basis[flow['ledger_id']] = 'account'
    return basis
