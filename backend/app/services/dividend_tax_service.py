# -*- coding: utf-8 -*-
"""红利税「待补记」识别（#541）——**只提醒，不自动算税**。

## 为什么不做自动扣税

A 股股息红利税是**差异化**的：按「买入批次实际持有期」在**卖出时**补扣
（≤1 个月 20% / 1 个月~1 年 10% / >1 年 0）。要算准它，必须知道每笔分红对应的
每一份股份是哪天买的——那是 lot 级批次账，本系统从未建立（`transactions` 只有
聚合持仓 + 流水，`positions` 只有成本均价）。

在聚合持仓上按某个税率反推，产出的不是「税」，而是一个**会被交易所按先进先出
否掉的猜测数字**。加上一个猜出来的负数进账本，比不记更糟：它会污染已实现盈亏、
股息率与 XIRR，且用户无从分辨哪笔是券商真值、哪笔是我们编的。

## 这一层做什么

只回答两个用户自己能判断的问题：

1. **「哪一笔现金分红，还没有对应的扣税流水？」** → 该补记（`status='未扣'`）；
2. **「哪一笔已经记了税，但扣的明显不像红利税？」** → 该核对（`status='已记-比例异常'`）。

判据（全部是账内已有的事实，不做任何外部推断）：

- 取该家庭的 `txn_type='dividend'` 现金分红（红利再投不算、债券/存款派息不算）；
- 对**每笔分红**（不是每年聚合）找「同一标的 + 同一账户 + 扣税日落在分红日之后
  N 天内」的 `dividend_tax` 流水，按金额从大到小逐笔配对；
- 配上了 ⇒ 这笔已结清；配不上 ⇒ 这笔该补记。

## 三个刻意的口径选择

- **按笔、不按年**（2026-10-19 修正，此前是按年）：按年匹配会让「今年已经扣过一次」
  把整年的分红都当成已结清——于是第二次分红要等到明年才会被看见，
  而这正是用户投诉的「过了几个月才提醒，这消息有什么价值」。逐笔匹配才谈得上及时。
  代价是券商的合并扣税会留下几笔「没配上」的尾巴，见下条。
- **合并扣税不猜对应关系**：券商的「股息红利差异扣税」常把多笔分红合成一条，
  单笔金额对不上是常态。故配对判据**不看金额是否相等**，只看「同标的同账户、
  扣税日在分红日之后 N 天内、金额还没被别的分红用光」。这对「A 分红 100 元、
  B 分红 500 元、合并扣税 60 元」会把更大的那笔当已结清、更小的那笔继续提醒——
  这是有意的：**两笔里必有一笔没对上，用户去交割单看一眼就能收尾**，
  比整年装死好。宁可多提醒一次（用户看一眼就关），不可漏提醒一笔（钱就少记了）。
- **只认「分红类」现金流入**：`txn_type='dividend'` 是个大杂烩，同花顺的
  「利息归本」「债券兑息」「转股零款」「配股退款退息」全落成它，而
  「债券兑息兑付」甚至被映射成 `dividend_tax`。不排掉这些，用户会被推着去
  给一笔存款利息补红利税——提醒一次错的就是在教用户不信任提醒。
  判据用两样账内事实：标的资产类型（`positions.asset_type` / 流水 `asset_type`）
  与操作名关键词（`notes`）。
- **只看现金分红**：红利再投已经改变了份额，不产生现金，也就没有「该扣的现金税」。

## 与 `dividend_service` 的关系

`dividend_service` 是分红**统计**的唯一归口（净分红 = 现金 + 再投 − 税），
本模块是它**输入侧的核对**：告诉用户「净分红这个数还缺一块税」。
两者不互相调用，都直接读 `transactions`，避免统计口径被提醒逻辑改写。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.constants import THS_OP_TYPE_MAP
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

# 通知来源标识（写入 notifications.source_type）
SOURCE_TYPE = 'dividend_tax_pending'  # 有一笔分红还没记扣税
SOURCE_TYPE_SUSPECT = 'dividend_tax_suspect'  # 已记扣税，但金额占分红比例异常

# 级别：P1（消息盒 + 首页未读计数）。钱的事值得看见，但不至于占首页横栏挤掉紧急项。
REMINDER_LEVEL = 'P1'
# 只看最近 N 天的分红：更早的税早已在券商交割单里结清，催一年以上的旧账没有意义。
DEFAULT_LOOKBACK_DAYS = 400
# 扣税流水允许落在分红日之后多少天内（同一天记的算在窗口内）。
# 券商实务：红利税多在红利发放后数日到数周内补扣，一周是常态。
# 太窄会把「已扣过」判成「没扣」（多提醒，用户翻一次交割单就关）；
# 太宽会把上一季的扣税串到这一笔上（漏提醒，钱就这么少记了）。
# 故取 30 天：覆盖「次月合并扣」这个最常见的形态。
DEFAULT_TAX_WINDOW_DAYS = 30
# 只对「分红金额够大」的笔做「比例异常」复核：几块钱的分红扣了几毛钱，
# 比例算出来 12% 还是 8% 都不说明问题，提示只会让人烦。
SUSPECT_MIN_DIVIDEND_CENTS = 10_000  # 100 元
# 已记税的占分红比例超过这个阈值 ⇒ 提示复核。
# **这不是税率**：真实税率取决于买入批次持有期，本系统算不出来（见模块 docstring）。
# 这里只回答一个更粗的问题——「这笔扣税大到不像红利税，是不是记错了品种？」
# 20% 是差异化税率的**上限**，超过它就不可能是红利税。
SUSPECT_RATIO_THRESHOLD = 0.20

# 分红类流入的白名单关键词：操作名（`notes`）里出现这些才算「分红 / 派息」。
# 取自 `core/constants.THS_OP_TYPE_MAP` 里落成 `dividend` 的六个操作名，
# 外加「利息」——存款/理财利息也被映射成 dividend，这里用「含利息 ⇒ 排除」反着用。
_DIVIDEND_KEYWORDS = ('红利', '分红', '派息', '股息', '兑息')
# 非分红类的关键词：命中即排除（利息 / 兑付 / 退款 / 零款）。
_NOT_DIVIDEND_KEYWORDS = ('利息', '兑付', '退款', '退息', '零款', '兑息')
# 不给红利税补记提示的资产类型：可转债（`bond`）的派息是利息，货基/逆回购同理。
_NO_DIVIDEND_TAX_ASSET_TYPES = frozenset({'bond', 'money_fund', 'reverse_repo', 'cash', 'bank'})
# 归入「同一账户」的兜底键：账户为空（手动记账 / 老数据）时，空账户之间互相匹配。
_EMPTY_ACCOUNT = ''

STATUS_PENDING = '未扣'
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


def _event_date(txn: Transaction) -> Optional[date]:
    """流水发生日：确认日优先，未确认退回交易日（与 `dividend_service` 同口径）。"""
    if txn.confirm_date is not None:
        return txn.confirm_date
    if txn.trade_date is None:
        return None
    return txn.trade_date.date() if isinstance(txn.trade_date, datetime) else txn.trade_date


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


def _position_asset_types(db: Session, family_id: int) -> dict[str, str]:
    """标的代码 → 资产类型（持仓表快照；流水自带 `asset_type` 时优先用流水的）。"""
    rows = (
        db.query(Position.symbol, Position.asset_type)
        .filter(Position.family_id == family_id, Position.symbol.isnot(None))
        .all()
    )
    return {symbol: asset_type for symbol, asset_type in rows if symbol}


def _is_dividend_income(txn: Transaction, asset_type: Optional[str]) -> bool:
    """这笔 `txn_type='dividend'` 是不是「该考虑红利税」的那一类现金分红。

    三道判据（任一命中即排除）：

    1. 资产类型是债 / 货基 / 逆回购 / 存款——它们的派息是利息，与红利税无关；
    2. 操作名里含「利息 / 兑付 / 退款 / 退息 / 零款」——同花顺把这些也映射成 dividend；
    3. 操作名里既没有「红利 / 分红 / 派息 / 股息 / 兑息」，也不是空（手动记账常写
       「现金分红」，含「分红」二字）。
    """
    if asset_type and asset_type in _NO_DIVIDEND_TAX_ASSET_TYPES:
        return False
    notes = (txn.notes or '').strip()
    if notes:
        # 注：`_DIVIDEND_KEYWORDS` 里也含「兑息」（基金/债券的派息说法），所以
        # 排除表里必须显式带上「兑息」并**先判**——顺序不能反，否则「债券兑息」
        # 会走成「这是分红」。
        if any(word in notes for word in _NOT_DIVIDEND_KEYWORDS):
            return False
        return any(word in notes for word in _DIVIDEND_KEYWORDS)
    # 手动记账 / 未标 notes 的分红：默认算分红（宁可提醒，不可漏）
    return True


def compute_import_hash(symbol: str, confirm_date: Optional[date]) -> str:
    """自动生成的扣税流水用的事件幂等键（`transactions.import_hash`）。

    为什么不复用 `build_dedup_key`：`import_hash` 列长 64、且落在
    `uq_txn_import_hash` 唯一约束上（含 `COALESCE(ledger_id, -1)` 哨兵），
    与通知的 `dedup_key`（最长 120，带业务日期）是两家事，不能混用。

    键里**不含金额**：同一标的同一天只会扣一次红利税，金额若参与键，
    用户改一次金额就能再生成一条，幂等就白做了。也不含持有份额——
    份额变了那笔税也不会变（同 `dividend_split_job` 的事件键口径）。
    """
    day = (confirm_date or date.today()).isoformat()
    return f'dividend_tax|{symbol}|{day}'


def _match_taxes(
    dividends: list[Transaction],
    taxes: list[Transaction],
    window_days: int,
) -> tuple[dict[int, Transaction], list[tuple[Transaction, Transaction]]]:
    """把扣税流水配对到分红流水上。

    返回 `(分红 id → 消耗掉的扣税笔列表的首笔, [(分红, 扣税), …])`，后者的第二项是
    「配上了但比例异常」的候选。

    配对规则（不猜券商怎么合并的）：

    - 只配「同一标的 + 同一账户 + 扣税日 ∈ [分红日, 分红日 + window_days]」；
    - 分红按日期升序、扣税按日期升序，各笔扣税**只能用一次**（用金额做额度，
      扣税金额可以从多笔分红里「花掉」，直到花光）；
    - 金额相等不是必要条件（合并扣税是常态），但**优先消耗金额最接近的那笔**，
      避免「100 元的分红先吃掉一笔 60 元税」，把更该配的那笔留成尾巴。
    """
    matched: dict[int, Transaction] = {}
    consumed: set[int] = set()
    suspect: list[tuple[Transaction, Transaction]] = []

    taxes_by_key: dict[tuple[str, str], list[Transaction]] = {}
    for tax in taxes:
        tax_day = _event_date(tax)
        if tax_day is None or int(tax.amount or 0) >= 0:
            continue
        key = ((tax.symbol or '').strip(), tax.account_name or _EMPTY_ACCOUNT)
        taxes_by_key.setdefault(key, []).append(tax)
    for bucket in taxes_by_key.values():
        bucket.sort(key=lambda t: (_event_date(t) or date.min, -abs(int(t.amount or 0))))

    # 分红按**金额降序**配对：合并扣税（如 100 + 500 元两笔、合并扣 60 元）应优先结清
    # 大额那笔——税是按股息金额收的，先贴给小额会把大额的税「藏」在尾巴里。
    # 同额再按日期升序，保证同输入的配对结果稳定（用例与回放都要可复现）。
    for div in sorted(dividends, key=lambda d: (-int(d.amount or 0), _event_date(d) or date.min)):
        div_day = _event_date(div)
        if div_day is None:
            continue
        key = ((div.symbol or '').strip(), div.account_name or _EMPTY_ACCOUNT)
        candidates = [
            t
            for t in taxes_by_key.get(key, ())
            if id(t) not in consumed
            and (d := _event_date(t)) is not None
            and div_day <= d <= div_day + timedelta(days=window_days)
        ]
        if not candidates:
            continue
        div_amount = int(div.amount or 0)
        # 优先选「金额不超过这笔分红」的最近一笔；都超了就选金额最小的（它至少同键同日）
        within = [t for t in candidates if abs(int(t.amount or 0)) <= div_amount]
        pool = within or candidates
        pool.sort(key=lambda t: (abs(abs(int(t.amount or 0)) - div_amount), _event_date(t) or date.min))
        picked = pool[0]
        consumed.add(id(picked))
        matched[div.id] = picked
        if (
            div_amount >= SUSPECT_MIN_DIVIDEND_CENTS
            and abs(int(picked.amount or 0)) > div_amount * SUSPECT_RATIO_THRESHOLD
        ):
            suspect.append((div, picked))
    return matched, suspect


def scan_pending_tax(
    db: Session,
    family_id: int,
    *,
    today: Optional[date] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    window_days: int = DEFAULT_TAX_WINDOW_DAYS,
) -> list[PendingTaxItem]:
    """列出需要用户看一眼的红利税项（未扣 + 比例异常），按分红日降序。

    纯读、无副作用——对账台直接展示、通知生成直接消费。
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
        return []

    reinvest_groups = _reinvest_group_ids(db, family_id)
    position_types = _position_asset_types(db, family_id)

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
        asset_type = txn.asset_type or position_types.get((txn.symbol or '').strip())
        if not _is_dividend_income(txn, asset_type):
            continue
        dividends.append(txn)

    matched, suspect_pairs = _match_taxes(dividends, taxes, window_days)
    suspect_ids = {div.id for div, _ in suspect_pairs}

    items: list[PendingTaxItem] = []
    for div in dividends:
        div_day = _event_date(div)
        tax = matched.get(div.id)
        if tax is None:
            items.append(
                PendingTaxItem(
                    symbol=(div.symbol or '').strip(),
                    name=div.position_name or '',
                    account_name=div.account_name or '',
                    year=div_day.year if div_day else 0,
                    status=STATUS_PENDING,
                    dividend_cents=int(div.amount or 0),
                    dividend_on=div_day,
                    tax_cents=0,
                    tax_on=None,
                )
            )
        elif div.id in suspect_ids:
            items.append(
                PendingTaxItem(
                    symbol=(div.symbol or '').strip(),
                    name=div.position_name or '',
                    account_name=div.account_name or '',
                    year=div_day.year if div_day else 0,
                    status=STATUS_SUSPECT,
                    dividend_cents=int(div.amount or 0),
                    dividend_on=div_day,
                    tax_cents=abs(int(tax.amount or 0)),
                    tax_on=_event_date(tax),
                )
            )
    items.sort(key=lambda i: (i.dividend_on or date.min, i.symbol), reverse=True)
    return items


