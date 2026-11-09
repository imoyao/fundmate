# -*- coding: utf-8 -*-
"""
招商证券交割单解析器单测。

⚠️ 隐私约定：本文件所有数据**均为虚构模拟值**——证券名称、代码、流水号、
股东代码、金额全部由测试构造，不含任何真实账户信息；真实交割单样本不进仓库、
不进 fixture、不进日志。新增用例不得粘贴真实导出文件的任何一行。
"""

from decimal import Decimal

import pytest

from app.core.constants import CASH_SYMBOL, PositionSource
from app.core.venues import EXCHANGE
from app.services.importer.ipo_events import NullAliasResolver
from app.services.importer.mappings import (
    CMS_CASH_TRANSFER_OPS,
    CMS_IGNORED_OPS,
    CMS_OP_MAP,
)
from app.services.importer.parsers.cms_stock import CMSStockParser
from app.services.importer.registry import get_all_sources, get_parser

# 招商证券导出文件的固定列序（模拟，与真实样本的列结构一致）。
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


def _f(value) -> str:
    """券商防科学计数法的 Excel 公式文本外壳。"""
    return f'="{value}"'


def _row(**overrides) -> list:
    """构造一行 21 列的模拟数据。"""
    defaults = {
        '币种': '人民币',
        '证券名称': '',
        '成交日期': '20230119',
        '成交价格': _f('0.0000'),
        '成交数量': _f('0'),
        '发生金额': '0.00',
        '资金余额': _f('0.00'),
        '剩余数量': _f('0'),
        '合同编号': _f('0'),
        '流水号': _f('000000000001'),
        '业务名称': '证券买入',
        '印花税': _f('0.00'),
        '佣金': _f('0.00'),
        '经手费': _f('0.00'),
        '证管费': _f('0.00'),
        '结算费': _f('0.00'),
        '过户费': _f('0.00'),
        '其他费用': _f('0.00'),
        '证券代码': '',
        '股东代码': _f('0000000000'),
        '备注': '',
    }
    defaults.update(overrides)
    return [defaults[name] for name in HEADER]


def _file(rows, encoding='gb18030', width=21, header=None):
    """按样本形态生成 TSV。

    width 模拟券商导出对尾部空列的截断：21=完整、20=省略备注、18=无证券信息的行。
    """
    lines = ['\t'.join(header if header is not None else HEADER)]
    for cells in rows:
        lines.append('\t'.join(cells[:width]))
    return ('\n'.join(lines) + '\n').encode(encoding)


def _buy_sz(**kw):
    """深市转债买入 80 张 @116.50，费用 9.32 → 净额 9329.32。"""
    base = {
        '证券名称': '示例转债',
        '成交价格': '116.5000',
        '成交数量': '80',
        '发生金额': '-9329.32',
        '佣金': '8.95',
        '经手费': '0.37',
        '证券代码': '127001',
    }
    base.update(kw)
    return _row(**base)


@pytest.fixture
def parser():
    return CMSStockParser()


class TestFileFormat:
    def test_gb18030_tsv_with_formula_cells(self, parser):
        """扩展名 .xls 实为 GB18030 制表符文本；公式文本外壳必须剥离。"""
        records, errors = parser.parse(_file([_buy_sz()], width=20))
        assert errors == []
        assert len(records) == 1
        rec = records[0]
        assert rec.confirm_date.isoformat() == '2023-01-19'
        assert rec.symbol == 'SZ127001'
        assert rec.name == '示例转债'
        assert rec.shares == Decimal('80')
        assert rec.nav == Decimal('116.5000')

    def test_utf8_variant(self, parser):
        records, errors = parser.parse(_file([_buy_sz()], encoding='utf-8', width=20))
        assert errors == []
        assert records[0].symbol == 'SZ127001'

    def test_tail_columns_truncated_to_18(self, parser):
        """无证券信息行只有 18 列，必须按索引补空，不能整体错位。"""
        row = _row(
            业务名称='银行转存',
            发生金额='5000.00',
            流水号='000000000042',
        )
        records, errors = parser.parse(_file([row], width=18))
        assert errors == []
        assert records[0].business_type == 'deposit'
        assert records[0].amount == Decimal('5000.00')

    def test_header_not_on_first_line(self, parser):
        """表头前有导出说明行时仍能定位。"""
        content = ('导出日期：模拟说明行\n' + _file([_buy_sz()], width=20).decode('gb18030')).encode('gb18030')
        records, errors = parser.parse(content)
        assert errors == []
        assert len(records) == 1

    def test_missing_required_columns(self, parser):
        header = [c for c in HEADER if c != '业务名称']
        cells = [_buy_sz()[HEADER.index(c)] for c in header]
        content = ('\t'.join(header) + '\n' + '\t'.join(cells) + '\n').encode('gb18030')
        records, errors = parser.parse(content)
        assert records == []
        assert any('缺少必要列' in e.message and '业务名称' in e.message for e in errors)

    def test_empty_file_and_non_broker_content(self, parser):
        for payload in (b'', b'not a broker file\nfoo\tbar\n'):
            records, errors = parser.parse(payload)
            assert records == []
            assert errors


