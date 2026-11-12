# -*- coding: utf-8 -*-
"""流水「有效日」口径回归网（#2914）。

缺陷背景（真实库 1,930 笔实测）：1,491 笔 `trade_date` 为 NULL（历史导入只填确认日），
导致三个静默错误：

1. **时间筛选整批漏行**：`trade_date >= start` 把只有确认日的行全部漏掉——
   「近 30 天」实测少 28/61 笔、「近 365 天」少 660/916 笔。用户看着列表里有日期
   （`TransactionTable` 印的就是确认日兜底），按时间筛出来却没有，账对不上。
2. **区间上界漏当天**：`trade_date <= '2026-01-20'` 与带时分秒的存量行
   （`2026-01-20 00:00:00.000000`，159 笔）比较恒 False，选「到 1 月 20 日」
   20 号当天的账不显示。
3. **无日期行仍会被写出来**：手工/孤儿路径不兜底，NULL 排最前、被筛选漏掉。

修复：排序 / 筛选 / 写入兜底统一收进 `app/domains/transactions/dates.py`，
本文件钉住三件事——筛选含确认日行、闭区间两端含当天、写入侧必产日期。
"""

from datetime import date, datetime, timedelta

from app.core.time_utils import today_shanghai
from app.domains.positions.state import derive_state_from_txns
from app.domains.transactions.dates import (
    order_by_effective_day,
    resolve_trade_date,
)
from app.domains.transactions.models import Transaction
from app.services.transaction_service import build_transaction_list


def _list(db, **filters):
    payload = build_transaction_list(db, family_id=1, page=1, per_page=50, filters=filters)
    return payload['data']


def _make_confirm_only_row(make_position, make_transaction, *, symbol, confirm_day, position=None, **kw):
    """造一条「历史导入」形态的流水：`trade_date` NULL、只有确认日。

    传 ``position`` 时复用已有持仓，否则为该 symbol 新建一行。
    """
    if position is None:
        position = make_position(symbol=symbol, quantity=100, avg_price=10, account_name='测试账户')
    return make_transaction(
        position_id=position.id,
        ledger_id=position.ledger_id,
        symbol=symbol,
        txn_type=kw.pop('txn_type', 'buy'),
        quantity=10,
        price=10,
        confirm_date=confirm_day,
        allow_null_trade_date=True,
        **kw,
    )


def test_近30天包含只有确认日的行(db, make_position, make_transaction):
    """修复前：`trade_date >= today-30` 会把确认日落在窗口内的行整批漏掉（真实库少 28/61 笔）。"""
    recent = today_shanghai() - timedelta(days=5)
    _make_confirm_only_row(make_position, make_transaction, symbol='000100', confirm_day=recent)
    # 更早的确认日行不应命中近 30 天
    _make_confirm_only_row(
        make_position, make_transaction, symbol='000200', confirm_day=today_shanghai() - timedelta(days=40)
    )

    rows = _list(db, time_range='1m')
    assert [r['symbol'] for r in rows] == ['000100']


def test_custom区间上界含当天(db, make_position, make_transaction):
    """`<= end` 撞上带时分秒的行恒 False（159 笔存量形态），上界必须改半开区间。"""
    end_day = date(2026, 1, 20)
    pos = make_position(symbol='600000', quantity=100, avg_price=10, account_name='测试账户')
    # 存量导入形态：trade_date 带时分秒、恰好落在 end 当天
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='600000',
        txn_type='buy',
        quantity=10,
        price=10,
        trade_date=datetime(2026, 1, 20, 0, 0, 0),
        created_at=datetime(2026, 1, 21),
    )
    # 只有确认日的行、也在 end 当天
    _make_confirm_only_row(make_position, make_transaction, symbol='600100', confirm_day=end_day)
    # end 之后一天的两类行都不应命中
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='600200',
        txn_type='buy',
        quantity=10,
        price=10,
        trade_date=datetime(2026, 1, 21, 0, 0, 0),
        created_at=datetime(2026, 1, 22),
    )

    rows = _list(db, time_range='custom', start_date='2026-01-01', end_date='2026-01-20')
    assert sorted(r['symbol'] for r in rows) == ['600000', '600100']


def test_custom区间坏参数不筛空(db, make_position, make_transaction):
    """start/end 解析失败时忽略该端（不因一个坏参数把整张表筛空，也不 500）。"""
    _make_confirm_only_row(make_position, make_transaction, symbol='000300', confirm_day=date(2026, 3, 1))
    rows = _list(db, time_range='custom', start_date='不是日期', end_date='')
    assert len(rows) == 1


# ── 写入侧：TransactionService.create 是唯一汇点，缺日期必须兜底 ──────────────────


