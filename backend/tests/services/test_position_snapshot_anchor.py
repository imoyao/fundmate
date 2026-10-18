# -*- coding: utf-8 -*-
"""持仓快照锚点：份额派生与时间轴守卫（份额被「快照 + 流水」重复累加的回归网）。

## 背景

`positions.quantity` 曾同时承担两种语义：

- `upsert_from_holding`（快照导入）用 SET 写绝对值；
- `process_buy_or_deposit` / `process_sell_or_withdraw`（流水落库）用 INCR 累加/扣减。

两条路径没有时序约束。先导持仓快照、再导快照日之前的交易流水时，这部分流水会被
**二次计入**。实测账户 012708：快照 11,083.22 份 → 导入三笔历史买入后又加了
11,083.22 → 22,166.444（精确 2 倍，市值/盈亏全部虚高）。

修复后 `quantity` 是派生值：

    quantity = snapshot_quantity + Σ(归属日 > snapshot_date 的流水净额)

本文件锁住四类行为：
1. 锚点派生（先快照后流水不累加 / 先流水后快照正确 / 快照后流水叠加 / 无锚点向后兼容）；
2. 时间轴守卫（旧快照拒绝 / 同日 external 可覆盖 / 同日 manual 优先）；
3. 卖出路径（锚点内的卖出不扣减）；
4. 重算路径（`nav_backfill` 调度 `recompute` 时不得把锚点结果覆盖掉——最隐蔽的复发形态）。
"""

from datetime import date

import pytest

from app.core.constants import AnchorKind
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService, compute_anchored_state

SNAP_DATE = date(2026, 8, 12)


@pytest.fixture
def ledger(db):
    lg = Ledger(name='基金账户', ledger_type='stock', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _snapshot(ledger_id, qty=11083, price=1.3401, snap_date=SNAP_DATE, **overrides):
    data = {
        'symbol': '600000',
        'name': '示例基金',
        'asset_type': 'stock',
        'ledger_id': ledger_id,
        'quantity': qty,
        'avg_price': price,
        'current_price': price,
        'snapshot_date': snap_date,
        'source': 'manual',
        'family_id': 1,
    }
    data.update(overrides)
    return data


def _buy(ledger_id, qty, price, confirm_date, **overrides):
    data = {
        'symbol': '600000',
        'name': '示例基金',
        'asset_type': 'stock',
        'ledger_id': ledger_id,
        'op_type': 'buy',
        'quantity': qty,
        'avg_price': price,
        'trade_date': confirm_date,
        'confirm_date': confirm_date,
        'source': 'manual',
        'family_id': 1,
    }
    data.update(overrides)
    return data


def _shares(pos):
    return round(Money.min_unit_to_shares(pos.quantity), 4)


# ── 1. 锚点派生 ──────────────────────────────────────────────


def test_snapshot_then_historical_buys_do_not_double_count(db, ledger):
    """**本 bug 的正面回归**：先导快照、再导快照日之前的历史买入 → 份额保持 1 倍。

    修复前该场景会得到 22,166.44（2 倍），因为三笔历史买入被无条件累加到快照值上。
    """
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id))
    assert _shares(pos) == 11083

    # 三笔都发生在快照日之前 → 已包含在快照里，不得再累加
    for qty, price, confirm in (
        (7757, 1.2875, date(2026, 1, 27)),
        (1487, 1.3433, date(2026, 5, 26)),
        (1839, 1.3582, date(2026, 6, 18)),
    ):
        PositionService.process_buy_or_deposit(db, _buy(ledger.id, qty, price, confirm))
        db.flush()
        assert _shares(pos) == 11083, '快照日之前的流水不得再次计入份额'

    # 流水仍然全部落库（只是不再驱动份额）——交易记录不能丢
    assert db.query(Transaction).count() == 3
    # 成本均价也不得被历史买入加权污染
    assert round(Money.price_units_to_yuan(pos.avg_price), 4) == 1.3401


def test_buys_then_snapshot_is_still_correct(db, ledger):
    """先导流水、后导快照（正确顺序）→ 快照仍是权威值，锚点派生不改变它。"""
    for qty, price, confirm in (
        (100.0, 1.0, date(2026, 3, 1)),
        (200.0, 1.0, date(2026, 4, 1)),
    ):
        PositionService.process_buy_or_deposit(db, _buy(ledger.id, qty, price, confirm))
    db.flush()

    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=500.0))
    assert _shares(pos) == 500.0


