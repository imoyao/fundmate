# -*- coding: utf-8 -*-
"""对账可信度三处闸门的回归网（#3123）。

三件事各自一个「真库证据 → 判据」的小节：

1. **域 C 陈旧孤儿卡**：导入后修好的数据不会让卡消失（真库 94 张全部已不成立）；
2. **补录查重**：同一笔被补录两遍 ⇒ 差异被「轧平」成假修复（真库 8 对重复行）；
3. **同标的悬空流水**：`127078` 装了 114 个标的的流水，差异卡却建议补录那笔卖出。

每条判据都配一个反向对照（不是「凡有悬空就拦」），因为过宽的闸门会让人改不动数据。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.reconciliation.models import ReconciliationDiscrepancy
from app.domains.transactions.models import Transaction
from app.services.reconciliation_service import DOMAIN_B, DOMAIN_C, apply_decision, run_reconciliation

_DAY = date(2024, 6, 12)
_DEAD_POSITION_ID = 999_999  # 指向不存在的持仓行 ⇒ 悬空


@pytest.fixture
def ledger(db):
    lg = Ledger(name='同花顺（银河证券）', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _pos(db, ledger_id, symbol, shares, *, name='中装转2', asset_type='bond', status='active'):
    p = Position(
        symbol=symbol,
        name=name,
        market='CN_A',
        asset_type=asset_type,
        ledger_id=ledger_id,
        family_id=1,
        quantity=Money.shares_to_min_unit(shares),
        avg_price=Money.yuan_to_price_units(100),
        current_price=Money.yuan_to_price_units(100),
        ownership_status=status,
    )
    db.add(p)
    db.flush()
    return p


def _txn(db, ledger_id, symbol, *, shares, txn_type='buy', price=100, day=_DAY, position_id=None, name='中装转2'):
    t = Transaction(
        position_id=position_id,
        ledger_id=ledger_id,
        family_id=1,
        symbol=symbol,
        txn_type=txn_type,
        confirm_date=day,
        quantity=Money.shares_to_min_unit(shares),
        price=Money.yuan_to_price_units(price),
        amount=Money.multiply_price_quantity(Money.yuan_to_price_units(price), Money.shares_to_min_unit(shares)),
        position_name=name,
        asset_type='bond',
    )
    db.add(t)
    db.flush()
    return t


def _disc(db, *, domain, ledger_id, symbol, dtype='orphan', status='pending', expected=100, is_permanent=False):
    d = ReconciliationDiscrepancy(
        family_id=1,
        domain=domain,
        ledger_id=ledger_id,
        symbol=symbol,
        discrepancy_type=dtype,
        expected_value=Money.shares_to_min_unit(expected),
        actual_value=0,
        diff=Money.shares_to_min_unit(expected),
        status=status,
        is_permanent=is_permanent,
    )
    db.add(d)
    db.flush()
    return d


# ── 1. 域 C 的孤儿卡随域 B 的 run 刷新 ──────────────────────


def test_domain_b_run_clears_stale_domain_c_orphan(db, ledger):
    """数据修好（代码现在有持仓）之后，导入时留下的域 C 孤儿卡必须消失。

    域 C 只在导入时机跑一次；不刷新的话，卡片永远停在导入那一刻 —— 真库实测 94 张
    pending 全部已不成立，用户看到的是一批早就修好的「孤儿流水」。
    """
    pos = _pos(db, ledger.id, 'SZ127033', 100)
    _txn(db, ledger.id, 'SZ127033', shares=100, position_id=pos.id)
    stale = _disc(db, domain=DOMAIN_C, ledger_id=ledger.id, symbol='SZ127033')

    run_reconciliation(db, 1, DOMAIN_B)

    assert stale.status == 'cleared'
    assert stale.last_run_id is not None


def test_domain_b_run_keeps_and_refreshes_live_domain_c_orphan(db, ledger):
    """反向对照：孤儿仍成立时不能顺手清掉，还要把数值刷成最新（否则卡片说的是旧账）。"""
    _txn(db, ledger.id, 'SZ127033', shares=100, position_id=_DEAD_POSITION_ID)
    live = _disc(db, domain=DOMAIN_C, ledger_id=ledger.id, symbol='SZ127033', expected=1)
    _txn(db, ledger.id, 'SZ127033', shares=50, txn_type='buy', position_id=_DEAD_POSITION_ID)

    run_reconciliation(db, 1, DOMAIN_B)

    assert live.status == 'pending'
    assert live.expected_value == Money.shares_to_min_unit(150)
    assert live.diff == Money.shares_to_min_unit(150)


def test_domain_b_run_does_not_overturn_ignored_domain_c_card(db, ledger):
    """用户裁决过的卡（含永久忽略）不因系统重算被翻案。"""
    pos = _pos(db, ledger.id, 'SZ127033', 100)
    _txn(db, ledger.id, 'SZ127033', shares=100, position_id=pos.id)
    ignored = _disc(db, domain=DOMAIN_C, ledger_id=ledger.id, symbol='SZ127033', status='ignored', is_permanent=True)

    run_reconciliation(db, 1, DOMAIN_B)

    assert ignored.status == 'ignored'
    assert ignored.is_permanent is True


# ── 2. 补录查重 ────────────────────────────────────────────


def _sell_payload(ledger_id, **overrides):
    data = {
        'kind': 'increment',
        'op_type': 'sell',
        'ledger_id': ledger_id,
        'symbol': 'SZ127033',
        'quantity': 30,
        'avg_price': 36.5,
        'confirm_date': '2024-06-12',
    }
    data.update(overrides)
    return data


def test_supplement_rejects_identical_existing_transaction(db, ledger):
    """同账本 + 同标的 + 同类型 + 同日 + 同数量 + 同单价 ⇒ 这笔已经记过了。

    真库那 8 对重复行正是这么来的：差异卡看不到「那笔已在库里」，用户照着对账单又录一遍，
    `recompute_linked_discrepancy` 只看聚合数字轧没轧平 ⇒ 差异「消失」⇒ 下一张卡。
    """
    pos = _pos(db, ledger.id, 'SZ127033', 100)
    _txn(db, ledger.id, 'SZ127033', shares=30, txn_type='sell', price=36.5, position_id=pos.id)

    with pytest.raises(ValueError, match='这笔已经记过了'):
        apply_decision(db, 1, _sell_payload(ledger.id))
    assert db.query(Transaction).filter_by(txn_type='sell').count() == 1


def test_supplement_allows_different_price_same_day(db, ledger):
    """反向对照：同日同量但价格不同是两笔真实成交（分批卖出），不能被判成重复。"""
    pos = _pos(db, ledger.id, 'SZ127033', 100)
    _txn(db, ledger.id, 'SZ127033', shares=30, txn_type='sell', price=35.5, position_id=pos.id)

    apply_decision(db, 1, _sell_payload(ledger.id))

    assert db.query(Transaction).filter_by(txn_type='sell').count() == 2


# ── 3. 同标的还有流水缺归属 ⇒ 不许补录 ──────────────────────


def test_supplement_blocked_by_dangling_same_name(db, ledger):
    """挂错的代码可能完全是另一只标的（`127078` vs `SZ127033`），只能靠标的名认出来。

    真库 2026-11-15：114 个标的的流水被写成同一个代码，域 B 按 (账本, 代码) 聚合时
    每个真实代码的桶「只有买入没有卖出」⇒ 差异卡建议补录卖出，而那批卖出正躺在悬空流水里。
    """
    _pos(db, ledger.id, 'SZ127033', 100, name='中装转2')
    _txn(db, ledger.id, '127078', shares=30, txn_type='sell', position_id=_DEAD_POSITION_ID, name='中装转2')

    with pytest.raises(ValueError, match='还有 1 条流水没挂到持仓上'):
        apply_decision(db, 1, _sell_payload(ledger.id))


def test_supplement_allows_when_dangling_belongs_to_another_symbol(db, ledger):
    """反向对照：悬空流水是别的标的（代码与名字都不同）时不该拦。"""
    _pos(db, ledger.id, 'SZ127033', 100, name='中装转2')
    _txn(db, ledger.id, 'SZ127079', shares=30, txn_type='sell', position_id=_DEAD_POSITION_ID, name='优彩转债')

    apply_decision(db, 1, _sell_payload(ledger.id))

    assert db.query(Transaction).filter_by(txn_type='sell', symbol='SZ127033').count() == 1
