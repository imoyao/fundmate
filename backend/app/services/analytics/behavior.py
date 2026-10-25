# -*- coding: utf-8 -*-
# Author : imoyao
"""交易行为画像（#994 模块一 · 账户级核心，#1986「结构性例外：永不退役项」）。

只吃**用户自己的 L1 流水**——盈米 MCP 结构上无法提供（看不到用户交易），
这正是「fundfof 花钱也买不到」的差异化锚点。XIRR 回答「年化多少」，本模块回答
「你是怎样的投资者」：胜率 / 盈亏比 / 平均持仓周期。

## 口径 v2（2026-10-17 真实库实测后修正，改动前先读）

1. **盈亏 = FIFO 配对自算，不读 `realized_pnl`**。
   真实库实测（主仓 invest.db 2026-10-17）：存量/导入流水的 `realized_pnl` **全为 0**
   （如 022365：买入 808373 分、卖出 698611 分，realized_pnl 仍 0）——写入侧结转
   只覆盖部分交易路径，0 与「真零盈亏」无法区分。故本模块自己配对：
   **配对盈亏 = 卖出回款 × (配对份额/卖出份额) − 配对买入成本份额摊销**
   （`amount` 列，分；买入 amount 为含费总投入、卖出为回款，费用差异不再单独摊，
   属可复核的近似口径，见 caveats）。
2. **观察单位 = 卖出笔**：一笔 sell 的配对盈亏合计 > 0 记胜。
   - **全额配对**（卖出份额全部找到买入批次）才进胜率/盈亏比样本——部分配对的
     未配对部分成本未知，摊进样本会偏；
   - 部分配对 / 无份额（quantity=0 的卖出，如场外转出）只进持仓周期（按已配对份额）
     并计数 `unmatched_sell_count`，**不编造成本**；
   - `withdraw` 是现金类取出，非平仓决策：不进盈亏样本、不参与配对。
3. **平均持仓周期**：FIFO 配对 buy / dividend_reinvest → sell，按配对份额加权平均自然日。
   - 进队：`buy`（申购/买入）、`dividend_reinvest`（再投增加份额，等价买入）。
     `deposit` 不进队（现金类无份额概念）。
   - 单位：`quantity` 存储单位 = 0.0001 份（整数），配对全程原始整数，无浮点误差。
   - 持有期 = 卖出确认日 − 买入确认日；`confirm_date` 缺失回退 `trade_date`；双方皆缺的
     批次不进周期（弹出队列防死循环）。
   - 同 symbol 多账户合并（产品级口径，与 `calculate_symbol_xirr` 同一收敛键）。
4. **分红单列**：`dividend_cash` 不是平仓决策，不进胜率样本，单列 `cash_dividend_total`（元）。
5. **is_income 排除**（#863）：收益发放行（渠道导入的收益）不是交易决策，一律排除。
6. 金额单位：流水侧 `amount` / `fee` 以**分**存储（列注释），出参一律**元**（round 2 位）；
   份额出参保持 0.0001 份整数原形态。

## #2619 增补指标（口径写死，便于手工复算）

| 指标 | 公式 / 边界 |
|---|---|
| `holding_days_p25/p50/p75` | 样本 = **每笔卖出**的份额加权持有天数（`Σ份额×天数 / 配对份额`）；`statistics.quantiles(n=4, method='inclusive')` 线性插值后**统一保留 1 位小数**（与 `avg_holding_days` 同精度，故 1.25 会显示 1.2）；样本 < 2 回 `None` |
| `avg_holding_days` | 全局份额加权（`Σ份额×天数 / Σ配对份额`），**不是**分位数的均值——两处分母不同，别互相校验 |
| `consecutive_add_count` | 同一标的**相邻两笔均为买入**（中间无卖出）且**不同一天**的对数；再投 `dividend_reinvest` 视为买入；**同日多笔视为一次建仓的拆单，不计加仓** |
| `rebuy_after_loss_count` | 某标的**全额配对且盈亏 < 0** 的卖出之后，该标的再次买入的次数；每次亏损卖出最多记一次（回补后标志清除，不重复计） |

⚠️ 两个「不做好坏评价」的边界：本模块只出统计量，**不输出**「换手过高」「追涨」这类
价值判断；也不做跨用户对比。

## 范围

本模块出**指标**；API 端点（Pro 面板模块一）由 Phase 2 后续卡接入 views。
"""