def _short(date_value: Optional[date]) -> str:
    return date_value.strftime('%m-%d') if date_value else '—'


def build_notification_candidates(
    items: Iterable[PendingTaxItem],
    *,
    today: Optional[date] = None,
) -> list[dict]:
    """把待处理项转成 `notification_service.emit_many` 的候选（不写库）。

    粒度是**每笔分红一条**，dedup_key = `来源:标的:分红日`，**不含今天**——
    用户已经看过这个消息，明天不该再冒出来一条一模一样的。
    这就是「及时性」与「幂等性」同时成立的做法：新分红 ⇒ 新键 ⇒ 立刻提醒；
    同一笔分红 ⇒ 同一键 ⇒ 永远只提醒一次。
    """
    day = today or date.today()
    del day  # 键里刻意不带今天，见 docstring；保留参数是为了对齐 emit 侧的签名习惯
    candidates: list[dict] = []
    for item in items:
        label = item.name or item.symbol
        account = f'（{item.account_name}）' if item.account_name else ''
        if item.status == STATUS_SUSPECT:
            ratio = item.ratio_pct or 0.0
            candidates.append(
                {
                    'level': REMINDER_LEVEL,
                    'category': 'system',
                    'title': f'扣税金额待核对：{label} {item.dividend_on or ""}'.strip(),
                    'body': (
                        f'{label}{account} 在 {_short(item.dividend_on)} 的现金分红 '
                        f'{item.dividend_cents / 100:.2f} 元，'
                        f'配到的扣税流水为 {item.tax_cents / 100:.2f} 元（{ratio:.1f}%）。'
                        f'红利税上限为 20%，这笔看起来更像别的品种的费用（如债券利息的税）。'
                        f'请核对一下是不是记错了品种——提醒只做核对，不改账。'
                    ),
                    'dedup_key': f'{SOURCE_TYPE_SUSPECT}:{item.symbol}:{item.dividend_on.isoformat() if item.dividend_on else "?"}',
                    'source_type': SOURCE_TYPE_SUSPECT,
                    'source_key': item.symbol,
                }
            )
            continue
        candidates.append(
            {
                'level': REMINDER_LEVEL,
                'category': 'system',
                'title': (f'分红未记扣税：{label} {_short(item.dividend_on)} 红利 {item.dividend_cents / 100:.2f} 元'),
                'body': (
                    f'{label}{account} 在 {item.dividend_on.isoformat() if item.dividend_on else "—"} '
                    f'有一笔现金分红 {item.dividend_cents / 100:.2f} 元，'
                    f'账上没有与之对应的红利税流水。'
                    f'A 股红利税按实际持股期在卖出时补扣，本系统不自动推算'
                    f'（税率取决于买入批次，而账上只有聚合持仓）。'
                    f'若券商交割单里有扣税记录，请在流水中补记一笔「扣税」；'
                    f'没有（持股超一年）就可以忽略这条。'
                ),
                'dedup_key': f'{SOURCE_TYPE}:{item.symbol}:{item.dividend_on.isoformat() if item.dividend_on else "?"}',
                'source_type': SOURCE_TYPE,
                'source_key': item.symbol,
            }
        )
    return candidates


