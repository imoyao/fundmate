# -*- coding: utf-8 -*-
"""结构化叙事分块解析单测（#1712）。

覆盖验收标准 1 的三档降级（合规块 / 乱格式 / 完全非结构）+ 表格契约
（列序 / 截断 / kind 标注 / 嵌套防御）+ Emoji 剔除。不触网、不碰 DB。
"""

from app.services.ai_recognizer.narrative_blocks import (
    MAX_TABLE_COLS,
    MAX_TABLE_ROWS,
    parse_narrative_blocks,
)

COMPLIANT = (
    '【结论】组合整体盈利，年化收益约 10%。\n'
    '【明细】其中基金贡献主要收益，股票拖累明显。\n'
    '【风险提示】市场波动可能使收益回撤。'
)


# ── 合规块 ──
def test_compliant_text_parses_to_blocks():
    blocks = parse_narrative_blocks(COMPLIANT, tool_data=None)
    assert blocks is not None
    assert [b['type'] for b in blocks] == ['summary', 'text', 'risk']
    assert blocks[0]['text'] == '组合整体盈利，年化收益约 10%。'
    assert blocks[1]['text'] == '其中基金贡献主要收益，股票拖累明显。'
    assert blocks[2]['text'] == '市场波动可能使收益回撤。'


def test_compliant_with_row_data_builds_table_after_detail():
    data = {
        'items': [
            {
                'symbol': '110011',
                'name': '赚的基金',
                'pnl': 10.0,
                'pnl_rate': 10.0,
                'market_value': 110.0,
                'nested': {'a': 1},
            },
            {'symbol': '600000', 'name': '亏的股票', 'pnl': -10.0, 'pnl_rate': -10.0},
        ],
        'count': 2,
    }
    blocks = parse_narrative_blocks(COMPLIANT, tool_data=data)
    assert blocks is not None
    types = [b['type'] for b in blocks]
    # 表格紧跟明细节文本之后、风险提示之前
    assert types == ['summary', 'text', 'table', 'risk']
    table = blocks[2]
    keys = [c['key'] for c in table['columns']]
    # 列序走契约优先级，嵌套字段（nested）被剥掉；count 是外层键不进行
    assert 'symbol' in keys and 'name' in keys and 'pnl' in keys and 'pnl_rate' in keys
    assert 'nested' not in keys and 'count' not in keys
    kind_by_key = {c['key']: c['kind'] for c in table['columns']}
    assert kind_by_key['pnl'] == 'pnl' and kind_by_key['pnl_rate'] == 'pnl'
    assert kind_by_key['market_value'] == 'plain'
    assert table['truncated'] is False
    assert table['rows'][1]['pnl'] == -10.0


def test_table_column_cap_drops_low_priority():
    """列数上限：契约尾部低优先列（cost/type/account_name）先被截掉。"""
    row = {
        'symbol': '110011',
        'name': '基金',
        'quantity': 100.0,
        'avg_price': 1.0,
        'current_price': 1.1,
        'market_value': 110.0,
        'pnl': 10.0,
        'pnl_rate': 10.0,
        'cost': 100.0,
        'type': 'fund',
        'account_name': '测试账户',
    }
    blocks = parse_narrative_blocks('【结论】ok\n【明细】如下\n【风险提示】暂无', tool_data={'items': [row]})
    table = next(b for b in blocks if b['type'] == 'table')
    assert len(table['columns']) == MAX_TABLE_COLS
    keys = [c['key'] for c in table['columns']]
    assert 'cost' not in keys and 'type' not in keys and 'account_name' not in keys


def test_table_row_cap_marks_truncated():
    rows = [{'symbol': str(i), 'name': f'基金{i}', 'pnl': float(i)} for i in range(MAX_TABLE_ROWS + 5)]
    blocks = parse_narrative_blocks('【结论】ok\n【明细】如下\n【风险提示】暂无', tool_data={'items': rows})
    table = next(b for b in blocks if b['type'] == 'table')
    assert table['truncated'] is True
    assert len(table['rows']) == MAX_TABLE_ROWS


# ── 乱格式（局部契约漂移） ──
def test_missing_risk_section_still_parses():
    blocks = parse_narrative_blocks('【结论】盈利。\n【明细】如下。', tool_data=None)
    assert blocks is not None
    assert [b['type'] for b in blocks] == ['summary', 'text']


def test_out_of_marker_text_preserved_as_text_block():
    blocks = parse_narrative_blocks('开头一句。\n【结论】盈利。', tool_data=None)
    assert blocks is not None
    assert [b['type'] for b in blocks] == ['text', 'summary']
    assert blocks[0]['text'] == '开头一句。'


def test_repeated_marker_does_not_crash():
    blocks = parse_narrative_blocks('【结论】A\n【结论】B\n【明细】C', tool_data=None)
    assert blocks is not None
    summaries = [b for b in blocks if b['type'] == 'summary']
    assert len(summaries) == 2


def test_table_dropped_for_mixed_rows():
    """行内混入非 dict → 整体放弃成表，文本块不受影响（宁缺毋滥）。"""
    data = {'items': [{'symbol': 'a', 'pnl': 1}, '不是行']}
    blocks = parse_narrative_blocks('【结论】ok\n【明细】如下\n【风险提示】暂无', tool_data=data)
    assert blocks is not None
    assert all(b['type'] != 'table' for b in blocks)


def test_table_strips_nested_column_but_keeps_table():
    """行内嵌套值：剥掉该列、表格保留（缺一列好过丢一张表）。"""
    data = {'items': [{'symbol': 'a', 'meta': {'x': 1}, 'pnl': 1}]}
    blocks = parse_narrative_blocks('【结论】ok\n【明细】如下\n【风险提示】暂无', tool_data=data)
    table = next(b for b in blocks if b['type'] == 'table')
    keys = [c['key'] for c in table['columns']]
    assert 'symbol' in keys and 'pnl' in keys and 'meta' not in keys
    assert all('meta' not in row for row in table['rows'])


# ── 完全非结构（降级 None） ──
def test_plain_text_returns_none():
    assert parse_narrative_blocks('就是一段普通总结，没有小节标记。', tool_data=None) is None


def test_empty_or_non_string_returns_none():
    assert parse_narrative_blocks('', tool_data=None) is None
    assert parse_narrative_blocks(None, tool_data=None) is None
    assert parse_narrative_blocks('   \n  ', tool_data=None) is None


# ── Emoji 剔除（后端防线，前端 stripEmoji 兜底） ──
def test_emoji_stripped_from_block_text_and_table_cells():
    text = '【结论】收益不错 😀📈\n【明细】如下 👍\n【风险提示】暂无'
    data = {'items': [{'symbol': '110011', 'name': '基金🚀', 'pnl': 1.0}]}
    blocks = parse_narrative_blocks(text, tool_data=data)
    assert all('😀' not in b.get('text', '') for b in blocks if b['type'] != 'table')
    table = next(b for b in blocks if b['type'] == 'table')
    assert all('🚀' not in str(v) for row in table['rows'] for v in row.values())
