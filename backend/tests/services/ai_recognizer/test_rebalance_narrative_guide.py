# -*- coding: utf-8 -*-
"""调仓解读输出范式 + 合规兜底（#3259 · L4 验收标准 3）。

覆盖：
1. **输出范式 prompt**：`_REBALANCE_NARRATIVE_GUIDE` 含「只对照呈现、禁指令措辞、
   由你判断」的措辞约束；
2. **output_filter 兜底**：调仓解读场景下模型若仍产出「建议替换 / 应该买入」等指令
   措辞，`filter_output` 命中 R2/R3 并替换（三道防线最后一道）。
"""

from app.services.ai_recognizer.safety.output_filter import filter_output
from app.services.rebalance_interpretation import REBALANCE_NARRATIVE_GUIDE


def test_rebalance_narrative_guide_exists_and_constrains_wording():
    """输出范式 prompt 存在，且明确禁止指令措辞、落到「由你判断」。"""
    guide = REBALANCE_NARRATIVE_GUIDE
    assert '建议' in guide
    assert '替换' in guide
    assert '由你判断' in guide
    assert '禁止' in guide


def test_narrative_guide_injected_only_for_rebalance_tool():
    """措辞铁律只在 get_advisor_rebalance 场景注入，不污染其它工具。"""
    guide = REBALANCE_NARRATIVE_GUIDE
    assert '调仓解读措辞铁律' in guide


def test_source_line_injects_guide_only_for_rebalance_tool():
    """source_line（叙事 prompt 数据来源行）只在 rebalance 工具注入措辞铁律。"""
    from app.services.ai_recognizer.plan_executor import source_line

    rebalance = source_line({'data': {}}, 'get_advisor_rebalance', '{"x": 1}')
    assert '调仓解读措辞铁律' in rebalance

    other = source_line({'data': {}}, 'get_fund_nav', '{"x": 1}')
    assert '调仓解读措辞铁律' not in other


def test_output_filter_blocks_rebalance_advice():
    """兜底：即便模型产出「建议卖出」，output_filter 命中 advice 类规则替换为免责声明。"""
    text = '结论：该组合减仓了权益。明细：建议卖出你手里的 A，换入它重仓的 B。'
    verdict = filter_output(text, used_tools=True)
    assert verdict.blocked is True
    # 指令短语「建议卖出」被整句替换成免责声明（免责声明本身含「建议」是允许的）
    assert '建议卖出' not in verdict.sanitized
    assert '由你自行决定' in verdict.sanitized


def test_output_filter_blocks_replace_directive():
    """「建议换」形态的指令措辞命中 R2（advice 类），被替换。"""
    text = '建议换成它重仓的基金。'
    verdict = filter_output(text, used_tools=True)
    assert verdict.blocked is True


def test_output_filter_blocks_should_buy_sell():
    """「应该买入 / 应该卖出」命中 R3，被替换。"""
    text = '你应该买入这只组合重仓的基金。'
    verdict = filter_output(text, used_tools=True)
    assert verdict.blocked is True


def test_objective_rebalance_statement_passes():
    """客观陈述（不含指令措辞）不被误伤：只陈述事实与分歧。"""
    text = (
        '【结论】远足于 2026-11-24 调仓，净增权益。'
        '【明细】加仓股票型基金 000001，占比 10% 提到 20%；调仓理由与实际动作方向一致。'
        '【风险提示】是否参考由你判断。'
    )
    verdict = filter_output(text, used_tools=True)
    # 纯客观陈述，无建议/推荐/预测措辞 → 不应命中（blocked=False）
    assert verdict.blocked is False