def refresh_reminders(
    db: Session,
    family_id: int,
    *,
    today: Optional[date] = None,
) -> int:
    """扫一次「未记扣税 / 扣税存疑」并写入站内通知，返回**新建**条数。

    为什么做成显式 refresh 而不是「查通知列表时顺带生成」：写副作用不该藏在 GET 里
    ——GET 会被预取 / 重试，把写放在 GET 上迟早会生成意料之外的消息
    （与 `strategy_engine/allocation.py` 的 `refresh_reminders` 同一取舍）。
    触发点有两处：对账台域 E 的读取（用户主动查账）、导入完成后（刚记完必然要看）。

    导入置于函数内：`notification_service` 与本模块同属 services 层，顶层互引会在
    将来调整包结构时触发循环导入。
    """
    from app.services import notification_service  # noqa: PLC0415

    items = scan_pending_tax(db, family_id, today=today)
    candidates = build_notification_candidates(items, today=today)
    return notification_service.emit_many(db, family_id, candidates)


def pending_after_import(
    db: Session,
    family_id: int,
    symbol: str,
    *,
    today: Optional[date] = None,
) -> list[PendingTaxItem]:
    """导入完成后立刻问一句：这只标的还有没有漏记的税。

    导入是「用户刚刚面对过交割单」的时刻——此时提醒的命中率最高；
    等到第二天定时任务再冒出来，用户早就想不起那张单子长什么样了。
    """
    symbol = (symbol or '').strip()
    if not symbol:
        return []
    return [i for i in scan_pending_tax(db, family_id, today=today) if i.symbol == symbol]


