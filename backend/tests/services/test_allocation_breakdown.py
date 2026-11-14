# -*- coding: utf-8 -*-
"""五笔钱成员边界与分桶（#3031 / G4）的判据。

反向验证锚点（任一条失守即说明「活钱」又变回空态，或负债被算进长期增值）：

- ``test_liability_never_hits_any_bucket``：负债若进桶，本用例必须红；
- ``test_cash_asset_falls_into_liquid``：若把资产行重新排除出分布（P0-1 回潮），必须红；
- ``test_buckets_sum_equals_scope_denominator``：恒等断言，防「Σ桶 ≠ 分母」的双算；
- ``test_user_source_overrides_derivation``：显式配置被推导规则改写，必须红；
- ``test_scope_buckets_keep_empty_slots``：五笔钱空档被过滤掉（首页「保命钱 0」看不见了），必须红。
"""

from app.core.constants import ALLOCATION_LABELS
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.positions.models import Position
from app.services.allocation_breakdown import (
    allocation_group_items,
    allocation_payload,
    asset_allocation_value,
)


def _pos_value(p):
    """持仓市值替身：数量(份) × 现价（元）。保持与 summary_service 注入同语义。"""
    return Money.min_unit_to_shares(p.quantity) * Money.price_units_to_yuan(p.current_price)


def _make_pos(db, *, symbol='A', allocation='longterm', quantity=100, price=1000):
    pos = Position(
        symbol=symbol,
        name=symbol,
        market='CN_A',
        asset_type='stock',
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(price),
        current_price=Money.yuan_to_price_units(price),
        currency='CNY',
        allocation=allocation,
        account_name='账户',
    )
    db.add(pos)
    return pos


def _make_asset(db, *, name, major_category, amount, allocation=None, allocation_source=None):
    kwargs = {}
    if allocation is not None:
        kwargs['allocation'] = allocation
    if allocation_source is not None:
        kwargs['allocation_source'] = allocation_source
    asset = Asset(
        user_id=1,
        major_category=major_category,
        name=name,
        amount=Money.yuan_to_cents(amount),
        currency='CNY',
        **kwargs,
    )
    if db is not None:
        db.add(asset)
    return asset


def _find(dist, name):
    return next((d['value'] for d in dist if d['name'] == name), None)


class TestAssetAllocationValue:
    """单行归置：优先级链 用户显式 > 大类推导 > 默认值。"""

    def test_cash_asset_falls_into_liquid(self):
        # 现金行没被显式配置过（来源 default）⇒ 按大类推导进活钱
        assert asset_allocation_value(_make_asset(None, name='活期', major_category='cash', amount=1)) == 'liquid'
        assert (
            ALLOCATION_LABELS[asset_allocation_value(_make_asset(None, name='活期', major_category='cash', amount=1))]
            == '活钱'
        )

    def test_user_source_overrides_derivation(self):
        asset = _make_asset(
            None, name='现金', major_category='cash', amount=1, allocation='stable', allocation_source='user'
        )
        assert asset_allocation_value(asset) == 'stable'

    def test_bank_wealth_is_stable(self):
        asset = _make_asset(None, name='理财', major_category='bank_wealth', amount=1)
        assert asset_allocation_value(asset) == 'stable'