def test_buy_after_snapshot_is_added(db, ledger):
    """快照日之后的买入 → 正常叠加到锚点上。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    PositionService.process_buy_or_deposit(db, _buy(ledger.id, 200.0, 1.5, date(2026, 9, 1)))
    db.flush()
    assert _shares(pos) == 1200.0


def test_buy_on_snapshot_date_is_treated_as_included(db, ledger):
    """边界：归属日 == 快照日 → 视为已包含（基金按确认日切分，当日份额已登记）。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    PositionService.process_buy_or_deposit(db, _buy(ledger.id, 200.0, 1.5, SNAP_DATE))
    db.flush()
    assert _shares(pos) == 1000.0


def test_without_anchor_keeps_legacy_full_flow(db, ledger):
    """无锚点的持仓（迁移后 snapshot_quantity 仍为 NULL 的存量行）→ 旧口径不变。"""
    PositionService.process_buy_or_deposit(db, _buy(ledger.id, 100.0, 1.0, date(2026, 3, 1)))
    db.flush()
    pos = db.query(Position).first()
    assert pos.snapshot_quantity is None
    PositionService.process_buy_or_deposit(db, _buy(ledger.id, 200.0, 1.0, date(2026, 4, 1)))
    db.flush()
    assert _shares(pos) == 300.0


def test_snapshot_avg_price_is_persisted(db, ledger):
    """快照成本价必须单独落库：重算时 avg_price 已被加权覆盖，不能拿它顶替。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, price=1.3401))
    assert pos.snapshot_avg_price == Money.yuan_to_price_units(1.3401)
    assert pos.snapshot_quantity == Money.shares_to_min_unit(11083)
    assert pos.snapshot_date == SNAP_DATE
    assert pos.anchor_kind == AnchorKind.EXTERNAL.value


# ── 2. 时间轴守卫 ────────────────────────────────────────────


def test_older_snapshot_is_rejected(db, ledger):
    """更旧的快照拒绝覆盖当前锚点（时间不可倒流）。"""
    PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    with pytest.raises(ValueError, match='早于该持仓当前锚点'):
        PositionService.upsert_from_holding(
            db, _snapshot(ledger.id, qty=800.0, snap_date=date(2026, 6, 1))
        )


def test_same_day_external_snapshot_can_overwrite(db, ledger):
    """同日 external 快照可覆盖：用户发现导错了重导一次是正当场景。"""
    PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1200.0))
    assert _shares(pos) == 1200.0


def test_same_day_external_cannot_overwrite_manual(db, ledger):
    """同日 manual 锚点优先于同日外部数据：手工校准不得被下一次同日导入抹掉。"""
    PositionService.upsert_from_holding(
        db,
        _snapshot(ledger.id, qty=1000.0, anchor_kind=AnchorKind.MANUAL.value),
    )
    with pytest.raises(ValueError, match='人工校准'):
        PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1200.0))


def test_newer_snapshot_overwrites_manual(db, ledger):
    """更新日期的外部快照可以推进 manual 锚点（用户给了更新的真实数据）。"""
    PositionService.upsert_from_holding(
        db,
        _snapshot(ledger.id, qty=1000.0, snap_date=date(2026, 8, 1), anchor_kind=AnchorKind.MANUAL.value),
    )
    pos = PositionService.upsert_from_holding(
        db, _snapshot(ledger.id, qty=1500.0, snap_date=date(2026, 9, 1))
    )
    assert _shares(pos) == 1500.0
    assert pos.anchor_kind == AnchorKind.EXTERNAL.value


def test_allow_rewind_bypasses_guard(db, ledger):
    """对账工作台 `set`（allow_anchor_rewind=True）允许旧日期写入：那是人工设定，不是导旧快照。"""
    PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    pos = PositionService.upsert_from_holding(
        db,
        _snapshot(ledger.id, qty=700.0, snap_date=date(2026, 6, 1), anchor_kind=AnchorKind.MANUAL.value),
        allow_anchor_rewind=True,
    )
    assert _shares(pos) == 700.0
    assert pos.anchor_kind == AnchorKind.MANUAL.value


# ── 3. 卖出路径 ──────────────────────────────────────────────


def test_sell_before_snapshot_does_not_reduce(db, ledger):
    """快照日之前的卖出已反映在快照里 → 只落流水，不扣份额。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    PositionService.process_sell_or_withdraw(
        db,
        {
            'position_id': pos.id,
            'op_type': 'sell',
            'quantity': 300.0,
            'avg_price': 1.5,
            'confirm_date': date(2026, 7, 1),
            'asset_type': 'stock',
            'family_id': 1,
        },
        skip_lot_check=True,
        auto_purchase=False,
    )
    db.flush()
    assert _shares(pos) == 1000.0


