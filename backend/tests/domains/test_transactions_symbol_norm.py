# -*- coding: utf-8 -*-
"""#1662 遗留项：流水身份键（`transactions.symbol_norm`）的写入与读取回归。

## 为什么单独立文件

`positions.symbol_norm` 有 `test_migrations_positions_symbol_norm.py` 与唯一索引兜着，
流水侧没有唯一约束（同一标的天经地义有多笔），**约束层帮不上忙** —— 它只能靠
「写入时算对 + 读取时按它匹配」两条腿站住。这两条腿各自失效都是静默的，
必须各自钉住。

## 本文件钉住的事实

- 落库时 `symbol_norm` 由 mapper 事件自动算，调用方无需传（14 处写入路径漏一处就复发）；
- 带前缀的场外码与裸码收敛到同一身份（`SZ001937` / `001937` → `OTC:001937`）；
- `asset_type` 缺失时**不猜 venue**，退化为 `NO_VENUE:` 降级形态（与 `core/venues` 一致）；
- 读侧按身份键匹配，能跨写法命中（本卡修的那个漏算）。
"""

from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.position_service import list_position_transactions
from app.services.symbol_scope import (
    build_position_symbol_conditions,
    build_transaction_symbol_conditions,
)


def test_mapper_event_fills_symbol_norm_without_caller(make_transaction):
    """写入路径不传 symbol_norm 也要自动算出来 —— 这是「不依赖调用方自觉」的关键。"""
    txn = make_transaction(position_id=None, ledger_id=1, symbol='SH600519', asset_type='stock')
    assert txn.symbol_norm == 'EXCHANGE:SH600519'


def test_otc_prefix_variant_collapses_to_bare_code(make_transaction):
    """场外码被套上交易所前缀时，身份键必须收敛到裸码形态。

    这是本机实测的污染形态：持仓 `001937`、流水 `SZ001937`，两侧字面量永远不等，
    但身份相等 —— 读侧能力就从「字面量」升级到「身份」。
    """
    txn = make_transaction(position_id=None, ledger_id=1, symbol='SZ001937', asset_type='fund')
    assert txn.symbol_norm == 'OTC:001937'
    # symbol 字面量保持快照原貌，不因归一而被改写
    assert txn.symbol == 'SZ001937'


def test_same_segment_different_venue_gets_distinct_identity(make_transaction):
    """`970164`（场外货基）与 `SH970164`（沪市场内货基）代码段相同、场所不同，身份必须不同。

    只看 symbol 判不了 venue —— 这正是 `symbol_identity` 要求 `asset_type` 的原因。
    """
    otc = make_transaction(position_id=None, ledger_id=1, symbol='970164', asset_type='money_fund')
    exch = make_transaction(position_id=None, ledger_id=1, symbol='SH970164', asset_type='money_fund')
    assert otc.symbol_norm == 'OTC:970164'
    assert exch.symbol_norm == 'EXCHANGE:SH970164'
    assert otc.symbol_norm != exch.symbol_norm


def test_missing_asset_type_degrades_without_guessing(make_transaction):
    """`asset_type` 为空时**不猜场所**，退化为 `NO_VENUE:{字面量}`。

    这是已知降级：宁可身份不等、让审计暴露，也不能把一笔真股票猜成场外基金
    （`000638` 同名段：基金「富国富钱包货币A」/ 深市「*ST万方」）。
    """
    txn = make_transaction(position_id=None, ledger_id=1, symbol='SZ000638')
    assert txn.asset_type is None
    assert txn.symbol_norm == 'NO_VENUE:SZ000638'


def test_symbol_norm_recomputed_on_update(make_transaction, db):
    """`before_update` 重算：改了 symbol / asset_type 却留着旧身份，等于把错误固化。"""
    txn = make_transaction(position_id=None, ledger_id=1, symbol='SZ001937')
    assert txn.symbol_norm == 'NO_VENUE:SZ001937'

    txn.asset_type = 'fund'
    db.flush()
    assert txn.symbol_norm == 'OTC:001937'

    db.refresh(txn)
    assert txn.symbol_norm == 'OTC:001937'


def test_read_side_matches_across_symbol_forms(make_position, make_transaction, db):
    """持仓裸码 + 流水带前缀，`list_position_transactions` 必须命中。

    这是本卡修的那条真实漏算路径（`position_service` 的持仓抽屉数据源）。
    """
    pos = make_position(symbol='001937', name='兴银现金增利货币', asset_type='fund', account_name='测试账户')
    txn = make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='SZ001937',
        asset_type='fund',
        position_name='兴银现金增利货币',
    )

    rows = list_position_transactions(db, pos)
    assert [r.id for r in rows] == [txn.id]


def test_read_side_does_not_match_other_product(make_position, make_transaction, db):
    """反证：身份键匹配不能把别的标的也捞进来（否则就是把漏算换成多算）。"""
    pos = make_position(symbol='001937', name='兴银现金增利货币', asset_type='fund', account_name='测试账户')
    make_transaction(position_id=pos.id, ledger_id=pos.ledger_id, symbol='SZ001937', asset_type='fund')
    make_transaction(position_id=None, ledger_id=pos.ledger_id, symbol='SZ003474', asset_type='fund')

    rows = list_position_transactions(db, pos)
    assert [r.symbol for r in rows] == ['SZ001937']


def test_transaction_conditions_cover_prefix_and_bare_forms():
    """条件构造本身：`001937` 的传入值要能覆盖 `SZ001937` 那批行的身份。"""
    from app.core.symbol_utils import symbol_identity

    # 传入裸码 → 生成 OTC:001937 条件 → 命中 symbol 为 SZ001937、身份为 OTC:001937 的行
    assert symbol_identity('SZ001937', 'fund') == 'OTC:001937'
    conditions = build_transaction_symbol_conditions('001937')
    assert any('symbol_norm' in str(c) for c in conditions)
    # 字面量条件仍在（兼容迁移前的 NO_VENUE 降级行）
    assert any('symbol' in str(c) for c in conditions)


def test_position_and_transaction_conditions_share_vocabulary():
    """两侧条件必须同源：持仓 `001937` 与流水 `SZ001937` 归一到同一身份键。"""
    from app.core.symbol_utils import symbol_identity

    assert symbol_identity('001937', 'fund') == symbol_identity('SZ001937', 'fund')
    assert build_position_symbol_conditions('001937')
    assert build_transaction_symbol_conditions('001937')


def test_position_model_still_has_identity(tmp_path):
    """模型层的 symbol_norm 列仍在（防止有人「清理」时把它当冗余删掉）。"""
    assert 'symbol_norm' in Transaction.__table__.columns
    assert 'symbol_norm' in Position.__table__.columns
