# -*- coding: utf-8 -*-
"""组合内基金两两相关性矩阵（#2686 第二交付）。

## 口径全部复用，不另造

| 环节 | 复用 |
|---|---|
| 成员 | ``holding_overlap.merge_fund_positions``（与重叠度矩阵同一份持仓合并口径） |
| 序列 | ``pro_allocation.trend_points``（1Y；场内前复权收盘 / 场外累计净值） |
| 判据 | ``analytics.correlation.pearson_correlation``（日期交集配对、``MIN_OVERLAP``、零方差不出值） |
| 截断 | ``matrix_members.select_matrix_members``（覆盖 ≥90% / 上限 20 / 下限 8） |

后三条都各只有一个实现，这是「同一对基金在矩阵与列表里数值必须相等」的前提。

## 成员为什么与重叠度矩阵同源

owner 2026-10-28 拍板：两张矩阵共用同一条截断规则与同一份成员清单，切换视图时行列
一致。相关性**本身不需要持仓明细**（只要有净值序列），同源在数据上是「多取一份」，
但换来的是「不会换个视图少 8 只」——这个一致性比省一次查询重要。

## 三种「没有值」必须可区分（卡面验收第 5 条）

- ``no_series``：该基金没有净值/价格序列（新成立、未入库）；
- ``short_overlap``：同期交易日不足 ``MIN_OVERLAP``（净值披露日历不同、上市不足一季度）；
- ``zero_variance``：净值长期不变（货基、长期停牌），Pearson 数学上未定义。

三者都不许画成 ``0``：``0`` 的含义是「无关」，而它们是「无信息」，两者天差地别。
实测（2026-10-28 本地库）：96 只同源成员 100% 可算；把成员放宽到全部基金持仓时，
失败 125 对里 124 对来自同一只净值披露日历不同的基金——**失败会成行成列地出现**，
前端应按行/列整块降级，而不是散落灰格。
"""

from __future__ import annotations

from itertools import combinations
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.positions.models import Position
from app.services.analytics.correlation import MIN_OVERLAP, correlation_caveats, pearson_correlation
from app.services.holding_overlap import merge_fund_positions
from app.services.matrix_members import (
    MATRIX_COVERAGE_TARGET,
    MATRIX_MAX_MEMBERS,
    MATRIX_MIN_MEMBERS,
    select_matrix_members,
)
from app.services.position_aggregation import get_fund_aggregation
from app.services.pro_allocation import trend_points

#: 序列窗口：1Y——与 ``pro_allocation._RANGE`` / ``pro_risk`` 同窗，三处不许有两个窗口。
WINDOW = '1Y'

#: 出参的数据来源标识（前端据此标注「净值/收盘价序列」）。
SOURCE = 'daily_worth/price_history'

#: 百分比换算基数（与 ``holding_overlap._PERCENT_SCALE`` 同值，语义见该处注释）。
_PERCENT_SCALE = 100

#: ``pearson_correlation`` 的 reason 文案 → 机器可读状态码。
#:
#: 前端只认 code、不解析中文：判据文案以后改了措辞，不该让前端一起改。
_STATUS_BY_REASON = (
    ('缺少有效净值', 'no_series'),
    ('同期交易日不足', 'short_overlap'),
    ('无波动', 'zero_variance'),
)

#: 矩阵口径声明：与 ``correlation_caveats()`` 合并后随值下发，前端原样展示。
_MATRIX_CAVEATS = (
    f'矩阵成员按市值覆盖 {int(MATRIX_COVERAGE_TARGET * 100)}% 截断（上限 {MATRIX_MAX_MEMBERS} 只、'
    f'下限 {MATRIX_MIN_MEMBERS} 只）；未展开的基金不计入本次结论',
    f'相关性基于近 {WINDOW} 日收益、同期交易日不少于 {MIN_OVERLAP} 天；窗口变化结论可能不同',
)


def _empty_result() -> Dict[str, Any]:
    """空结果骨架（降级 / 不足 2 只时返回，字段与正常路径完全一致）。"""
    return {
        'window': WINDOW,
        'min_overlap': MIN_OVERLAP,
        'funds': [],
        'cells': [],
        'fund_count': 0,
        'computed_pairs': 0,
        'total_pairs': 0,
        'truncated': {'count': 0, 'market_value_pct': 0.0},
        'matrix_rule': {
            'coverage_target': MATRIX_COVERAGE_TARGET,
            'max_members': MATRIX_MAX_MEMBERS,
            'min_members': MATRIX_MIN_MEMBERS,
        },
        'caveats': list(_MATRIX_CAVEATS) + correlation_caveats(),
        'degraded': False,
        'source': SOURCE,
    }


