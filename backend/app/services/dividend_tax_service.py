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

## 所以这一层做什么

只回答一个用户自己能判断的问题：**「哪些现金分红，账上还没有对应的扣税流水？」**

判据（全部是账内已有的事实，不做任何外部推断）：

1. 取该家庭的 `txn_type='dividend'` 现金分红（红利再投不算——份额已经增加，
   不产生现金，也就没有「该扣的税款」这一说）；
2. 除权日所在**自然年**内，同一 `(symbol, account_name)` 是否存在
   `txn_type='dividend_tax'` 流水；
3. 没有 ⇒ 这条分红是「未扣税」的候选。

## 两个刻意的口径选择

- **按年匹配、不按笔匹配**：券商对同一账户同一标的的红利税常把多笔合并成一条
  「股息红利差异扣税」，且扣税日可能晚于分红日数周。逐笔一一对应必然误报，
  故退一步问「这一年有没有记过税」——宁可漏报（用户看到的分红比实际略多），
  不可滥报（天天提醒一件已经做过的事）。
- **只看现金分红**：红利再投已经改变了份额，其税款最终体现在卖出流水的成本里，
  拿它去催用户补一笔现金支出是错的。

## 与 `dividend_service` 的关系

`dividend_service` 是分红**统计**的唯一归口（净分红 = 现金 + 再投 − 税），
本模块是它**输入侧的核对**：告诉用户「净分红这个数还缺一块税」。两者不互相调用，
都直接读 `transactions`，避免统计口径被提醒逻辑改写。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.domains.transactions.models import Transaction
from app.services.notification_service import build_dedup_key

# 通知来源标识（写入 notifications.source_type）
SOURCE_TYPE = 'dividend_tax_pending'
# 级别：P1（消息盒 + 首页未读计数）。钱的事值得看见，但不至于占首页横栏挤掉紧急项。
REMINDER_LEVEL = 'P1'
# 只看最近 N 天的分红：更早的税早已在券商交割单里结清，催一年以上的旧账没有意义。
DEFAULT_LOOKBACK_DAYS = 400


@dataclass(frozen=True)
class PendingTaxItem:
    """一条「现金分红没有对应扣税流水」的记录（按 年 + 标的 + 账户 聚合）。"""

    symbol: str
    name: str
    account_name: str
    year: int
    dividend_cents: int
    last_dividend_on: Optional[date]
    dividend_count: int

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'account_name': self.account_name,
            'year': self.year,
            'dividend_cents': self.dividend_cents,
            'last_dividend_on': self.last_dividend_on.isoformat() if self.last_dividend_on else None,
            'dividend_count': self.dividend_count,
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


def scan_pending_tax(
    db: Session,
    family_id: int,
    *,
    today: Optional[date] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> list[PendingTaxItem]:
    """列出「有现金分红、但该年该标的没有扣税流水」的项，按金额降序。

    纯读、无副作用——对账台直接展示、通知生成直接消费。
    """
    today = today or date.today()
    since = today.fromordinal(today.toordinal() - lookback_days)

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

    taxed: set[tuple[str, str, int]] = set()
    dividends: dict[tuple[str, str, int], dict] = {}
    for txn in rows:
        occurred = _event_date(txn)
        if occurred is None:
            continue
        symbol = (txn.symbol or '').strip()
        if not symbol:
            # 无代码的流水对不上任何持仓/事件，提醒也提醒不到有意义的东西
            continue
        account = txn.account_name or ''
        key = (symbol, account, occurred.year)
        if txn.txn_type == 'dividend_tax':
            taxed.add(key)
            continue
        # 现金分红：排除红利再投（同组有 buy）与金额非正的行
        if txn.link_group_id and txn.link_group_id in reinvest_groups:
            continue
        amount = int(txn.amount or 0)
        if amount <= 0:
            continue
        if occurred < since:
            continue
        bucket = dividends.get(key)
        if bucket is None:
            bucket = {
                'symbol': symbol,
                'name': txn.position_name or '',
                'account_name': account,
                'year': occurred.year,
                'dividend_cents': 0,
                'last_dividend_on': occurred,
                'dividend_count': 0,
            }
            dividends[key] = bucket
        bucket['dividend_cents'] += amount
        bucket['dividend_count'] += 1
        if bucket['last_dividend_on'] is None or occurred > bucket['last_dividend_on']:
            bucket['last_dividend_on'] = occurred

    items = [PendingTaxItem(**bucket) for key, bucket in dividends.items() if key not in taxed]
    items.sort(key=lambda i: (-i.dividend_cents, i.symbol))
    return items


def build_notification_candidates(
    items: list[PendingTaxItem],
    *,
    today: Optional[date] = None,
) -> list[dict]:
    """把待补记项转成 `notification_service.emit_many` 的候选（不写库）。

    粒度是**每标的每年一条**，而不是「全库汇总一条」——用户看到「某某股票 2026 年
    有 420 元分红未记扣税」才知道该去翻哪张交割单；只说「你有 7 笔未扣税」等于
    让他自己再数一遍。dedup_key 含年份，故同一标的同一年只提醒一次。
    """
    today = today or date.today()
    candidates: list[dict] = []
    for item in items:
        label = item.name or item.symbol
        account = f'（{item.account_name}）' if item.account_name else ''
        candidates.append(
            {
                'level': REMINDER_LEVEL,
                'category': 'system',
                'title': f'分红未记扣税：{label} {item.year} 年 {item.dividend_cents / 100:.2f} 元',
                'body': (
                    f'{label}{account}在 {item.year} 年有 {item.dividend_count} 笔现金分红，'
                    f'账上没有对应的红利税流水。'
                    f'A 股红利税按实际持股期在卖出时补扣，本系统不自动推算'
                    f'（税率取决于买入批次，而账上只有聚合持仓）。'
                    f'若券商交割单里有扣税记录，请在流水中补记一笔「扣税」。'
                ),
                'dedup_key': build_dedup_key(SOURCE_TYPE, f'{item.symbol}:{item.year}', today),
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
    """扫一次「未记扣税」并写入站内通知，返回**新建**条数（已存在则跳过）。

    为什么做成显式 refresh 而不是「查通知列表时顺带生成」：写副作用不该藏在 GET 里
    ——GET 会被预取 / 重试，把写放在 GET 上迟早会生成意料之外的消息
    （与 `strategy_engine/allocation.py` 的 `refresh_reminders` 同一取舍）。

    导入置于函数内：`notification_service` 与本模块同属 services 层，顶层互引会在
    将来调整包结构时触发循环导入。
    """
    from app.services import notification_service  # noqa: PLC0415

    items = scan_pending_tax(db, family_id, today=today)
    candidates = build_notification_candidates(items, today=today)
    return notification_service.emit_many(db, family_id, candidates)
