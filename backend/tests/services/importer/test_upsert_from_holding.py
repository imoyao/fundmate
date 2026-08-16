# -*- coding: utf-8 -*-
"""PositionService.upsert_from_holding 测试（#1012 核心新方法）。

覆盖：
- SET 语义：同 (ledger_id, symbol) 重复导入 → 数量整条替换，不累加；
- 绝不创建交易流水（持仓 vs 交易流水的本质区别）；
- 溯源元数据写入 position_import_meta（1:1 upsert）；
- avg_price 缺失时降级为当前净值近似；
- import_hash 幂等（同快照日重复导入不产生重复持仓）。
"""

from datetime import date

import pytest

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService


@pytest.fixture
def fund_ledger(db):
    ledger = Ledger(name='基金E账户', ledger_type='e_account', family_id=1)
    db.add(ledger)
    db.flush()
    return ledger


def _holding_data(ledger_id, **overrides):
    data = {
        'symbol': '012345',
        'name': '示例红利优选混合A',
        'asset_type': 'fund',
        'ledger_id': ledger_id,
        'account_name': '基金E账户',
        'quantity': 10000.0,
        'avg_price': 1.2345,
        'current_price': 1.2345,
        'snapshot_date': date(2026, 8, 12),
        'currency': 'CNY',
        'source': 'e_account_holding',
        'source_broker': '示例基金销售',
        'family_id': 1,
        'meta': {
            'fund_manager': '示例基金管理',
            'share_class': '前收费',
            'fund_account': 'FUNDACC0001',
            'trade_account': 'TRADEACC0001',
            'dividend_preference': '现金分红',
            'market_value': 12345.0,
        },
    }
    data.update(overrides)
    return data


def test_upsert_creates_position_without_transaction(db, fund_ledger):
    """新建持仓：落 positions，绝不产生交易流水。"""
    pos = PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id))

    assert pos.symbol == '012345'
    assert pos.quantity == Money.shares_to_min_unit(10000.0)
    assert pos.avg_price == Money.yuan_to_cents(1.2345)
    assert pos.current_price == Money.yuan_to_cents(1.2345)
    assert pos.confirm_date == date(2026, 8, 12)
    assert pos.source == 'e_account_holding'
    assert pos.source_broker == '示例基金销售'
    assert pos.import_hash  # 已生成去重哈希

    # 核心断言：不建交易流水
    assert db.query(Transaction).count() == 0

    # 溯源元数据写入
    meta = db.query(PositionImportMeta).filter_by(position_id=pos.id).first()
    assert meta is not None
    assert meta.fund_manager == '示例基金管理'
    assert meta.share_class == '前收费'
    assert meta.fund_account == 'FUNDACC0001'
    assert meta.trade_account == 'TRADEACC0001'
    assert meta.dividend_preference == '现金分红'
    assert meta.market_value == Money.yuan_to_cents(12345.0)
    assert meta.snapshot_date == date(2026, 8, 12)


def test_upsert_set_semantics_replaces_quantity(db, fund_ledger):
    """SET 语义：同 (ledger_id, symbol) 再次导入 → 数量整条替换，不累加。"""
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id, quantity=10000.0))

    # 第二次导入：数量变化（快照更新）
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id, quantity=20000.0, avg_price=1.5))

    positions = db.query(Position).filter_by(ledger_id=fund_ledger.id).all()
    assert len(positions) == 1  # 不产生重复持仓
    assert positions[0].quantity == Money.shares_to_min_unit(20000.0)  # 替换而非 30000 累加
    assert positions[0].avg_price == Money.yuan_to_cents(1.5)
    assert db.query(Transaction).count() == 0

    # meta 1:1 更新（不新增行）
    metas = db.query(PositionImportMeta).all()
    assert len(metas) == 1


def test_upsert_avg_cost_fallback_to_nav(db, fund_ledger):
    """avg_price 缺失 → 降级为当前净值近似（用户已确认）。"""
    data = _holding_data(fund_ledger.id)
    data.pop('avg_price')
    pos = PositionService.upsert_from_holding(db, data)
    assert pos.avg_price == Money.yuan_to_cents(1.2345)


def test_upsert_import_hash_idempotent(db, fund_ledger):
    """同快照日重复导入：import_hash 相同，持仓仍只有一条（幂等）。"""
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id))
    PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id))
    assert db.query(Position).count() == 1


def test_upsert_requires_symbol_and_ledger(db):
    """缺 symbol / ledger_id → ValueError。"""
    with pytest.raises(ValueError, match='symbol'):
        PositionService.upsert_from_holding(db, _holding_data(None))
    with pytest.raises(ValueError, match='ledger_id'):
        PositionService.upsert_from_holding(db, _holding_data(1, symbol=''))


def test_upsert_rejects_non_positive_quantity(db, fund_ledger):
    """数量非正 → ValueError。"""
    with pytest.raises(ValueError, match='数量'):
        PositionService.upsert_from_holding(db, _holding_data(fund_ledger.id, quantity=0))
