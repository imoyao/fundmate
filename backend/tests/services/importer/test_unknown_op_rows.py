# tests/services/importer/test_unknown_op_rows.py
"""#2854：导入映射表漏一个操作名 = 整行静默消失。

三条判据（对应 issue 的「丢弃必须可见 / 行数对账 / 声明式忽略」）：

1. `THS_OP_MAP` 查不到的操作名 → `SBImportError`，带行号与券商原文操作名，
   不再 `logger.debug` 之后 `return None`；
2. `THS_IGNORED_OPS` 里的操作名 → 不报错，但计入 `ignored_row_count`；
3. 行数对账恒等式：
   `source_row_count == len(records) + len(errors) + ignored_row_count`。

修复前这三条全不成立：未知行走 `return None`，连 `errors` 都不进；
预览响应的 `total` 是丢弃后的计数，源文件行数从未参与上报。
"""

import pandas as pd

from app.services.importer.mappings import THS_IGNORED_OPS, THS_OP_MAP
from app.services.importer.parsers.ths_stock import THSStockParser

COLUMNS = [
    '证券代码',
    '证券名称',
    '操作',
    '成交数量',
    '成交均价',
    '成交金额',
    '发生金额',
    '佣金',
    '印花税',
    '过户费',
    '其他杂费',
    '币种',
    '交收日期',
    '合同编号',
]


def _row(op: str, line: int = 2) -> dict:
    return {
        '证券代码': '600519',
        '证券名称': '贵州茅台',
        '操作': op,
        '成交数量': '100',
        '成交均价': '1650.00',
        '成交金额': '165000.00',
        '发生金额': '-165015.00',
        '佣金': '5.00',
        '印花税': '8.50',
        '过户费': '1.00',
        '其他杂费': '0.50',
        '币种': 'CNY',
        '交收日期': '20220101',
        '合同编号': str(line),
        'fee': '15.00',
    }


def _file_bytes(*ops: str) -> bytes:
    """构造制表符分隔的同花顺交割单（含表头）。"""
    lines = ['\t'.join(COLUMNS)]
    for i, op in enumerate(ops):
        r = _row(op, i + 2)
        lines.append('\t'.join(str(r[c]) for c in COLUMNS))
    return ('\n'.join(lines) + '\n').encode('utf-8-sig')


class TestUnknownOperationRows:
    def test_unknown_op_becomes_visible_error_with_line_and_raw_name(self):
        """未知操作名必须产出一条带行号 + 原文操作名的错误，而不是静默消失。"""
        parser = THSStockParser()
        df = pd.DataFrame([_row('快速取现', 2), _row('证券买入', 3)])
        records, errors, ignored = parser._iterrows_to_records(df)

        assert len(records) == 1
        assert ignored == 0
        assert len(errors) == 1
        err = errors[0]
        assert err.line_number == 2
        assert err.raw_value == '快速取现'
        assert '快速取现' in err.message
        assert err.field_name == '操作'

    def test_ignored_ops_are_declared_and_counted_not_reported(self):
        """「有意忽略」与「解析失败」是两类语义：前者不报错，但要进对账计数。"""
        parser = THSStockParser()
        assert THS_IGNORED_OPS, '忽略集合为空时，本判据等于没写'
        for op in THS_IGNORED_OPS:
            df = pd.DataFrame([_row(op, 2), _row('证券买入', 3)])
            records, errors, ignored = parser._iterrows_to_records(df)
            assert len(records) == 1
            assert errors == []
            assert ignored == 1

    def test_row_reconciliation_identity_holds(self):
        """源文件行数 = 可导入 + 解析失败 + 有意忽略，三类互斥且完备。"""
        parser = THSStockParser()
        records, errors = parser.parse(_file_bytes('证券买入', '快速取现', '指定交易', '证券卖出'))

        assert parser.source_row_count == 4
        assert parser.ignored_row_count == 1
        assert len(records) == 2
        assert len(errors) == 1
        assert parser.source_row_count == len(records) + len(errors) + parser.ignored_row_count

    def test_all_registered_ops_still_produce_records(self):
        """反向验证：改动不能波及正常路径——每个已登记的操作名都仍能解析成一行。"""
        parser = THSStockParser()
        ops = list(THS_OP_MAP.keys())
        records, errors = parser.parse(_file_bytes(*ops))
        assert errors == [], f'已登记操作名出现解析错误: {[e.message for e in errors]}'
        assert len(records) == len(ops)
        assert parser.source_row_count == len(ops)
        assert parser.ignored_row_count == 0