class TestTrades:
    def test_buy_shenzhen_convertible_bond(self, parser):
        records, errors = parser.parse(_file([_buy_sz()], width=20))
        assert errors == []
        rec = records[0]
        assert rec.business_type == 'buy'
        assert rec.asset_type == 'bond'
        assert rec.venue == EXCHANGE
        assert rec.amount == Decimal('9329.32')
        assert rec.net_amount == Decimal('9329.32')
        assert rec.trade_amount == Decimal('9320.0000')
        assert rec.fee == Decimal('9.32')
        assert rec.fee_commission == Decimal('8.95')
        assert rec.fee_stamp_duty == Decimal('0.00')
        assert rec.fee_transfer_fee == Decimal('0.00')
        assert rec.fee_other == Decimal('0.37')
        assert rec.transaction_id == '20230119-000000000001-证券买入'
        assert rec.raw_op_type == '证券买入'
        assert rec.source == PositionSource.BROKER_CMS.value

    def test_sell_shenzhen_convertible_bond(self, parser):
        row = _buy_sz(
            业务名称='证券卖出',
            成交数量='-80',
            发生金额='9310.68',
            流水号=_f('000000000002'),
        )
        records, errors = parser.parse(_file([row], width=20))
        assert errors == []
        rec = records[0]
        assert rec.business_type == 'sell'
        assert rec.shares == Decimal('80')
        assert rec.amount == Decimal('9310.68')
        assert rec.trade_amount == Decimal('9320.0000')

    def test_sh_convertible_bond_lot_to_sheets(self, parser):
        """沪市转债数量单位是手（1 手 = 10 张），不换算会让 份额×净值 差 10 倍。"""
        row = _row(
            证券名称='模拟沪债',
            成交价格='114.0000',
            成交数量='1',
            发生金额='-1141.00',
            佣金='0.95',
            经手费='0.05',
            证券代码='110059',
        )
        records, errors = parser.parse(_file([row], width=20))
        assert errors == []
        rec = records[0]
        assert rec.symbol == 'SH110059'
        assert rec.shares == Decimal('10')
        assert rec.nav == Decimal('114.0000')
        assert rec.trade_amount == Decimal('1140.0000')
        assert rec.amount == Decimal('1141.00')
        # 买入恒等式：|净额| = 毛额 + 费用
        assert rec.net_amount == rec.trade_amount + rec.fee

    def test_stock_code_normalized(self, parser):
        row = _row(
            证券名称='模拟股票',
            成交价格='12.3400',
            成交数量='100',
            发生金额='-1234.00',
            证券代码='600000',
        )
        records, errors = parser.parse(_file([row], width=20))
        assert errors == []
        assert records[0].symbol == 'SH600000'
        assert records[0].asset_type == 'stock'
        assert records[0].trade_amount == Decimal('1234.0000')

    def test_fee_breakdown_sum_equals_fee(self, parser):
        row = _row(
            证券名称='模拟股票',
            成交价格='10.0000',
            成交数量='100',
            发生金额='-1003.00',
            业务名称='证券买入',
            印花税='1.00',
            佣金='0.50',
            经手费='0.20',
            证管费='0.10',
            结算费='0.05',
            过户费='0.10',
            其他费用='1.05',
            证券代码='600000',
        )
        rec = parser.parse(_file([row], width=20))[0][0]
        assert rec.fee == Decimal('3.00')
        parts = (rec.fee_commission, rec.fee_stamp_duty, rec.fee_transfer_fee, rec.fee_other)
        assert sum(parts, Decimal('0')) == rec.fee

    def test_fee_split_disabled_when_column_missing(self, parser):
        header = [c for c in HEADER if c != '结算费']
        row = _buy_sz()
        # 删掉「结算费」列对应的值，保持与 header 对齐
        idx = HEADER.index('结算费')
        cells = row[:idx] + row[idx + 1 :]
        content = ('\t'.join(header) + '\n' + '\t'.join(cells[: len(header)]) + '\n').encode('gb18030')
        rec = parser.parse(content)[0][0]
        assert (rec.fee_commission, rec.fee_stamp_duty, rec.fee_transfer_fee, rec.fee_other) == (
            None,
            None,
            None,
            None,
        )
        assert rec.fee == Decimal('9.32')


