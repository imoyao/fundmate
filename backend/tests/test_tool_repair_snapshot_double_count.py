# -*- coding: utf-8 -*-
"""存量修复工具 `repair_snapshot_double_count` 的回归网。

## 为什么单独锁这个工具

这个工具会**直接改写真实账本的份额与成本**，一旦判定口径错了，损失比它要修的 bug 更大。
2026-10-18 在真实库（153 持仓 / 1,924 流水）上实跑，两处口径错误当场暴露：

1. **快照后流水没扣**：当前值 = 锚点 + 快照前流水(仅重复累加时) + 快照后流水，
   反推锚点写 `current − pre_net` 会让 `recompute` 再把 post 加一次 ⇒ 凭空多一份。
   当天库里 post_net 全为 0，属**潜伏缺陷**，靠单测才能拦住。
2. **`import_hash` 反解不足以定案**：14 行「hash 说明最后一次写入是快照前流水」里
   13 行是假阳性（如 023887：推算快照份额 12,465.43 < 快照日前已买入 17,086，
   份额不可能凭空消失）。加了可行性反证后收敛到 1 行真阳性。

3. **成本反解量纲错**：`avg_price × quantity` 是 1e-8 元，`multiply_price_quantity`
   返回分，两者相差 1e6。直接相减会把快照成本抹成 0，均价退化成 `avg × 2`
   （012708 实测 1.3234 → 2.6468）。真实库上已发生一次，需回写修正。

本文件的断言全部针对**正确口径**，不得为了让实现通过而放宽。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.import_records import compute_position_hash
from app.services.position_service import PositionService
from app.tools.repair_snapshot_double_count import (
    _implied_avg_price,
    analyse_position,
    apply_fix,
    apply_freeze,
)

SNAP = date(2026, 8, 12)
SYMBOL = '012708'


@pytest.fixture
def ledger(db):
    lg = Ledger(name='基金账户', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _legacy_position(db, ledger, *, quantity, avg_price=1.3401, hash_date=None):
    """构造「修复前」形态的持仓行：份额被流水污染、锚点列为空。

    `quantity` 用**份**传入，内部转最小单位，避免测试里到处都是 10000 的倍数。
    """
    pos = Position(
        symbol=SYMBOL,
        name='示例基金',
        asset_type='fund',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        snapshot_date=SNAP,
        snapshot_quantity=None,
        anchor_kind=None,
        source='manual',
        ownership_status='active',
        import_hash=compute_position_hash('manual', ledger.id, SYMBOL, hash_date or SNAP),
    )
    db.add(pos)
    db.flush()
    return pos


def _add_txn(db, ledger, pos, *, qty, price, confirm, txn_type='buy'):
    """`qty` 用份、`price` 用元，内部转存储单位。"""
    t = Transaction(
        position_id=pos.id,
        ledger_id=ledger.id,
        family_id=1,
        symbol=SYMBOL,
        txn_type=txn_type,
        quantity=Money.shares_to_min_unit(qty),
        price=Money.yuan_to_price_units(price),
        trade_date=confirm,
        confirm_date=confirm,
        source='manual',
    )
    db.add(t)
    db.flush()
    return t


# ── 1. 快照后流水必须从锚点里扣掉 ────────────────────────────


def test_post_snapshot_flow_is_deducted_from_anchor(db, ledger):
    """快照日之后买入 → 当前值已含它，锚点必须是 `current − post`，否则重算凭空多一份。"""
    pos = _legacy_position(db, ledger, quantity=1200.0)
    _add_txn(db, ledger, pos, qty=200.0, price=1.5, confirm=date(2026, 9, 1))
    db.flush()

    item = analyse_position(db, pos)

    assert item['verdict'] == 'safe'
    # 锚点应为 1000（快照当日真实份额），而不是 1200
    assert item['implied_qty'] == Money.shares_to_min_unit(1000)
    assert item['post_flow_net'] == Money.shares_to_min_unit(200)


def test_apply_on_post_snapshot_flow_keeps_quantity_unchanged(db, ledger):
    """写入锚点后重算，份额必须原地不动——这是「扣 post」是否正确的最终判据。"""
    pos = _legacy_position(db, ledger, quantity=1200.0)
    _add_txn(db, ledger, pos, qty=200.0, price=1.5, confirm=date(2026, 9, 1))
    db.flush()

    item = analyse_position(db, pos)
    apply_fix(db, pos, item)
    db.flush()
    db.refresh(pos)

    assert Money.min_unit_to_shares(pos.quantity) == 1200.0
    assert Money.min_unit_to_shares(pos.snapshot_quantity) == 1000.0


# ── 2. 全量重复累加的可行性反证 ──────────────────────────────


def test_infeasible_double_count_is_not_confirmed(db, ledger):
    """快照份额推算值小于快照日前已买入份额 → 全量重复累加不可能，不得判为确证。

    真实库 023887：current 29,551.43、pre 17,086，推算快照 12,465.43 < 17,086。
    若按「确证」写入，会把 2.9 万份改成 1.2 万份。
    """
    pos = _legacy_position(db, ledger, quantity=29551.43, hash_date=date(2026, 3, 24))
    _add_txn(db, ledger, pos, qty=9000.0, price=1.0, confirm=date(2026, 3, 10))
    _add_txn(db, ledger, pos, qty=4000.0, price=1.0, confirm=date(2026, 3, 23))
    _add_txn(db, ledger, pos, qty=4086.0, price=1.0, confirm=date(2026, 3, 24))
    db.flush()

    item = analyse_position(db, pos)

    assert item['verdict'] == 'no_double_count', item['evidence']
    assert '反证' in item['evidence']


def test_feasible_double_count_is_confirmed(db, ledger):
    """恰好 2 倍且 hash 指向快照前流水 → 确证，锚点 = 1 倍。

    快照 1000 + 快照前两笔买入 1000 = 2000（重复累加后），
    所以「修复前」入库的 quantity 是 4000，锚点应回到 2000。
    """
    pos = _legacy_position(db, ledger, quantity=4000.0, hash_date=date(2026, 6, 18))
    _add_txn(db, ledger, pos, qty=1000.0, price=1.2, confirm=date(2026, 5, 26))
    _add_txn(db, ledger, pos, qty=1000.0, price=1.2, confirm=date(2026, 6, 18))
    db.flush()

    item = analyse_position(db, pos)

    assert item['verdict'] == 'double_count_confirmed', item['evidence']
    assert item['implied_qty'] == Money.shares_to_min_unit(2000)


# ── 3. 成本反解的量纲 ────────────────────────────────────────


def test_implied_avg_price_does_not_degrade_to_double(db, ledger):
    """加权价 1.3234 / 快照 11,083.22 / 三笔历史买入 → 快照成本必须 ≈1.3401，不是 2.6468。

    量纲错误会让 `total_cost(1e-8元)` 与 `pre_cost(分)` 直接相减，快照成本被抹成 0，
    结果退化成 `avg × 当前份额 / 快照份额`（012708 实测翻倍）。
    """
    pos = _legacy_position(db, ledger, quantity=22166.4444, avg_price=1.3234)
    _add_txn(db, ledger, pos, qty=1838.4627, price=1.3582, confirm=date(2026, 1, 28))
    _add_txn(db, ledger, pos, qty=1487.0840, price=1.3433, confirm=date(2026, 5, 27))
    _add_txn(db, ledger, pos, qty=7757.6777, price=1.2875, confirm=date(2026, 6, 22))
    db.flush()

    txns = db.query(Transaction).filter(Transaction.position_id == pos.id).all()
    implied = _implied_avg_price(pos, txns, Money.shares_to_min_unit(11083.22))

    assert round(Money.price_units_to_yuan(implied), 4) == 1.3401


def test_implied_avg_price_falls_back_when_pre_cost_exceeds(db, ledger):
    """历史买入成本已超过总成本（异常数据）→ 退回当前均价，不得写负价/荒谬价。"""
    pos = _legacy_position(db, ledger, quantity=1000.0, avg_price=1.0)
    _add_txn(db, ledger, pos, qty=1000.0, price=5.0, confirm=date(2026, 1, 1))
    db.flush()

    txns = db.query(Transaction).filter(Transaction.position_id == pos.id).all()
    implied = _implied_avg_price(pos, txns, Money.shares_to_min_unit(1000))

    assert implied == pos.avg_price


# ── 5. 只有快照、没有流水的持仓不能被重算删掉 ────────────────


def test_recompute_keeps_anchored_position_without_transactions(db, ledger):
    """纯快照持仓（零流水）重算后必须仍在，且份额等于锚点。

    修复前 `if not txns: db.delete(pos)` 早于锚点判断，任何一次重算都会让这类持仓
    整行消失。真实库实测 105 行里 79 行零流水——这不是边角，是主场景。
    """
    pos = Position(
        symbol=SYMBOL,
        name='示例基金',
        asset_type='fund',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(1300.05),
        avg_price=Money.yuan_to_price_units(1.3),
        snapshot_quantity=Money.shares_to_min_unit(1300.05),
        snapshot_avg_price=Money.yuan_to_price_units(1.3),
        snapshot_date=SNAP,
        anchor_kind='external',
        source='manual',
        ownership_status='active',
    )
    db.add(pos)
    db.flush()
    pos_id = pos.id

    PositionService.recompute_position_from_transactions(db, pos_id)
    db.flush()

    survived = db.query(Position).filter_by(id=pos_id).first()
    assert survived is not None, '有锚点的纯快照持仓不得被重算删除'
    assert Money.min_unit_to_shares(survived.quantity) == 1300.05


def test_recompute_still_deletes_position_without_anchor_and_transactions(db, ledger):
    """无锚点 + 零流水 = 真正的空壳行，仍应删除（不能把旧清理语义一并去掉）。"""
    pos = _legacy_position(db, ledger, quantity=0, hash_date=SNAP)
    pos.snapshot_date = None
    db.flush()
    pos_id = pos.id

    PositionService.recompute_position_from_transactions(db, pos_id)
    db.flush()

    assert db.query(Position).filter_by(id=pos_id).first() is None


def test_freeze_keeps_quantity_unchanged_for_snapshot_only_position(db, ledger):
    """freeze 的判据：写入锚点后重算，份额与成本一分不动。"""
    pos = _legacy_position(db, ledger, quantity=29551.43, avg_price=0.8267)
    _add_txn(db, ledger, pos, qty=9000.0, price=0.8, confirm=date(2026, 3, 10))
    _add_txn(db, ledger, pos, qty=4000.0, price=0.85, confirm=date(2026, 3, 23))
    _add_txn(db, ledger, pos, qty=4086.0, price=0.83, confirm=date(2026, 3, 24))
    db.flush()

    item = analyse_position(db, pos)
    assert item['verdict'] == 'no_double_count'

    before_qty = pos.quantity
    before_avg = pos.avg_price
    apply_freeze(db, pos, item)
    db.flush()
    db.refresh(pos)

    assert pos.quantity == before_qty, 'freeze 不得改变份额'
    assert Money.min_unit_to_shares(pos.snapshot_quantity) == 29551.43
    assert Money.price_units_to_yuan(pos.avg_price) == pytest.approx(Money.price_units_to_yuan(before_avg), abs=1e-4)


# ── 4. 端到端：确证行写库后的份额与成本 ──────────────────────


def test_apply_confirmed_double_count_restores_single_count(db, ledger):
    """012708 实测形态：写完锚点后份额回到 1 倍，成本保持快照口径。"""
    pos = _legacy_position(db, ledger, quantity=22166.4444, avg_price=1.3234, hash_date=date(2026, 6, 22))
    _add_txn(db, ledger, pos, qty=1838.4627, price=1.3582, confirm=date(2026, 1, 28))
    _add_txn(db, ledger, pos, qty=1487.0840, price=1.3433, confirm=date(2026, 5, 27))
    _add_txn(db, ledger, pos, qty=7757.6777, price=1.2875, confirm=date(2026, 6, 22))
    db.flush()

    item = analyse_position(db, pos)
    assert item['verdict'] == 'double_count_confirmed'
    apply_fix(db, pos, item)
    db.flush()
    db.refresh(pos)

    assert Money.min_unit_to_shares(pos.quantity) == 11083.22
    assert Money.min_unit_to_shares(pos.snapshot_quantity) == 11083.22
    assert round(Money.price_units_to_yuan(pos.avg_price), 4) == 1.3401
    # 流水一条都不能少
    assert db.query(Transaction).count() == 3
    # 重算幂等：再跑一次不得再变
    PositionService.recompute_position_from_transactions(db, pos.id)
    db.flush()
    db.refresh(pos)
    assert Money.min_unit_to_shares(pos.quantity) == 11083.22
