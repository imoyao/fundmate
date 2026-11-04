# -*- coding: utf-8 -*-
"""配对规则（``importer/linking.py``）单测。

钉的是「哪些行属于同一笔现金流」这条业务判据，不是某个解析器的实现细节——
故用 ``StandardTransactionRecord`` 直接构造，全程不经过解析器。这样换券商、
加解析器都不会让这些用例失效；反过来，规则本身改错会立刻红。

真实数据锚点（table1101.xls，同花顺交割单）：
- 丰山转债 SH113649：债券兑息 90 元 + 债券兑息兑付 −18 元（20% 个税）
- 龙大转债 SZ128119：债券兑息 220 + 税 −44；债券兑付 12430 元 + 股份转出 110 张
"""

from datetime import date
from decimal import Decimal

from app.services.import_records import StandardTransactionRecord
from app.services.importer.linking import RULES, apply_linking_rules

DAY = date(2026, 6, 26)


def rec(**overrides) -> StandardTransactionRecord:
    """构造一条最小可用记录，只显式给配对关心的字段。"""
    fields = {
        'confirm_date': DAY,
        'trade_date': DAY,
        'asset_type': 'stock',
        'symbol': 'SH113649',
        'name': '丰山转债',
        'business_type': 'dividend_cash',
        'amount': Decimal('90'),
        'account_name': '券商账户',
        'raw_op_type': '债券兑息',
    }
    fields.update(overrides)
    return StandardTransactionRecord(**fields)


def interest(**overrides) -> StandardTransactionRecord:
    return rec(**overrides)


def tax(**overrides) -> StandardTransactionRecord:
    base = {'business_type': 'tax', 'amount': Decimal('-18'), 'raw_op_type': '债券兑息兑付'}
    base.update(overrides)
    return rec(**base)


def redeem(**overrides) -> StandardTransactionRecord:
    base = {
        'business_type': 'bond_redeem',
        'amount': Decimal('12430'),
        'raw_op_type': '债券兑付',
        'symbol': 'SZ128119',
        'name': '龙大转债',
    }
    base.update(overrides)
    return rec(**base)


def share_out(**overrides) -> StandardTransactionRecord:
    """兑付时券商附带的「股份转出」：有份额、无现金。"""
    base = {
        'business_type': 'withdraw',
        'amount': Decimal('0'),
        'shares': Decimal('110'),
        'raw_op_type': '股份转出',
        'symbol': 'SZ128119',
        'name': '龙大转债',
    }
    base.update(overrides)
    return rec(**base)