class TestNonTradeRows:
    def test_cash_transfer_direction_by_amount(self, parser):
        deposit = _row(业务名称='银行转存', 发生金额='5000.00', 流水号='000000000010')
        withdraw = _row(业务名称='银行转取', 发生金额='-1500.00', 流水号='000000000011')
        records, errors = parser.parse(_file([deposit, withdraw], width=18))
        assert errors == []
        assert [r.business_type for r in records] == ['deposit', 'withdraw']
        assert [r.amount for r in records] == [Decimal('5000.00'), Decimal('1500.00')]
        assert all(r.asset_type == 'cash' and r.symbol == CASH_SYMBOL for r in records)
        assert all(r.net_amount == r.amount for r in records)
        assert all(r.venue == '' for r in records)

    def test_dividend_and_interest(self, parser):
        dividend = _row(业务名称='股息入账', 证券名称='示例转债', 发生金额='41.60', 证券代码='127001')
        interest = _row(业务名称='利息归本', 发生金额='0.05', 流水号='000000000020')
        records, errors = parser.parse(_file([dividend, interest], width=18))
        assert errors == []
        assert records[0].business_type == 'dividend_cash'
        assert records[0].amount == Decimal('41.60')
        assert records[0].shares == Decimal('0')
        assert records[1].asset_type == 'cash'
        assert records[1].symbol == CASH_SYMBOL
        assert records[1].amount == Decimal('0.05')

    def test_ignored_ops_are_counted_not_silently_dropped(self, parser):
        rows = [_row(业务名称=op, 流水号=f'00000000{i:04d}') for i, op in enumerate(sorted(CMS_IGNORED_OPS), start=1)]
        rows.append(_buy_sz())
        records, errors = parser.parse(_file(rows, width=20))
        assert errors == []
        assert len(records) == 1
        assert parser.ignored_row_count == len(CMS_IGNORED_OPS)
        assert parser.source_row_count == len(CMS_IGNORED_OPS) + 1
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

    def test_unknown_operation_reports_line_and_original_text(self, parser):
        rows = [_buy_sz(), _row(业务名称='未来新业务', 流水号='000000000099')]
        records, errors = parser.parse(_file(rows, width=20))
        assert len(records) == 1
        assert len(errors) == 1
        assert errors[0].line_number == 3
        assert errors[0].field_name == '业务名称'
        assert errors[0].raw_value == '未来新业务'
        assert '未来新业务' in errors[0].message
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

    def test_bad_date_and_unsupported_currency_do_not_break_batch(self, parser):
        rows = [
            _row(业务名称='证券买入', 成交日期='不是日期', 证券代码='600000', 发生金额='-10.00'),
            _row(业务名称='证券买入', 币种='美元', 证券代码='600000', 发生金额='-10.00'),
            _buy_sz(),
        ]
        records, errors = parser.parse(_file(rows, width=20))
        assert len(records) == 1
        assert len(errors) == 2
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

    def test_trailing_blank_line_is_not_a_data_row(self, parser):
        content = _file([_buy_sz()], width=20).decode('gb18030') + '\n'
        records, errors = parser.parse(content.encode('gb18030'))
        # 尾部空行由 _read_rows 过滤，不计入数据行
        assert len(records) == 1 and errors == []
        assert parser.source_row_count == 1


class TestPrivacy:
    def test_account_identifier_columns_never_enter_record(self, parser):
        """股东代码、资金余额、备注等账户标识不得进入记录（含 raw_text / 名称）。"""
        row = _buy_sz(股东代码=_f('SIMULATED_SHAREHOLDER'), 资金余额='999999.99', 备注='模拟备注')
        rec = parser.parse(_file([row], width=21))[0][0]
        assert rec.raw_text is None or rec.raw_text == ''
        assert 'SIMULATED_SHAREHOLDER' not in repr(rec)
        assert '模拟备注' not in repr(rec)
        assert '999999.99' not in repr(rec)


