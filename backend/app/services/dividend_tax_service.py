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

## 关键制度事实（2026-11-08 修正，此前判据与它冲突）

- 财税〔2015〕101 号：持股 >1 年**免税**；≤1 个月实际税负 20%；1 个月~1 年 10%。
- **派息时一律暂不扣缴**——对持股 1 年以内（含）的，上市公司暂不扣，待个人
  **转让股票时**才由中登按持股期计算、券商从资金账户扣收；持股超 1 年的，卖出时也不扣。
- 财税〔2002〕128 号：个人从**基金**分配中取得的收入暂不征个税（该优惠经
  财政部 税务总局公告 2018 年第 177 号确认继续有效）。

推论：「分红之后没有扣税流水」在**卖出之前是法定常态**，不是漏记。
2026-11-08 之前的判据是「分红日起 30 天内配不到扣税流水 ⇒ 待补记」，于是：

1. 对**任何尚未卖出**的分红误报（owner 用海大集团 30 元红利复现：派息时本就不扣）；
2. 30 天窗口假定扣税紧跟分红，而实际可能在持有 11 个月后卖出时才扣 ⇒ 已卖出的也漏配；
3. 免税品种漏了 `fund` ⇒ 基金/ETF 分红全部误报。

## 这一层做什么（按「是否已卖出」分诊）

对每笔现金分红，先问一个**账内可确定**的问题：该标的该账户在分红日之后有没有卖出过？

| 情形 | 交割单 | 结论 | 进待办 |
|---|---|---|---|
| 未卖出 | 只有红利 | `暂不扣税`（法定暂缓） | 否 |
| 已卖出，持股 >1 年 | 无税 | `依法免税` | 否 |
| 已卖出，持股 ≤1 年 | 有税 | 已结清 | 否 |
| 已卖出，持股 ≤1 年 | 无税 | `待核对`（漏导入 / 券商未扣） | 是 |
| 用户已确认无需记账 | — | 不显示（`dividend_tax_acks`） | 否 |

只有第四行需要用户动作。判据全部来自账内事实（`txn_type='sell'` 的日期、资产类型、
已存在的确认记录），**不做外部推断**。

### 为什么这条分诊不需要 lot 账

「没卖出 ⇒ 一定没扣」是 101 号文给的**确定性**，与 FIFO 无关。
只有「已卖出」才轮到持股期，而那时直接看交割单里有没有那笔税即可——系统只做
匹配、不做推算。持股期只用于一个**粗判**（`EXEMPT_HOLDING_DAYS`）：
明显超过一年就不打扰用户，判不准就请用户核对。粗判的偏差方向是**倾向判免税**，
与下面「宁可少记一笔税，不要多记一笔假税」的取舍一致。

## 三个刻意的口径选择

- **按笔、不按年**（2026-10-19 修正，此前是按年）：按年匹配会让「今年已经扣过一次」
  把整年的分红都当成已结清——于是第二次分红要等到明年才会被看见，
  而这正是用户投诉的「过了几个月才提醒，这消息有什么价值」。逐笔匹配才谈得上及时。
- **合并扣税不猜对应关系**：券商的「股息红利差异扣税」常把多笔分红合成一条，
  单笔金额对不上是常态。故配对判据**不看金额是否相等**，只看「同标的同账户、
  扣税日落在配对窗口内、金额还没被别的分红用光」。窗口上限取
  `max(分红日 + 30 天, 末次卖出日 + 5 天)`：前者覆盖「次月合并扣」，
  后者覆盖「持有大半年、卖出时才扣」。对「A 分红 100 元、B 分红 500 元、合并扣税
  60 元」会把更大的那笔当已结清、更小的那笔继续提醒——这是有意的：
  **两笔里必有一笔没对上，用户去交割单看一眼就能收尾**，
  比整年装死好。宁可多提醒一次（用户看一眼就关），不可漏提醒一笔（钱就少记了）。
- **只认「分红类」现金流入**：`txn_type='dividend'` 是个大杂烩，同花顺的
  「利息归本」「债券兑息」「转股零款」「配股退款退息」全落成它，而
  「债券兑息兑付」甚至被映射成 `dividend_tax`。不排掉这些，用户会被推着去
  给一笔存款利息补红利税——提醒一次错的就是在教用户不信任提醒。
  判据用两样账内事实：标的资产类型（`positions.asset_type` / 流水 `asset_type`）
  与操作名关键词（`notes`）。基金（含场内 ETF）按 128 号文整类豁免，见
  `dividend_tax_rules.NO_DIVIDEND_TAX_ASSET_TYPES`。
- **只看现金分红**：红利再投已经改变了份额，不产生现金，也就没有「该扣的现金税」。

## 与 `dividend_service` 的关系

`dividend_service` 是分红**统计**的唯一归口（净分红 = 现金 + 再投 − 税），
本模块是它**输入侧的核对**：告诉用户「净分红这个数还缺一块税」。
两者不互相调用，都直接读 `transactions`，避免统计口径被提醒逻辑改写。
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.reconciliation.models import DividendTaxAck
from app.domains.transactions.ledger_guard import dividend_tax_source_fields
from app.domains.transactions.models import Transaction
from app.services.dividend_tax_scan import (
    STATUS_PENDING,
    STATUS_SUSPECT,
    PendingTaxItem,
    scan_dividend_tax,
    scan_pending_tax,
)
from app.services.importer.mappings import THS_OP_MAP, BusinessType

