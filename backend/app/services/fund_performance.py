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

#167 追加之二：**基准相对指标 + 同类内分位**
--------------------------------------------
用户原话：「债基跟股基该参照的东西不一样，用同一个标准衡量它们的夏普率是不是有问题」。

这句话里那个「对的一半」是**基准**：债基不该拿沪深300 比。落地分两块：

- **基准相对**（超额收益 / 信息比率 / 上行下行捕获率）：基准指数由 ``fund_benchmark.resolve``
  按 ``fund_type.name`` 映射（**不解析** ``Fund.benchmark`` 那句自然语言），序列从
  ``index_daily`` 取。映射命不中（货基 / 指数型 / QDII）**不给基准**，不拿宽基顶替。
- **同类内分位**：绝对值跨类别不可比 ⇒ 补「在同类里排前 X%」。计算在
  ``fund_risk_ranking.peer_percentiles_for``，分母只含当前口径版本、`basis='acc_nav'` 的行。

两者都只做读取，无新抓取（D21）。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.data_sources import FUND_NAV_SOURCE_LABEL
from app.core.time_utils import today_shanghai
from app.services.fund_benchmark import BENCHMARK_LABELS, load_index_points
from app.services.fund_benchmark import resolve as resolve_benchmark
from app.services.fund_metrics import compute_max_drawdown, load_nav_points
from app.services.fund_nav_on_demand import maybe_trigger_nav_backfill
from app.services.fund_risk_metrics import (
    RISK_FREE_RATE_ANNUAL,
    WINDOW_3Y,
    RiskMetricsResult,
    benchmark_diagnostics,
    compute_risk_metrics,
    shape_gain,
    shape_gain2,
)
from app.services.money_fund_yield import CALIBER_NOTE, WINDOW_DAYS

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

# #2120 P0-2：本模块对外声明的最长档位跨度（自然日）。序列起点晚于
# 「今天 − 该跨度」即说明 5y / since 档位拿不到数据，触发按需回补。
# 从 _PERIODS 派生而非写死 1825：档位表调整时本值自动跟随，不会漂移。
_LONGEST_PERIOD_DAYS = max(days for _key, _label, days in _PERIODS if days is not None)


def _is_money_fund(fund) -> bool:
    """货基判定：基金小类名含「货币」（如「货币型」）。无 is_money_fund 标志，靠类型名。"""
    fund_type = getattr(fund, 'fund_type', None)
    name = getattr(fund_type, 'name', None) or ''
    return '货币' in name


def _money_fund_samples(db: Session, fund_code: str, as_of: date) -> int:
    """该行往前 7 个自然日窗口内**已发布**的万份收益样本数（#2121 口径元数据）。

    只数行、不重算：七日年化已随行落库（`money_fund_yield`），这里只是把「这个值
    由几个样本摊出来」这个元数据补上，让前端脚注能交代清楚。`nav_per_10k` 为空的
    日子不算样本（与计算口径一致）。
    """
    from app.domains.funds.models import MoneyFundDailyWorth

    start = as_of - timedelta(days=WINDOW_DAYS - 1)
    return (
        db.query(MoneyFundDailyWorth.date)
        .filter(
            MoneyFundDailyWorth.fund_code == fund_code,
            MoneyFundDailyWorth.date >= start,
            MoneyFundDailyWorth.date <= as_of,
            MoneyFundDailyWorth.nav_per_10k.isnot(None),
        )
        .count()
    )


def _money_fund_performance(db: Session, fund_code: str) -> Dict[str, Any]:
    """货基：万份收益 + 七日年化（money_fund_daily_worth 最新一期）。

    除数值外还返回**口径元数据**（#2121 验收项）：`window_days`（7 个**自然日**，
    不是 7 个观测——观测口径会让国庆这类长假把窗口拉到 13 天）、`samples`（窗口内
    实际有几个已发布样本）、`caliber_note`（给前端脚注用的人话版）。没有这些，
    用户看到的「七日年化」是个无法自证的数字。
    """
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
            'window_days': WINDOW_DAYS,
            'samples': 0,
            'caliber_note': CALIBER_NOTE,
        }
    as_of = row.date
    return {
        'fund_kind': 'money',
        'applicable': True,
        'basis': 'money_fund',
        'annual_return_7d': round(float(row.annual_return_7d), 4) if row.annual_return_7d is not None else None,
        'nav_per_10k': float(row.nav_per_10k) if row.nav_per_10k is not None else None,
        'as_of': as_of.isoformat() if as_of else None,
        'source': FUND_NAV_SOURCE_LABEL,
        # 口径元数据：window_days=7 个自然日；samples 可能 < 7（节假日缺发布日）
        'window_days': WINDOW_DAYS,
        'samples': _money_fund_samples(db, fund_code, as_of) if as_of else 0,
        'caliber_note': CALIBER_NOTE,
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
        # 基准相对指标（#167）：「拿什么比」在 `_benchmark_payload`、「比出什么」在
        # `result.benchmark`，两者由 `_merge_benchmark` 合成一块。缺失时给 None，
        # 由调用方按「无基准 / 基准序列缺」两种情形分别下发。
        'benchmark': result.benchmark,
    }