def is_tax_import_note(note: str) -> bool:
    """操作名是不是「红利税」类（导入链路据此跳过即时提醒）。

    纯字符串判据、无外部依赖，供 `orchestrator_commit` 在确认导入后决定
    「要不要马上跑一次复核」——刚导入的就是那笔税，此时提醒只会自相矛盾。
    """
    raw = (note or '').strip()
    if not raw:
        return False
    if THS_OP_TYPE_MAP.get(raw) == 'tax':
        return True
    return bool(re.search(r'红利|股息', raw)) and bool(re.search(r'扣税|差异|纳税|税费', raw))


def record_tax(
    db: Session,
    family_id: int,
    *,
    symbol: str,
    amount_cents: int,
    tax_on: Optional[date] = None,
    account_name: str = '',
) -> Transaction:
    """为用户补记一笔红利税流水（`txn_type='dividend_tax'`，金额取负）。

    为什么要有这个入口：原来的设计是「提醒你自己去流水页记一笔」，可红利税在
    导出对账单里往往是一条独立的「股息红利差异扣税」，多数用户并不打算为此
    打开记账表单填六个字段。提醒里给一个按钮，这件事才会被真的做掉——
    没被做的提醒等于没提醒。

    **幂等**由两样东西共同保证（不是"先查再插"）：

    1. `import_hash = compute_import_hash(symbol, tax_on)` 落在
       `uq_txn_import_hash` 唯一约束上 ⇒ 同标的同一天重复提交直接撞约束；
    2. 撞约束时通过 `IntegrityError` 兜底并返回既有那笔（语义 = 「这笔已经记过了」），
       而不是报错。**不用「先查后插」**：两个标签页同时点，先查后插会双双查空。

    金额符号：`amount` 存负数（与 `orchestrator_commit` 落库口径一致，
    `dividend_service` 的净分红也是这么减的）。调用方传正数即可。
    """
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    symbol = (symbol or '').strip()
    if not symbol:
        raise ValueError('缺少标的代码')
    if amount_cents <= 0:
        raise ValueError('税额必须大于 0')
    tax_on = tax_on or date.today()
    import_hash = compute_import_hash(symbol, tax_on)

    existing = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.import_hash == import_hash,
        )
        .first()
    )
    if existing is not None:
        return existing

    position = (
        db.query(Position)
        .filter(Position.family_id == family_id, Position.symbol == symbol)
        .order_by(Position.id.desc())
        .first()
    )
    txn = Transaction(
        position_id=position.id if position else None,
        symbol=symbol,
        txn_type='dividend_tax',
        trade_date=datetime.combine(tax_on, datetime.min.time()),
        confirm_date=tax_on,
        quantity=0,
        price=0,
        fee=0,
        amount=-abs(int(amount_cents)),
        status='success',
        entry_status='orphan' if position is None else None,
        position_name=(position.name if position else '') or symbol,
        account_name=account_name or (position.account_name if position else '') or '',
        ledger_id=position.ledger_id if position else None,
        asset_type=position.asset_type if position else None,
        notes='红利税补记',
        import_hash=import_hash,
        family_id=family_id,
    )
    # savepoint 隔离：撞唯一约束时只回滚这一条，不动本请求事务里已经落好的其它写
    # （`db.rollback()` 会把整个 `user_session()` 事务一起抹掉 —— AGENTS.md 记过这个坑）。
    try:
        with db.begin_nested():
            db.add(txn)
    except IntegrityError:
        # 并发提交：另一个请求先落库了同一键，交回既有那笔（语义 = 「已经记过了」）
        again = (
            db.query(Transaction)
            .filter(
                Transaction.family_id == family_id,
                Transaction.import_hash == import_hash,
            )
            .first()
        )
        if again is None:  # pragma: no cover - 约束冲突却查不到，属数据异常
            raise
        return again
    return txn