class TestBondInterestTax:
    def test_interest_and_tax_share_one_group(self):
        """兑息 90 + 税 −18：同一笔利息的两面，必须同组（前端才能折成「实收 72」）。"""
        rows = [interest(), tax()]
        warnings = apply_linking_rules(rows)

        assert rows[0].link_group_id
        assert rows[0].link_group_id == rows[1].link_group_id
        assert warnings == []

    def test_group_id_is_deterministic(self):
        """同一份交割单重复导入应得到同一个组名（排查时肉眼可读）。"""
        first = [interest(), tax()]
        apply_linking_rules(first)

        second = [interest(), tax()]
        apply_linking_rules(second)

        assert first[0].link_group_id == second[0].link_group_id
        assert 'SH113649' in first[0].link_group_id

    def test_tax_ratio_mismatch_keeps_group_but_warns(self):
        """税率不对不拆组：拆了用户要多修两行，而问题本来只是一条提示。

        本例税 27 元 = 利息的 30%，超出「20% ± 容差」。
        """
        rows = [interest(), tax(amount=Decimal('-27'))]
        warnings = apply_linking_rules(rows)

        # 仍然同组（数据有问题也比丢关联强）
        assert rows[0].link_group_id == rows[1].link_group_id
        # 但两侧都带上提示，前端可展示
        assert '20%' in rows[0].link_warning
        assert rows[0].link_warning == rows[1].link_warning
        assert len(warnings) == 1

    def test_small_rounding_slippage_is_tolerated(self):
        """分位四舍五入（±0.02 元内）不该报——利息 0.90 元时 20% 为 0.18，差一分很正常。"""
        rows = [interest(amount=Decimal('0.90')), tax(amount=Decimal('-0.19'))]
        warnings = apply_linking_rules(rows)

        assert rows[0].link_warning == ''
        assert warnings == []

    def test_different_day_is_not_paired(self):
        """跨日不配：兑息与税同日发生才是同一笔（跨日的 A 股红利税补扣刻意不配）。"""
        rows = [interest(), tax(trade_date=date(2026, 6, 25), confirm_date=date(2026, 6, 25))]
        apply_linking_rules(rows)

        assert rows[0].link_group_id is None
        assert rows[1].link_group_id is None

    def test_different_symbol_is_not_paired(self):
        rows = [interest(), tax(symbol='SZ128119')]
        apply_linking_rules(rows)

        assert rows[0].link_group_id is None
        assert rows[1].link_group_id is None

    def test_plain_cash_dividend_is_never_paired(self):
        """A 股「红利入账 + 同日扣税」刻意不配。

        股息红利是按持股期限的**差别化税率**（1 个月内 20% / 1 月~1 年 10% /
        1 年以上免征），拿 20% 去校验会大面积误报；且真实样本里这种扣税常常
        隔 17~30 天、一笔分红对多笔税，配上去就是假关联。
        """
        rows = [
            rec(raw_op_type='红利入账', amount=Decimal('175.01'), symbol='SH603327'),
            tax(amount=Decimal('-17.50'), symbol='SH603327'),
        ]
        warnings = apply_linking_rules(rows)

        assert rows[0].link_group_id is None
        assert rows[1].link_group_id is None
        assert warnings == []

    def test_ambiguous_candidates_skip_pairing(self):
        """同标的同日出现两笔税：数量不唯一，放弃配对（宁可不折，不造假关联）。"""
        rows = [interest(), tax(amount=Decimal('-18')), tax(amount=Decimal('-9'))]
        warnings = apply_linking_rules(rows)

        assert all(r.link_group_id is None for r in rows)
        assert len(warnings) == 1
        assert '不唯一' in warnings[0]

    def test_already_grouped_rows_are_left_alone(self):
        """幂等：已带 link_group_id 的行不再重新配对（解析重跑不该改历史分组）。"""
        rows = [interest(), tax()]
        rows[0].link_group_id = 'existing-group'
        apply_linking_rules(rows)

        assert rows[0].link_group_id == 'existing-group'
        assert rows[1].link_group_id is None


class TestRedeemShareClearing:
    def test_pure_share_withdraw_is_consumed(self):
        """兑付已清仓（#2835），券商附带的「股份转出」若再入账就是双重扣份额。"""
        rows = [redeem(), share_out()]
        apply_linking_rules(rows)

        assert rows[1].consumed_by == 'redeem_share_clearing'
        # 主记录不受影响：它要正常入账
        assert rows[0].consumed_by == ''

    def test_cash_withdraw_is_never_consumed(self):
        """带现金的 withdraw 是**资金取出**，绝不能消费——吞掉它用户会看到钱少了却没记录。"""
        rows = [redeem(), share_out(amount=Decimal('12430'), shares=Decimal('0'))]
        apply_linking_rules(rows)

        assert rows[1].consumed_by == ''

    def test_withdraw_on_another_day_is_not_consumed(self):
        rows = [redeem(), share_out(trade_date=date(2026, 7, 17), confirm_date=date(2026, 7, 17))]
        apply_linking_rules(rows)

        assert rows[1].consumed_by == ''


class TestRuleTable:
    def test_rule_names_are_unique(self):
        """规则名会写进 consumed_by 与日志，重名会让「是哪条规则干的」失去意义。"""
        names = [r.name for r in RULES]
        assert len(names) == len(set(names))

    def test_actions_are_declared_values(self):
        """action 是封闭枚举：写错应在开发期就被发现，而不是运行时静默跳过。"""
        assert {r.action for r in RULES} <= {'merge', 'consume'}

    def test_every_rule_explains_why(self):
        """每条规则都要写清「不配会怎样」——否则后来者不敢删也看不懂能不能改。"""
        for rule in RULES:
            assert rule.why, f'规则 {rule.name} 缺少 why'