def _status_of(reason: Optional[str]) -> str:
    """把判据文案归类成状态码；无 reason 即算出来了。"""
    text = reason or ''
    for needle, code in _STATUS_BY_REASON:
        if needle in text:
            return code
    return 'ok'


def _asset_type_map(db: Session, family_id: int, symbols: List[str]) -> Dict[str, str]:
    """``symbol -> asset_type``：序列取数要按品类分派（场内收盘 / 场外净值）。"""
    if not symbols:
        return {}
    rows = (
        db.query(Position.symbol, Position.asset_type)
        .filter(Position.family_id == family_id, Position.symbol.in_(symbols))
        .all()
    )
    mapping: Dict[str, str] = {}
    for symbol, asset_type in rows:
        if symbol and asset_type:
            mapping.setdefault(symbol, asset_type)
    return mapping


def portfolio_holding_correlation(db: Session, family_id: int = 1) -> Dict[str, Any]:
    """组合内基金两两相关性矩阵（家庭作用域）。

    Args:
        db: 路由会话（持仓在 user 域、净值/收盘序列在 market 域，跨域零 JOIN）。
        family_id: 家庭 ID（数据隔离维度）。

    Returns:
        见模块 docstring 的出参结构：``funds`` 是**已截断**的矩阵成员（市值降序），
        ``cells`` 是成员内两两结果（上三角，``fund_code_a/b`` 无序），``truncated``
        给出被折叠只数与市值占比。``fund_count`` 是**截断前**的成员总数，前端据此
        区分「组合里只有 3 只基金」（无需截断提示）与「有 96 只但只展开 20 只」。

    降级：持仓聚合失败 → ``degraded=True`` + 空矩阵，不 500、不拿 0 冒充「不相关」。
    """
    result = _empty_result()

    try:
        payload = get_fund_aggregation(db, family_id, page_size=0)
        groups = payload.get('groups') or []
    except Exception as exc:  # noqa: BLE001 - 展示接口不该因取数失败整体挂掉
        logger.warning(f'相关性矩阵：持仓聚合失败（降级回空）: {exc}')
        result['degraded'] = True
        return result

    # 市值降序 + code 兜底排序：与重叠度矩阵 `funds` 的排序口径一致（行列顺序稳定）
    funds = sorted(
        merge_fund_positions(groups),
        key=lambda fund: (-fund.market_value_cents, fund.fund_code),
    )
    result['fund_count'] = len(funds)
    if len(funds) < 2:
        return result

    total_mv = sum(fund.market_value_cents for fund in funds)
    members, truncated_count, truncated_pct = select_matrix_members(funds)
    result['truncated'] = {'count': truncated_count, 'market_value_pct': truncated_pct}
    result['funds'] = [
        {
            'fund_code': fund.fund_code,
            'symbol': fund.symbol,
            'name': fund.name,
            'market_value_cents': fund.market_value_cents,
            'market_value_pct': (
                round(fund.market_value_cents / total_mv * _PERCENT_SCALE, 1) if total_mv > 0 else 0.0
            ),
        }
        for fund in members
    ]

    type_map = _asset_type_map(db, family_id, [fund.symbol for fund in members])
    series: Dict[str, List[Any]] = {}
    for fund in members:
        points, _basis = trend_points(db, fund.symbol, type_map.get(fund.symbol))
        series[fund.fund_code] = points

    cells: List[Dict[str, Any]] = []
    computed = 0
    for fund_a, fund_b in combinations(members, 2):
        pair = pearson_correlation(series.get(fund_a.fund_code) or [], series.get(fund_b.fund_code) or [])
        status = _status_of(pair['reason'])
        if status == 'ok':
            computed += 1
        cells.append(
            {
                'fund_code_a': fund_a.fund_code,
                'fund_code_b': fund_b.fund_code,
                'correlation': pair['correlation'],
                'overlap_days': pair['overlap_days'],
                'status': status,
                'reason': pair['reason'] or '',
            }
        )

    result['cells'] = cells
    result['computed_pairs'] = computed
    result['total_pairs'] = len(cells)
    return result
