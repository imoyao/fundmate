# -*- coding: utf-8 -*-
"""红利税扫描与分诊（2026-11-08 从 `dividend_tax_service` 拆出）。

为什么单独一个模块：**「怎么判断该不该提醒」与「提醒怎么落库」是两件事**。
混在一个文件里既顶破 services 体量闸门（`scripts/guard_service_size.py`），
也让口径调整（本次）和写入路径改动互相牵制。

制度依据、为什么不做自动算税、分诊表与三条刻意的取舍，都写在
`dividend_tax_service` 的模块 docstring 里——那是给读代码的人看的说明，
不重复到本文件，免得两处漂移。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.domains.reconciliation.models import DividendTaxAck
from app.domains.transactions.models import Transaction
from app.services.dividend_tax_rules import is_dividend_income, position_asset_types, resolve_asset_type

# 只看最近 N 天的分红：更早的税早已在券商交割单里结清，催一年以上的旧账没有意义。
DEFAULT_LOOKBACK_DAYS = 400
# 配对窗口的**基准**宽度：扣税流水允许落在分红日之后多少天内。
# 券商实务：红利税多在红利发放后数日到数周内补扣，一周是常态。
# 太窄会把「已扣过」判成「没扣」（多提醒，用户翻一次交割单就关）；
# 太宽会把上一季的扣税串到这一笔上（漏提醒，钱就这么少记了）。
# 故取 30 天：覆盖「次月合并扣」这个最常见的形态。
DEFAULT_TAX_WINDOW_DAYS = 30
# 卖出结算宽限：扣税实际发生在**卖出时**（101 号文），券商当日或 T+1/T+2 从资金账户
# 扣收。窗口上限因此取 `max(分红日 + 30 天, 末次卖出日 + 5 天)`——
# 「持有大半年、卖出才扣」的场景靠后半段兜住，而卖出发生在 30 天内的场景不放大窗口
# （保持既有用例与既有误报边界不变）。
TAX_SETTLE_GRACE_DAYS = 5
# 持股超过一年即免税（财税〔2015〕101 号）。用「最早取得日 → 分红日」的间隔近似，
# 不是 FIFO 精确值（本系统没有 lot 账）。偏差方向**倾向判免税**：宁可少记一笔税
# （用户看得见「这儿没记」），不要多记一笔假的（用户以为算过了）。
EXEMPT_HOLDING_DAYS = 365
# 只对「分红金额够大」的笔做「比例异常」复核：几块钱的分红扣了几毛钱，
# 比例算出来 12% 还是 8% 都不说明问题，提示只会让人烦。
SUSPECT_MIN_DIVIDEND_CENTS = 10_000  # 100 元
# 已记税的占分红比例超过这个阈值 ⇒ 提示复核。
# **这不是税率**：真实税率取决于买入批次持有期，本系统算不出来（见模块 docstring）。
# 这里只回答一个更粗的问题——「这笔扣税大到不像红利税，是不是记错了品种？」
# 20% 是差异化税率的**上限**，超过它就不可能是红利税。
SUSPECT_RATIO_THRESHOLD = 0.20

# 分红 / 免税口径与关键词表见 `app/services/dividend_tax_rules.py`（纯规则单独成模块）。
# 归入「同一账户」的兜底键：账户为空（手动记账 / 老数据）时，空账户之间互相匹配。
_EMPTY_ACCOUNT = ''

# 四种状态，只有 `STATUS_PENDING` / `STATUS_SUSPECT` 进待办（其余两种只是告诉用户
# 「系统看过了、此刻按制度不用处理」）。
# 2026-11-08 前只有一个 `'未扣'`，把「法定暂缓」与「真漏记」混成一类，
# 于是每一笔还没卖出的分红都在催用户——那是系统错，不是用户漏。
STATUS_DEFERRED = '暂不扣税'
STATUS_EXEMPT = '依法免税'
STATUS_PENDING = '待核对'
STATUS_SUSPECT = '已记-比例异常'


@dataclass(frozen=True)
class PendingTaxItem:
    """一笔现金分红的扣税核对结果。

    粒度是**一笔分红**（不是「某标的某年」）：用户拿着对账单一条条扫，
    提醒里说得出「哪一天、多少钱」才有用；说「该标的今年有 3 笔共 1200 元未扣税」
    等于让他自己再数一遍。
    """

    symbol: str
    name: str
    account_name: str
    year: int
    status: str
    dividend_cents: int
    dividend_on: Optional[date]
    tax_cents: int
    tax_on: Optional[date]

    @property
    def ratio_pct(self) -> Optional[float]:
        """已记税占分红的百分比（无分红金额时为 None，不做除零）。"""
        if self.dividend_cents <= 0 or self.tax_cents <= 0:
            return None
        return round(self.tax_cents * 100.0 / self.dividend_cents, 1)

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'account_name': self.account_name,
            'year': self.year,
            'status': self.status,
            'dividend_cents': self.dividend_cents,
            'dividend_on': self.dividend_on.isoformat() if self.dividend_on else None,
            'tax_cents': self.tax_cents,
            'tax_on': self.tax_on.isoformat() if self.tax_on else None,
            'ratio_pct': self.ratio_pct,
        }


@dataclass(frozen=True)
class DividendTaxScan:
    """一次扫描的完整结果：待办 + 两类「按制度此刻不用处理」的分红。

    为什么不只返回待办：域 E 需要把「系统看过了，但按 101 号文派息时本就不扣」
    告诉用户。全藏起来会让人以为分红没被识别（owner 就曾对着「只有红利入账」怀疑
    系统漏记）；全列进待办又会让这个列表永远清不完——那才是真正的噪音。
    """

    items: list[PendingTaxItem]
    deferred: list[PendingTaxItem]
    exempt: list[PendingTaxItem]

    @property
    def deferred_count(self) -> int:
        return len(self.deferred)

    @property
    def exempt_count(self) -> int:
        return len(self.exempt)

    @property
    def deferred_dividend_cents(self) -> int:
        return sum(i.dividend_cents for i in self.deferred)

    @property
    def exempt_dividend_cents(self) -> int:
        return sum(i.dividend_cents for i in self.exempt)


def _event_date(txn: Transaction) -> Optional[date]:
    """流水发生日：确认日优先，未确认退回交易日（与 `dividend_service` 同口径）。"""
    if txn.confirm_date is not None:
        return txn.confirm_date
    if txn.trade_date is None:
        return None
    return txn.trade_date.date() if isinstance(txn.trade_date, datetime) else txn.trade_date


def _key_of(txn: Transaction) -> tuple[str, str]:
    """(标的, 账户) 配对键——与 `_match_taxes` 里的键完全同源，避免两处口径分叉。"""
    return ((txn.symbol or '').strip(), txn.account_name or _EMPTY_ACCOUNT)


def _item_of(div: Transaction, status: str, tax: Optional[Transaction] = None) -> PendingTaxItem:
    """把一条分红流水（+ 可选的已配对扣税流水）摊成一条展示项。"""
    div_day = _event_date(div)
    return PendingTaxItem(
        symbol=(div.symbol or '').strip(),
        name=div.position_name or '',
        account_name=div.account_name or '',
        year=div_day.year if div_day else 0,
        status=status,
        dividend_cents=int(div.amount or 0),
        dividend_on=div_day,
        tax_cents=abs(int(tax.amount or 0)) if tax is not None else 0,
        tax_on=_event_date(tax) if tax is not None else None,
    )


def _sell_days_by_key(db: Session, family_id: int) -> dict[tuple[str, str], list[date]]:
    """(标的, 账户) → 卖出日升序。

    这是整套判据的支点：101 号文规定派息时暂不扣缴、**转让时才结算**，
    所以「分红日之后有没有卖出过」直接决定了这一刻该不该有扣税流水。
    """
    rows = db.query(Transaction).filter(Transaction.family_id == family_id, Transaction.txn_type == 'sell').all()
    out: dict[tuple[str, str], list[date]] = {}
    for txn in rows:
        day = _event_date(txn)
        if day is None:
            continue
        out.setdefault(_key_of(txn), []).append(day)
    for days in out.values():
        days.sort()
    return out


def _first_holding_day_by_key(db: Session, family_id: int) -> dict[tuple[str, str], date]:
    """(标的, 账户) → 最早取得日，用于「是否已持有超一年」的粗判。

    取值优先级：持仓快照的 `confirm_date`（从券商持仓导入，能覆盖比流水更早的历史）
    → 账内最早一笔买入。两者都没有 ⇒ 不出现在结果里 ⇒ 调用方按「判不准」处理，
    请用户对照交割单（而不是替他猜）。
    """
    out: dict[tuple[str, str], date] = {}
    for symbol, account, confirm_date in (
        db.query(Position.symbol, Position.account_name, Position.confirm_date)
        .filter(Position.family_id == family_id, Position.symbol.isnot(None))
        .all()
    ):
        if confirm_date is None:
            continue
        bare = (symbol or '').strip()
        if not bare:
            continue
        key = (bare, account or _EMPTY_ACCOUNT)
        current = out.get(key)
        if current is None or confirm_date < current:
            out[key] = confirm_date
    for txn in db.query(Transaction).filter(Transaction.family_id == family_id, Transaction.txn_type == 'buy').all():
        day = _event_date(txn)
        if day is None:
            continue
        key = _key_of(txn)
        current = out.get(key)
        if current is None or day < current:
            out[key] = day
    return out


def _acked_keys(db: Session, family_id: int) -> set[tuple[str, str, date]]:
    """用户已确认「这笔分红无需记账」的键集合（与 `PendingTaxItem` 的身份同源）。"""
    rows = (
        db.query(DividendTaxAck.symbol, DividendTaxAck.account_name, DividendTaxAck.dividend_on)
        .filter(DividendTaxAck.family_id == family_id)
        .all()
    )
    return {
        ((symbol or '').strip(), account or _EMPTY_ACCOUNT, day) for symbol, account, day in rows if day is not None
    }


def _reinvest_group_ids(db: Session, family_id: int) -> set[str]:
    """红利再投的配对组（与 `dividend_service._reinvest_group_ids` 同一判据）。

    再投是「分红 + 申购」双流水，其中分红那一笔 `txn_type` 同样是 `dividend`。
    不排除它，就会把再投也算成「该扣税却没扣」——而再投本就没有现金到手。
    """
    rows = (
        db.query(Transaction.link_group_id)
        .filter(
            Transaction.family_id == family_id,
            Transaction.txn_type == 'buy',
            Transaction.link_group_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return {gid for (gid,) in rows if gid}


def _tax_buckets(taxes: list[Transaction]) -> dict[tuple[str, str], list[Transaction]]:
    """扣税流水按 (标的, 账户) 分桶，桶内按日期升序、同额按金额降序。

    只收**金额为负**的流水：正的 `dividend_tax` 多半是导入时把符号弄反了，
    拿它来配对会把一笔支出当成收入抵掉。
    """
    buckets: dict[tuple[str, str], list[Transaction]] = {}
    for tax in taxes:
        if _event_date(tax) is None or int(tax.amount or 0) >= 0:
            continue
        buckets.setdefault(_key_of(tax), []).append(tax)
    for bucket in buckets.values():
        bucket.sort(key=lambda t: (_event_date(t) or date.min, -abs(int(t.amount or 0))))
    return buckets


def _window_candidates(
    bucket: list[Transaction],
    consumed: set[int],
    div_day: date,
    window_end: date,
) -> list[Transaction]:
    """落在配对窗口内、且还没被别的分红用掉的扣税流水。"""
    return [
        tax
        for tax in bucket
        if id(tax) not in consumed and (day := _event_date(tax)) is not None and div_day <= day <= window_end
    ]


def _pick_tax(div_amount: int, candidates: list[Transaction]) -> Transaction:
    """优先选「金额不超过这笔分红」且金额最接近的那笔（避免小额分红吃掉大额税）。

    都超过时退回金额最小的那笔——它至少同键同在窗口内，比不配更接近事实。
    """
    within = [tax for tax in candidates if abs(int(tax.amount or 0)) <= div_amount]
    pool = within or candidates
    pool.sort(
        key=lambda tax: (
            abs(abs(int(tax.amount or 0)) - div_amount),
            _event_date(tax) or date.min,
        )
    )
    return pool[0]


def _is_suspect(div_amount: int, tax_amount: int) -> bool:
    """扣税金额是否大到不可能是红利税（超过 20% 上限）。"""
    return div_amount >= SUSPECT_MIN_DIVIDEND_CENTS and abs(tax_amount) > div_amount * SUSPECT_RATIO_THRESHOLD


def _match_taxes(
    dividends: list[Transaction],
    taxes: list[Transaction],
    window_days: int,
    *,
    window_end_by_div: Optional[dict[int, date]] = None,
) -> tuple[dict[int, Transaction], list[tuple[Transaction, Transaction]]]:
    """把扣税流水配对到分红流水上。

    返回 `(分红 id → 配到的扣税流水, [(分红, 扣税), …])`，后者是「配上了但比例异常」
    的候选。

    配对规则（不猜券商怎么合并的）：

    - 只配「同一标的 + 同一账户 + 扣税日 ∈ [分红日, 窗口上限]」；
    - 窗口上限默认 `分红日 + window_days`；已卖出过的分红由调用方通过
      `window_end_by_div` 传入「末次卖出日 + 结算宽限」，覆盖「持有大半年、
      卖出时才扣」的场景；
    - 各笔扣税**只能用一次**（按金额大小顺序消耗），金额相等不是必要条件
      （合并扣税是常态）；
    - 分红按金额降序配对：100 + 500 元两笔分红、合并扣 60 元时，应先结清大额那笔
      ——税是按股息金额收的，先贴给小额会把大额的税「藏」在尾巴里。
    """
    matched: dict[int, Transaction] = {}
    consumed: set[int] = set()
    suspect: list[tuple[Transaction, Transaction]] = []
    buckets = _tax_buckets(taxes)
    windows = window_end_by_div or {}

    for div in sorted(dividends, key=lambda d: (-int(d.amount or 0), _event_date(d) or date.min)):
        div_day = _event_date(div)
        if div_day is None:
            continue
        window_end = windows.get(div.id) or (div_day + timedelta(days=window_days))
        candidates = _window_candidates(buckets.get(_key_of(div), []), consumed, div_day, window_end)
        if not candidates:
            continue
        div_amount = int(div.amount or 0)
        picked = _pick_tax(div_amount, candidates)
        consumed.add(id(picked))
        matched[div.id] = picked
        if _is_suspect(div_amount, int(picked.amount or 0)):
            suspect.append((div, picked))
    return matched, suspect


def _collect_rows(
    rows: list[Transaction],
    *,
    reinvest_groups: set[str],
    position_types: dict[str, str],
    since: date,
) -> tuple[list[Transaction], list[Transaction]]:
    """把原始流水分成「待判定的现金分红」与「扣税流水」两堆（过滤规则全在这里）。"""
    dividends: list[Transaction] = []
    taxes: list[Transaction] = []
    for txn in rows:
        occurred = _event_date(txn)
        if occurred is None:
            continue
        if not (txn.symbol or '').strip():
            # 无代码的流水对不上任何持仓/事件，提醒也提醒不到有意义的东西
            continue
        if txn.txn_type == 'dividend_tax':
            taxes.append(txn)
            continue
        if txn.link_group_id and txn.link_group_id in reinvest_groups:
            continue
        if int(txn.amount or 0) <= 0:
            continue
        if occurred < since:
            continue
        asset_type = resolve_asset_type(txn.symbol, txn.asset_type, position_types)
        if not is_dividend_income(txn, asset_type):
            continue
        dividends.append(txn)
    return dividends, taxes


def _partition_by_sell(
    dividends: list[Transaction],
    sell_days: dict[tuple[str, str], list[date]],
    window_days: int,
) -> tuple[list[Transaction], list[PendingTaxItem], dict[int, date]]:
    """按「分红之后有没有卖出过」分诊。

    返回 `(需要配对的分红, 暂不扣税的展示项, 每笔分红的配对窗口上限)`。

    这是整套判据的支点：101 号文规定派息时暂不扣缴、**转让时才结算**，
    没卖过的分红此刻没有税是法定的，不是用户漏记（2026-11-08 之前最大的误报源）。
    """
    to_match: list[Transaction] = []
    deferred: list[PendingTaxItem] = []
    windows: dict[int, date] = {}
    for div in dividends:
        div_day = _event_date(div)
        if div_day is None:
            continue
        later_sells = [d for d in sell_days.get(_key_of(div), ()) if d > div_day]
        if not later_sells:
            deferred.append(_item_of(div, STATUS_DEFERRED))
            continue
        to_match.append(div)
        # 窗口上限取两者较大：卖出在 30 天内不放大窗口（保持既有边界），
        # 卖出在几个月后的场景由「末次卖出日 + 结算宽限」兜住。
        windows[div.id] = max(
            div_day + timedelta(days=window_days),
            max(later_sells) + timedelta(days=TAX_SETTLE_GRACE_DAYS),
        )
    return to_match, deferred, windows


def _build_items(
    to_match: list[Transaction],
    matched: dict[int, Transaction],
    suspect_ids: set[int],
    first_days: dict[tuple[str, str], date],
    acked: set[tuple[str, str, date]],
) -> tuple[list[PendingTaxItem], list[PendingTaxItem]]:
    """把配对结果摊成 `(待办项, 依法免税项)`。已结清的不进任何列表。"""
    items: list[PendingTaxItem] = []
    exempt: list[PendingTaxItem] = []
    for div in to_match:
        div_day = _event_date(div)
        tax = matched.get(div.id)
        if tax is not None:
            if div.id in suspect_ids:
                items.append(_item_of(div, STATUS_SUSPECT, tax))
            continue
        first_day = first_days.get(_key_of(div))
        if first_day is not None and div_day is not None and (div_day - first_day).days > EXEMPT_HOLDING_DAYS:
            # 持股明显超过一年 ⇒ 依法免税，卖出时也不会补扣
            exempt.append(_item_of(div, STATUS_EXEMPT))
            continue
        if div_day is not None:
            ack_key = ((div.symbol or '').strip(), div.account_name or _EMPTY_ACCOUNT, div_day)
            if ack_key in acked:
                # 用户已确认「这笔确实没有税」，不再打扰
                continue
        items.append(_item_of(div, STATUS_PENDING))
    return items, exempt


def scan_dividend_tax(
    db: Session,
    family_id: int,
    *,
    today: Optional[date] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    window_days: int = DEFAULT_TAX_WINDOW_DAYS,
) -> DividendTaxScan:
    """扫一遍红利税：待办 + 暂不扣税 + 依法免税（纯读、无副作用）。

    分诊顺序很重要：**先按「分红之后有没有卖出过」把不需要配对的分红摘出去**，
    再对剩下的做扣税配对。反过来会让未卖出分红的空档期去消耗同标的的扣税流水
    （`_match_taxes` 按金额降序消耗），把本该结清的那笔挤成待办。
    """
    today = today or date.today()
    since = today - timedelta(days=lookback_days)

    rows = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.txn_type.in_(('dividend', 'dividend_tax')),
        )
        .all()
    )
    if not rows:
        return DividendTaxScan([], [], [])

    dividends, taxes = _collect_rows(
        rows,
        reinvest_groups=_reinvest_group_ids(db, family_id),
        position_types=position_asset_types(db, family_id),
        since=since,
    )
    to_match, deferred, windows = _partition_by_sell(dividends, _sell_days_by_key(db, family_id), window_days)
    matched, suspect_pairs = _match_taxes(to_match, taxes, window_days, window_end_by_div=windows)
    items, exempt = _build_items(
        to_match,
        matched,
        {div.id for div, _ in suspect_pairs},
        _first_holding_day_by_key(db, family_id),
        _acked_keys(db, family_id),
    )
    for bucket in (items, deferred, exempt):
        bucket.sort(key=lambda i: (i.dividend_on or date.min, i.symbol), reverse=True)
    return DividendTaxScan(items, deferred, exempt)


def scan_pending_tax(
    db: Session,
    family_id: int,
    *,
    today: Optional[date] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    window_days: int = DEFAULT_TAX_WINDOW_DAYS,
) -> list[PendingTaxItem]:
    """待办清单（`待核对` + `已记-比例异常`），按分红日降序。

    只返回**需要用户动作**的项。「暂不扣税 / 依法免税 / 已确认无需记账」不在其中
    ——它们是结论，不是待办。要看全貌用 `scan_dividend_tax`。
    """
    return scan_dividend_tax(
        db,
        family_id,
        today=today,
        lookback_days=lookback_days,
        window_days=window_days,
    ).items
