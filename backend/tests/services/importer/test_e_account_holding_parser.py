# -*- coding: utf-8 -*-
"""E账户持仓解析器测试（#1012）。

覆盖：
- 表头定位容错：带个人信息（真实上传场景）与无个人信息（用户已处理）两种样本均正确解析；
- 列映射：symbol/name/shares/snapshot_date/nav/market_value/currency 及溯源字段；
- 非法文件与坏行容错。
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services.importer.parsers.e_account_holding import EAccountHoldingParser

FIXTURES = Path(__file__).resolve().parent.parent.parent / 'fixtures'

SAMPLE_WITH_PERSONAL = FIXTURES / 'e_account_holding_sample.xlsx'
SAMPLE_CLEAN = FIXTURES / 'e_account_holding_sample_clean.xlsx'


@pytest.fixture
def parser():
    return EAccountHoldingParser()


def _parse(parser, path):
    data = path.read_bytes() if isinstance(path, Path) else path
    records, errors = parser.parse(data)
    return records, errors


def test_parse_sample_with_personal_info(parser):
    """带标题+个人信息样本：跳过头部，正确定位表头并解析 3 条持仓。"""
    records, errors = _parse(parser, SAMPLE_WITH_PERSONAL)
    assert errors == []
    assert len(records) == 3

    first = records[0]
    assert first.symbol == '012345'
    assert first.name == '示例红利优选混合A'
    assert first.shares == Decimal('10000.00')
    assert first.snapshot_date == date(2026, 8, 12)
    assert first.nav == Decimal('1.2345')
    assert first.market_value == Decimal('12345.00')
    assert first.currency == 'CNY'
    assert first.asset_type == 'fund'
    assert first.source == 'e_account_holding'

    # 溯源字段完整保留（用户诉求：不丢数据）
    assert first.source_broker == '示例基金销售'
    assert first.fund_manager == '示例基金管理'
    assert first.share_class == '前收费'
    assert first.fund_account == 'FUNDACC0001'
    assert first.trade_account == 'TRADEACC0001'
    assert first.dividend_preference == '现金分红'


def test_parse_sample_clean_header(parser):
    """无个人信息样本（用户已处理）：直接从表头开始，同样解析 3 条。"""
    records, errors = _parse(parser, SAMPLE_CLEAN)
    assert errors == []
    assert len(records) == 3
    assert records[0].symbol == '012345'
    assert records[2].dividend_preference == '红利转投'


def test_parse_currency_mapping(parser):
    """币种中文 → ISO 映射。"""
    records, _ = _parse(parser, SAMPLE_CLEAN)
    assert all(r.currency == 'CNY' for r in records)


def test_parse_invalid_file(parser):
    """非 E账户 xlsx（无表头关键列）→ 报错且无记录。"""
    import io

    import pandas as pd

    df = pd.DataFrame([['随便一个表', '没有基金代码'], ['1', '2']])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False, engine='openpyxl')

    records, errors = _parse(parser, buf.getvalue())
    assert records == []
    assert len(errors) == 1
    assert '基金代码' in errors[0].message


def test_parse_bad_rows_collected(parser):
    """坏行（基金代码非法/份额无效）收集到 errors，不中断解析。"""
    # 构造：表头 + 1 条合法 + 1 条坏行（代码非 6 位）+ 1 条坏行（份额无效）
    import io

    import pandas as pd

    header = [
        '序号',
        '基金代码',
        '基金名称',
        '持有份额',
        '份额日期',
        '基金净值',
        '资产情况\n（结算币种）',
        '结算币种',
        '分红方式',
    ]
    df = pd.DataFrame(
        [
            header,
            ['1', '012345', '示例基金A', '100.00', '2026/08/12', '1.0000', '100.00', '人民币', '现金分红'],
            ['2', 'ABC', '坏代码', '100.00', '2026/08/12', '1.0000', '100.00', '人民币', '现金分红'],
            ['3', '023456', '坏份额', 'abc', '2026/08/12', '1.0000', '100.00', '人民币', '现金分红'],
        ]
    )
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False, engine='openpyxl')
    records, errors = _parse(parser, buf.getvalue())

    assert len(records) == 1
    assert records[0].symbol == '012345'
    assert len(errors) == 2
    assert any('基金代码' in e.message for e in errors)
    assert any('持有份额' in e.message for e in errors)


def test_validate_rejects_invalid_records(parser):
    """validate：快照日期晚于今天 / 份额非正 → 过滤并报错。"""
    from datetime import timedelta

    from app.services.importer.records import StandardHoldingRecord

    good = StandardHoldingRecord(
        symbol='012345', name='示例基金', shares=Decimal('100'), snapshot_date=date(2026, 8, 12)
    )
    bad_future = StandardHoldingRecord(
        symbol='023456', name='未来基金', shares=Decimal('100'), snapshot_date=date.today() + timedelta(days=1)
    )
    bad_shares = StandardHoldingRecord(
        symbol='034567', name='零份额', shares=Decimal('0'), snapshot_date=date(2026, 8, 12)
    )

    valid, errors = parser.validate([good, bad_future, bad_shares])
    assert len(valid) == 1
    assert valid[0].symbol == '012345'
    assert len(errors) == 2
