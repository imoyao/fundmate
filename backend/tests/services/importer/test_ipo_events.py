# -*- coding: utf-8 -*-
"""
通用「申购中签事件折叠器」单测。

⚠️ 隐私约定：本文件所有数据**均为虚构模拟值**——证券名称、申购/上市代码、
流水号、金额全部由测试构造，代码段取 999 结尾等不存在的号码；不含任何真实
账户信息，真实交割单样本不进仓库、不进 fixture、不进日志。
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.importer.ipo_events import (
    InMemoryAliasResolver,
    IpoEventFolder,
    IpoEventPolicy,
    IpoRow,
    NullAliasResolver,
    to_decimal,
)
from app.services.importer.mappings import (
    CMS_IPO_ANCHOR_OPS,
    CMS_IPO_CASH_OPS,
    CMS_IPO_CREDIT_OPS,
    CMS_IPO_LISTED_CODE_PREFIXES,
    CMS_IPO_MEMBER_OPS,
    CMS_IPO_PRICE_OP,
)
from app.services.importer.parsers.cms_stock import CMS_IPO_POLICY, CMSStockParser

# 虚构代码：不对应任何真实证券
APPLY_SZ = '072999'
APPLY_SH = '783999'
LISTED_SZ = '123999'
LISTED_SH = '113999'

POLICY = IpoEventPolicy(
    platform='mock_broker',
    anchor_ops=CMS_IPO_ANCHOR_OPS,
    member_ops=CMS_IPO_MEMBER_OPS,
    cash_ops=CMS_IPO_CASH_OPS,
    credit_ops=CMS_IPO_CREDIT_OPS,
    price_op=CMS_IPO_PRICE_OP,
)


def row(op, day, price, qty, amount, code=APPLY_SZ, name='模拟发债', line_no=2) -> IpoRow:
    return IpoRow(
        line_no=line_no,
        op=op,
        code=code,
        name=name,
        trade_date=day,
        price=Decimal(price),
        quantity=Decimal(qty),
        amount=Decimal(amount),
    )


def one_event(*, code=APPLY_SZ, anchor=date(2023, 1, 10), qty='10', reverse=False):
    """模拟招商「6 行一笔」中签链：净额恒为 −1000。"""
    d = anchor
    rows = [
        row('市值申购中签', d, '100.0000', qty, '0.00', code, line_no=2),
        row('市值申购中签扣款', d + timedelta(days=1), '0.0000', '0', '-1000.00', code, line_no=3),
        row('新股申购确认缴款', d + timedelta(days=3), '100.0000', qty, '-1000.00', code, line_no=4),
        row('市值申购中签扣款回冲', d + timedelta(days=3), '100.0000', '0', '1000.00', code, line_no=5),
        row('托管转出', d + timedelta(days=3), '0.0000', '0', '0.00', code, line_no=6),
    ]
    # 真实招商交割单是按日期**倒序**导出的，reverse 用来锁住这个回归。
    return list(reversed(rows)) if reverse else rows


def credit(day=date(2023, 2, 1), code=LISTED_SH, qty='1', name='模拟转债') -> IpoRow:
    return row('新股入账', day, '0.0000', qty, '0.00', code, name, line_no=9)


def build(rows, *, resolver=None, prefixes=CMS_IPO_LISTED_CODE_PREFIXES, policy=POLICY):
    folder = IpoEventFolder(
        policy,
        resolver=resolver,
        normalizer=None,  # 单测只断言原始码，不走交易所归一
        source='cms_stock',
        listed_code_prefixes=prefixes,
    )
    for r in rows:
        folder.collect(r)
    return folder.finalize()


class TestFolding:
    def test_six_rows_fold_into_one_buy(self):
        records, errors, consumed = build(one_event())
        assert errors == []
        assert len(records) == 1
        rec = records[0]
        assert rec.business_type == 'buy'
        assert rec.amount == Decimal('1000.00')  # 净现金流，冲正对自然抵消
        assert rec.shares == Decimal('10.0000')
        assert rec.nav == Decimal('100.0000')
        assert rec.shares * rec.nav == rec.amount  # 与卖出口径严格对齐
        assert rec.fee == Decimal('0')
        assert rec.confirm_date == date(2023, 1, 13)  # 最后一笔真实付款日
        assert consumed == 4  # 5 行折叠成 1 条记录，只算 4 行被消耗

    def test_reverse_chronological_export_still_groups_correctly(self):
        """招商按新→旧导出：分组不能依赖文件行序。"""
        records, errors, _ = build(one_event(reverse=True))
        assert errors == []
        assert len(records) == 1
        assert records[0].amount == Decimal('1000.00')

    @pytest.mark.parametrize('qty,code', [('10', APPLY_SZ), ('1', APPLY_SH)])
    def test_sh_and_sz_lot_units_both_become_ten_sheets(self, qty, code):
        """沪市 1「手」与深市 10「张」本金都是 1000，除法天然抹平 10 倍差。"""
        records, errors, _ = build(one_event(code=code, qty=qty))
        assert errors == []
        assert records[0].shares == Decimal('10.0000')
        assert records[0].amount == Decimal('1000.00')

    def test_two_wins_on_same_apply_code_produce_two_records(self):
        first = one_event(anchor=date(2023, 1, 10))
        second = [
            IpoRow(
                line_no=r.line_no + 10,
                op=r.op,
                code=r.code,
                name=r.name,
                trade_date=r.trade_date,
                price=r.price,
                quantity=r.quantity,
                amount=r.amount,
            )
            for r in one_event(anchor=date(2023, 3, 10))
        ]
        records, errors, _ = build(first + second)
        assert errors == []
        assert len(records) == 2
        assert len({r.transaction_id for r in records}) == 2
        assert all(r.amount == Decimal('1000.00') for r in records)

    def test_zero_net_cash_does_not_open_position(self):
        """未中签 / 全额退款：不建仓，但行仍被消耗、不报错。"""
        rows = [
            row('市值申购中签', date(2023, 1, 10), '100.0000', '10', '0.00'),
            row('市值申购中签扣款', date(2023, 1, 11), '0.0000', '0', '-1000.00'),
            row('市值申购中签扣款回冲', date(2023, 1, 12), '0.0000', '0', '1000.00'),
        ]
        records, errors, consumed = build(rows)
        assert records == [] and errors == []
        assert consumed == 3

    def test_invalid_anchor_price_reports_error(self):
        rows = one_event()
        rows[0] = IpoRow(
            line_no=2,
            op='市值申购中签',
            code=APPLY_SZ,
            name='模拟发债',
            trade_date=date(2023, 1, 10),
            price=Decimal('0'),
            quantity=Decimal('10'),
            amount=Decimal('0'),
        )
        records, errors, _ = build(rows)
        assert records == []
        assert len(errors) == 1
        assert '中签价无效' in errors[0].message

    def test_orphan_detail_without_anchor_reports_error(self):
        records, errors, _ = build([row('市值申购中签扣款', date(2023, 1, 11), '0', '0', '-1000.00')])
        assert records == []
        assert len(errors) == 1
        assert '找不到对应的中签记录' in errors[0].message


class TestSymbolResolution:
    def test_no_candidate_keeps_apply_code_with_warning(self):
        records, errors, _ = build(one_event())
        assert errors == []
        assert records[0].symbol == APPLY_SZ
        assert '打新中签建仓' in records[0].link_warning
        assert '请在预览页把证券代码改为上市代码' in records[0].link_warning

    def test_unique_credit_candidate_resolves_listed_code(self):
        rows = one_event(code=APPLY_SH) + [credit()]
        records, errors, _ = build(rows)
        assert errors == []
        assert records[0].symbol == LISTED_SH
        assert records[0].link_warning == ''
        assert records[0].name == '模拟转债'  # 名称对齐到上市简称

    def test_multiple_candidates_never_guess(self):
        rows = one_event(code=APPLY_SH) + [credit(), credit(code='113998', qty='1')]
        records, errors, _ = build(rows)
        assert errors == []
        assert records[0].symbol == APPLY_SH
        assert '存在多个，不自动匹配' in records[0].link_warning

    def test_alias_resolver_wins_over_candidates(self):
        resolver = InMemoryAliasResolver({APPLY_SZ: LISTED_SZ})
        rows = one_event() + [credit(), credit(code='113998')]
        records, errors, _ = build(rows, resolver=resolver)
        assert errors == []
        assert records[0].symbol == LISTED_SZ
        assert records[0].link_warning == ''

    def test_null_resolver_is_default(self):
        assert NullAliasResolver().resolve(APPLY_SZ, date(2023, 1, 10), '模拟发债') is None

    def test_credit_rows_are_not_counted_as_independent_flows(self):
        records, _, consumed = build(one_event(code=APPLY_SH) + [credit()])
        assert len(records) == 1
        assert consumed == 5  # 5 明细 + 1 入账 - 1 产出记录


class TestIdempotencyAndPrivacy:
    def test_event_key_is_stable_and_independent_of_broker_serial(self):
        rec1 = build(one_event())[0][0]
        rec2 = build(one_event(reverse=True))[0][0]
        assert rec1.transaction_id == rec2.transaction_id == 'IPO-20230110-072999'

    def test_no_account_identifiers_leak_into_record(self):
        rec = build(one_event())[0][0]
        assert rec.raw_text is None
        assert rec.error == ''
        for forbidden in ('0000000000', '资金余额', '股东代码', '备注'):
            assert forbidden not in repr(rec)

    def test_policy_rejects_inconsistent_membership(self):
        with pytest.raises(ValueError):
            IpoEventPolicy(
                platform='bad',
                anchor_ops=frozenset({'中签'}),
                member_ops=frozenset({'中签'}),
                cash_ops=frozenset({'扣款'}),  # 不在成员表
                credit_ops=frozenset(),
                price_op='中签',
            )

    @pytest.mark.parametrize('raw,expected', [('', 0), ('-', 0), ('nan', 0), ('1,000.50', Decimal('1000.50'))])
    def test_to_decimal_tolerates_placeholders(self, raw, expected):
        assert to_decimal(raw) == expected


class TestUnexplainedCredit:
    """入账行不配对时必须报出：这是「行数对账显示平、持仓却少了」的隐蔽丢行形态。"""

    def test_credit_without_any_event_is_reported(self):
        records, errors, consumed = build([credit()])
        assert records == []
        assert len(errors) == 1
        assert '找不到可配对的中签记录' in errors[0].message
        assert errors[0].line_number == 9
        assert consumed == 0  # 已作为错误计数，不能再算「被消耗」

    def test_credit_size_mismatch_is_reported(self):
        records, errors, _ = build(one_event() + [credit(qty='100')])
        assert len(records) == 1
        assert len(errors) == 1
        assert '找不到可配对的中签记录' in errors[0].message

    def test_zero_quantity_credit_stays_silent(self):
        """数量为 0 的入账行不可归属，维持既有口径：静默计入 consumed，不误报。"""
        records, errors, consumed = build(one_event() + [credit(qty='0')])
        assert errors == []
        assert consumed == 5

    def test_matched_credit_is_not_reported(self):
        records, errors, consumed = build(one_event(code=APPLY_SH) + [credit()])
        assert errors == []
        assert consumed == 5


class TestCmsParserIntegration:
    """端到端：招商解析器把打新链折叠成可导入的买入，且行数对账不破。"""

    HEADER = [
        '币种',
        '证券名称',
        '成交日期',
        '成交价格',
        '成交数量',
        '发生金额',
        '资金余额',
        '剩余数量',
        '合同编号',
        '流水号',
        '业务名称',
        '印花税',
        '佣金',
        '经手费',
        '证管费',
        '结算费',
        '过户费',
        '其他费用',
        '证券代码',
        '股东代码',
        '备注',
    ]

    @staticmethod
    def _cms_row(op, day, price, qty, amount, code, serial):
        values = {
            '币种': '人民币',
            '证券名称': '模拟发债',
            '成交日期': day,
            '成交价格': price,
            '成交数量': qty,
            '发生金额': amount,
            '资金余额': '0.00',
            '剩余数量': '0',
            '合同编号': '0',
            '流水号': serial,
            '业务名称': op,
            '印花税': '0.00',
            '佣金': '0.00',
            '经手费': '0.00',
            '证管费': '0.00',
            '结算费': '0.00',
            '过户费': '0.00',
            '其他费用': '0.00',
            '证券代码': code,
            '股东代码': '0000000000',
            '备注': '',
        }
        return [values[c] for c in TestCmsParserIntegration.HEADER]

    def _file(self, rows):
        lines = ['\t'.join(self.HEADER)] + ['\t'.join(r) for r in rows]
        return ('\n'.join(lines) + '\n').encode('gb18030')

    def test_ipo_chain_becomes_one_buy_and_identity_holds(self):
        rows = [
            self._cms_row('市值申购中签', '20230110', '100.0000', '10', '0.00', APPLY_SZ, '000000000001'),
            self._cms_row('市值申购中签扣款', '20230111', '0.0000', '0', '-1000.00', APPLY_SZ, '000000000002'),
            self._cms_row('新股申购确认缴款', '20230113', '100.0000', '10', '-1000.00', APPLY_SZ, '000000000003'),
            self._cms_row('市值申购中签扣款回冲', '20230113', '100.0000', '0', '1000.00', APPLY_SZ, '000000000004'),
            self._cms_row('托管转出', '20230113', '0.0000', '0', '0.00', APPLY_SZ, '000000000005'),
            self._cms_row('新股入账', '20230201', '0.0000', '10', '0.00', LISTED_SZ, '000000000006'),
        ]
        parser = CMSStockParser()
        records, errors = parser.parse(self._file(rows))
        assert errors == []
        assert len(records) == 1
        assert parser.folded_event_count == 1
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count
        rec = records[0]
        assert rec.business_type == 'buy'
        assert rec.amount == Decimal('1000.00')
        assert rec.shares == Decimal('10.0000')
        assert rec.nav == Decimal('100.0000')
        assert rec.transaction_id.startswith('IPO-')
        # 唯一入账候选且数量一致 → 自动归一到上市代码，无需人工补全
        assert rec.symbol != APPLY_SZ
        assert rec.link_warning == ''

    def test_alias_resolver_injection_changes_symbol_without_logic_change(self):
        resolver = InMemoryAliasResolver({APPLY_SZ: LISTED_SZ})
        rows = [
            self._cms_row('市值申购中签', '20230110', '100.0000', '10', '0.00', APPLY_SZ, '000000000001'),
            self._cms_row('新股申购确认缴款', '20230113', '100.0000', '10', '-1000.00', APPLY_SZ, '000000000003'),
        ]
        parser = CMSStockParser(alias_resolver=resolver)
        records, errors = parser.parse(self._file(rows))
        assert errors == []
        assert len(records) == 1
        assert records[0].link_warning == ''
        assert parser.pending_alias_count == 0

    def test_cms_policy_is_well_formed(self):
        assert CMS_IPO_POLICY.platform == 'cms_stock'
        assert CMS_IPO_POLICY.anchor_ops <= CMS_IPO_POLICY.member_ops

    def test_unsupported_new_stock_rows_never_disappear_silently(self):
        """新股中签（业务名未登记）+ 新股入账：不崩，且每一行都有明确交代。

        背景：新股申购的业务名没有真实样本，无法纳入正式折叠口径。这里锁的是
        「防御」本身——旧实现里 `新股入账` 属于 CREDIT_OPS，会被折叠器吞掉却无事件
        配对，最终静默计入 ignored，行数对账还显示「平」，用户完全看不出少了一只。
        """
        rows = [
            self._cms_row('新股中签', '20240301', '7.3500', '500', '0.00', '732543', '000000000301'),
            self._cms_row('新股中签缴款', '20240302', '0.0000', '0', '-3675.00', '732543', '000000000302'),
            self._cms_row('新股入账', '20240308', '7.3500', '500', '0.00', '603543', '000000000303'),
            self._cms_row('证券买入', '20240310', '116.5000', '80', '-9329.32', '127999', '000000000400'),
        ]
        parser = CMSStockParser(alias_resolver=NullAliasResolver())
        records, errors = parser.parse(self._file(rows))

        # 正常交易照进，不打折；三行新股相关各自留下可追溯的记录
        assert len(records) == 1
        assert records[0].symbol.endswith('127999')
        assert {e.raw_value for e in errors} == {'新股中签', '新股中签缴款', '新股入账'}
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

        # 文案必须说清「是什么、怎么办」，不能只说「无法识别」
        ipo_msg = next(e.message for e in errors if e.raw_value == '新股中签')
        assert '仅支持可转债打新' in ipo_msg and '手动补录' in ipo_msg
        credit_msg = next(e.message for e in errors if e.raw_value == '新股入账')
        assert '找不到可配对的中签记录' in credit_msg