def _merge_benchmark(mapped: Optional[Dict[str, Any]], relative: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """合并「基准映射结果」与「基准相对指标」成一个基准块。

    `mapped` 回答「拿什么比、凭什么」（`code` / `name` / `matched_by` / `available`），
    `relative` 回答「比出了什么」（超额 / 跟踪误差 / 信息比率 / 捕获率）。

    两者缺一不可，故合并而非覆盖。`mapped['available'] is False`（选了基准但序列缺）
    时只下发映射结果——这是**有意义的**状态（用户知道「本想拿它比」），比留白好。

    `points` 是内部用的原始序列，**不下发**：前端不该自己算，500+ 个点也不该进响应体。
    """
    if mapped is None:
        return None
    out = {k: v for k, v in mapped.items() if k != 'points'}
    if out.get('available') and relative:
        # `relative` 里同名的键（basis / sample_points）以它为准：它是真算过的那个口径
        for key, value in relative.items():
            if key != 'basis' or key not in out:
                out[key] = value
        out['basis'] = relative.get('basis', out.get('basis'))
    return out


def _peer_percentiles(db: Session, fund_code: str) -> Optional[Dict[str, float]]:
    """同类内分位（该基金各指标在同类中的百分位，越大越好）。

    只是把 ``fund_risk_ranking.peer_percentiles_for`` 的异常兜住：分位是**锦上添花**
    的信息（主指标已经给出），它的失败不该让整个业绩块 500——详情页会因为一个
    「排序参考」而整块打不开，那是本末倒置。

    返回 ``None`` 表示本基金不在任何同类样本里（快照还没有它 / 同类样本不足）。
    """
    try:
        from app.services.fund_risk_ranking import peer_percentiles_for

        return peer_percentiles_for(db, [fund_code]).get(fund_code) or None
    except Exception as e:  # noqa: BLE001
        logger.warning(f'同类分位计算失败 {fund_code}: {e}')
        return None


def _benchmark_payload(db: Session, fund) -> Optional[Dict[str, Any]]:
    """基准相对指标块（按 `fund_type` 映射基准，序列取自 `index_daily`）。

    返回 ``None`` 表示**本基金不适用基准**（货基 / 指数型 / QDII，或类型缺失）。
    调用方据此下发「暂无基准」——**不得**退回沪深300 顶替：拿沪深300 去比债基，
    超额收益会是「负多少」这个没有意义的数，而用户读不出「它其实没被比过」。

    映射成立但序列取不到（源侧未收录 / 尚未跑同步）时，下发 ``available=False``
    的块并带 ``reason``，前端显式说明「基准已选定、但数据暂缺」——
    这与「没给基准」（整个块为 ``None``）是两种状态，不该长得一样。
    """
    choice = resolve_benchmark(
        getattr(getattr(fund, 'fund_type', None), 'name', None),
        getattr(getattr(fund, 'variety', None), 'name', None),
    )
    if choice is None:
        return None

    points = load_index_points(db, choice.code, limit=int(WINDOW_3Y * 1.1))
    if not points:
        return {
            'code': choice.code,
            'name': BENCHMARK_LABELS.get(choice.code, choice.name),
            'matched_by': choice.matched_by,
            'available': False,
            'reason': '该基准指数无日线数据（尚未同步），不以上述以外的指数顶替',
        }

    return {
        'code': choice.code,
        'name': BENCHMARK_LABELS.get(choice.code, choice.name),
        'matched_by': choice.matched_by,
        'available': True,
        'points': points,  # 交给 compute_risk_metrics 做「共同日对齐」
    }


def _load_risk_metrics(
    db: Session,
    fund_code: str,
    points: List[Tuple[date, float]],
    *,
    benchmark_points: Optional[List[Tuple[date, float]]] = None,
) -> Dict[str, Any]:
    """风险指标：**优先读每日快照，缺失/口径过期则现算回退**。

    为什么优先读快照而不是每次都现算：详情页已经读过一遍 3 年日净值，再跑一遍同一套
    计算是重复劳动；而列表页按指标横向筛**只能**靠物化的表（逐只现算撑不起全市场排序）。
    两条路径共用 ``compute_risk_metrics`` 这一个纯函数，故数字逐位相等。

    回退的触发条件有三个，都要覆盖：
    1. 快照表里还没有这只基金（新基金 / job 还没跑到它）；
    2. 快照的 ``caliber_version`` 是旧的（口径改过，旧数字与新口径不可比）；
    3. 快照的 ``as_of`` 落后于当前净值序列的最新日（净值在快照之后又更新了）。

    ``benchmark_points`` 只影响基准相对块（超额 / 信息比率 / 捕获率），**两条路径都现场算**：
    它不进快照表（基准映射会变、基准序列每天增长，物化它等于把「改映射后旧快照仍生效」
    这个坑引进来）。故基准块是「永远现算」，而它是**纯函数 + 共同日对齐**，代价是一次交集。
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
        # 基准块**不走快照**：映射与基准序列都会变，物化它会让「改了映射但快照没重算」
        # 变成一个静默的错值。它本身很便宜（一次去交集），两条路径都现算。
        payload['benchmark'] = (
            benchmark_diagnostics(points, benchmark_points, window=WINDOW_3Y) if benchmark_points else None
        )
        return payload

    result = compute_risk_metrics(
        points,
        window=WINDOW_3Y,
        window_label='近3年',
        benchmark_points=benchmark_points,
    )
    payload = _risk_metrics_payload(result)
    payload['max_drawdown'] = result.max_drawdown
    payload['risk_source'] = 'computed'
    return payload


def _open_fund_performance(db: Session, fund, code: str, today: date) -> Dict[str, Any]:
    """场外基金：区间收益 + 最大回撤 + 年化波动率 + 风险指标 + 基准相对（同源 acc_nav）。

    ``fund`` 传实体而非仅 code：基准要按 ``fund.fund_type.name`` 映射，多查一次
    ``Fund``（调用方刚查过）是白费一次查询。fund_code 仍单独传入——不必让本函数
    依赖实体的某个属性，调用方手里本来就有这个字符串（也少一处能对不上的地方）。
    """
    fund_code = code
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

    # #2120 P0-2：冷集长曲线按需取。本函数对外声明了 1y/2y/3y/5y/since 档位（见
    # _PERIODS），若本地序列起点晚于**最长档位**起点，说明这些档位根本拿不到数据 ——
    # 按 fund-nav-retention.md §1「同一只基金、同一接口、不同时间返回不同档位 =
    # 对外契约不稳定」的口径，此时后台单只回补全历史。
    # 本请求不等待；缺的档位照旧返回 None，由前端渲染「—」（诚实降级，不编造）。
    # 放在 `len(points) < _MIN_POINTS` 早退**之前**：完全没有数据才是最该回补的情况。
    maybe_trigger_nav_backfill(fund_code, points, today - timedelta(days=_LONGEST_PERIOD_DAYS))

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
            # 固定契约：样本不足时也保留 key（前端据「有 key 但 null」降级「—」，
            # 与 shape_gain2 字段在正常路径下的形态一致——字段直接缺席时前端只能猜）
            'shape_gain': None,
            'shape_gain2': None,
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

    # 基准（#167）：按 fund_type 映射，不解析 Fund.benchmark 的自然语言串。
    bench = _benchmark_payload(db, fund)
    bench_points = bench.get('points') if bench and bench.get('available') else None

    risk = _load_risk_metrics(db, fund_code, points, benchmark_points=bench_points)

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
    # 基准块（#167）：**映射结果**（哪只指数、凭什么选中）来自 `_benchmark_payload`，
    # **相对指标**（超额 / 信息比率 / 捕获率）来自 `risk['benchmark']`（现算）。
    # 两块必须合并成一个对象而不是后者覆盖前者——它们各带一半信息：
    # 只留映射结果，前端拿不到数字；只留相对指标，用户不知道拿什么比的。
    out['benchmark'] = _merge_benchmark(bench, out.pop('benchmark', None))
    # 同类内分位（#167）：绝对值跨类别不可比，分位可读。
    out['peer_percentiles'] = _peer_percentiles(db, fund_code)
    # 拟涨幅 / 拟涨幅2（#167 收尾）：
    #   原版 = 四期滚动涨幅经 K 归一化到年频后的加权几何平均；
    #   2 版 = 四段互不重叠区间收益的加权连乘。
    # 历史不足一年 ⇒ 两者皆 None（不拿「成立以来」凑，理由见各自 docstring）。
    out['shape_gain'] = shape_gain(points, as_of=today)
    out['shape_gain2'] = shape_gain2(points, as_of=today)
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
    return _open_fund_performance(db, fund, code, today_shanghai())