import statistics
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

_BUY_LOT_TYPES = frozenset({'buy', 'dividend_reinvest'})
_SELL_TYPE = 'sell'
_DIVIDEND_CASH_TYPE = 'dividend_cash'

_CAVEATS = [
    '盈亏按 买入→卖出 FIFO 配对自算（卖出回款−配对买入成本），不依赖流水结转字段',
    '手续费不单独摊销（买入 amount 为含费总投入、卖出为回款，费用已内含于近似口径）',
    '平均持仓周期按份额加权；导入前已有的持仓无买入流水，不参与',
]


def _txn_date(txn: Any) -> Optional[date]:
    """确认日优先、交易日兜底的日期部分（与 XIRR 用 confirm_date 同一语义）。"""
    d = getattr(txn, 'confirm_date', None) or getattr(txn, 'trade_date', None)
    if isinstance(d, datetime):
        d = d.date()
    return d


def _is_income_row(txn: Any) -> bool:
    # #863 收益行标记：NULL = 未标记（历史数据），仅 True 才排除
    return bool(getattr(txn, 'is_income', None))


def _empty_stats() -> Dict[str, Any]:
    """空形态：与 xirr 的 _empty_xirr_result 同风格，前端据此降级「—」。"""
    return {
        'closed_count': 0,  # 全额配对的卖出笔数（胜率/盈亏比样本量）
        'win_rate': None,
        'avg_win': None,
        'avg_loss': None,
        'profit_loss_ratio': None,
        'avg_holding_days': None,
        # #2619 持有期分位数：样本 = 每笔卖出（份额加权天数），与 avg_holding_days
        # 的「全局份额加权」口径不同——一个答「平均拿多久」，一个答「拿得久的有多久」。
        'holding_days_p25': None,
        'holding_days_p50': None,
        'holding_days_p75': None,
        'holding_days_samples': 0,
        # #2619 交易结构：连续加仓 = 同标的相邻两笔均买入的对数；
        # 割肉回补 = 亏损卖出之后同一标的再次买入的次数（每次亏损卖出最多记一次）。
        'consecutive_add_count': 0,
        'rebuy_after_loss_count': 0,
        'realized_pnl_total': None,  # Σ 配对盈亏（元），仅全额配对的卖出笔
        'cash_dividend_total': None,
        'buy_count': 0,
        'sell_count': 0,
        'unmatched_sell_count': 0,  # 部分配对/无份额的卖出笔数（不进盈亏样本）
        'unmatched_sell_shares': 0,  # 未配对卖出份额（0.0001 份）
        'caveats': list(_CAVEATS),
    }


