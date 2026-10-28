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
from app.domains.funds.models import Fund, FundStyleExposure
from app.domains.positions.models import Position
from app.services.fund_utils import normalize_fund_code
from app.services.nav_service import NavService
from app.services.position_valuation import market_value_cents
from app.services.scope import filter_positions_by_scope

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

# **可覆盖**风格箱的品类（#2628）：只有场外基金与 ETF 才可能拿到箱体。
# 货基/现金不会出现在任何风格箱里，把它们留在分母只会制造一个永远到不了 100% 的
# 天花板（实测 121 只持仓 → 8.35%），并被误读成「同步没在跑」。
ELIGIBLE_COVERAGE_ASSET_TYPES = ('fund', 'etf')

# 历史序列默认返回的时点数（月度频率 → 默认约 5 年）与硬上限（上游实测最长 283 点）
HISTORY_DEFAULT_LIMIT = 60
HISTORY_MAX_LIMIT = 500

# QDII 的判定特征。上游**无结构化 QDII 字段**（东财/同花顺基金档案都没有），
# 既有做法是按名称特征判定（见 `services/fund_benchmark.py` 的同名关键词表）。
QDII_NAME_MARKERS = ('QDII', '海外')

STYLE_SOURCE = 'jiucaishuo_style'


def _qdii_codes(db: Session, fund_codes: List[str]) -> set[str]:
    """返回这批基金里被判为 QDII 的代码集合。

    查 `funds` 表取**基金官方简称**而不是持仓录入名——用户可能把持仓命名为
    「老婆的纳指基金」，按录入名判会漏检。

    判不出来时返回空集（按「不含 QDII」处理）：QDII 只影响展示层的口径说明与
    「可覆盖分母」的取数，不影响风格数值本身；误判为「有」会让每条提示都挂一句
    无关警告，也会平白把一只基金从分母里摘掉。
    """
    codes = [code for code in fund_codes if code]
    if not codes:
        return set()
    try:
        rows = db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all()
    except Exception:
        return set()
    return {code for code, name in rows if any(marker in (name or '') for marker in QDII_NAME_MARKERS)}


def _has_qdii(db: Session, fund_codes: List[str]) -> bool:
    """持仓基金里是否含 QDII（风格分类口径存疑，消费方需要能标注出来）。"""
    return bool(_qdii_codes(db, fund_codes))


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