class TestAllocationPayload:
    """分布出口：成员边界 + 恒等关系 + 「未纳入」显式可见。"""

    def test_liability_never_hits_any_bucket(self, db):
        _make_pos(db)
        _make_asset(db, name='房贷', major_category='liability', amount=1760000, allocation='longterm')
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=1760000.0,
        )
        assert data['allocation_distribution'] == [{'name': '长期增值', 'value': 100000.0}]
        assert data['allocation_scope']['liabilities_total'] == 1760000.0

    def test_cash_asset_joins_liquid_bucket(self, db):
        _make_pos(db)
        _make_asset(db, name='活期', major_category='cash', amount=50000)
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=0.0,
        )
        assert _find(data['allocation_distribution'], '长期增值') == 100000.0
        assert _find(data['allocation_distribution'], '活钱') == 50000.0

    def test_non_member_asset_is_excluded_not_bucketed(self, db):
        _make_pos(db)
        _make_asset(db, name='房子', major_category='real_estate', amount=2200091)
        _make_asset(db, name='借款应收', major_category='receivable', amount=50000)
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=0.0,
        )
        # 只持仓那一档：房产 / 应收 不进任何桶（G0 冻结口径「只算可投资资产端」）
        assert data['allocation_distribution'] == [{'name': '长期增值', 'value': 100000.0}]
        scope = data['allocation_scope']
        assert scope['denominator'] == 100000.0
        assert scope['excluded_total'] == 2250091.0
        assert {row['name'] for row in scope['excluded']} == {'房产', '应收款'}

    def test_buckets_sum_equals_scope_denominator(self, db):
        _make_pos(db, allocation='longterm')
        _make_pos(db, symbol='B', allocation='stable', quantity=10, price=100)
        _make_asset(db, name='活期', major_category='cash', amount=33333.33)
        _make_asset(db, name='理财', major_category='bank_wealth', amount=66666.67)
        _make_asset(db, name='房贷', major_category='liability', amount=1760000)
        _make_asset(db, name='房子', major_category='real_estate', amount=2200091)
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=1760000.0,
        )
        total = round(sum(row['value'] for row in data['allocation_distribution']), 2)
        assert total == data['allocation_scope']['denominator']
        # 分母只含持仓 + 成员资产：100000 + 1000 + 33333.33 + 66666.67
        assert total == 201000.0

    def test_zero_amount_asset_ignored(self, db):
        _make_asset(db, name='空账户', major_category='cash', amount=0)
        db.commit()
        data = allocation_payload([], db.query(Asset).all(), pos_value=_pos_value, liabilities_total=0.0)
        assert data['allocation_distribution'] == []
        assert data['allocation_scope']['denominator'] == 0.0

    def test_scope_buckets_keep_empty_slots(self, db):
        """五档全在、顺序固定、空档为 0.0 —— 首页「心理账户」卡靠它显示「保命钱为 0」。

        反向验证锚点：若 ``_buckets_with_zeros`` 退回成「只返回非零档」或直接复用
        ``allocation_distribution``，本用例必须红（那正是 #3115 D4 要防的形态：
        卡片只显示一档有钱，其余四笔钱静默消失）。
        """
        _make_pos(db)
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=0.0,
        )
        buckets = data['allocation_scope']['buckets']
        assert [b['key'] for b in buckets] == list(ALLOCATION_LABELS)
        assert [b['label'] for b in buckets] == list(ALLOCATION_LABELS.values())
        assert {b['key']: b['value'] for b in buckets} == {
            'liquid': 0.0,
            'stable': 0.0,
            'longterm': 100000.0,
            'speculative': 0.0,
            'security': 0.0,
        }
        # 两个键用途不同：distribution 是图表契约（不出零值扇区），buckets 是「五笔钱各多少」
        assert data['allocation_distribution'] == [{'name': '长期增值', 'value': 100000.0}]

    def test_scope_buckets_sum_equals_denominator(self, db):
        """``Σ buckets.value ≡ denominator``——与 distribution 同一恒等关系。"""
        _make_pos(db, allocation='longterm')
        _make_pos(db, symbol='B', allocation='stable', quantity=10, price=100)
        _make_asset(db, name='活期', major_category='cash', amount=33333.33)
        db.commit()

        data = allocation_payload(
            db.query(Position).all(),
            db.query(Asset).all(),
            pos_value=_pos_value,
            liabilities_total=0.0,
        )
        total = round(sum(b['value'] for b in data['allocation_scope']['buckets']), 2)
        assert total == data['allocation_scope']['denominator'] == 134333.33


class TestAllocationGroupItems:
    """分组出口：活钱可下钻，负债与非成员零命中。"""

    def test_group_items_include_member_assets(self, db):
        _make_pos(db)
        _make_asset(db, name='活期', major_category='cash', amount=50000)
        _make_asset(db, name='房贷', major_category='liability', amount=1760000)
        _make_asset(db, name='房子', major_category='real_estate', amount=2200091)
        db.commit()

        items = allocation_group_items(
            db.query(Position).all(),
            db.query(Asset).all(),
            lambda p: {'name': p.name, 'market_value': _pos_value(p)},
            lambda a: {'name': a.name, 'market_value': Money.cents_to_yuan(a.amount)},
        )
        keys = [key for key, _ in items]
        names = [payload['name'] for _, payload in items]
        assert '活钱' in keys
        assert names == ['A', '活期']  # 负债（房贷）与房产均不出现
