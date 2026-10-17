# -*- coding: utf-8 -*-
"""清仓周期统计（#2131 · 账本对齐 A' 卡）——从 L1 流水聚合「首买→末卖」周期。

WHY
    单笔已实现盈亏记在流水上（`transactions.realized_pnl`，#1183），清仓时持仓行被
    delete（`position_service.process_sell_or_withdraw`），记在持仓上会随之丢失——故
    「这一轮投资整体赚了多少」只能从流水聚合。本模块回答的正是这个问题：按
    「清仓周期」（首买 → 末卖，份额归零即周期关闭）给出累计已实现盈亏 / 胜率 /
    盈亏比 / 平均持有天数 / 交易次数，并跨全部已清仓标的出汇总。

与 `analytics/behavior.py` 的分工（#994 定稿口径，勿造第二套）：

- behavior 的观察单位是 **FIFO 卖出笔**（一笔 sell 的配对盈亏记一个样本），服务
  产品详情页 Pro 卡（单 symbol）；
- 本模块的观察单位是 **清仓周期**（一个持仓生命周期记一个样本），服务全账户
  「清仓复盘」列表 + 汇总。一轮周期里可以有多笔买卖，FIFO 配对引擎同源。

口径（全部随值下发 caveats，用户换个参数要能对上账）：

1. **盈亏 = FIFO 配对自算，不读 `realized_pnl` 列**——与 behavior 口径 v2 同一
   理由：2026-10-17 真库实测存量/导入流水该列全为 0，与「真零盈亏」不可区分。
2. **周期边界**：`buy` / `dividend_reinvest`（份额>0）入队即开周期；`sell` 按 FIFO
   配对消耗份额，**队列耗尽即关周期**（与 `trade_timeline` 的 `closed=True` 同源）。
   数据末尾队列仍非空 = 仍在持有，**不产出**（只统计已清仓周期）。
3. **部分配对不编造成本**：卖出份额 > 可配份额（存量迁移形态：先卖后买、无买入
   流水）或买入批次 `amount` 缺失时，该周期标 `pnl_known=False`，仍展示但不进
   胜率/盈亏比样本（与 behavior 的 `unmatched_sell_count` 同纪律）。
4. **现金分红单列**：`dividend_cash` 与历史码 `dividend` 都认（真机两码并存，
   #2171 实测 69/66 笔），计入所属周期窗口的 `dividend_total`，**不进盈亏样本**
   （分红不是平仓决策）。
5. **`is_income` 收益行一律排除**（#863）；**类现金资产默认排除**
   （`EXCLUDED_ASSET_TYPES`：货基/逆回购/cash，与 behavior/XIRR 同一套），
   传 `include_cash_equivalents=True` 才纳入。
6. **symbol 收敛**：清仓后持仓行已删，无法经持仓侧归一（`symbol_scope` 两步法
   依赖持仓行），故分组键直接用 `symbol_identity(symbol, asset_type)`（#1662
   单一真相源，吃流水自带的 asset_type 快照）——同一标的的写法变体（实测
   `HK00700` / `00700.HK`）归为一轮；跨市场同 digits 的不同产品（如指数与股票）
   身份键不同、不合并。多账户合并（产品级口径，与 behavior/XIRR 一致）。

单位：流水侧 amount/fee 为**分**、份额为 0.0001 份整数；出参一律**元**（round 2）、
日期 ISO 字符串。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from app.core.symbol_utils import strip_exchange_prefix, symbol_identity

# 入队的份额增加类型（deposit 不进队：现金类无份额概念，与 behavior 同口径）
_BUY_LOT_TYPES = frozenset({'buy', 'dividend_reinvest'})
_SELL_TYPE = 'sell'
# 现金分红：历史码 dividend + 新码 dividend_cash 并存（#2171 实测）
_DIVIDEND_TYPES = frozenset({'dividend', 'dividend_cash'})

_CENTS_PER_YUAN = 100

_CAVEATS = [
    '盈亏按 FIFO 配对自算（卖出回款−配对买入成本），不读流水 realized_pnl 列（存量库该列全 0）',
    '周期 = 首买→份额归零；数据末尾仍持有的标的未完结，不产出',
    '部分配对（先卖后买/无买入流水）的周期不进胜率与盈亏比样本',
    '现金分红单列不计入盈亏样本；symbol 按归一身份键分组（#1662，吃流水 asset_type 快照）',
]


def _txn_date(txn: Any) -> Optional[date]:
    """确认日优先、交易日兜底（与 behavior/XIRR 同一语义）。"""
    d = getattr(txn, 'confirm_date', None) or getattr(txn, 'trade_date', None)
    if isinstance(d, datetime):
        d = d.date()
    return d


def _is_income_row(txn: Any) -> bool:
    # #863 收益行标记：NULL = 未标记（历史数据），仅 True 才排除
    return bool(getattr(txn, 'is_income', None))


def _group_key(txn: Any) -> str:
    """周期分组键 = symbol 归一身份键（#1662 单一真相源），异常退字面量。

    为什么不能按字面量（或只剥前缀）分组：同一标的的写法变体在流水里**真实并存**
    （端到端实测：买入写 `HK00700`、卖出写 `00700.HK`），字面量分组会把一轮周期
    劈成两半、卖出变成「无周期可归集」。清仓后持仓行已删，走不了
    `symbol_scope` 的「持仓侧两步法」，故直接用流水自带的 `asset_type` 快照做
    身份归一（与 `positions.symbol_norm` 同一个函数、同一套口径）。
    """
    raw = getattr(txn, 'symbol', None) or ''
    if not raw:
        return ''
    try:
        return symbol_identity(raw, getattr(txn, 'asset_type', None)) or raw
    except Exception:  # noqa: BLE001 — 归一失败退字面量，不让整个聚合失败
        return raw


def _yuan(cents: Optional[int]) -> Optional[float]:
    if cents is None:
        return None
    return round(cents / _CENTS_PER_YUAN, 2)


def _new_cycle(symbol: str, name: Optional[str], first_buy: date, number: int) -> Dict[str, Any]:
    return {
        'symbol': symbol,
        'name': name,
        'cycle_number': number,
        'first_buy_date': first_buy,
        'last_sell_date': None,
        'buy_count': 0,
        'sell_count': 0,
        'trade_count': 0,
        'total_buy_cents': 0,
        'total_sell_cents': 0,
        'matched_cost_cents': 0,
        'realized_pnl_cents': None,
        'dividend_cents': 0,
        'weighted_days': 0,
        'matched_shares': 0,
        'partial': False,
    }


def compute_cleared_cycles(transactions: Sequence[Any]) -> List[Dict[str, Any]]:
    """由流水序列聚合清仓周期（纯函数，不碰 db、不做资产类型过滤）。

    Args:
        transactions: 具备 ``txn_type / quantity / amount / confirm_date /
            trade_date / is_income / symbol`` 属性的对象序列（Transaction 或
            同形态 duck-type）。内部按交易日升序重排，乱序输入安全；按
            ``strip_exchange_prefix(symbol)`` 分组，多账户合并。

    Returns:
        周期 dict 列表（出参单位见模块 docstring），按 ``last_sell_date`` 降序。
    """
    ordered = sorted(
        (t for t in (transactions or []) if not _is_income_row(t) and getattr(t, 'txn_type', None)),
        key=lambda t: _txn_date(t) or date.min,
    )

    queues: Dict[str, List[Dict[str, Any]]] = {}  # group → FIFO 批次 [{'date','shares','cost'}]
    cycles: Dict[str, List[Dict[str, Any]]] = {}  # group → 已关闭周期
    open_cycle: Dict[str, Optional[Dict[str, Any]]] = {}  # group → 进行中周期
    unmatched_sells = 0

    for txn in ordered:
        txn_type = txn.txn_type
        key = _group_key(txn)
        if not key:
            continue  # symbol 缺失无法归属，跳过（不静默计入任何组）
        d = _txn_date(txn)
        cycle = open_cycle.get(key)

        if txn_type in _DIVIDEND_TYPES:
            # 现金分红：计入当前周期窗口（若有），不进配对、不进样本
            if cycle is not None:
                cycle['dividend_cents'] += int(getattr(txn, 'amount', None) or 0)
            continue

        if txn_type in _BUY_LOT_TYPES:
            shares = int(getattr(txn, 'quantity', None) or 0)
            amount = int(getattr(txn, 'amount', None) or 0)
            if shares <= 0:
                continue  # qty=0 的“买入”（异常/导入噪声）：不占份额、不开周期
            if cycle is None:
                # 开周期：首买日、序号按该 group 已关闭周期数递增
                number = len(cycles.get(key, [])) + 1
                cycle = _new_cycle(getattr(txn, 'symbol', None) or key, getattr(txn, 'position_name', None), d, number)
                open_cycle[key] = cycle
            cycle['buy_count'] += 1
            cycle['trade_count'] += 1
            cycle['total_buy_cents'] += amount
            # 展示名/名称取最近一次写（流水快照可能比开周期时更完整）
            if getattr(txn, 'position_name', None):
                cycle['name'] = txn.position_name
            if getattr(txn, 'symbol', None):
                cycle['symbol'] = txn.symbol
            queues.setdefault(key, []).append({'date': d, 'shares': shares, 'cost': amount})
            continue

        if txn_type != _SELL_TYPE:
            continue  # deposit/withdraw/拆分/兑付/扣税/其他：不进 share 周期口径

        sell_shares = abs(int(getattr(txn, 'quantity', None) or 0))
        if sell_shares == 0:
            # 场外转出等无份额卖出：不可配对、不关周期，也不污染周期盈亏样本
            # （与 behavior 同口径：只进 unmatched 计数）
            unmatched_sells += 1
            continue

        if cycle is None:
            # 无进行中周期的卖出（存量迁移：先卖后买/无买入流水）→ 无周期可归集
            unmatched_sells += 1
            continue

        cycle['sell_count'] += 1
        cycle['trade_count'] += 1
        cycle['total_sell_cents'] += int(getattr(txn, 'amount', None) or 0)
        if getattr(txn, 'position_name', None):
            cycle['name'] = txn.position_name
        if getattr(txn, 'symbol', None):
            cycle['symbol'] = txn.symbol

        queue = queues.setdefault(key, [])
        matched = 0
        cost = 0
        days_weighted = 0
        fully_matched = True
        while matched < sell_shares and queue:
            lot = queue[0]
            take = min(sell_shares - matched, lot['shares'])
            if lot['date'] is not None and d is not None:
                days_weighted += take * max((d - lot['date']).days, 0)
            if lot['shares'] > 0 and lot['cost'] > 0:
                # 成本按份额摊销，批次剩余成本同步扣减（behavior 同款，防重复摊销）
                take_cost = lot['cost'] * take // lot['shares']
                cost += take_cost
                lot['cost'] -= take_cost
            else:
                fully_matched = False  # 批次无成本信息 → 盈亏不可算
            matched += take
            lot['shares'] -= take
            if lot['shares'] == 0:
                queue.pop(0)

        cycle['weighted_days'] += days_weighted
        cycle['matched_shares'] += matched
        cycle['matched_cost_cents'] += cost
        if matched < sell_shares or not fully_matched:
            cycle['partial'] = True

        if not queue:
            # 份额归零 → 周期关闭。盈亏 = 本轮全部卖出回款 − 本轮全部配对成本
            # （非 partial 周期下每笔 sell 均全额配对，故总额口径与逐笔累计等价）
            if not cycle['partial']:
                cycle['realized_pnl_cents'] = cycle['total_sell_cents'] - cycle['matched_cost_cents']
            cycle['last_sell_date'] = d
            cycles.setdefault(key, []).append(cycle)
            open_cycle[key] = None

    result: List[Dict[str, Any]] = []
    for group_cycles in cycles.values():
        for c in group_cycles:
            result.append(
                {
                    'symbol': c['symbol'],
                    'name': c['name'],
                    'cycle_number': c['cycle_number'],
                    'first_buy_date': c['first_buy_date'].isoformat() if c['first_buy_date'] else None,
                    'last_sell_date': c['last_sell_date'].isoformat() if c['last_sell_date'] else None,
                    'buy_count': c['buy_count'],
                    'sell_count': c['sell_count'],
                    'trade_count': c['trade_count'],
                    'total_buy_amount': _yuan(c['total_buy_cents']),
                    'total_sell_amount': _yuan(c['total_sell_cents']),
                    'realized_pnl': _yuan(c['realized_pnl_cents']),
                    'pnl_pct': (
                        round(c['realized_pnl_cents'] / c['matched_cost_cents'] * 100, 2)
                        if c['realized_pnl_cents'] is not None and c['matched_cost_cents'] > 0
                        else None
                    ),
                    'avg_holding_days': (
                        round(c['weighted_days'] / c['matched_shares'], 1) if c['matched_shares'] > 0 else None
                    ),
                    'dividend_total': _yuan(c['dividend_cents']) if c['dividend_cents'] else None,
                    'pnl_known': c['realized_pnl_cents'] is not None,
                    'caveats': list(_CAVEATS),
                }
            )

    result.sort(key=lambda c: (c['last_sell_date'] or '', c['symbol'] or ''), reverse=True)
    logger.debug(f'清仓周期聚合：{len(result)} 个已关闭周期，未归集卖出 {unmatched_sells} 笔')
    return result


def summarize_cycles(cycles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """跨周期汇总：胜率 / 盈亏比 / 平均持有天数 / 累计已实现盈亏。

    样本口径与 behavior 对齐：仅 `pnl_known=True` 的周期进胜率/盈亏比；
    零盈亏周期计样本不计胜负；无亏损笔时盈亏比回 None（不输出 Infinity）。
    """
    known = [c for c in (cycles or []) if c.get('pnl_known')]
    wins = [c for c in known if (c.get('realized_pnl') or 0) > 0]
    losses = [c for c in known if (c.get('realized_pnl') or 0) < 0]
    holding = [c['avg_holding_days'] for c in known if c.get('avg_holding_days') is not None]

    win_rate = round(len(wins) / len(known) * 100, 2) if known else None
    profit_loss_ratio = None
    if wins and losses:
        avg_win = sum(c['realized_pnl'] for c in wins) / len(wins)
        avg_loss = abs(sum(c['realized_pnl'] for c in losses) / len(losses))
        profit_loss_ratio = round(avg_win / avg_loss, 4) if avg_loss > 0 else None

    return {
        'cycle_count': len(cycles or []),
        'sample_count': len(known),
        'win_count': len(wins),
        'loss_count': len(losses),
        'win_rate': win_rate,
        'profit_loss_ratio': profit_loss_ratio,
        'avg_holding_days': round(sum(holding) / len(holding), 1) if holding else None,
        'realized_pnl_total': round(sum(c['realized_pnl'] for c in known), 2) if known else None,
        'total_trade_count': sum(c.get('trade_count') or 0 for c in (cycles or [])),
        'caveats': list(_CAVEATS),
    }


def build_cleared_cycles(
    db,
    family_id: int = 1,
    *,
    ledger_id: Optional[int] = None,
    symbol: Optional[str] = None,
    include_cash_equivalents: bool = False,
) -> Dict[str, Any]:
    """db 入口：按家庭取流水，聚合清仓周期 + 汇总。

    Args:
        db: 会话（transactions/positions 同库）。
        family_id: 家庭作用域（视图层经 ``get_family_id()`` 注入）。
        ledger_id: 可选，限定单账户；不传 = 家庭全部账户合并（产品级口径）。
        symbol: 可选，单标的过滤。按**归一身份键**匹配（与周期分组口径一致）：
            查询 ``00700.HK`` 可命中存成 ``HK00700`` 的流水，反之亦然。
            在 Python 侧过滤而非 SQL——``transactions`` 只有字面量 symbol、
            没有 symbol_norm 列，SQL 里做不了归一（#1662 同款约束）。
        include_cash_equivalents: 是否纳入类现金资产（默认排除，同 behavior/XIRR）。

    Returns:
        ``{'cycles': [...], 'summary': {...}}``。
    """
    from app.core.asset_types import EXCLUDED_ASSET_TYPES
    from app.domains.transactions.models import Transaction

    query = db.query(Transaction).filter(Transaction.family_id == family_id)
    if ledger_id is not None:
        query = query.filter(Transaction.ledger_id == ledger_id)
    if not include_cash_equivalents:
        # NULL 的 asset_type 默认视为投资类资产，纳入计算（与 behavior 同口径）
        query = query.filter(Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES))

    transactions = query.all()
    if symbol:
        # 双轨匹配：身份键相等（同场所同代码，如 HK00700 ↔ 00700.HK），
        # 或剥前缀字面量相等（查询侧没有 asset_type、定不了场所，如 600519 ↔ SH600519）。
        # 代价是跨场所同 digits 的不同产品会被一起命中——与分组口径的合并范围一致，可接受。
        try:
            wanted_identity = symbol_identity(symbol) or symbol
        except Exception:  # noqa: BLE001 — 归一失败退字面量
            wanted_identity = symbol
        wanted_stripped = strip_exchange_prefix(symbol)
        transactions = [
            t
            for t in transactions
            if _group_key(t) == wanted_identity or strip_exchange_prefix(getattr(t, 'symbol', None) or '') == wanted_stripped
        ]
    logger.debug(f'清仓周期聚合(family={family_id}, ledger={ledger_id})：候选流水 {len(transactions)} 笔')
    cycles = compute_cleared_cycles(transactions)
    return {'cycles': cycles, 'summary': summarize_cycles(cycles)}
