# -*- coding: utf-8 -*-
"""基金业绩与风险（#2029 卡 B · 详情页业绩与风险卡）。

一次算完**区间收益切面 + 最大回撤 + 年化波动率**，前端一次请求拿到表现卡全部字段。
字段缺失一律返回 ``None`` 由前端降级为「—」，不编造占位值（设计 §6 诚实降级）。

口径（设计卡 §4.2⑥⑦，与自选域同源）：
- 统一用 ``daily_worth.acc_nav``（累计净值）；``acc_nav`` 缺失回退 ``unit_nav``，
  与 ``fund_metrics.load_nav_points`` 同一逻辑，避免详情页与自选页数字打架；
- 业务日一律 ``today_shanghai()``（硬规则），避免 UTC 16:00–24:00 差一天；
- 最大回撤复用 ``fund_metrics.compute_max_drawdown``（纯计算），不复制算法。

货基分支（§4.2⑧）：货币基金没有日涨跌 / 回撤口径，走 ``money_fund_daily_worth``
的**万份收益 + 七日年化**——不显净值型指标，避免用户误读「货币也跌了」。

#167 追加：**风险指标块**（本轮回撤 / 卡玛 / 夏普 / 索提诺 / UI / UPI / 波回比 / 胜率）
-----------------------------------------------------------------------------
「回撤恢复得怎么样」与「涨跌对称不对称」是选基的两件独立的事，只给最大回撤会把
「跌 30% 但已修复」与「跌 30% 且仍在水下」显示成同一个数，故补 ``current_drawdown``
（本轮回撤）一族。

实现上**不重算**：数值来源是每日 ``fund_risk_metrics`` job 落库的快照（``fund_risk_metrics``
表），本函数只做「按 fund_code 取最新一行 + 口径版本校验」。理由：

- 详情页本来就已读一遍 3 年日净值；再跑一遍同一套计算等于每次请求做两次同样的活；
- 横向筛（列表页按指标排序）必须有一张物化的表才可行——同一套数不该有两条算法路径。

**快照缺失/口径过期时回退现算**（与 ``pnl_daily_snapshots`` 同口径：「读路径永不因快照
缺失而空白」）。回退路径与 job 走的是**同一个纯函数** ``compute_risk_metrics``，故物化读
与现算读逐位相等；这一点由 ``tests/services/test_fund_performance.py`` 的等价性用例钉住。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.data_sources import FUND_NAV_SOURCE_LABEL
from app.core.time_utils import today_shanghai
from app.services.fund_metrics import compute_max_drawdown, load_nav_points
from app.services.fund_risk_metrics import RISK_FREE_RATE_ANNUAL, WINDOW_3Y, RiskMetricsResult, compute_risk_metrics

# 区间档位（近 N + 今年以来 + 成立以来）。``days`` 为自然数日，用于定位起点；
# ``ytd`` / ``since`` 为特殊档（当年 1/1 / 序列首点）。标签与后端返回 key 一一对应。
_PERIODS: List[Tuple[str, str, Optional[int]]] = [
    ('1w', '近1周', 7),
    ('1m', '近1月', 30),
    ('3m', '近3月', 90),
    ('6m', '近6月', 180),
    ('1y', '近1年', 365),
    ('2y', '近2年', 730),
    ('3y', '近3年', 1095),
    ('5y', '近5年', 1825),
    ('ytd', '今年以来', None),
    ('since', '成立以来', None),
]

# 回撤固定窗口（与自选域 _apply_fund_drawdown_fields 一致，见 fund_metrics §3.10）
_DRAWDOWN_WINDOW_DAYS = 1095  # 近 3 年
_DRAWDOWN_MIN_SAMPLES = 20
_DRAWDOWN_WINDOW_LABEL = '近3年'

# 波动率窗口：近 1 年（年化口径，trailing 252 交易日）
_VOL_WINDOW_DAYS = 365

# 区间收益 / 回撤 / 波动率都要求至少 2 个有效点，否则无法构成「变化」
_MIN_POINTS = 2


def _is_money_fund(fund) -> bool:
    """货基判定：基金小类名含「货币」（如「货币型」）。无 is_money_fund 标志，靠类型名。"""
    fund_type = getattr(fund, 'fund_type', None)
    name = getattr(fund_type, 'name', None) or ''
    return '货币' in name


def _money_fund_performance(db: Session, fund_code: str) -> Dict[str, Any]:
    """货基：万份收益 + 七日年化（money_fund_daily_worth 最新一期）。"""
    from app.domains.funds.models import MoneyFundDailyWorth

    row = (
        db.query(MoneyFundDailyWorth)
        .filter(MoneyFundDailyWorth.fund_code == fund_code)
        .order_by(MoneyFundDailyWorth.date.desc())
        .first()
    )
    if row is None:
        return {
            'fund_kind': 'money',
            'applicable': True,
            'basis': 'insufficient',
            'annual_return_7d': None,
            'nav_per_10k': None,
            'as_of': None,
            'source': FUND_NAV_SOURCE_LABEL,
        }
    return {
        'fund_kind': 'money',
        'applicable': True,
        'basis': 'money_fund',
        'annual_return_7d': round(float(row.annual_return_7d), 4) if row.annual_return_7d is not None else None,
        'nav_per_10k': float(row.nav_per_10k) if row.nav_per_10k is not None else None,
        'as_of': row.date.isoformat() if row.date else None,
        'source': FUND_NAV_SOURCE_LABEL,
    }


def _interval_return(points: List[Tuple[date, float]], start_date: date) -> Optional[float]:
    """区间收益率（%）。起点取 ≥ start_date 的首个点，终点取序列末点（最新净值）。

    start_date 早于全部数据点时退化为首点（避免 None）；任一点净值缺失 / ≤0 返回 None。
    """
    if len(points) < _MIN_POINTS:
        return None
    start_idx = next((i for i, (d, _) in enumerate(points) if d >= start_date), 0)
    nav_start = points[start_idx][1]
    nav_end = points[-1][1]
    if nav_start is None or nav_end is None or nav_start <= 0:
        return None
    return round((nav_end / nav_start - 1) * 100, 2)


def _annualized_volatility(points: List[Tuple[date, float]], since: date) -> Optional[float]:
    """近 1 年年化波动率（%）。基于日收益标准差 × sqrt(252)。"""
    window = [(d, n) for d, n in points if d >= since and n is not None and n > 0]
    if len(window) < 3:
        return None
    rets: List[float] = []
    for i in range(1, len(window)):
        p0, p1 = window[i - 1][1], window[i][1]
        if p0 > 0:
            rets.append((p1 - p0) / p0)
    if len(rets) < 2:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round((var**0.5) * (252**0.5) * 100, 2)


def _risk_metrics_payload(result: RiskMetricsResult) -> Dict[str, Any]:
    """把 ``RiskMetricsResult`` 摊平成 API 字段（口径元数据一并下发）。

    **口径必须随值下发**（#167 拍板项）：不告诉用户 rf 取了多少、窗口是哪一段、
    样本几个点，数字不可复核——他换个 rf 就对不上账。
    """
    return {
        'current_drawdown': result.current_drawdown,
        'current_drawdown_peak_date': result.drawdown_peak_date.isoformat() if result.drawdown_peak_date else None,
        'current_drawdown_days': result.drawdown_days,
        'max_drawdown_peak_date': (
            result.max_drawdown_peak_date.isoformat() if result.max_drawdown_peak_date else None
        ),
        'max_drawdown_trough_date': (
            result.max_drawdown_trough_date.isoformat() if result.max_drawdown_trough_date else None
        ),
        'annual_return': result.annual_return,
        'annual_volatility': result.annual_volatility,
        'sharpe': result.sharpe,
        'sortino': result.sortino,
        'calmar': result.calmar,
        'ulcer_index': result.ulcer_index,
        'upi': result.upi,
        'return_drawdown_ratio': result.return_drawdown_ratio,
        'win_rate': result.win_rate,
        'win_rate_period': result.win_rate_period,
        'win_rate_overlap': result.overlap,
        'risk_window': result.window_label,
        'risk_sample_points': result.sample_points,
        'risk_free_rate': RISK_FREE_RATE_ANNUAL,
        'risk_basis': result.basis,
        'risk_caveats': result.caveats,
    }


def _load_risk_metrics(db: Session, fund_code: str, points: List[Tuple[date, float]]) -> Dict[str, Any]:
    """风险指标：**优先读每日快照，缺失/口径过期则现算回退**。

    为什么优先读快照而不是每次都现算：详情页已经读过一遍 3 年日净值，再跑一遍同一套
    计算是重复劳动；而列表页按指标横向筛**只能**靠物化的表（逐只现算撑不起全市场排序）。
    两条路径共用 ``compute_risk_metrics`` 这一个纯函数，故数字逐位相等。

    回退的触发条件有三个，都要覆盖：
    1. 快照表里还没有这只基金（新基金 / job 还没跑到它）；
    2. 快照的 ``caliber_version`` 是旧的（口径改过，旧数字与新口径不可比）；
    3. 快照的 ``as_of`` 落后于当前净值序列的最新日（净值在快照之后又更新了）。
    """
    from app.domains.funds.models import FundRiskMetrics
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    latest_nav_date = points[-1][0] if points else None
    snap = (
        db.query(FundRiskMetrics)
        .filter(FundRiskMetrics.fund_code == fund_code)
        .order_by(FundRiskMetrics.as_of.desc())
        .first()
    )
    fresh = (
        snap is not None
        and snap.caliber_version == CALIBER_VERSION
        and latest_nav_date is not None
        and snap.as_of == latest_nav_date
    )
    if fresh:
        # 快照与现算的字段集合必须一致 —— 否则前端在两条路径下看到不同的键。
        # 这里用同一份 payload 组装函数，只把来源替换成快照值。
        payload = _risk_metrics_payload(
            compute_risk_metrics([], window=WINDOW_3Y, window_label=snap.window_label)
        )  # 仅取「空骨架」的键集合，随后逐键覆盖（避免两处维护字段名单）
        payload.update(
            {
                'current_drawdown': float(snap.current_drawdown) if snap.current_drawdown is not None else None,
                'current_drawdown_peak_date': snap.drawdown_peak_date.isoformat() if snap.drawdown_peak_date else None,
                'current_drawdown_days': snap.drawdown_days,
                'max_drawdown_peak_date': (
                    snap.max_drawdown_peak_date.isoformat() if snap.max_drawdown_peak_date else None
                ),
                'max_drawdown_trough_date': (
                    snap.max_drawdown_trough_date.isoformat() if snap.max_drawdown_trough_date else None
                ),
                'annual_return': float(snap.annual_return) if snap.annual_return is not None else None,
                'annual_volatility': float(snap.annual_volatility) if snap.annual_volatility is not None else None,
                'sharpe': float(snap.sharpe) if snap.sharpe is not None else None,
                'sortino': float(snap.sortino) if snap.sortino is not None else None,
                'calmar': float(snap.calmar) if snap.calmar is not None else None,
                'ulcer_index': float(snap.ulcer_index) if snap.ulcer_index is not None else None,
                'upi': float(snap.upi) if snap.upi is not None else None,
                'return_drawdown_ratio': (
                    float(snap.return_drawdown_ratio) if snap.return_drawdown_ratio is not None else None
                ),
                'win_rate': float(snap.win_rate) if snap.win_rate is not None else None,
                'win_rate_period': snap.win_rate_period,
                'risk_window': snap.window_label,
                'risk_sample_points': snap.sample_points,
                'risk_basis': snap.basis,
                'risk_source': 'snapshot',
            }
        )
        payload['max_drawdown'] = float(snap.max_drawdown) if snap.max_drawdown is not None else None
        return payload

    result = compute_risk_metrics(points, window=WINDOW_3Y, window_label='近3年')
    payload = _risk_metrics_payload(result)
    payload['max_drawdown'] = result.max_drawdown
    payload['risk_source'] = 'computed'
    return payload


def _open_fund_performance(db: Session, fund_code: str, today: date) -> Dict[str, Any]:
    """场外基金：区间收益 + 最大回撤 + 年化波动率（同源 acc_nav）。"""
    from app.domains.funds.models import DailyWorth

    rows = (
        db.query(DailyWorth)
        .filter(DailyWorth.fund_code == fund_code, DailyWorth.acc_nav.isnot(None))
        .order_by(DailyWorth.date)
        .all()
    )
    # 复用 fund_metrics.load_nav_points：优先 acc_nav、缺失回退 unit_nav（与自选域同源）
    points: List[Tuple[date, float]] = []
    for d, nav in load_nav_points(rows):
        if nav is not None and float(nav) > 0:
            points.append((d, float(nav)))

    if len(points) < _MIN_POINTS:
        return {
            'fund_kind': 'fund',
            'applicable': False,
            'basis': 'insufficient',
            'intervals': [],
            'max_drawdown': None,
            'max_drawdown_basis': 'insufficient',
            'volatility_1y': None,
            'as_of': points[-1][0].isoformat() if points else None,
            'source': FUND_NAV_SOURCE_LABEL,
        }

    # 区间收益切面
    intervals = []
    for key, label, days in _PERIODS:
        if key == 'ytd':
            start = date(today.year, 1, 1)
        elif key == 'since':
            start = points[0][0]
        else:
            start = today - timedelta(days=days)
        intervals.append({'key': key, 'label': label, 'value': _interval_return(points, start)})

    # 最大回撤：近 3 年固定窗口（与自选域一致）
    dd_since = today - timedelta(days=_DRAWDOWN_WINDOW_DAYS)
    dd_points = [(d, n) for d, n in points if d >= dd_since]
    dd = compute_max_drawdown(dd_points) if len(dd_points) >= _MIN_POINTS else None
    if dd is None or dd.sample_size < _DRAWDOWN_MIN_SAMPLES:
        max_dd = None
        max_dd_basis = 'insufficient'
    else:
        max_dd = round(dd.max_drawdown, 2)
        max_dd_basis = 'fixed_3y'

    # 年化波动率：近 1 年
    vol = _annualized_volatility(points, today - timedelta(days=_VOL_WINDOW_DAYS))

    risk = _load_risk_metrics(db, fund_code, points)

    out = {
        'fund_kind': 'fund',
        'applicable': True,
        'basis': 'acc_nav',
        # acc_nav 是「分红不再投」口径的近似复权序列，非严格分红再投复权净值（fund_metrics §9-11）
        'acc_nav_caveat': '累计净值口径（分红不再投近似复权），非严格分红再投复权净值',
        'intervals': intervals,
        'max_drawdown': max_dd,
        'max_drawdown_basis': max_dd_basis,
        'max_drawdown_window': _DRAWDOWN_WINDOW_LABEL,
        'max_drawdown_as_of': dd.as_of.isoformat() if dd else None,
        'volatility_1y': vol,
        'as_of': points[-1][0].isoformat(),
        'source': FUND_NAV_SOURCE_LABEL,
    }
    # 风险指标块（#167）：本轮回撤 / 最大回撤 / 夏普族 + 口径元数据。
    # 其中 max_drawdown 是**快照优先**的同一字段（老字段不动，语义不变：窗口内最深回撤）。
    out.update(risk)
    return out


def build_fund_performance(db: Session, fund_code: str) -> Optional[Dict[str, Any]]:
    """构建单只基金的业绩与风险数据。

    Returns:
        字典；**基金不存在时返回 None**（调用方转 404）。
        货基走 ``_money_fund_performance``；场外基金走净值算法。
    """
    from app.domains.funds.models import Fund

    code = (fund_code or '').strip()
    if not code:
        raise ValueError('缺少 fund_code')

    fund = db.query(Fund).filter(Fund.fund_code == code).first()
    if fund is None:
        return None

    if _is_money_fund(fund):
        return _money_fund_performance(db, code)
    return _open_fund_performance(db, code, today_shanghai())