# 对外契约保留在这里：调用方（视图 / 测试 / 导入钩子）历来从本模块 import，
# 扫描逻辑搬家不该让它们跟着改。新增的 `STATUS_DEFERRED` / `STATUS_EXEMPT`
# 只用于展示，不从这里导出。
__all__ = [
    'SOURCE_TYPE',
    'SOURCE_TYPE_SUSPECT',
    'REMINDER_LEVEL',
    'STATUS_PENDING',
    'STATUS_SUSPECT',
    'PendingTaxItem',
    'ack_dividend_tax',
    'ack_from_payload',
    'build_notification_candidates',
    'compute_import_hash',
    'is_tax_import_note',
    'pending_after_import',
    'record_tax',
    'record_tax_from_payload',
    'refresh_reminders',
    'revoke_ack',
    'revoke_from_payload',
    'scan_dividend_tax',
    'scan_pending_tax',
]

# 通知来源标识（写入 notifications.source_type）
SOURCE_TYPE = 'dividend_tax_pending'  # 有一笔分红还没记扣税
SOURCE_TYPE_SUSPECT = 'dividend_tax_suspect'  # 已记扣税，但金额占分红比例异常

# 级别：P1（消息盒 + 首页未读计数）。钱的事值得看见，但不至于占首页横栏挤掉紧急项。
REMINDER_LEVEL = 'P1'


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
    if THS_OP_MAP.get(raw) == BusinessType.TAX.code:
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
        **dividend_tax_source_fields(db, family_id, symbol, position, account_name),
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


def _parse_iso_day(raw, *, label: str) -> Optional[date]:
    """把 `YYYY-MM-DD` 解析成 date；空串/None 返回 None，格式错抛 ValueError。"""
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw), '%Y-%m-%d').date()
    except ValueError:
        raise ValueError(f'{label} 必须是 YYYY-MM-DD') from None


def ack_dividend_tax(
    db: Session,
    family_id: int,
    *,
    symbol: str,
    account_name: str = '',
    dividend_on: date,
    reason: str = '',
) -> DividendTaxAck:
    """确认「这笔分红确实没有税，别再提醒」（域 E，2026-11-08）。

    WHY 不是「记一笔 0 元扣税」：0 元在税法上不是「交了 0 元税」，而是「无需纳税」，
    是两个不同的法律事实。记一笔 0 元流水会虚构一次现金流出；更麻烦的是将来真卖出
    被扣税时，这条假记录会参与 `_match_taxes` 的额度消耗，用户再也分不清哪笔是
    券商真值、哪笔是我们编的——那正是模块 docstring 里「多记一笔假税比少记更坏」
    要避免的。

    幂等由唯一约束保证（同 `record_tax`）：撞约束时只回滚这一个 savepoint 并返回
    既有行，语义 = 「这笔已经确认过了」。
    """
    from sqlalchemy.exc import IntegrityError  # noqa: PLC0415

    bare = (symbol or '').strip()
    if not bare:
        raise ValueError('缺少标的代码')
    if dividend_on is None:
        raise ValueError('缺少分红日')
    account = (account_name or '').strip()

    def _existing():
        return (
            db.query(DividendTaxAck)
            .filter(
                DividendTaxAck.family_id == family_id,
                DividendTaxAck.symbol == bare,
                DividendTaxAck.account_name == account,
                DividendTaxAck.dividend_on == dividend_on,
            )
            .first()
        )

    found = _existing()
    if found is not None:
        return found

    ack = DividendTaxAck(
        family_id=family_id,
        symbol=bare,
        account_name=account,
        dividend_on=dividend_on,
        reason=(reason or '').strip() or None,
    )
    try:
        with db.begin_nested():
            db.add(ack)
    except IntegrityError:
        again = _existing()
        if again is None:  # pragma: no cover - 约束冲突却查不到，属数据异常
            raise
        return again
    return ack


def revoke_ack(db: Session, family_id: int, *, symbol: str, account_name: str = '', dividend_on: date) -> bool:
    """撤销确认（幂等：本来不存在返回 False）。"""
    deleted = (
        db.query(DividendTaxAck)
        .filter(
            DividendTaxAck.family_id == family_id,
            DividendTaxAck.symbol == (symbol or '').strip(),
            DividendTaxAck.account_name == (account_name or '').strip(),
            DividendTaxAck.dividend_on == dividend_on,
        )
        .delete(synchronize_session=False)
    )
    return bool(deleted)


def ack_from_payload(db: Session, family_id: int, payload: dict) -> dict:
    """把 API payload 规整成 `ack_dividend_tax` 的参数（业务校验留在服务层）。"""
    day = _parse_iso_day(payload.get('dividend_on'), label='dividend_on')
    if day is None:
        raise ValueError('缺少 dividend_on')
    ack = ack_dividend_tax(
        db,
        family_id,
        symbol=str(payload.get('symbol') or '').strip(),
        account_name=str(payload.get('account_name') or ''),
        dividend_on=day,
        reason=str(payload.get('reason') or ''),
    )
    return {
        'id': ack.id,
        'symbol': ack.symbol,
        'account_name': ack.account_name,
        'dividend_on': ack.dividend_on.isoformat() if ack.dividend_on else None,
    }


def revoke_from_payload(db: Session, family_id: int, payload: dict) -> dict:
    """撤销确认的 payload 规整；返回 `{deleted: bool}`（幂等）。"""
    day = _parse_iso_day(payload.get('dividend_on'), label='dividend_on')
    if day is None:
        raise ValueError('缺少 dividend_on')
    deleted = revoke_ack(
        db,
        family_id,
        symbol=str(payload.get('symbol') or '').strip(),
        account_name=str(payload.get('account_name') or ''),
        dividend_on=day,
    )
    return {'deleted': deleted}
