# tests/services/importer/test_parse_preview_reconciliation.py
"""#2854：`parse_and_preview` 必须把解析错误与源文件行数下发到预览响应。

issue 的第 2 条证据：`orchestrator_parse.parse_and_preview` 的 `errors` 是
**只写变量**——只要文件里还有别的能解析的行，`errors` 就被直接丢掉，永远到不了
响应体。所以「改成 append SBImportError」这个最直觉的修法不会产生任何可见效果。
第 3 条证据：响应里的 `total` 是丢弃后的计数，源文件数据行数从未参与上报。

本测试钉住响应层的四个字段与行数恒等式。
"""

from app.services.importer.orchestrator import ImportOrchestrator

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


def _file_bytes(*ops: str) -> bytes:
    lines = ['\t'.join(COLUMNS)]
    for i, op in enumerate(ops):
        row = {
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
            '合同编号': str(i + 2),
        }
        lines.append('\t'.join(str(row[c]) for c in COLUMNS))
    return ('\n'.join(lines) + '\n').encode('utf-8-sig')


def test_parse_and_preview_surfaces_errors_and_row_counts(db):
    """混合文件（正常行 + 未知操作名 + 有意忽略）→ 预览响应四项齐全且能对账。"""
    orch = ImportOrchestrator(db, family_id=1)
    result = orch.parse_and_preview(
        _file_bytes('证券买入', '快速取现', '指定交易'),
        'ths_stock',
        '测试账户',
        1,
    )

    assert result['total'] == 1
    assert result['parse_error_count'] == 1
    assert result['parse_errors'][0]['raw_value'] == '快速取现'
    assert result['parse_errors'][0]['line'] == 3
    assert '快速取现' in result['parse_errors'][0]['message']
    assert result['source_row_count'] == 3
    assert result['ignored_row_count'] == 1
    # 恒等式：文件 3 行 = 可导入 1 + 无法识别 1 + 有意忽略 1
    assert result['source_row_count'] == (result['total'] + result['parse_error_count'] + result['ignored_row_count'])


def test_parse_and_preview_keeps_zero_loss_files_quiet(db):
    """全部已登记操作名 → 零错误、零忽略，行数恒等式仍成立（不回归正常路径）。"""
    orch = ImportOrchestrator(db, family_id=1)
    result = orch.parse_and_preview(
        _file_bytes('证券买入', '证券卖出', '利息归本', '基金红利拨入'),
        'ths_stock',
        '测试账户',
        1,
    )

    assert result['total'] == 4
    assert result['parse_error_count'] == 0
    assert result['parse_errors'] == []
    assert result['source_row_count'] == 4
    assert result['ignored_row_count'] == 0