def portfolio_style_exposure(
    db: Session,
    family_id: int,
    portfolio_id: Optional[int] = None,
    ledger_id: Optional[int] = None,
) -> Dict[str, Any]:
    """组合加权风格暴露（持仓透视）：按市值加权汇总持仓基金的风格箱。

    口径（与 ``strategy_engine/allocation.py`` 一致，勿在此重写市值逻辑）：

    1. 目标持仓 = 本家族 ``asset_type ∈ (fund, money_fund, etf)`` 的持仓行；
    2. 市值 = ``market_value_cents``（净值走 NavService 本地读，外币折 CNY）；
    3. 同一 symbol 多账户先合并，再按合并市值加权；
    4. 每只基金取**各自最新时点**的风格箱（新基金时点少，强制对齐共同日期会把
       它们整体排除、低估覆盖），加权结果天然合计 = 100（单只箱体合计 = 100）；
    5. **无风格箱的持仓不计入加权**，但全额计入分母并列入 ``uncovered``——
       覆盖率是结果的一部分，不是可以省看的注释。
    6. **两个覆盖率口径并存**（#2628）：``coverage_pct`` 分母 = 全部持仓（#2478 契约，
       保持不变）；``eligible_coverage_pct`` 分母只含**可能拿到箱体**的持仓
       （``ELIGIBLE_COVERAGE_ASSET_TYPES`` 且非 QDII）。货基/现金永远不会出现在
       风格箱里，留在分母只会把覆盖率压成一个永远到不了 100% 的数（实测 121 只持仓
       → 8.35%），并被误读成「同步没在跑」。**没有合格资产时返回 ``None`` 而不是 0**
       ——「0% 覆盖」与「没有可覆盖的资产」不是一回事。

    QDII 口径存疑（见模块 docstring）：加权结果包含 QDII 持仓的原样箱体，
    由消费方决定是否提示。

    ## 作用域（2026-10-27 收口）

    - 默认（两个参数都不传）= 家庭级；
    - ``ledger_id`` = 单账户；``portfolio_id`` = 该组合口径；
    - 作用域解析**委托** ``services.scope.filter_positions_by_scope``（组合语义 =
      显式 ``positions.portfolio_id`` + 成员账本继承），不在此手写成员账本查询——
      否则会漏掉「持仓显式归属」，与穿透 / 归因 / 持仓结构口径不一致。
    - 两者互斥：同时传抛 ``ValueError``（与其余分析类端点同文案，视图层转 400）；
      组合不存在 / 非本家庭同样抛 ``ValueError``。
    - 作用域内没有持仓时返回**空结构**，不退回家庭级。这条是刻意的：
      #2595 修过「组合详情页穿透面板不传 scope、实际拉的是家庭数据」，
      「传了但过滤为空」若静默放大成全家数据，就是同一个错误的复活。
    """
    positions = (
        db.query(Position)
        .filter(Position.family_id == family_id, Position.asset_type.in_(PORTFOLIO_STYLE_ASSET_TYPES))
        .all()
    )
    positions = filter_positions_by_scope(db, family_id, positions, ledger_id=ledger_id, portfolio_id=portfolio_id)
    result: Dict[str, Any] = {
        'styles': [],
        'fund_count': 0,
        'covered_market_value_cents': 0,
        'total_market_value_cents': 0,
        'coverage_pct': 0.0,
        # 可覆盖口径（#2628）：分母只含 fund/etf 且非 QDII 的持仓
        'eligible_market_value_cents': 0,
        'eligible_coverage_pct': None,
        'period_from': None,
        'period_to': None,
        'uncovered': [],
        # QDII 标记：风格分类对 QDII 不可靠（见模块头第 3 条），
        # 由本服务判定一次，**提示与面板共用同一个值**，避免两处口径打架
        'has_qdii': False,
        'source': STYLE_SOURCE,
    }
    if not positions:
        return result
    fund_codes = sorted({normalize_fund_code(p.symbol) or '' for p in positions if p.symbol} - {''})
    qdii_codes = _qdii_codes(db, fund_codes)
    result['has_qdii'] = bool(qdii_codes)

    # 1) 按 symbol 聚合市值（分，折 CNY）——先合并多账户，再定权重
    symbols = [p.symbol for p in positions if p.symbol]
    navs = NavService.get_latest_navs(db, symbols, allow_remote=False) if symbols else {}
    aggregated: Dict[str, Dict[str, Any]] = {}
    eligible_flags: Dict[str, bool] = {}
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
        # 合格判定按 symbol 收敛：同一 symbol 多账户里只要有一条不是 fund/etf，
        # 就整只从「可覆盖分母」里摘掉（宁可少算，也不要把货基市值当成分母）
        eligible_flags[symbol] = eligible_flags.get(symbol, True) and (pos.asset_type in ELIGIBLE_COVERAGE_ASSET_TYPES)
        if not bucket.get('name') or bucket['name'] == symbol:
            if pos.name:
                bucket['name'] = pos.name

    def _eligible(symbol: str) -> bool:
        """该 symbol 是否计入可覆盖分母（品类合格 且 非 QDII）。"""
        return bool(eligible_flags.get(symbol)) and normalize_fund_code(symbol) not in qdii_codes

    total_mv = sum(b['market_value_cents'] for b in aggregated.values())
    result['total_market_value_cents'] = total_mv
    eligible_mv = sum(b['market_value_cents'] for s, b in aggregated.items() if _eligible(s))
    result['eligible_market_value_cents'] = eligible_mv
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
    covered_eligible_mv = 0
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
        if _eligible(bucket['symbol']):
            covered_eligible_mv += mv
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
    # 可覆盖口径独立给值：`eligible_mv == 0` 时是 None（没有一个品种可能带箱体），
    # 不是 0%（有合格品种但一个都没覆盖）——两者对用户是不同结论。
    if eligible_mv > 0:
        result['eligible_coverage_pct'] = round(covered_eligible_mv / eligible_mv * 100, 2)
    result['uncovered'] = sorted(uncovered, key=lambda u: -u['market_value_cents'])
    return result