def compute_behavior_stats(
    transactions: Sequence[Any],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """由已收敛的流水序列计算行为画像（纯函数，不碰 db、不做资产类型过滤）。

    Args:
        transactions: 流水对象序列，需具备 ``txn_type / quantity / amount /
            confirm_date / trade_date / is_income / symbol`` 属性（Transaction
            或同形态 duck-type）。收敛键（symbol 变体 + family）由调用方保证。
            内部按交易日升序重排，乱序输入安全。
        start_date / end_date: 可选统计窗口（YYYY-MM-DD，含边界）。**必须传全量
            流水**：窗口只决定「哪些事件计入统计」，FIFO 配对始终在全量序列上做
            ——否则窗口内卖出找不到窗口前的买入批次，持有期会整批丢失。

    Returns:
        见模块 docstring 口径 v2 与 :func:`_empty_stats` 结构。
    """
    win_start = date.fromisoformat(start_date) if start_date else None
    win_end = date.fromisoformat(end_date) if end_date else None

    def _in_window(d: Optional[date]) -> bool:
        if win_start is None and win_end is None:
            return True
        if d is None:
            return False  # 区间统计下无日期事件无法归位（全期模式仍纳入）
        if win_start is not None and d < win_start:
            return False
        if win_end is not None and d > win_end:
            return False
        return True

    # 按交易日升序：FIFO 依赖时间序，不信任调用方给的顺序（同日买卖次序不影响周期=0）
    ordered = sorted(
        (t for t in (transactions or []) if not _is_income_row(t) and getattr(t, 'txn_type', None)),
        key=lambda t: _txn_date(t) or date.min,
    )

    buy_count = 0
    sell_count = 0
    closed_count = 0
    unmatched_sell_count = 0
    unmatched_sell_shares = 0

    # FIFO 配对队列：symbol → [{'date': date, 'shares': int, 'cost': int}]
    # cost = 该批次含费总投入（分）；份额/成本缺失的批次只用于周期，不用于盈亏
    lots: Dict[str, List[Dict[str, Any]]] = {}

    closed_pnls: List[int] = []  # 全额配对卖出笔的盈亏（分）
    weighted_days = 0  # Σ(配对份额 × 持有天数)
    matched_shares = 0  # Σ 配对份额
    holding_samples: List[float] = []  # 每笔卖出一个样本（份额加权天数，#2619）
    last_was_buy: Dict[str, bool] = {}  # 同标的上一次成交是否买入（连续加仓）
    last_buy_date: Dict[str, Optional[date]] = {}  # 同标的上一次买入日（排除同日拆单）
    loss_pending_rebuy: Dict[str, bool] = {}  # 该标的上一次全额配对是亏损（待回补）
    consecutive_add_count = 0
    rebuy_after_loss_count = 0
    dividend_total = 0
    has_dividend = False

    for txn in ordered:
        txn_type = txn.txn_type

        if txn_type == _DIVIDEND_CASH_TYPE:
            has_dividend = True
            dividend_total += int(getattr(txn, 'amount', None) or 0)
            continue

        if txn_type in _BUY_LOT_TYPES:
            key = getattr(txn, 'symbol', None) or ''
            d = _txn_date(txn)
            in_window = _in_window(d)
            if in_window:
                buy_count += 1
            # 连续加仓：上一笔也是买入（中间没有卖出）且**不是同一天**⇒ 记一次。
            # 为什么排除同日：渠道导入常把一笔建仓拆成多条流水（真库实测同日多笔极多），
            # 不排除会把「一次建仓的拆单」读成「反复加仓」，指标直接失去信息量
            # （真库 812 笔买入曾算出 565 次加仓）。状态标志无条件维护。
            if in_window and last_was_buy.get(key) and last_buy_date.get(key) != d:
                consecutive_add_count += 1
            last_was_buy[key] = True
            last_buy_date[key] = d
            # 割肉回补：亏损卖出之后再次买入；每次亏损卖出最多记一次。
            # 无论是否在窗口内，这次买入都已消费掉「待回补」状态。
            if loss_pending_rebuy.get(key):
                if in_window:
                    rebuy_after_loss_count += 1
                loss_pending_rebuy[key] = False
            shares = int(getattr(txn, 'quantity', None) or 0)
            if shares > 0:
                lots.setdefault(key, []).append(
                    {'date': _txn_date(txn), 'shares': shares, 'cost': int(getattr(txn, 'amount', None) or 0)}
                )

        if txn_type != _SELL_TYPE:
            continue

        sell_shares = abs(int(getattr(txn, 'quantity', None) or 0))
        d = _txn_date(txn)
        key = getattr(txn, 'symbol', None) or ''
        in_window = _in_window(d)
        last_was_buy[key] = False
        if in_window:
            sell_count += 1
        queue = lots.get(key, [])

        matched = 0  # 本笔已配对份额
        cost = 0  # 配对部分的买入成本（分）
        days_weighted = 0  # 本笔的 Σ(份额×天数)
        fully_matched = sell_shares > 0  # qty=0 的卖出（场外转出等）永远非全额配对

        while matched < sell_shares and queue:
            lot = queue[0]
            take = min(sell_shares - matched, lot['shares'])
            if lot['date'] is not None and d is not None:
                days_weighted += take * max((d - lot['date']).days, 0)
            if lot['shares'] > 0 and lot['cost'] > 0:
                # 成本按份额摊销（整数地板除），摊多少扣多少——批次剩余份额缩小后
                # cost 必须同步扣减，否则下一批卖出会重复摊销整批成本（实测踩过）
                take_cost = lot['cost'] * take // lot['shares']
                cost += take_cost
                lot['cost'] -= take_cost
            else:
                fully_matched = False  # 批次无成本信息（amount 缺失）→ 盈亏不可算
            matched += take
            lot['shares'] -= take
            if lot['shares'] == 0:
                queue.pop(0)

        if in_window:
            unmatched_sell_shares += sell_shares - matched
        if matched > 0 and in_window:
            weighted_days += days_weighted
            matched_shares += matched
            # 分位数样本：本笔卖出的份额加权持有天数（每笔一个样本）
            holding_samples.append(days_weighted / matched)

        if sell_shares == 0 or matched < sell_shares or not fully_matched:
            if in_window:
                unmatched_sell_count += 1
            continue

        proceeds = int(getattr(txn, 'amount', None) or 0)
        pnl = proceeds - cost
        # 亏损卖出 ⇒ 该标的进入「待回补」状态（下次买入计一次割肉回补）。
        # 状态无条件更新：窗口外的亏损卖出同样是真实发生的「割肉」。
        loss_pending_rebuy[key] = pnl < 0
        if in_window:
            closed_pnls.append(pnl)
            closed_count += 1

    out = _empty_stats()
    out['buy_count'] = buy_count
    out['sell_count'] = sell_count
    out['closed_count'] = closed_count
    out['unmatched_sell_count'] = unmatched_sell_count
    out['unmatched_sell_shares'] = unmatched_sell_shares
    if has_dividend:
        out['cash_dividend_total'] = round(dividend_total / 100, 2)

    if closed_pnls:
        wins = [p for p in closed_pnls if p > 0]
        losses = [p for p in closed_pnls if p < 0]
        out['realized_pnl_total'] = round(sum(closed_pnls) / 100, 2)
        out['win_rate'] = round(len(wins) / len(closed_pnls) * 100, 2)
        if wins:
            out['avg_win'] = round(sum(wins) / len(wins) / 100, 2)
        if losses:
            out['avg_loss'] = round(sum(losses) / len(losses) / 100, 2)  # 负数
        if wins and losses:
            avg_win = sum(wins) / len(wins)
            avg_loss = abs(sum(losses) / len(losses))
            out['profit_loss_ratio'] = round(avg_win / avg_loss, 4) if avg_loss > 0 else None

    if matched_shares > 0:
        out['avg_holding_days'] = round(weighted_days / matched_shares, 1)

    # #2619 持有期分位数：样本 ≥ 2 才算（单样本分位数无意义，回 None 不造假）
    out['holding_days_samples'] = len(holding_samples)
    if len(holding_samples) >= 2:
        q25, q50, q75 = statistics.quantiles(holding_samples, n=4, method='inclusive')
        out['holding_days_p25'] = round(q25, 1)
        out['holding_days_p50'] = round(q50, 1)
        out['holding_days_p75'] = round(q75, 1)

    out['consecutive_add_count'] = consecutive_add_count
    out['rebuy_after_loss_count'] = rebuy_after_loss_count

    logger.debug(
        f'行为画像：平仓 {closed_count} 笔 / 胜率 {out["win_rate"]} / '
        f'持有期 {out["avg_holding_days"]} 天 / 未配对卖出 {unmatched_sell_count} 笔'
    )
    return out


def build_symbol_behavior(
    db,
    symbol: str,
    family_id: int = 1,
    include_cash_equivalents: bool = False,
) -> Dict[str, Any]:
    """产品级行为画像：跨账户按 symbol 收敛流水（与 ``calculate_symbol_xirr`` 同口径）。

    收敛键 = 持仓真实写法变体（``symbol_scope.collect_transaction_symbol_variants``，
    #1966/#1972 同一真相源）；资产类型过滤与 XIRR 三个 scope 同一套
    ``EXCLUDED_ASSET_TYPES``。symbol 级口径不做市场消歧（与 XIRR 同边界）。
    """
    from app.core.asset_types import EXCLUDED_ASSET_TYPES
    from app.domains.transactions.models import Transaction
    from app.services.symbol_scope import collect_transaction_symbol_variants, query_positions_by_symbol

    if not symbol:
        raise ValueError('缺少 symbol 参数')

    positions = query_positions_by_symbol(db, symbol, family_id=family_id)
    symbols = collect_transaction_symbol_variants(symbol, positions)

    txn_q = db.query(Transaction).filter(Transaction.family_id == family_id, Transaction.symbol.in_(symbols))
    if not include_cash_equivalents:
        # NULL 的 asset_type 默认视为投资类资产，纳入计算（与 XIRR 同口径）
        txn_q = txn_q.filter(Transaction.asset_type.is_(None) | Transaction.asset_type.not_in(EXCLUDED_ASSET_TYPES))
    transactions = txn_q.all()

    logger.debug(f'产品级行为画像(symbol={symbol})：持仓行 {len(positions)}，流水 {len(transactions)} 笔')
    return compute_behavior_stats(transactions)