class TestContract:
    def test_validate_filters_invalid_records(self, parser):
        good = parser.parse(_file([_buy_sz()], width=20))[0][0]
        zero = parser.parse(_file([_buy_sz()], width=20))[0][0]
        zero.amount = Decimal('0')
        no_symbol = parser.parse(_file([_buy_sz()], width=20))[0][0]
        no_symbol.symbol = ''
        valid, errors = parser.validate([good, zero, no_symbol])
        assert valid == [good]
        assert len(errors) == 2

    def test_transaction_id_distinct_and_stable(self, parser):
        row_a = _buy_sz(业务名称='证券买入', 流水号='000000000077')
        row_b = _buy_sz(业务名称='证券卖出', 成交数量='-80', 发生金额='9310.68', 流水号='000000000077')
        first = parser.parse(_file([row_a, row_b], width=20))[0]
        second = parser.parse(_file([row_a, row_b], width=20))[0]
        assert first[0].transaction_id != first[1].transaction_id
        assert [r.transaction_id for r in first] == [r.transaction_id for r in second]

    def test_registered_in_registry(self, parser):
        registered = get_parser(PositionSource.BROKER_CMS.value)
        assert isinstance(registered, CMSStockParser)
        assert registered.target == 'transaction'
        assert PositionSource.BROKER_CMS.value in get_all_sources()
        assert registered.compute_import_hash(parser.parse(_file([_buy_sz()], width=20))[0][0])

    def test_mapping_tables_are_disjoint(self):
        assert not (set(CMS_OP_MAP) & CMS_IGNORED_OPS)
        assert not (set(CMS_OP_MAP) & CMS_CASH_TRANSFER_OPS)
        assert not (CMS_IGNORED_OPS & CMS_CASH_TRANSFER_OPS)


# ── 旧版导出格式（2020 及以前，11 列）──

LEGACY_HEADER = [
    '证券代码',
    '证券名称',
    '买卖标志',
    '成交日期',
    '成交时间',
    '成交价格',
    '成交数量',
    '成交金额',
    '成交编号',
    '委托编号',
    '股东代码',
]


def _legacy_row(**overrides) -> list:
    """构造一行 11 列的旧版模拟数据（公式文本外壳与真实导出一致）。"""
    defaults = {
        '证券代码': '',
        '证券名称': '',
        '买卖标志': '买入',
        '成交日期': '20201201',
        '成交时间': '15:00:00',
        '成交价格': _f('0.0000'),
        '成交数量': '0',
        '成交金额': '0.00',
        '成交编号': _f('0'),
        '委托编号': _f('0'),
        '股东代码': _f('0000000000'),
    }
    defaults.update(overrides)
    return [defaults[name] for name in LEGACY_HEADER]


def _legacy_file(rows) -> bytes:
    lines = ['\t'.join(LEGACY_HEADER)] + ['\t'.join(cells) for cells in rows]
    return ('\n'.join(lines) + '\n').encode('gb18030')


@pytest.fixture
def legacy_parser():
    """旧版用例不需要申购码→上市码的在线解析，固定用 Null 解析器隔离网络与库。"""
    return CMSStockParser(alias_resolver=NullAliasResolver())


