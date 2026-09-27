# -*- coding: utf-8 -*-
"""L3 输出侧词法过滤器（output_filter）单测。

三类必测：① 漏放（越界文本必须被拦）；② 误伤（历史/实际数据必须放行——
「历史年化 12.3%」是 XIRR 真实算出来的事实，被拦等于产品自我阉割）；
③ 替换粒度（命中句替换、其余保留，不整篇拒答，§7.3）。
"""

from app.services.ai_recognizer.safety.output_filter import (
    DISCLAIMER_TEMPLATE,
    filter_output,
)

# ── ① 漏放：越界输出必须命中 ──
BLOCKED_CASES = [
    ('照这个节奏，下周会涨。', 'R1'),
    ('这只基金明年大概率上涨。', 'R1'),
    ('建议你现在卖出。', 'R2'),
    ('你应该减仓。', 'R3'),  # 纯 R3 句式：R2 已覆盖「建议你…」形态，避免断言过细
    ('强烈推荐这只基金。', 'R4'),
    ('稳赚不赔，放心买。', 'R5a'),
    ('保证年化 10%。', 'R5a'),
    ('跌 5% 就卖。', 'R6'),
    ('这个基金经理很差劲。', 'R7'),
    ('给予买入评级。', 'R8'),
    ('什么时候买最合适？', 'R2'),  # R2 已含「什么时候(买|卖)」，先命中
    ('该何时入手这只基金？', 'R9'),  # 纯 R9 形态（R2 不覆盖「该何时…」）
    ('跟着抄作业必赚。', 'R10'),  # 「闭眼买肯定赚」会先命中 R5a（同一句话，同一免责声明）
]


def test_blocked_outputs_are_sanitized():
    for text, rule in BLOCKED_CASES:
        verdict = filter_output(text)
        assert verdict.blocked, f'漏放：{text!r}'
        assert rule in verdict.hit_rules, f'{text!r} 应命中 {rule}，实际 {verdict.hit_rules}'
        assert verdict.sanitized != text, '命中后必须替换原文'
        assert text.rstrip('。？！') not in verdict.sanitized, '原越界句不能留在输出里'


def test_disclaimer_present_after_replacement():
    verdict = filter_output('建议你现在卖出。')
    assert DISCLAIMER_TEMPLATE['advice'] in verdict.sanitized


# ── ② 误伤：历史 / 实际数据必须放行（白名单豁免是 §7.1 的核心）──
ALLOWED_CASES = [
    '组合过去一年年化 12.3%，跑赢基准 3 个百分点。',
    '该基金历史年化 8.5%，近一年涨幅 15%。',
    '截至上月底，实际年化为 5.2%。',
    '你的净资产是 0 元，暂无持仓。',
    '近30天回撤 2.1%，同期沪深300 下跌 4.0%。',
    '回测显示年化 6.1%。',
]


def test_historical_facts_pass_through():
    for text in ALLOWED_CASES:
        verdict = filter_output(text)
        assert not verdict.blocked, f'误伤历史事实：{text!r} → {verdict.hit_rules}'
        assert verdict.sanitized == text


def test_naked_annualized_rate_without_fact_marker_hits():
    """豁免只认事实标记词：没有「历史/过去/实际」等标记的裸年化仍是承诺式表述。"""
    verdict = filter_output('预期年化 8%。')
    assert verdict.blocked and 'R5b' in verdict.hit_rules


def test_full_width_digits_hit():
    """全角是漏检重灾区：`年化８．５％` 必须和 `年化 8.5%` 同等对待。"""
    verdict = filter_output('预期年化８．５％。')
    assert verdict.blocked and 'R5b' in verdict.hit_rules


# ── ③ 替换粒度：命中句替换，合规句保留（不整篇拒答）──
def test_replace_only_offending_sentence():
    text = '你的净资产是 0 元。建议你现在卖出。组合过去一年年化 12.3%。'
    verdict = filter_output(text)
    assert verdict.blocked
    assert '你的净资产是 0 元。' in verdict.sanitized  # 合规句 1 保留
    assert '组合过去一年年化 12.3%。' in verdict.sanitized  # 合规句 2（事实）保留
    assert '建议你现在卖出' not in verdict.sanitized  # 越界句被替换


# ── E1：未调工具却谈市场判断 → 整段替换（§6-E）──
def test_e1_blocks_market_judgment_without_tools():
    verdict = filter_output('当前市场趋势判断是震荡，机会在下半年。', used_tools=False)
    assert verdict.blocked and verdict.hit_rules == ('E1',)
    assert verdict.sanitized == DISCLAIMER_TEMPLATE['market_judgment']


def test_e1_not_applied_when_tools_used():
    """调过工具（有事实基础）时不启用 E1，否则每次正常分析都会被整段吞掉。"""
    verdict = filter_output('当前市场趋势判断是震荡。', used_tools=True)
    assert not verdict.blocked


def test_e1_not_trigger_on_plain_clarification():
    """正常追问不含市场判断词，不得触发 E1（误伤面回归）。"""
    verdict = filter_output('你想看多久的走势？', used_tools=False)
    assert not verdict.blocked


# ── 健壮性 ──
def test_empty_and_non_string_safe():
    assert filter_output('').blocked is False
    assert filter_output(None).blocked is False
    assert filter_output(None).sanitized == ''


def test_clean_text_unchanged():
    text = '你的组合近30天回撤 2.1%，同期沪深300 下跌 4.0%。'
    verdict = filter_output(text)
    assert not verdict.blocked
    assert verdict.sanitized == text
    assert not bool(verdict)  # 真值 = 有干预，可 `if verdict:` 短路


def test_multiline_preserved():
    """换行是叙事段落的排版，替换后不能把结构吞掉。"""
    text = '第一段是事实。\n建议你现在卖出。\n第三段也是事实。'
    verdict = filter_output(text)
    assert verdict.blocked
    assert '\n' in verdict.sanitized
    assert '第一段是事实。' in verdict.sanitized
