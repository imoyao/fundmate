# -*- coding: utf-8 -*-
"""配置目标归置规则单测（#3031 / G2）。

判据锚在**结构**上而不是全文 includes：负债守卫若被改成「静默返回 longterm」，
``test_liability_*`` 必须红；规则表若被塞进 liability，``test_rule_table_*`` 必须红。
"""

import pytest

from app.core.allocation_rules import (
    LIQUID,
    LONGTERM,
    MAJOR_CATEGORY_TO_ALLOCATION,
    NON_MEMBER_MAJOR_CATEGORIES,
    SECURITY,
    SPECULATIVE,
    STABLE,
    LiabilityAllocationError,
    derive_allocation,
    is_allocation_member,
    normalize_allocation_source,
)


class TestLiabilityGuard:
    """P0-6：负债永不进五笔钱。这是硬 fail，不是「返回个默认值」。"""

    def test_liability_raises(self):
        with pytest.raises(LiabilityAllocationError):
            derive_allocation('liability')

    def test_liability_raises_even_with_cash_asset_type(self):
        # 产品类型不能绕过负债红线
        with pytest.raises(LiabilityAllocationError):
            derive_allocation('liability', 'cash')

    def test_rule_table_has_no_liability(self):
        assert 'liability' not in MAJOR_CATEGORY_TO_ALLOCATION
        assert 'liability' in NON_MEMBER_MAJOR_CATEGORIES

    def test_speculative_not_in_rule_table(self):
        # speculative 不自动判，留人工
        assert SPECULATIVE not in MAJOR_CATEGORY_TO_ALLOCATION.values()


class TestMemberBoundary:
    """G0 冻结分母：只算可投资资产端，房产/应收/负债列为「未纳入」。"""

    @pytest.mark.parametrize(
        'cat', ['liability', 'real_estate', 'fixed', 'vehicle', 'receivable', 'precious_metal', 'custom']
    )
    def test_non_member_categories(self, cat):
        assert is_allocation_member(cat) is False

    @pytest.mark.parametrize('cat', ['cash', 'investment', 'bank_wealth', 'bond', 'insurance'])
    def test_member_categories(self, cat):
        assert is_allocation_member(cat) is True

    def test_none_is_not_member(self):
        assert is_allocation_member(None) is False

    @pytest.mark.parametrize('cat', ['real_estate', 'receivable', 'fixed', 'custom', None])
    def test_non_members_are_not_auto_assigned(self, cat):
        assert derive_allocation(cat) is None


class TestDerivation:
    """规则表：与 docs/design/allocation-governance.md §四 G2 逐条对齐。"""

    @pytest.mark.parametrize(
        'major,asset_type,want',
        [
            ('cash', None, LIQUID),
            ('cash', 'money_fund', LIQUID),
            ('investment', 'money_fund', LIQUID),
            ('investment', 'reverse_repo', LIQUID),
            ('investment', 'fund', LONGTERM),
            ('investment', 'stock', LONGTERM),
            ('bond', None, STABLE),
            ('bank_wealth', None, STABLE),
            ('insurance', None, SECURITY),
            ('wealth_insurance', None, SECURITY),
            ('advisory', None, LONGTERM),
            ('trust', None, LONGTERM),
            ('private_fund', None, LONGTERM),
        ],
    )
    def test_mapping(self, major, asset_type, want):
        assert derive_allocation(major, asset_type) == want

    def test_unknown_major_returns_none(self):
        assert derive_allocation('something_new') is None

    def test_cash_wins_over_major_default(self):
        # 用户反馈「每个账户里类似现金的东西应该自动归入活钱」：
        # 即便大类写的是 investment，产品类型是货基也必须判 liquid
        assert derive_allocation('investment', 'money_fund') == LIQUID


class TestSourceNormalization:
    """出参归一（#3031 / G1）：ORM 纯内存对象该列为 ``None`` 时仍输出 ``default``。

    CI services 组 10 例曾因 ``PositionOut.allocation_source`` 非 Optional 而全红：
    纯函数测试 new 出来的 ``Position`` 拿不到 ``Column(default=...)`` 的值。
    列本身 ``NOT NULL DEFAULT 'default'``，落库后必然是 ``default``，故归一与之等价；
    不许靠改夹具、放宽出参类型或写回 ORM 对象绕过（#2406）。
    """

    def test_none_becomes_default(self):
        assert normalize_allocation_source(None) == 'default'

    def test_empty_string_becomes_default(self):
        assert normalize_allocation_source('') == 'default'

    @pytest.mark.parametrize('src', ['default', 'import', 'user', 'governance'])
    def test_real_source_preserved(self, src):
        assert normalize_allocation_source(src) == src
