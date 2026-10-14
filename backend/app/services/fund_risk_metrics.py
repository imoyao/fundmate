# -*- coding: utf-8 -*-
"""基金风险收益指标（#167 · 调研卡 P0 落地的纯计算骨架）。

一次输入「基金净值序列（+ 可选基准序列）」，输出买方视角的风险收益指标：
最大回撤 / 年化波动 / 年化收益 / 夏普 / 索提诺 / 卡玛 / 溃疡指数 UI / UPI / 波回比 /
胜率 / 上行下行捕获率，以及每个指标的口径元数据。

**只做纯计算**：输入序列，输出数字与口径；取数（窗口、数据源、基准选择）由调用方决定
（沿用 ``fund_metrics.py`` 的同一条分工）。计算全部在内存中完成、**不落库**，符合
``data-strategy.md`` D21「按需算、禁止全量预计算堆砌」。

口径依据与待拍板结论（源 CNB #167，2026-10-14 收敛）：
- 默认窗口**近 3 年**（主）—— 年化夏普的估计误差 ≈ sqrt((1+S²/2)/T)，近 1 年只有 12 个月频
  样本、能分辨的真本事上限 ≈2.2，近 1 年榜单本质是「挑波动最顺的那个」（卡面实测：UPI 前 20
  平均收益 230%，即「按收益排序的化身」）。近 5 年作副显。
- rf 取**常量**（见 ``RISK_FREE_RATE_ANNUAL``）：同一批基金同减一个数**不改变排序**，
  只改变「及格线」；动态取国债 = 新数据源（撞 #1403 限流同族），收益与成本不成比例。
  **rf 必须随值下发**，否则夏普不可复核。
- **跨类别不可直接比绝对值**（债基波动小、夏普系统性偏高）⇒ 夏普只在**同类内**排序；
  需要跨类读时看「同类分位」，不是绝对值。
- 夏普把**上涨也算成风险**，对买方是错的 ⇒ 本模块以**只罚下行**的家族（UI/UPI/卡玛/
  索提诺/波回比）为主，夏普为参照。
- 胜率同时给**周期（日/周/月）**与**窗口**两个正交轴，默认拿月频近 3 年；滚动窗口**重叠**，
  是「持有体验」而非概率，须标 ``overlap``。
- **最大回撤 ≠ 本轮回撤**（#167）：「最大回撤」是窗口内**历史上最深**的那次；「本轮回撤」
  是**当前所处回撤区间**（最近一次新高 → 最新一日）。前者回答「最疼过多少」，后者回答
  「现在疼不疼」。两个都要看——只给最大值会把「已经爬出坑」和「还在坑底」显示成一样。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.fund_metrics import compute_max_drawdown

# ── 常量与口径 ────────────────────────────────────────────────────────────────

# 交易日/年：与 fund_performance._annualized_volatility 同源（252），避免两处数字打架。
TRADING_DAYS_PER_YEAR = 252

# 无风险利率（年化）。取「近年一年期国债收益率中枢」的常量近似。
# 讲究：① 它只决定夏普/UPI 的「及格线」，同窗口内所有基金同减一个数 ⇒ **不改变排序**；
#       ② 动态取 10 年国债会引入新数据源（撞 #1403 同族限流），而排序收益为零；
#       ③ 必须随值下发（RISK_FREE_RATE_BASIS），否则用户换一个 rf 就对不上账。
RISK_FREE_RATE_ANNUAL = 0.015
RISK_FREE_RATE_BASIS = '常量近似（近年一年期国债收益率中枢），非动态曲线；同窗口内不改变排序'

# 窗口（交易日）。近 3 年 ≈ 3×252，近 5 年 ≈ 5×252。
WINDOW_3Y = 3 * TRADING_DAYS_PER_YEAR
WINDOW_5Y = 5 * TRADING_DAYS_PER_YEAR

# 胜率周期 → 每期交易日数（重采样用）。
WIN_RATE_PERIODS: Dict[str, int] = {'day': 1, 'week': 5, 'month': 21}

# 单日跳变阈值（%）：超过则判该日净值序列受大额赎回/份额折算污染。
# acc_nav 与参考源同为「分红不再投近似复权」，同样会被折算污染——这是我们能做得比参考源好的地方。
JUMP_THRESHOLD_PCT = 15.0

# 最小样本：低于此值不出值（诚实降级，不缩窗口凑数）。
_MIN_RETURNS = 2


# ── 结果结构 ──────────────────────────────────────────────────────────────────


@dataclass
class DrawdownState:
    """本轮回撤（当前所处回撤区间）的结果与其口径元数据。"""

    current_drawdown: float  # 负数%；0.0 = 最新一日即新高
    peak_date: date  # 本轮高点日（最近一次创新高）
    as_of: date  # 序列最后一日（回撤计算到这天）
    days: int  # 自高点起的自然日数（用户体感用日历，不用交易日数）


@dataclass
class RiskMetricsResult:
    """风险指标计算结果。字段为 ``None`` 表示样本不足（前端降级为「—」，禁止编造）。"""

    window_label: str
    sample_points: int  # 参与计算的净值点数
    as_of: Optional[date]  # 序列最后一个净值日
    annual_return: Optional[float]  # 年化收益（%）
    annual_volatility: Optional[float]  # 年化波动率（%）
    max_drawdown: Optional[float]  # 最大回撤（负数%，与既有字段同号）
    max_drawdown_peak_date: Optional[date]  # 最大回撤的高点日
    max_drawdown_trough_date: Optional[date]  # 最大回撤的低点日
    current_drawdown: Optional[float]  # 本轮回撤（负数%，0.0 = 最新一日即新高）
    drawdown_peak_date: Optional[date]  # 本轮回撤起点（最近一次新高日）
    drawdown_days: Optional[int]  # 本轮自高点起熬过的自然日数
    sharpe: Optional[float]
    sortino: Optional[float]
    calmar: Optional[float]
    ulcer_index: Optional[float]  # UI（%）
    upi: Optional[float]  # 年化收益 / UI
    upi_standard: Optional[float]  # (年化收益 − rf) / UI（标准式，参考方为简化式）
    return_drawdown_ratio: Optional[float]  # 波回比 = 年化收益 /(波动率 × |最大回撤|/100)
    win_rate: Optional[float]  # 胜率（%，给定周期）
    win_rate_period: str  # day / week / month
    overlap: bool  # 胜率是否基于重叠滚动窗口（是 → 体验指标，非概率）
    benchmark: Optional[Dict[str, Any]] = None  # 基准相对指标（未传基准时为 None）
    basis: str = 'acc_nav'
    caveats: List[str] = field(default_factory=list)


# ── 基础工具 ──────────────────────────────────────────────────────────────────


def _clean(points: Sequence[Tuple[date, Optional[float]]]) -> List[Tuple[date, float]]:
    """剔除无效点（None / <=0），按日期升序，并去掉重复日（保留后者）。"""
    valid = [(d, float(v)) for d, v in points if v is not None and float(v) > 0]
    valid.sort(key=lambda x: x[0])
    dedup: List[Tuple[date, float]] = []
    for d, v in valid:
        if dedup and dedup[-1][0] == d:
            dedup[-1] = (d, v)
        else:
            dedup.append((d, v))
    return dedup


def _daily_returns(series: Sequence[Tuple[date, float]]) -> List[float]:
    """日简单收益率序列（小数，非百分数）。"""
    if len(series) < 2:
        return []
    return [(series[i][1] - series[i - 1][1]) / series[i - 1][1] for i in range(1, len(series))]


def _mean(xs: Sequence[float]) -> Optional[float]:
    return sum(xs) / len(xs) if xs else None


def _std(xs: Sequence[float], ddof: int = 1) -> Optional[float]:
    """样本标准差（ddof=1，与 fund_performance 一致）。"""
    if len(xs) <= ddof:
        return None
    m = sum(xs) / len(xs)
    var = sum((x - m) ** 2 for x in xs) / (len(xs) - ddof)
    return var**0.5


def _annualized_return(series: Sequence[Tuple[date, float]]) -> Optional[float]:
    """年化收益（%）：按**自然日跨度**折算，不用点数，避免点密度不均导致的偏差。

    基金不满一年时按实际天数外推——调用方须自行判断是否展示（样本不足应标 basis）。
    """
    if len(series) < 2:
        return None
    days = (series[-1][0] - series[0][0]).days
    if days <= 0:
        return None
    total = series[-1][1] / series[0][1]
    if total <= 0:
        return None
    years = days / 365.0
    if years <= 0:
        return None
    return round((total ** (1.0 / years) - 1) * 100, 4)


def detect_jumps(
    points: Sequence[Tuple[date, Optional[float]]], threshold_pct: float = JUMP_THRESHOLD_PCT
) -> List[date]:
    """检测净值单日跳变（> threshold_pct%），返回命中日期。

    用途：大额赎回 / 份额折算会污染「分红不再投近似复权」的 acc_nav，
    命中即应由调用方标 ``basis=distorted`` 并把该基金**剔除出横向排序**。
    仅报告，不改序列——是否剔除是调用方的策略。
    """
    series = _clean(points)
    hits: List[date] = []
    for i in range(1, len(series)):
        prev, cur = series[i - 1][1], series[i][1]
        if prev <= 0:
            continue
        if abs((cur - prev) / prev) * 100 > threshold_pct:
            hits.append(series[i][0])
    return hits


def ulcer_index(points: Sequence[Tuple[date, Optional[float]]], window: int = WINDOW_3Y) -> Optional[float]:
    """溃疡指数 UI（%）：sqrt( 平均(DD_t²) )，DD_t 为相对**历史高点**的回撤幅度（%）。

    与最大回撤的差别：最大回撤只看最深那一次，UI 看**整段煎熬**（每个交易日都在计分）。
    只罚下行、不罚上涨 —— 贴买方视角。
    """
    series = _clean(points)[-window:] if window else _clean(points)
    if len(series) < _MIN_RETURNS:
        return None
    peak = series[0][1]
    dds: List[float] = []
    for _d, nav in series:
        if nav > peak:
            peak = nav
        dds.append((nav - peak) / peak * 100.0)
    if not dds:
        return None
    return round((sum(x * x for x in dds) / len(dds)) ** 0.5, 4)


def drawdown_series(points: Sequence[Tuple[date, Optional[float]]]) -> List[Tuple[date, float]]:
    """逐日回撤序列（%），DD_t = (净值_t − 历史高点) / 历史高点，恒 ≤ 0。

    与 ``ulcer_index`` 共用同一条 peak 走法：创新高即重置 peak，DD 归 0；
    否则记录相对高点的跌幅。返回**已按日期升序**的完整序列（不截窗口），
    调用方自行截取——UI 要的是「整段煎熬」的形状，截窗口是调用方的口径决定。
    """
    series = _clean(points)
    if not series:
        return []
    peak = series[0][1]
    out: List[Tuple[date, float]] = []
    for d, nav in series:
        if nav > peak:
            peak = nav
        out.append((d, round((nav - peak) / peak * 100.0, 4)))
    return out


def current_drawdown(points: Sequence[Tuple[date, Optional[float]]]) -> Optional[DrawdownState]:
    """**本轮回撤**：当前所处回撤区间（最近一次净值新高 → 序列最后一日）。

    与 ``compute_max_drawdown`` 是**两个不同问题**，不可互相替代：

    | | 最大回撤 | 本轮回撤 |
    |---|---|---|
    | 问的是什么 | 窗口内**最疼过多少** | **现在疼不疼** |
    | 窗口内已爬出坑 | = 那次的深度 | = 0（已在/接近新高） |
    | 窗口内仍在坑里 | = 那次的深度 | 可能远小于它（还在半山腰） |

    只给最大回撤，会把「跌下去 30% 但已修复」与「跌 30% 且仍在水下」显示成同一个数——
    对「跌起来比涨得还猛、回不来」的筛选，后者才是要抓的形态（#167 用户原话）。

    实现：单次遍历维护 running peak 与**最近一次创新高的日期**；序列走完后，
    最新一日相对该高点的跌幅即本轮回撤。
        - 最新一日即新高 ⇒ ``current_drawdown = 0.0``（**不是 None**：在最高点是事实，
          不是缺数据。返回 None 会让前端显示成「—」，把一个明确结论藏起来）；
        - ``days`` 是自然日跨度，不是交易日数（用户体感的是日历，不是 K 线根数）。
    """
    series = _clean(points)
    if len(series) < 1:
        return None
    peak_date, peak_nav = series[0]
    for d, nav in series:
        if nav > peak_nav:
            peak_nav, peak_date = nav, d
    last_date, last_nav = series[-1]
    return DrawdownState(
        current_drawdown=round((last_nav - peak_nav) / peak_nav * 100.0, 4),
        peak_date=peak_date,
        as_of=last_date,
        days=(last_date - peak_date).days,
    )


def _downside_std(rets: Sequence[float], mar_daily: float = 0.0) -> Optional[float]:
    """下行标准差（只统计低于最小可接受收益 MAR 的偏离），年化。

    索提诺的分母：上涨波动不计入 —— 这是它与夏普的唯一差别，也是它更贴买方的原因。
    """
    if not rets:
        return None
    downs = [min(0.0, r - mar_daily) ** 2 for r in rets]
    # 分母用全部期数（标准式），退化情形下的口径在 docstring 已说明。
    var = sum(downs) / len(rets)
    return (var**0.5) * (TRADING_DAYS_PER_YEAR**0.5)


def _resample(series: Sequence[Tuple[date, float]], freq: int) -> List[Tuple[date, float]]:
    """按每 ``freq`` 个交易日抽样（取每个区间的最后一个点），用于胜率的多周期口径。"""
    if freq <= 1:
        return list(series)
    out: List[Tuple[date, float]] = []
    for i in range(freq - 1, len(series), freq):
        out.append(series[i])
    # 补上最后一点，保证「到现在」被计入
    if series and (not out or out[-1][0] != series[-1][0]):
        out.append(series[-1])
    return out


def win_rate(
    points: Sequence[Tuple[date, Optional[float]]],
    period: str = 'month',
    window: int = WINDOW_3Y,
) -> Optional[float]:
    """胜率（%）：给定**周期**上「该周期收益 > 0」的占比，在给定**窗口**上统计。

    ⚠️ 周期与窗口是两个正交的轴，不是「同一个指标的三种精度」：
    - 日频 55%：一天赚一天跌，累计仍可能巨幅回撤（且因序列长期向上而系统性偏高）；
    - 月频近 3 年 92%：三年持有基本必赚。
    只给日频 = 只回答「明天」，不回答「我拿三年会怎样」——后者才是用户的问题。

    ⚠️ 窗口内相邻区间**重叠**（滚动），样本不独立，**不能当概率读**；它表达的是
    「历史上任意时点开始持有 N 期的盈利体验」。调用方须把 ``overlap=True`` 写进口径元数据。
    """
    freq = WIN_RATE_PERIODS.get(period)
    if freq is None:
        raise ValueError(f'未知胜率周期：{period}（可选 {sorted(WIN_RATE_PERIODS)}）')
    series = _clean(points)
    if window:
        series = series[-window:]
    sampled = _resample(series, freq)
    rets = _daily_returns(sampled)
    if len(rets) < _MIN_RETURNS:
        return None
    ups = sum(1 for r in rets if r > 0)
    return round(ups / len(rets) * 100, 2)


# ── 拟涨幅2（#167 收尾 · 参考源自创指标）────────────────────────────────────────
#
# 口径与出处（源 CNB #167，原文「拟涨幅」的再次讨论，逐字核对）：
#
#   1 月 / 3 月 / 6 月 / 1 年这四个**滚动涨幅**彼此**重叠**（近1年区间包含了近6月），
#   直接加权等于把同一段行情数了多遍。故先把它们拆成四段**互不重叠**的收益：
#       p1 = r1                                  （近 1 月这一段）
#       p2 = (1+r2)/(1+r1) − 1                   （1~3 月这一段）
#       p3 = (1+r3)/(1+r2) − 1                   （3~6 月这一段）
#       p4 = (1+r4)/(1+r3) − 1                   （6~12 月这一段）
#   四段合起来正好是**一整年**，且不重不漏。
#   2. 按「越近权重越高」加权（远→近 0.1 / 0.2 / 0.3 / 0.4，和为 1）：
#       拟涨幅2 = (1+0.4·p1)(1+0.3·p2)(1+0.2·p3)(1+0.1·p4) − 1
#
#   ⚠️ 是**连乘**而非加权求和：乘法对应复利（先涨 50% 再跌 30% ≠ 净 20%），
#   且保证「四段全 0 → 结果 0」与「单调性」两条性质。
#
# **为什么只实现「拟涨幅2」而不做原版「拟涨幅」**：原版要 K 值把不同周期的涨幅
# 统一到年频，而**K 值的定义在可得的公开材料里查不到**（调研卡 §2/§6 均记为
# 「K 系数需定义」，原文《自创指标："拟涨幅"》抓取只得到登录墙 stub）。
# 按 data-strategy 的口径纪律，**不猜一个系数**——猜出来的 K 会让这个指标
# 看起来有数、实际不可复核。故原版仍留在「待拍板」清单里。

#: 拟涨幅2 的四段权重（远→近）。和为 1，改这里即改变口径，**必须同步更新
#: `SHAPE_GAIN2_BASIS`**，否则随值下发的口径说明会与实现脱节。
SHAPE_GAIN2_WEIGHTS: Tuple[float, ...] = (0.1, 0.2, 0.3, 0.4)

#: 四段的分界（自然日）。近 1 月 / 3 月 / 6 月 / 1 年，与参考站「滚动收益率」的
#: 20 / 60 / 120 / 250 交易日口径**不同**——此处按自然日定位起点，因为净值是
#: 按自然日发布的序列；交易日口径会在长假前后漂移，而本指标的价值在于跨基金可比。
SHAPE_GAIN2_SPANS: Tuple[int, ...] = (30, 90, 180, 365)

SHAPE_GAIN2_BASIS = (
    '四段互不重叠的区间收益加权连乘（权重远→近 '
    + '/'.join(f'{w}' for w in SHAPE_GAIN2_WEIGHTS)
    + '）；不含无风险利率，跨类别不可直接比'
)

#: 四段都要有足够样本，否则整指标不出值（诚实降级，不缩窗口凑数）。
_SHAPE_GAIN2_MIN_POINTS = 5


def shape_gain2(
    points: Sequence[Tuple[date, Optional[float]]],
    *,
    as_of: Optional[date] = None,
) -> Optional[Dict[str, Any]]:
    """拟涨幅2（%）：四个**互不重叠**区间收益的加权连乘（见上方口径块）。

    为什么要去重叠：近 1 月 / 3 月 / 6 月 / 1 年这四个滚动涨幅彼此包含，
    直接加权会把同一段行情数上多遍（近 1 月的行情在四个数里各出现一次）。

    Args:
        points: 升序 ``(日期, 净值)``；非法点（None / ≤0）由内部剔除。
        as_of: 计算基准日；默认取序列最后一点。**与 `fund_performance` 的现算路径
            共用同一业务日**，避免同页两处数字差一天。

    Returns:
        ``{'shape_gain2', 'segments', 'basis'}``；段样本不足时返回 ``None``
        （**不缩窗口凑数**——那样「成立 2 个月的基金」会得到一个看起来很正常的数）。
        `segments` 是四段的原始收益（%），随值下发供复核。
    """
    series = _clean(points)
    if as_of is not None:
        series = [(d, v) for d, v in series if d <= as_of]
    if len(series) < _SHAPE_GAIN2_MIN_POINTS:
        return None

    end_date, end_nav = series[-1]

    # 每个分界日取「≥ 该日的首个点」，与 fund_performance._interval_return 同一手法
    # （不插值、不就近取——净值只在发布日存在，插值出来的点是编的）。
    #
    # ⚠️ **序列起点晚于 target 时必须回 None**（不是「退化取首点」）：
    # 成立才 3 个月的基金，`_nav_at(365)` 若退化取首点，这段就变成了「成立以来」，
    # 而它还要和其它三段加权连乘 ⇒ 结果既不是「近一年」也不是「成立以来」，
    # 是个无意义却看着正常的数。这正是「历史不足一年 ⇒ 不出值」的判据所在。
    first_date = series[0][0]

    def _nav_at(days_back: int) -> Optional[float]:
        target = end_date - timedelta(days=days_back)
        if first_date > target:
            return None
        for d, v in series:
            if d >= target:
                return v
        return None

    # 四个分界日的净值。任一段取不到 ⇒ **整指标不出值**（不拿 0 / 不拿成立以来顶替）：
    # 近 1 年那段用「成立以来」凑的话，r4 与其它段的口径就不一致了，而四个数还要
    # 加权连乘——掺一个口径不同的数进去，结果既不是「近一年」也不是「成立以来」。
    navs: List[Optional[float]] = [_nav_at(s) for s in SHAPE_GAIN2_SPANS]
    if any(nav is None or nav <= 0 for nav in navs):
        return None

    # 滚动涨幅 r1..r4（%）
    rolling: List[float] = [(end_nav / nav - 1) * 100 for nav in navs]  # type: ignore[operator]

    # 去重叠：p1 = r1；p_i = (1+r_i)/(1+r_{i-1}) − 1
    prev = 0.0
    segments: List[float] = []
    for r in rolling:
        segments.append((1 + r / 100) / (1 + prev / 100) - 1)
        prev = r

    # 加权连乘。段序是「近 → 远」，权重表也按「近 → 远」给出（0.4 给最近的 p1）。
    weights = SHAPE_GAIN2_WEIGHTS[::-1]  # 权重表是「远→近」，此处按段序「近→远」对齐
    value = 1.0
    for seg, w in zip(segments, weights):
        value *= 1 + w * seg

    return {
        'shape_gain2': round((value - 1) * 100, 4),
        'segments': [round(s * 100, 4) for s in segments],
        'basis': SHAPE_GAIN2_BASIS,
    }


# ── 基准相对指标 ──────────────────────────────────────────────────────────────


def benchmark_diagnostics(
    fund_points: Sequence[Tuple[date, Optional[float]]],
    bench_points: Sequence[Tuple[date, Optional[float]]],
    window: int = WINDOW_3Y,
) -> Dict[str, Any]:
    """基准相对指标：超额收益 / 跟踪误差 / 信息比率 / 上行下行捕获率。

    用途正是「不同产品参照不同东西」——债基对债指数、股基对万得全A，而不是所有人对沪深300。
    两个序列按**共同交易日**对齐后计算（先取交集，避免错配导致假超额）。

    捕获率的定义（逐日算术口径，只在**基准同向**的交易日上取比值，非回归）：
    - 上行捕获 = Σ(基金日收益 | 基准涨) / Σ(基准日收益 | 基准涨) × 100；
    - 下行捕获 = 同上，取基准跌的那些交易日。
    上行 > 100 = 涨得比基准多（好）；下行 < 100 = 跌得比基准少（好）。
    用「和之比」而非「累计乘积」：后者会把基准为正的**离散**日连乘，等于假设那些日连续复利，
    口径不成立。逐日和之比与业界「涨跌捕获」的直觉一致且对样本量稳健。
    """
    fmap = dict(_clean(fund_points))
    bmap = dict(_clean(bench_points))
    common = sorted(set(fmap) & set(bmap))
    if window:
        common = common[-window:]
    if len(common) < _MIN_RETURNS + 1:
        return {'basis': 'insufficient', 'sample_points': len(common)}

    fser = [(d, fmap[d]) for d in common]
    bser = [(d, bmap[d]) for d in common]

    f_ret = _annualized_return(fser)
    b_ret = _annualized_return(bser)

    fr = _daily_returns(fser)
    br = _daily_returns(bser)
    diff = [a - b for a, b in zip(fr, br)]
    tracking_error = _std(diff)
    te_annual = round(tracking_error * (TRADING_DAYS_PER_YEAR**0.5) * 100, 4) if tracking_error else None

    # 信息比率：年化超额 / 年化跟踪误差
    info_ratio = None
    if f_ret is not None and b_ret is not None and te_annual:
        info_ratio = round((f_ret - b_ret) / te_annual, 4)

    # 上行/下行捕获：按基准涨跌分组，取「和之比」（见 docstring 的口径理由）
    up_f = sum(a for a, b in zip(fr, br) if b > 0)
    up_b = sum(b for _a, b in zip(fr, br) if b > 0)
    down_f = sum(a for a, b in zip(fr, br) if b < 0)
    down_b = sum(b for _a, b in zip(fr, br) if b < 0)

    up_capture = round(up_f / up_b * 100, 2) if abs(up_b) > 1e-9 else None
    down_capture = round(down_f / down_b * 100, 2) if abs(down_b) > 1e-9 else None

    return {
        'basis': 'ok',
        'sample_points': len(common),
        'as_of': common[-1].isoformat(),
        'fund_annual_return': f_ret,
        'bench_annual_return': b_ret,
        'excess_return': round(f_ret - b_ret, 4) if f_ret is not None and b_ret is not None else None,
        'tracking_error_annual': te_annual,
        'information_ratio': info_ratio,
        'upside_capture': up_capture,
        'downside_capture': down_capture,
    }


# ── 主入口 ────────────────────────────────────────────────────────────────────


def compute_risk_metrics(
    points: Sequence[Tuple[date, Optional[float]]],
    *,
    window: int = WINDOW_3Y,
    window_label: str = '近3年',
    win_rate_period: str = 'month',
    rf_annual: float = RISK_FREE_RATE_ANNUAL,
    benchmark_points: Optional[Sequence[Tuple[date, Optional[float]]]] = None,
) -> RiskMetricsResult:
    """从净值序列派生全套风险收益指标（纯计算，不落库）。

    Args:
        points: 升序 ``(日期, 净值)``；用 ``daily_worth.acc_nav``，缺失回退 ``unit_nav``。
        window: 使用的交易日数（默认近 3 年，见模块 docstring 的窗口论证）。
        window_label: 窗口中文标签，随值下发（口径透明）。
        win_rate_period: 胜率周期（day / week / month），默认月频。
        rf_annual: 无风险利率（年化小数），默认常量 1.5%。
        benchmark_points: 可选基准序列；给了才算超额/信息比率/捕获率。

    Returns:
        ``RiskMetricsResult``；样本不足的字段为 ``None``（诚实降级，不缩窗口凑数）。
    """
    series = _clean(points)
    if window:
        series = series[-window:]
    rets = _daily_returns(series)

    result = RiskMetricsResult(
        window_label=window_label,
        sample_points=len(series),
        as_of=series[-1][0] if series else None,
        annual_return=None,
        annual_volatility=None,
        max_drawdown=None,
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        current_drawdown=None,
        drawdown_peak_date=None,
        drawdown_days=None,
        sharpe=None,
        sortino=None,
        calmar=None,
        ulcer_index=None,
        upi=None,
        upi_standard=None,
        return_drawdown_ratio=None,
        win_rate=None,
        win_rate_period=win_rate_period,
        overlap=True,  # 滚动窗口必然重叠，见 win_rate docstring
    )
    result.caveats.append('acc_nav 为「分红不再投」近似复权口径，非严格分红再投；大额赎回/份额折算会污染序列')
    result.caveats.append(f'rf={rf_annual:.4f}（{RISK_FREE_RATE_BASIS}）')

    jumps = detect_jumps(series)
    if jumps:
        result.basis = 'distorted'
        result.caveats.append(
            f'检出单日跳变 {len(jumps)} 处（首个 {jumps[0].isoformat()}），疑似份额折算/大额赎回，建议剔除出横向排序'
        )

    if len(rets) < _MIN_RETURNS:
        return result

    ann_ret = _annualized_return(series)
    sd = _std(rets)
    # ⚠️ 必须 `is not None`：净值恒定时 sd == 0.0 是**合法值**（真无波动），
    # 写成 `if sd` 会把它误判成 None，进而丢掉「波动率 0」这个诚实结论。
    ann_vol = round(sd * (TRADING_DAYS_PER_YEAR**0.5) * 100, 4) if sd is not None else None

    dd = compute_max_drawdown(series) if len(series) >= 2 else None
    max_dd = round(dd.max_drawdown, 4) if dd else None

    ui = ulcer_index(series, window=0)  # series 已按窗口截断

    result.annual_return = ann_ret
    result.annual_volatility = ann_vol
    result.max_drawdown = max_dd
    result.ulcer_index = ui
    if dd is not None:
        result.max_drawdown_peak_date = dd.peak_date
        result.max_drawdown_trough_date = dd.trough_date

    # 本轮回撤（与上方的最大回撤是**两个问题**，见 current_drawdown docstring）：
    # 用「窗口截断后」的序列，与 max_drawdown 同窗口，避免两字数出不同区间。
    dd_state = current_drawdown(series)
    if dd_state is not None:
        result.current_drawdown = dd_state.current_drawdown
        result.drawdown_peak_date = dd_state.peak_date
        result.drawdown_days = dd_state.days

    rf_pct = rf_annual * 100
    # 夏普：分母为 0（无波动）时不出值，避免 inf。
    if ann_ret is not None and ann_vol:
        result.sharpe = round((ann_ret - rf_pct) / ann_vol, 4)

    dstd = _downside_std(rets, mar_daily=rf_annual / TRADING_DAYS_PER_YEAR)
    if ann_ret is not None and dstd:
        ann_dstd = dstd * 100
        result.sortino = round((ann_ret - rf_pct) / ann_dstd, 4) if ann_dstd else None

    if ann_ret is not None and max_dd:
        result.calmar = round(ann_ret / abs(max_dd), 4)

    if ui:
        if ann_ret is not None:
            result.upi = round(ann_ret / ui, 4)
            result.upi_standard = round((ann_ret - rf_pct) / ui, 4)

    if ann_ret is not None and ann_vol and max_dd:
        # 波回比 = 年化收益 /（年化波动率 × 最大回撤率）；两个分母都用百分数入算，
        # 量纲与参考方一致（结果是无量纲比值）。|max_dd| 取绝对值（它存的是负数）。
        denom = ann_vol * (abs(max_dd) / 100.0)
        if denom:
            result.return_drawdown_ratio = round(ann_ret / denom, 4)

    result.win_rate = win_rate(series, period=win_rate_period, window=0)

    if benchmark_points:
        result.benchmark = benchmark_diagnostics(points, benchmark_points, window=window)

    return result
