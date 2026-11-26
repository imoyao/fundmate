# -*- coding: utf-8 -*-
"""投顾组合 vs 我的账户：**投资方向**（风格暴露）对照。

## 这块回答什么

「我持有 · 组合里没有」的清单本身不说明问题——109 只、占比 99.8% 只告诉用户
「几乎全是自己的」，告诉不了「我们差在哪」。本模块把两边都折成**五个方向**
（大盘 / 中盘 / 小盘 / 港股 / 固收）的占比，让「中盘 34% vs 17%、固收 9% vs 32%」
这种结构性差异直接可见。

## 口径（重要，勿自行改）

1. **风格来源**：`fund_style_exposures`（晨星式八分类：大盘成长/大盘价值/中盘成长/
   中盘价值/小盘成长/小盘价值/港股风格/固收风格）。八分类聚成五组是**展示层聚合**，
   不是重新分类——单只基金的箱体仍是上游原值。
2. **组合侧加权**：`advisor_holdings` 最新快照日的 `after_ratio`（披露权重）×
   每只基金**各自最新时点**的箱体。各取各自最新时点（与
   `fund_style_service.portfolio_style_exposure` 同一条理由：强制对齐共同日期会把
   新基金整体排除、低估覆盖）。分母是**有权重且有箱体**的基金权重合计，
   覆盖率单列给前端——不是可以省看的注释。
3. **我侧加权**：复用 `portfolio_style_exposure(db, family_id)`，不在此重写市值与
   加权逻辑。它已完成「按 symbol 合并多账户 → 按市值加权 → 无箱体不计入加权但
   计入分母」。本模块只做八分类 → 五组的求和。
4. **剔除货基/债基**：组合侧沿用 `advisor_comparison._load_advisor_holdings`
   （按 `fund_types.name` 剔除货币型/债券型）。**刻意 import 同一份实现**而不是抄一份：
   两处口径漂移会让「对比页说 12 只、方向页算 14 只」，那是最难查的一类不一致。
   货基没有风格箱，留在分母只会把覆盖率压低并被误读成「同步没跑」。
5. **只陈述、不评判**：不输出「更优 / 建议替换」这类词（合规红线，与
   `advisor_comparison` 一致）。

## 降级契约

- 组合不存在 → `ValueError`（视图转 404/1002，与其余 advisor 端点同码）；
- 组合无持仓快照 → `advisor.directions` 为空 + `has_snapshot=False`，
  **不拿五个 0 冒充**（0% 是「都不配」这个结论，不是「没有数据」）；
- 我侧取数失败 → `mine.degraded=True` + 空方向，同样不拿 0 冒充。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.funds.models import AdvisorPortfolio
from app.services.advisor_comparison import _load_advisor_holdings
from app.services.fund_style_service import _rows_at_latest, portfolio_style_exposure

#: 展示层的五个方向及其对应的上游风格名（顺序即渲染顺序，勿随手排序）
DIRECTIONS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ('大盘', ('大盘成长', '大盘价值')),
    ('中盘', ('中盘成长', '中盘价值')),
    ('小盘', ('小盘成长', '小盘价值')),
    ('港股', ('港股风格',)),
    ('固收', ('固收风格',)),
)

_STYLE_TO_DIRECTION: Dict[str, str] = {style: key for key, styles in DIRECTIONS for style in styles}

#: 口径声明（前端直接渲染，不在这里拼句子以外的东西）
_CAVEATS: Tuple[str, ...] = (
    '方向取自基金最近一期的风格暴露。',
    '组合按披露权重、我的持仓按市值加权；无风格箱的基金不计入。',
    '只做客观对照，不构成投资建议。',
)


def _direction_rows(weighted: Dict[str, float]) -> List[Dict[str, Any]]:
    """五方向定序输出；缺项补 0（这一侧确实没有该方向，0 是结论不是缺数）。"""
    return [{'key': key, 'value': round(weighted.get(key, 0.0), 2)} for key, _ in DIRECTIONS]


def _advisor_side(db: Session, portfolio: AdvisorPortfolio) -> Dict[str, Any]:
    """组合侧：披露权重 × 各自最新箱体，归一到「有箱体的权重合计」。"""
    as_of, holdings = _load_advisor_holdings(db, portfolio.id)
    weighted = {key: 0.0 for key, _ in DIRECTIONS}
    total_weight = 0.0
    covered_weight = 0.0
    covered_funds = 0
    missing: List[Dict[str, Any]] = []

    for item in holdings:
        ratio = item.get('after_ratio')
        if ratio is None or ratio <= 0:
            continue
        total_weight += ratio
        _, rows = _rows_at_latest(db, item['fund_code'])
        if not rows:
            missing.append(
                {
                    'fund_code': item['fund_code'],
                    'fund_name': item.get('fund_name'),
                    'weight_pct': round(float(ratio), 2),
                }
            )
            continue
        covered_weight += ratio
        covered_funds += 1
        for style_name, value in rows:
            key = _STYLE_TO_DIRECTION.get(style_name)
            if key is None or value is None:
                continue
            weighted[key] += float(ratio) * float(value) / 100.0

    # 归一到覆盖部分：covered_weight 为 0 时不给占比（除零），由 has_snapshot 之外
    # 的 covered_funds 表达「有快照但没有一只带箱体」
    directions = (
        _direction_rows({k: v / covered_weight * 100.0 for k, v in weighted.items()}) if covered_weight > 0 else []
    )
    return {
        # `_load_advisor_holdings` 已把日期转成 ISO 字符串（与对比端点出参同形）
        'as_of_date': as_of,
        'has_snapshot': bool(holdings),
        'directions': directions,
        'fund_count': covered_funds,
        'covered_weight_pct': round(covered_weight, 2) if covered_weight > 0 else None,
        'coverage_pct': round(covered_weight / total_weight * 100.0, 2) if total_weight > 0 else None,
        'missing': missing,
        'degraded': False,
    }


def _mine_side(db: Session, family_id: int) -> Dict[str, Any]:
    """我侧：复用组合透视（已按市值加权），只做八分类 → 五组的求和。"""
    try:
        data = portfolio_style_exposure(db, family_id)
    except Exception as exc:  # 取数失败 → 显式降级，不拿 0 冒充
        logger.warning(f'advisor_style_compare：我的持仓风格透视失败（降级）: {exc}')
        return {
            'directions': [],
            'total_market_value_cents': 0,
            'coverage_pct': None,
            'fund_count': 0,
            'period_to': None,
            'degraded': True,
        }

    weighted = {key: 0.0 for key, _ in DIRECTIONS}
    for item in data.get('styles') or []:
        key = _STYLE_TO_DIRECTION.get(item.get('style_name') or '')
        value = item.get('value')
        if key is None or value is None:
            continue
        weighted[key] += float(value)

    return {
        'directions': _direction_rows(weighted),
        'total_market_value_cents': data.get('total_market_value_cents') or 0,
        'coverage_pct': data.get('coverage_pct'),
        'fund_count': data.get('fund_count') or 0,
        'period_to': data.get('period_to'),
        'degraded': False,
    }


def build_advisor_style_compare(db: Session, code: str, family_id: int) -> Dict[str, Any]:
    """组合 vs 我的账户的方向对照（五方向占比 + 覆盖率 + 口径声明）。

    Args:
        db: 路由会话（跨域读：投顾在 market 域、我的持仓在 user 域，与
            `advisor_comparison` 同一套做法，零 JOIN）。
        code: 平台组合码（`advisor_portfolios.code`）。
        family_id: 当前家庭 id。

    Raises:
        ValueError: 组合不存在（视图转 404/1002）。
    """
    portfolio = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == code).first()
    if portfolio is None:
        raise ValueError(f'投顾组合不存在：{code}')

    return {
        'code': portfolio.code,
        'name': portfolio.name,
        'platform': portfolio.platform,
        'advisor': _advisor_side(db, portfolio),
        'mine': _mine_side(db, family_id),
        'caveats': list(_CAVEATS),
    }