class TestLegacyExportSchema:
    """旧版导出的三处口径差异：列名、业务名（买入/卖出）、金额符号（恒为正）。"""

    def test_legacy_header_recognized_and_sell_mapped(self, legacy_parser):
        row = _legacy_row(
            证券代码='123001',
            证券名称='示例转债',
            买卖标志='卖出',
            成交价格='110.0000',
            成交数量='-10',
            成交金额='1100.00',
        )
        records, errors = legacy_parser.parse(_legacy_file([row]))
        assert errors == []
        assert len(records) == 1
        rec = records[0]
        assert rec.business_type == 'sell'
        assert rec.symbol == 'SZ123001'
        assert rec.amount == Decimal('1100.00')
        assert rec.shares == Decimal('10')
        assert rec.nav == Decimal('110.0000')

    def test_legacy_buy_mapped_to_buy(self, legacy_parser):
        row = _legacy_row(
            证券代码='600001',
            证券名称='示例股份',
            买卖标志='买入',
            成交价格='10.0000',
            成交数量='100',
            成交金额='1000.00',
        )
        records, errors = legacy_parser.parse(_legacy_file([row]))
        assert errors == []
        assert records[0].business_type == 'buy'
        assert records[0].symbol == 'SH600001'
        assert records[0].shares == Decimal('100')
        assert records[0].amount == Decimal('1000.00')

    def test_legacy_sh_bond_lot_converted_to_sheets(self, legacy_parser):
        """沪市 113 段：成交数量 1「手」= 10 张，金额 1450 = 145 × 10 张。"""
        row = _legacy_row(
            证券代码='113001',
            证券名称='示例转债',
            买卖标志='卖出',
            成交价格='145.0000',
            成交数量='-1',
            成交金额='1450.00',
        )
        records, errors = legacy_parser.parse(_legacy_file([row]))
        assert errors == []
        assert records[0].shares == Decimal('10')
        assert records[0].trade_amount == Decimal('1450.0000')

    def test_legacy_ipo_chain_principal_is_net_cash(self, legacy_parser):
        """旧版金额恒为正：中签链必须补号，否则「扣款/缴款」会把 1000 元本金算成 3000 元。"""
        rows = [
            _legacy_row(
                证券代码='072001',
                证券名称='示例发债',
                买卖标志='市值申购中签',
                成交日期='20201209',
                成交价格='100.0000',
                成交数量='10',
                成交金额='0.00',
            ),
            _legacy_row(
                证券代码='072001',
                证券名称='示例发债',
                买卖标志='市值申购中签扣款',
                成交日期='20201210',
                成交金额='1000.00',
            ),
            _legacy_row(
                证券代码='072001',
                证券名称='示例发债',
                买卖标志='新股申购确认缴款',
                成交日期='20201211',
                成交价格='100.0000',
                成交数量='10',
                成交金额='1000.00',
            ),
            _legacy_row(
                证券代码='072001',
                证券名称='示例发债',
                买卖标志='市值申购中签扣款回冲',
                成交日期='20201211',
                成交价格='100.0000',
                成交金额='1000.00',
            ),
            _legacy_row(
                证券代码='072001',
                证券名称='示例发债',
                买卖标志='托管转出',
                成交日期='20201211',
                成交价格='100.0000',
                成交数量='-10',
                成交金额='0.00',
            ),
        ]
        records, errors = legacy_parser.parse(_legacy_file(rows))
        assert errors == []
        assert len(records) == 1
        rec = records[0]
        assert rec.business_type == 'buy'
        assert rec.amount == Decimal('1000.00')  # 不是 3000：冲正对已抵消
        assert rec.shares == Decimal('10.0000')
        assert rec.shares * rec.nav == rec.amount
        assert legacy_parser.ignored_row_count == 4  # 5 行折叠成 1 条，4 行被消耗

    def test_legacy_repo_row_ignored_by_gross_ratio(self, legacy_parser):
        """报价回购在旧版里被记成「买入」：价格是年化收益率，金额 ÷ (价格×数量) 不成 1:1。"""
        row = _legacy_row(
            证券代码='132007',
            证券名称='示例宝',
            买卖标志='买入',
            成交价格='1.3800',
            成交数量='10',
            成交金额='1000.00',
        )
        records, errors = legacy_parser.parse(_legacy_file([row]))
        assert records == [] and errors == []
        assert legacy_parser.ignored_row_count == 1
        assert legacy_parser.source_row_count == 1

    def test_legacy_designated_account_row_ignored(self, legacy_parser):
        """「指定或撤指定」是交易单元操作：无资金、无持仓，计入忽略而不是报错。"""
        row = _legacy_row(
            证券代码='799999',
            证券名称='示例指定',
            买卖标志='指定或撤指定',
            成交价格='1.0000',
            成交金额='0.00',
        )
        records, errors = legacy_parser.parse(_legacy_file([row]))
        assert records == [] and errors == []
        assert legacy_parser.ignored_row_count == 1

    def test_legacy_row_count_identity(self, legacy_parser):
        """#2854 对账恒等式在旧版格式上同样成立。"""
        rows = [
            _legacy_row(
                证券代码='123001',
                证券名称='示例转债',
                买卖标志='卖出',
                成交价格='110.0000',
                成交数量='-10',
                成交金额='1100.00',
                成交编号=_f('000000000001'),
            ),
            _legacy_row(
                证券代码='132007',
                证券名称='示例宝',
                买卖标志='买入',
                成交价格='1.3800',
                成交数量='10',
                成交金额='1000.00',
                成交编号=_f('000000000002'),
            ),
            _legacy_row(
                证券代码='070001',
                证券名称='示例配号',
                买卖标志='申购配号',
                成交数量='1000',
                成交编号=_f('000000000003'),
            ),
        ]
        records, errors = legacy_parser.parse(_legacy_file(rows))
        assert errors == []
        assert len(records) == 1
        assert legacy_parser.source_row_count == len(records) + len(errors) + legacy_parser.ignored_row_count

    def test_legacy_missing_required_column_reports_column_name(self, legacy_parser):
        """缺「成交数量」时应点名缺列，而不是笼统报「未找到表头」。"""
        header = [c for c in LEGACY_HEADER if c != '成交数量']
        content = ('\t'.join(header) + '\n').encode('gb18030')
        records, errors = legacy_parser.parse(content)
        assert records == []
        assert errors and '成交数量' in errors[0].message