def _create_via_service(db, **kw):
    from app.services.trading import TransactionService

    # 汇点现在校验「非空 ledger_id 必须指向本家庭真实账本」，故夹具补建 id=1。
    # #2875 撤掉的只是「NULL 即报错」的硬拦，NULL 仍是合法形态。
    from app.domains.ledgers.models import Ledger

    if db.query(Ledger).filter_by(id=1).first() is None:
        db.add(Ledger(id=1, name='测试账户', ledger_type='fund', family_id=1))
        db.flush()
    kw.setdefault('ledger_id', 1)
    txn = TransactionService.create(db=db, symbol='000400', txn_type='buy', quantity=0, price=0, amount=0, **kw)
    db.flush()
    return txn


def test_create缺trade_date时用confirm_date(db):
    """只给确认日 ⇒ trade_date 取确认日（与导入器落库口径 `trade_date=confirm_date` 一致）。"""
    cd = date(2026, 10, 15)
    txn = _create_via_service(db, confirm_date=cd, status='success')
    assert txn.trade_date is not None
    assert getattr(txn.trade_date, 'date', lambda: txn.trade_date)() == cd


def test_create两个日期都没有时兜底今天(db):
    """两个都没有 ⇒ 今天（东八区业务日）。不返回 None 是硬约束：无日期行不允许再产生。"""
    txn = _create_via_service(db, status='success')
    assert txn.trade_date is not None
    assert getattr(txn.trade_date, 'date', lambda: txn.trade_date)() == today_shanghai()


def test_create显式trade_date不被覆盖(db):
    """用户/文件给了交易日 ⇒ 原样保留（兜底只对缺失生效，不篡改事实）。"""
    td = datetime(2023, 6, 1, 9, 30, 0)
    txn = _create_via_service(db, trade_date=td, confirm_date=date(2023, 6, 2), status='success')
    assert txn.trade_date == td


def test_汇点不拦合法NULL(db):
    """#2875 定案（owner 2026-11-05）：唯一构造汇点不硬拦 NULL。

    全仓十余处 create 调用里手工建仓 / API 等合法路径不带账本，汇点硬拦会让
    它们 400（CI 实测 65 例回归）。现在汇点校验的是**另一件事**：非空 id 必须
    指向本家庭真实账本（防止导入预览行 / 红利税继承复制已删账本的悬空 id），
    见 test_ledger_ref_guard.py。本例钉住「NULL 仍可写」，两者不冲突。
    """
    txn = _create_via_service(db, status='success', ledger_id=None)
    assert txn.trade_date is not None  # 日期兜底仍在汇点，不受本次口径变更影响
    db.rollback()


def test_resolve_trade_date空字符串视同缺失():
    """导入器解析失败会传 `''`（orchestrator_parse 历史行为），必须与 None 同等对待。"""
    cd = date(2026, 5, 5)
    assert resolve_trade_date('', cd) == cd
    assert resolve_trade_date(None, cd) == cd
    assert resolve_trade_date('', '') == today_shanghai()
    assert resolve_trade_date(None, None) == today_shanghai()


# ── 排序：与展示同一把键；派生结果与顺序无关 ─────────────────────────────────────


def test_排序不因id顺序而乱(db, make_position, make_transaction):
    """无日期行的顺序必须由确认日决定，不能退化成 id 顺序（将来补录历史流水即触发）。"""
    pos = make_position(symbol='000500', quantity=100, avg_price=10, account_name='测试账户')
    # 按确认日**倒序**插入（id 越大日期越早——补录历史流水的典型形态）
    for day in (date(2026, 3, 10), date(2026, 2, 1), date(2026, 1, 5)):
        _make_confirm_only_row(make_position, make_transaction, symbol='000500', confirm_day=day, position=pos)

    rows = order_by_effective_day(db.query(Transaction).filter(Transaction.position_id == pos.id), descending=False)
    confirm_order = [t.confirm_date for t in rows.all()]
    assert confirm_order == sorted(confirm_order), '累加顺序必须按确认日升序，与插入顺序无关'


def test_派生份额与累加顺序无关(make_position, make_transaction):
    """`derive_state_from_txns` 是纯求和 ⇒ 同一组流水任意顺序结果一致。

    现在钉住它是为了把「顺序不影响账」从巧合变成不变量：将来若在推导里引入
    截断 / 已实现盈亏这类**顺序敏感**逻辑，本用例转红，就必须先回到这里讨论口径。
    """

    class _T:  # 轻量桩：derive 只读 txn_type / quantity / price
        def __init__(self, txn_type, quantity, price):
            self.txn_type = txn_type
            self.quantity = quantity
            self.price = price

    txns = [_T('buy', 100, 10), _T('buy', 50, 12), _T('sell', 30, 11)]
    forward = derive_state_from_txns(txns, 0, 0)
    backward = derive_state_from_txns(list(reversed(txns)), 0, 0)
    assert forward == backward
    assert forward[0] == 120  # 100 + 50 - 30