def record_tax_from_payload(db: Session, family_id: int, payload: dict) -> dict:
    """把 API 的 payload 规整成 `record_tax` 的参数并落库（#541）。

    为什么解析放这里不放视图：`scripts/check_view_thickness.py` 判的是「视图只做
    HTTP 编排，业务规则下沉 services」。`amount_cents` / `amount`（元）二选一、
    `tax_on` 的日期格式、"税额必须为正" 全属于**业务校验**，不是 HTTP 编排——
    留在视图里，视图就会随每次口径调整继续变厚（本次实测 419 行 > 基线 311）。
    """
    raw_cents = payload.get('amount_cents')
    raw_yuan = payload.get('amount')
    if raw_cents is None and raw_yuan is None:
        raise ValueError('缺少金额（amount 或 amount_cents）')
    try:
        amount_cents = int(raw_cents) if raw_cents is not None else Money.yuan_to_cents(float(raw_yuan))
    except (TypeError, ValueError):
        raise ValueError('金额格式不正确') from None

    tax_on: Optional[date] = None
    raw_day = payload.get('tax_on')
    if raw_day:
        try:
            tax_on = datetime.strptime(str(raw_day), '%Y-%m-%d').date()
        except ValueError:
            raise ValueError('tax_on 必须是 YYYY-MM-DD') from None

    txn = record_tax(
        db,
        family_id,
        symbol=str(payload.get('symbol') or '').strip(),
        amount_cents=amount_cents,
        tax_on=tax_on,
        account_name=str(payload.get('account_name') or ''),
    )
    return {
        'id': txn.id,
        'symbol': txn.symbol,
        'amount_cents': txn.amount,
        'confirm_date': txn.confirm_date.isoformat() if txn.confirm_date else None,
    }
