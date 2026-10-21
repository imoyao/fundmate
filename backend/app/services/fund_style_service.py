# -*- coding: utf-8 -*-
"""基金投资风格箱读取服务（#2478）：详情页风格箱 + 漂移序列 + 组合加权暴露。

数据来源只有一处：``fund_style_exposures`` 表（job 侧写入，见
``services/sync/jobs/fund_style_job.py``）。本模块**纯只读**，不抓取、不写库。

三个消费场景（对应评估文档 ``fund_style_tag_feasibility.md`` 的买方价值）：

1. **风格定位**（详情页）：:func:`get_fund_style_box` 给最新时点的 8 分类暴露；
2. **风格漂移**（纪律性监控）：:func:`get_fund_style_history` 给月度序列，
   :func:`get_fund_style_box` 附带上一时点主导风格做「漂移信号」；
3. **组合透视**（持仓加权）：:func:`portfolio_style_exposure` 按市值加权汇总
   持仓基金的风格暴露。

## 硬约束（与全库纪律一致）

1. **数据不足诚实回空**：无风格箱的基金 / 持仓一律不进结果，不用 0 或默认值顶替
   （manager_style 同款纪律）。组合透视额外报告覆盖率与未覆盖清单——遮住不看的
   「100% 覆盖」比明示的缺口更危险。
2. **市值唯一口径**：组合加权走 ``services/position_valuation.market_value_cents``
   （strategy_engine/allocation.py 的契约），外币按 ``EXCHANGE_RATES`` 折 CNY 后
   再算权重，净值走 ``NavService.get_latest_navs(allow_remote=False)``——
   展示路径不得为拿净值阻塞请求。
3. **QDII 口径存疑原样透出**：韭圈儿对海外资产映射不合理（270042 纳指100 实测
   「固收风格 81.28」），本模块不做修正也不剔除，由消费方决定是否提示。
4. **后端不返回颜色**：风格名是稳定字符串枚举，配色由前端令牌决定。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.domains.funds.models import FundStyleExposure
from app.domains.positions.models import Position
from app.services.fund_utils import normalize_fund_code
from app.services.nav_service import NavService
from app.services.position_valuation import market_value_cents

# 8 分类展示顺序（晨星式）。上游顺序确定，但读取侧自持一份固定序，
# 上游调整顺序时 API 响应不变；上游增删分类时未知名追加在末尾（排序稳定）。
STYLE_DISPLAY_ORDER: tuple[str, ...] = (
    '大盘成长',
    '大盘价值',
    '中盘成长',
    '中盘价值',
    '小盘成长',
    '小盘价值',
    '港股风格',
    '固收风格',
)

# 风格箱覆盖的持仓品类：场外基金 + 货基 + 场内 ETF（与 job 的 resolve_pool 一致）
PORTFOLIO_STYLE_ASSET_TYPES = ('fund', 'money_fund', 'etf')

# 历史序列默认返回的时点数（月度频率 → 默认约 5 年）与硬上限（上游实测最长 283 点）
HISTORY_DEFAULT_LIMIT = 60
HISTORY_MAX_LIMIT = 500

STYLE_SOURCE = 'jiucaishuo_style'


def _to_float(value: Any) -> Optional[float]:
    """SafeNumeric/Decimal → float；None 直传（「未设置」不退化成 0）。"""
    if value is None:
        return None
    return float(value)


def _style_sort_key(name: str) -> tuple[int, str]:
    """固定展示序；未知名排末尾并按名称稳定排序。"""
    if name in STYLE_DISPLAY_ORDER:
        return (STYLE_DISPLAY_ORDER.index(name), '')
    return (len(STYLE_DISPLAY_ORDER), name)


def _order_styles(rows: List[Any]) -> List[Dict[str, Any]]:
    """把 ``(style_name, value)`` 行按固定展示序整形。"""
    return [
        {'style_name': name, 'value': _to_float(value)}
        for name, value in sorted(rows, key=lambda r: _style_sort_key(r[0]))
    ]


def _dominant_of(items: List[Dict[str, Any]]) -> Optional[str]:
    """暴露值最大的风格；并列取序列首位（与 job 派生口径一致：上游顺序确定）。

    理论上每时点合计 = 100，不会全 0；防御性地返回 None 而非 '未知'。
    """
    best: Optional[Dict[str, Any]] = None
    for item in items:
        if item.get('value') is None:
            continue
        if best is None or item['value'] > best['value']:
            best = item
    if best is None or not best.get('value'):
        return None
    return best['style_name']


def _rows_at_latest(db: Session, fund_code: str) -> tuple[Optional[Any], List[Any]]:
    """取某基金**最新时点**的风格行与该时点。

    Returns:
        (latest_date, [(style_name, value), ...])；无数据时 (None, [])。
    """
    latest_date = (
        db.query(FundStyleExposure.stat_date)
        .filter(FundStyleExposure.fund_code == fund_code)
        .order_by(FundStyleExposure.stat_date.desc())
        .first()
    )
    if latest_date is None:
        return None, []
    latest_date = latest_date[0]
    rows = (
        db.query(FundStyleExposure.style_name, FundStyleExposure.value)
        .filter(FundStyleExposure.fund_code == fund_code, FundStyleExposure.stat_date == latest_date)
        .all()
    )
    return latest_date, rows


def get_fund_style_box(db: Session, fund_code: str) -> Optional[Dict[str, Any]]:
    """最新风格箱（详情页首屏）。

    返回 ``None`` 表示该基金无风格箱数据（未同步 / 上游无值）——前端降级「—」，
    不编造占位箱体。

    附带**漂移信号**：``prev_dominant_style`` / ``prev_period`` 为上一时点的主导
    风格（若有），``dominant_changed`` 明示是否发生主导风格切换。这是「宣称风格
    vs 实际漂移」的最粗粒度信号，细粒度曲线走 :func:`get_fund_style_history`。
    """
    if not fund_code:
        return None
    latest_date, rows = _rows_at_latest(db, fund_code)
    if latest_date is None or not rows:
        return None

    items = _order_styles(rows)
    dominant = _dominant_of(items)

    # 上一时点（< latest_date 的最近一个 distinct stat_date）的主导风格
    prev_date_row = (
        db.query(FundStyleExposure.stat_date)
        .filter(FundStyleExposure.fund_code == fund_code, FundStyleExposure.stat_date < latest_date)
        .order_by(FundStyleExposure.stat_date.desc())
        .first()
    )
    prev_dominant: Optional[str] = None
    prev_period: Optional[str] = None
    if prev_date_row is not None:
        prev_date = prev_date_row[0]
        prev_period = prev_date.isoformat()
        prev_rows = (
            db.query(FundStyleExposure.style_name, FundStyleExposure.value)
            .filter(FundStyleExposure.fund_code == fund_code, FundStyleExposure.stat_date == prev_date)
            .all()
        )
        prev_dominant = _dominant_of(_order_styles(prev_rows))

    return {
        'fund_code': fund_code,
        'stat_date': latest_date.isoformat(),
        'styles': items,
        'dominant_style': dominant,
        'style_period': latest_date.isoformat(),
        'prev_dominant_style': prev_dominant,
        'prev_period': prev_period,
        'dominant_changed': bool(dominant and prev_dominant and dominant != prev_dominant),
        'source': STYLE_SOURCE,
    }


def get_fund_style_history(db: Session, fund_code: str, limit: Optional[int] = None) -> Dict[str, Any]:
    """风格漂移序列（月度，倒序）。

    每个时点返回 **wide** 形态（``{stat_date, styles: {风格名: 值}}``）——前端
    画多序列折线（8 条风格曲线）时 wide 比 long 少一次客户端透视。

    ``limit`` 为时点数上限（默认 60 ≈ 5 年，硬上限 500 覆盖上游最长 283 点）。
    """
    if not fund_code:
        return {'fund_code': fund_code, 'points': [], 'count': 0}
    if limit is None:
        limit = HISTORY_DEFAULT_LIMIT
    limit = max(1, min(HISTORY_MAX_LIMIT, int(limit)))

    # 先取最近 N 个时点，再取这些时点的全部风格行（两次索引查询，避免全历史拉回）
    dates = [
        r[0]
        for r in (
            db.query(FundStyleExposure.stat_date)
            .filter(FundStyleExposure.fund_code == fund_code)
            .distinct()
            .order_by(FundStyleExposure.stat_date.desc())
            .limit(limit)
            .all()
        )
    ]
    if not dates:
        return {'fund_code': fund_code, 'points': [], 'count': 0}

    rows = (
        db.query(FundStyleExposure.stat_date, FundStyleExposure.style_name, FundStyleExposure.value)
        .filter(FundStyleExposure.fund_code == fund_code, FundStyleExposure.stat_date.in_(dates))
        .all()
    )
    grouped: Dict[Any, Dict[str, Optional[float]]] = {d: {} for d in dates}
    for stat_date, style_name, value in rows:
        grouped[stat_date][style_name] = _to_float(value)

    points = [{'stat_date': d.isoformat(), 'styles': grouped[d]} for d in sorted(grouped, reverse=True)]
    return {'fund_code': fund_code, 'points': points, 'count': len(points)}


def portfolio_style_exposure(db: Session, family_id: int) -> Dict[str, Any]:
    """组合加权风格暴露（持仓透视）：按市值加权汇总持仓基金的风格箱。

    口径（与 ``strategy_engine/allocation.py`` 一致，勿在此重写市值逻辑）：

    1. 目标持仓 = 本家族 ``asset_type ∈ (fund, money_fund, etf)`` 的持仓行；
    2. 市值 = ``market_value_cents``（净值走 NavService 本地读，外币折 CNY）；
    3. 同一 symbol 多账户先合并，再按合并市值加权；
    4. 每只基金取**各自最新时点**的风格箱（新基金时点少，强制对齐共同日期会把
       它们整体排除、低估覆盖），加权结果天然合计 = 100（单只箱体合计 = 100）；
    5. **无风格箱的持仓不计入加权**，但全额计入分母并列入 ``uncovered``——
       覆盖率是结果的一部分，不是可以省看的注释。

    QDII 口径存疑（见模块 docstring）：加权结果包含 QDII 持仓的原样箱体，
    由消费方决定是否提示。
    """
    positions = (
        db.query(Position)
        .filter(Position.family_id == family_id, Position.asset_type.in_(PORTFOLIO_STYLE_ASSET_TYPES))
        .all()
    )
    result: Dict[str, Any] = {
        'styles': [],
        'fund_count': 0,
        'covered_market_value_cents': 0,
        'total_market_value_cents': 0,
        'coverage_pct': 0.0,
        'period_from': None,
        'period_to': None,
        'uncovered': [],
        'source': STYLE_SOURCE,
    }
    if not positions:
        return result

    # 1) 按 symbol 聚合市值（分，折 CNY）——先合并多账户，再定权重
    symbols = [p.symbol for p in positions if p.symbol]
    navs = NavService.get_latest_navs(db, symbols, allow_remote=False) if symbols else {}
    aggregated: Dict[str, Dict[str, Any]] = {}
    for pos in positions:
        symbol = pos.symbol
        if not symbol:
            continue
        rate = EXCHANGE_RATES.get(getattr(pos, 'currency', None) or 'CNY', 1.0)
        value = market_value_cents(pos, effective_nav_yuan=navs.get(normalize_fund_code(symbol)), rate=rate)
        bucket = aggregated.setdefault(
            symbol,
            {'symbol': symbol, 'name': pos.name or symbol, 'market_value_cents': 0},
        )
        bucket['market_value_cents'] += value
        if not bucket.get('name') or bucket['name'] == symbol:
            if pos.name:
                bucket['name'] = pos.name

    total_mv = sum(b['market_value_cents'] for b in aggregated.values())
    result['total_market_value_cents'] = total_mv
    if total_mv <= 0:
        # 全 0 市值（如仅 balance 模式未录市值）→ 权重无定义，诚实回空
        result['uncovered'] = [
            {'symbol': b['symbol'], 'name': b['name'], 'market_value_cents': b['market_value_cents']}
            for b in aggregated.values()
        ]
        return result

    # 2) 每只基金取各自最新时点箱体；无箱体 → uncovered
    weighted: Dict[str, float] = {}
    covered_mv = 0
    covered_dates: List[Any] = []
    uncovered: List[Dict[str, Any]] = []
    for bucket in aggregated.values():
        code = normalize_fund_code(bucket['symbol'])
        if not code:
            uncovered.append(dict(bucket))
            continue
        latest_date, rows = _rows_at_latest(db, code)
        if latest_date is None or not rows:
            uncovered.append(dict(bucket))
            continue
        mv = bucket['market_value_cents']
        covered_mv += mv
        covered_dates.append(latest_date)
        for item in _order_styles(rows):
            value = item.get('value')
            if value is None:
                continue
            weighted[item['style_name']] = weighted.get(item['style_name'], 0.0) + mv * value

    if covered_mv > 0:
        result['styles'] = [
            {'style_name': name, 'value': round(weighted[name] / covered_mv, 2)}
            for name in sorted(weighted, key=_style_sort_key)
        ]
        result['covered_market_value_cents'] = covered_mv
        result['coverage_pct'] = round(covered_mv / total_mv * 100, 2)
        result['period_from'] = min(covered_dates).isoformat()
        result['period_to'] = max(covered_dates).isoformat()
        result['fund_count'] = len(covered_dates)
    result['uncovered'] = sorted(uncovered, key=lambda u: -u['market_value_cents'])
    return result