def test_sell_after_snapshot_reduces(db, ledger):
    """快照日之后的卖出 → 正常扣减。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0))
    PositionService.process_sell_or_withdraw(
        db,
        {
            'position_id': pos.id,
            'op_type': 'sell',
            'quantity': 300.0,
            'avg_price': 1.5,
            'confirm_date': date(2026, 9, 1),
            'asset_type': 'stock',
            'family_id': 1,
        },
        skip_lot_check=True,
        auto_purchase=False,
    )
    db.flush()
    assert _shares(pos) == 700.0


# ── 4. 重算路径（nav_backfill 的复发点） ─────────────────────


def test_recompute_respects_anchor(db, ledger):
    """`recompute_position_from_transactions` 必须走锚点，不能退回全量流水。

    这是最隐蔽的复发路径：`nav_backfill_job` 在官方净值回填后会调本函数。
    若它走旧口径，用户修好的份额会在下一次净值回填时被静默打回 2 倍。
    """
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id))
    for qty, price, confirm in (
        (7757, 1.2875, date(2026, 1, 27)),
        (1487, 1.3433, date(2026, 5, 26)),
        (1839, 1.3582, date(2026, 6, 18)),
    ):
        PositionService.process_buy_or_deposit(db, _buy(ledger.id, qty, price, confirm))
    db.flush()

    # 模拟净值回填后的重算
    PositionService.recompute_position_from_transactions(db, pos.id)
    db.flush()

    assert _shares(pos) == 11083, '重算不得把快照日之前的流水再加一遍'


def test_recompute_without_anchor_uses_full_flow(db, ledger):
    """无锚点持仓的重算保持旧口径（历史行为不变）。"""
    for qty, price, confirm in ((100.0, 1.0, date(2026, 3, 1)), (200.0, 1.0, date(2026, 4, 1))):
        PositionService.process_buy_or_deposit(db, _buy(ledger.id, qty, price, confirm))
    db.flush()
    pos = db.query(Position).first()
    PositionService.recompute_position_from_transactions(db, pos.id)
    db.flush()
    assert _shares(pos) == 300.0


# ── 5. 纯函数口径 ────────────────────────────────────────────


def test_compute_anchored_state_cost_is_based_on_anchor_price(db, ledger):
    """成本 =（快照份额 × 快照价 + 快照后买入成本）/（快照份额 + 快照后买入份额）。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=1000.0, price=1.0))
    PositionService.process_buy_or_deposit(db, _buy(ledger.id, 1000.0, 2.0, date(2026, 9, 1)))
    db.flush()

    net_qty, avg = compute_anchored_state(db, pos)
    assert net_qty == Money.shares_to_min_unit(2000.0)
    # (1000×1.0 + 1000×2.0) / 2000 = 1.5
    assert round(Money.price_units_to_yuan(avg), 4) == 1.5


def test_shadow_position_skips_anchor(db, ledger):
    """E账户影子行不走锚点：它只在 meta 层有日期，写 positions 锚点会搅乱对账链路。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id), ownership_status='shadow')
    assert pos.snapshot_quantity is None
    assert pos.snapshot_date is None
    assert pos.anchor_kind is None


def test_import_meta_snapshot_date_still_written(db, ledger):
    """锚点改动不破坏既有溯源：position_import_meta.snapshot_date 照旧写入（E账户对账依赖它）。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id))
    meta = db.query(PositionImportMeta).filter_by(position_id=pos.id).first()
    assert meta is not None
    assert meta.snapshot_date == SNAP_DATE


# ── 6. 清仓不删行与再买入复用（#2343 第二步，2026-10-18 实测定稿）──


def _sell_all(pos, qty, price, confirm, **overrides):
    data = {
        'position_id': pos.id,
        'symbol': '600000',
        'name': '示例基金',
        'asset_type': 'stock',
        'ledger_id': pos.ledger_id,
        'op_type': 'sell',
        'quantity': qty,
        'avg_price': price,
        'trade_date': confirm,
        'confirm_date': confirm,
        'source': 'manual',
        'family_id': 1,
    }
    data.update(overrides)
    return data


