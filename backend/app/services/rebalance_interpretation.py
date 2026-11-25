# -*- coding: utf-8 -*-
"""调仓解读（#3259 ·「调仓解读付费功能」L4 深度解读 + 分歧识别）。

## 定位

L1 提醒「调仓了」之后，用户在 Agent 里主动追问「这次调仓是什么意思」。本模块是
L4 的**数据编排层**：输入 = 某投顾组合 code，输出 = 最近一次调仓的结构化解读
（方向 / 成分变化 / 「说的 vs 做的」分歧标记）。文案生成仍由 AgentLoop 叙事轮负责，
本模块只产出**客观、可断言的数据**，不下结论、不写建议（合规红线 design §2）。

与 L3（``advisor_comparison``）的分工：L3 回答「我的持仓 vs 它的持仓」的**基金级重合**
（三集合 + 指标对照）；本模块回答「它这次调仓**做了什么、方向是什么、说和做一不一致**」。
两者是调仓解读的两个正交维度，组合页 / 抽屉可并列展示。

## 核心口径（2026-11-25 拍板，勿自行改）

1. **粒度 = 最近一次调仓**：取 ``advisor_adjust_histories`` 最新的 ``adjust_date``，
   不铺开多期回溯。
2. **方向解读 = 成分基金类型 + 操作方向**：加仓/建仓「股票型」「混合型（偏股）」视为
   加权益，加「债券型」视为加债；「混合型」库里无偏股/偏债二级分类，归入权益类兜底
   （与 L3 同口径）。
3. **「说的 vs 做的」分歧 = 代码规则 + 不确定兜底**：
   - 「说的」= ``reason`` 文本（B 级），用关键词库判方向；
   - 「做的」= 本次成分 ``pre_ratio → after_ratio`` 的净方向（A 级）；
   - 两者方向可判且相反 → ``divergence=True``；可判且一致 → ``False``；
   - reason 无信息量（模板话术，如「资产配置结构优化。」）或无法判定 → ``unknown``
     （**不强行判定**，见 design §9.1.1 的实证：天天基金理由极简、文本价值低）。

## 合规

本模块只产出事实数据（日期 / 占比 / 操作名 / 方向标签 / 分歧标记）。措辞约束
（避开「建议/推荐/应该买入/卖出/替换」）由输出范式 prompt + ``output_filter`` 兜底，
不在这里拼建议文本。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.fund_utils import _lookup_market_type_names, normalize_fund_code

# ── 方向关键词（reason 文本 → 方向） ──────────────────────────────────────
# 增权益/进攻方向：reason 里出现这些词，倾向「说的 = 加权益/进攻」。
_BULLISH_HINTS = (
    '加仓',
    '增配',
    '增持',
    '加',
    '进攻',
    '成长',
    '权益',
    '股票',
    '股',
    '看好',
    '增权益',
    '提高',
    '上调',
    '提升',
)
# 减权益/防守方向：reason 里出现这些词，倾向「说的 = 减权益/防守」。
_BEARISH_HINTS = (
    '减仓',
    '减持',
    '降',
    '防守',
    '稳健',
    '债券',
    '债',
    '防御',
    '避险',
    '降低',
    '下调',
    '调降',
    '风险',
)

# 加权益方向的操作码（建仓/加仓/新增）。
_EQUITY_ADD_OPS = {1, 2, 4}
# 减权益方向的操作码（减仓）。
_EQUITY_REDUCE_OPS = {3}

# 债基类型名（与 advisor_comparison 同口径，混合型归入权益兜底）。
_BOND_TYPE_NAMES = {'债券型', '货币型'}

# ── 调仓解读输出范式（#3259 · L4，供 agent_loop 叙事轮注入）────────────────
# 「调仓解读」场景的专门措辞约束（design §2 合规边界）：让模型生成时**主动避开**
# 指令性措辞，只做「对照 + 呈现 + 由你判断」。最终仍由 ``output_filter``（R1~R10 + E1）
# 兜底——三道防线各司其职，本段是「让模型别往枪口上撞」，不是替代最后一道防线。
REBALANCE_NARRATIVE_GUIDE = (
    '调仓解读措辞铁律（本工具专用）：\n'
    '- 只做客观对照与呈现：陈述「某组合某日调仓、加了什么、方向是加权益还是加债」这类事实，'
    '以及「调仓理由与实际动作方向一致 / 不一致」这类可查证结论。\n'
    '- 禁止出现「建议 / 推荐 / 应该买入 / 应该卖出 / 替换 / 换仓 / 跟着调 / 抄作业」'
    '等指令性措辞，也禁止给出任何「你该不该跟着动」的操作方向。\n'
    '- 结尾一律落到「是否参考由你判断」，把决策权交还用户。\n'
    '- divergence 为 unknown 时如实说明「调仓理由信息量不足，无法判断说与做是否一致」，'
    '不得强行下「他说的未必是他做的」的结论。\n'
)


def _reason_direction(reason: str) -> Optional[str]:
    """从调仓理由文本判「说的」方向。

    Returns:
        ``'add'``（说加权益/进攻）/ ``'reduce'``（说减权益/防守）/ ``None``（无法判定，
        含模板话术与无信息量文本）。
    """
    text = (reason or '').strip()
    if not text:
        return None
    bull = sum(text.count(w) for w in _BULLISH_HINTS)
    bear = sum(text.count(w) for w in _BEARISH_HINTS)
    if bull > bear:
        return 'add'
    if bear > bull:
        return 'reduce'
    return None


def _action_direction(components: List[Dict[str, Any]], type_names: Dict[str, str]) -> Optional[str]:
    """从实际动作判「做的」方向：按成分基金类型与操作方向聚合净变化。

    Returns:
        ``'add'``（净增权益）/ ``'reduce'``（净减权益）/ ``None``（无有效变化或无法判定）。
    """
    add = 0.0
    reduce = 0.0
    for comp in components:
        code = comp.get('fund_code', '')
        type_name = type_names.get(code, '')
        if type_name in _BOND_TYPE_NAMES:
            continue  # 债基/货基不参与权益方向判定（现金管理缓冲）
        op = comp.get('op_code')
        delta = abs(float(comp.get('delta') or 0.0))
        if op in _EQUITY_ADD_OPS:
            add += delta
        elif op in _EQUITY_REDUCE_OPS:
            reduce += delta
    if add <= 0.0 and reduce <= 0.0:
        return None
    if add > reduce:
        return 'add'
    if reduce > add:
        return 'reduce'
    return None


def _build_components(rows: List[Any]) -> List[Dict[str, Any]]:
    """把 ``advisor_adjust_histories`` 行投影为成分列表（前后占比 + 操作方向）。"""
    components: List[Dict[str, Any]] = []
    for r in rows:
        pre = float(r.pre_ratio) if r.pre_ratio is not None else None
        after = float(r.after_ratio) if r.after_ratio is not None else None
        delta = round(after - pre, 2) if (pre is not None and after is not None) else None
        components.append(
            {
                'fund_code': normalize_fund_code(r.fund_code),
                'fund_name': r.fund_name,
                'pre_ratio': pre,
                'after_ratio': after,
                'delta': delta,
                'op_code': r.op_code,
                'op_name': r.op_name,
            }
        )
    return components


def _classify_components(
    components: List[Dict[str, Any]],
    type_names: Dict[str, str],
) -> Dict[str, Any]:
    """把成分按「加权益 / 减权益 / 加债」分类，返回分类计数 + 净权益方向。"""
    equity_add: List[Dict[str, Any]] = []
    equity_reduce: List[Dict[str, Any]] = []
    bond_add: List[Dict[str, Any]] = []
    for c in components:
        type_name = type_names.get(c.get('fund_code', ''), '')
        op = c.get('op_code')
        if op in _EQUITY_ADD_OPS and type_name not in _BOND_TYPE_NAMES:
            equity_add.append(c)
        elif op in _EQUITY_REDUCE_OPS and type_name not in _BOND_TYPE_NAMES:
            equity_reduce.append(c)
        elif op in _EQUITY_ADD_OPS and type_name in _BOND_TYPE_NAMES:
            bond_add.append(c)
    action = _action_direction(components, type_names)
    return {
        'action': action,
        'equity_added_count': len(equity_add),
        'equity_reduced_count': len(equity_reduce),
        'bond_added_count': len(bond_add),
    }


def build_rebalance_interpretation(db, code: str) -> Dict[str, Any]:
    """构建某投顾组合最近一次调仓的结构化解读。

    Args:
        db: 路由会话（``advisor_adjust_histories`` 在 market 域，跨域读与 L3 同口径）。
        code: 投顾组合 code。

    Returns:
        出参 dict：
        - ``found``：组合是否存在；
        - ``has_rebalance``：有无调仓记录；
        - ``adjust_date`` / ``reason``：最近一次调仓的日期与理由；
        - ``components``：本次调仓成分（基金级前后占比 + 操作方向）；
        - ``direction``：方向解读（加权益/减权益/加债/无法判定）；
        - ``divergence``：说的 vs 做的分歧标记（True/False/unknown）。
    """
    from app.domains.funds.models import AdvisorAdjustHistory, AdvisorPortfolio

    normalized = (code or '').strip()
    portfolio = db.query(AdvisorPortfolio).filter_by(code=normalized).first()
    if portfolio is None:
        return {'code': normalized, 'found': False}

    latest_date = (
        db.query(AdvisorAdjustHistory.adjust_date)
        .filter(AdvisorAdjustHistory.portfolio_id == portfolio.id)
        .order_by(AdvisorAdjustHistory.adjust_date.desc())
        .first()
    )
    if latest_date is None:
        return {
            'code': portfolio.code,
            'name': portfolio.name,
            'platform': portfolio.platform,
            'found': True,
            'has_rebalance': False,
        }

    rows = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=portfolio.id, adjust_date=latest_date[0]).all()

    components = _build_components(rows)
    reason = rows[0].reason if rows else None

    # 方向解读：成分基金类型 + 操作方向
    codes = {c['fund_code'] for c in components if c['fund_code']}
    type_names: Dict[str, str] = {}
    if codes:
        try:
            type_names = _lookup_market_type_names(sorted(codes))
        except Exception:  # noqa: BLE001 - 名录不可达时退化为「不分类」，不阻断解读
            type_names = {}

    direction = _classify_components(components, type_names)

    # 说的 vs 做的分歧
    divergence = _resolve_divergence(_reason_direction(reason), direction['action'])

    return {
        'code': portfolio.code,
        'name': portfolio.name,
        'platform': portfolio.platform,
        'found': True,
        'has_rebalance': True,
        'adjust_date': latest_date[0].isoformat(),
        'reason': reason,
        'components': components,
        'direction': direction,
        'divergence': divergence,
    }


def _resolve_divergence(said: Optional[str], action: Optional[str]) -> Dict[str, Any]:
    """说的 vs 做的分歧判定（代码规则，不确定返回 unknown）。

    - 两者都可判且相反 → ``divergence=True``（「他说的未必是他做的」）；
    - 两者都可判且一致 → ``False``；
    - 任一侧无法判定（reason 无信息量 / 无有效动作）→ ``unknown``。
    """
    if said is None or action is None:
        return {'divergence': 'unknown', 'said': said, 'done': action}
    conflict = said != action
    return {'divergence': conflict, 'said': said, 'done': action}


__all__ = ['build_rebalance_interpretation', 'REBALANCE_NARRATIVE_GUIDE']