def test_clear_keeps_row_and_anchor(db, ledger):
    """清仓不再删行：行保留、cleared 标记、锚点与成本基线原样留存。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=5000.0, price=1.34))
    result = PositionService.process_sell_or_withdraw(
        db, _sell_all(pos, 5000.0, 1.50, date(2026, 10, 6))
    )

    # 调用方契约不变：清仓仍返回 None
    assert result is None
    db.refresh(pos)
    assert pos.ownership_status == 'cleared'
    assert _shares(pos) == 0
    assert pos.cleared_at is not None
    # 锚点四列不灭——这是本改动存在的全部理由
    assert Money.min_unit_to_shares(pos.snapshot_quantity) == 5000.0
    assert pos.snapshot_date == SNAP_DATE
    assert pos.anchor_kind == 'external'


def test_rebuy_reuses_row_with_correct_cost(db, ledger):
    """清仓后再买入：复用同一行 + 锚点重置，成本价必须是本轮的 1.60 而非 1.4375。

    数值来自 2026-10-18 的探针实测：不重置锚点时，上一轮成本额经卖出按比例核销后
    仍有残留，新一轮 3000 份 @1.60 会被派生成 1.4375（虚低 10.2%，浮盈虚高）。
    """
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=5000.0, price=1.34))
    PositionService.process_sell_or_withdraw(db, _sell_all(pos, 5000.0, 1.50, date(2026, 10, 6)))
    db.flush()

    result = PositionService.process_buy_or_deposit(db, _buy(ledger.id, 3000.0, 1.60, date(2026, 10, 20)))
    db.flush()

    assert result.id == pos.id, '同账户同标的受唯一约束，必须复用同一行'
    assert pos.ownership_status == 'active'
    assert _shares(pos) == 3000.0
    assert round(Money.price_units_to_yuan(pos.avg_price), 4) == 1.60
    # 锚点已重置为新一轮起点
    assert Money.min_unit_to_shares(pos.snapshot_quantity) == 0
    assert pos.snapshot_date == date(2026, 10, 6)
    assert pos.anchor_kind == 'manual'
    assert pos.cleared_at is not None, 'cleared_at 是周期下界，重新激活时刻意保留'


def test_delete_clearing_sell_revives_position(db, ledger):
    """删除清仓卖出流水 → 持仓复活（active + 锚点口径份额），锚点全程无断链。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=5000.0, price=1.34))
    PositionService.process_sell_or_withdraw(db, _sell_all(pos, 5000.0, 1.50, date(2026, 10, 6)))
    db.flush()
    assert pos.ownership_status == 'cleared'

    sell_txn = db.query(Transaction).filter_by(position_id=pos.id, txn_type='sell').one()
    db.delete(sell_txn)
    db.flush()
    PositionService.recompute_position_from_transactions(db, pos.id)
    db.refresh(pos)

    assert pos.ownership_status == 'active'
    assert _shares(pos) == 5000.0
    assert pos.cleared_at is not None, '历史周期下界保留'


def test_recompute_zero_marks_cleared_instead_of_delete(db, ledger):
    """重算归零 → 标记清仓而非删行（#2343：净份额归零不再 db.delete）。"""
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=5000.0, price=1.34))
    PositionService.process_sell_or_withdraw(db, _sell_all(pos, 5000.0, 1.50, date(2026, 10, 6)))
    db.flush()

    PositionService.recompute_position_from_transactions(db, pos.id)
    db.refresh(pos)

    assert pos is not None, '行必须保留'
    assert pos.ownership_status == 'cleared'
    assert _shares(pos) == 0
    assert pos.snapshot_date == SNAP_DATE, '锚点留存'


def test_cleared_row_accepts_older_snapshot(db, ledger):
    """已清仓行重新导入快照 = 开启新一轮周期，时间轴守卫放行。

    对照结构：同一份「比上一轮锚点更早」的快照，active 行被 _assert_anchor_accepts
    拒绝（时间不可倒流），cleared 行放行——旧锚点只是上一轮残留，对新一轮没有
    「当前值」意义。测试不断言份额：8-12 快照 5000 份 + 10-06 卖出 5000 份，与
    7-01 的新快照在时间线上互相矛盾，负份额钳 0 是既有兜底（已有用例覆盖钳 0）。
    """
    pos = PositionService.upsert_from_holding(db, _snapshot(ledger.id, qty=5000.0, price=1.34))
    with pytest.raises(ValueError, match='拒绝用更旧的数据覆盖'):
        PositionService.upsert_from_holding(
            db, _snapshot(ledger.id, qty=800.0, price=2.0, snap_date=date(2026, 7, 1))
        )

    PositionService.process_sell_or_withdraw(db, _sell_all(pos, 5000.0, 1.50, date(2026, 10, 6)))
    db.flush()

    # 清仓后，同一份更早的快照不再被拒，锚点被新一轮整条替换
    new_pos = PositionService.upsert_from_holding(
        db, _snapshot(ledger.id, qty=800.0, price=2.0, snap_date=date(2026, 7, 1))
    )
    db.flush()

    assert new_pos.id == pos.id
    assert new_pos.ownership_status == 'active'
    assert new_pos.snapshot_date == date(2026, 7, 1)


def test_zero_flow_shell_row_still_deleted_on_recompute(db, ledger):
    """无流水无锚点的空壳行重算仍删行——不是清仓历史，标记 cleared 反而伪造「曾持有」。"""
    shell = Position(
        symbol='600000',
        name='示例基金',
        asset_type='stock',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(1000.0),
        avg_price=Money.yuan_to_price_units(1.0),
        source='manual',
        ownership_status='active',
    )
    db.add(shell)
    db.flush()

    PositionService.recompute_position_from_transactions(db, shell.id)

    assert db.query(Position).filter_by(id=shell.id).first() is None
