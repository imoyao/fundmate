# -*- coding: utf-8 -*-
"""基金「类别 → 基准指数」映射与基准序列取数（#167）。

## 为什么需要这张表

用户原话（CNB #167）：**「债基跟股基该参照的东西不一样，用同一个标准衡量它们的
夏普率是不是有问题」**——这句话是对的，而它说的不是 rf（rf 全市场一个常数，同减
不改排序），说的是**基准**：债基不该拿沪深300 当参照。

`Fund.benchmark` 是**自然语言串**（实测形如「沪深300指数收益率×95%+银行活期存款
利率(税后)×5%」「中债综合全价(总值)指数收益率」），**直接解析不可行**：

- 权重、复合基准（股+债混合）、银行活期这些成分混在一句话里；
- 只覆盖少数基金（填充率低），且各基金公司写法不统一；
- 解析失败**静默**退化成「拿沪深300 比债基」—— 比不给基准更误导。

故本模块**不解析那句话**，改按 `Fund.fund_type_id → fund_types.name → 指数代码`
兜底。零解析、零新增抓取，且命中率远高于字段填充率（`fund_type` 覆盖率见 #1155，
但它有确定性回填 job，`benchmark` 没有）。

## 映射的粒度与理由

按**基金小类名**（`fund_types.name`，形如「混合型-偏股」「指数型-股票」「债券型-长期
纯债」）做前缀匹配，而不是按大类：单看「混合型」无法区分偏股与偏债，而这两类该比
的基准完全不同。匹配规则用**有序前缀表**，靠前的规则先命中（见 `_RULES`）。

## 口径纪律（§3.10）

- 每只基金下发的基准必须带 `code` / `name` / `matched_by`，说明「它是怎么被选中的」；
- 映射命不中时返回 `None`，**不猜**——前端降级为「暂无基准」，不拿沪深300 顶替；
- 基准序列可能短于基金序列（新指数），取**共同交易日**由调用方保证（见
  `fund_risk_metrics.benchmark_diagnostics`，它先取交集再算）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# ── 基准指数常量（代码形态 == `index_daily.index_code`，勿改成裸码）─────────────
#
# 每一条都必须能在 `index_daily` 里查到，否则映射就是「选了一个我们没数据的基准」——
# 那比不选更糟（前端显示「暂无基准」是诚实的，显示一个算不出的基准是欺骗）。
# `scripts/tests/fund_benchmark_targets.test.js` 与 tests 会校验本表与 sync 目标清单一致。

# 万得系（.WI）：`index_daily_job.WIND_INDEX_TARGETS` 内的基金型/风格指数。
# 交易所以外的「同类平均」用它最贴切（基金指数本身就是同类基金的加权组合）。
BENCH_EQUITY_FUND = '885000.WI'  # 万得普通股票型基金指数
BENCH_HYBRID_FUND = '885001.WI'  # 万得偏股混合型基金指数
BENCH_BALANCED_HYBRID_FUND = '885002.WI'  # 万得平衡混合型基金指数
# 债券族基准：**中证全债指数**（中证官网 `.CSI` 路，真实收盘，2005 年至今 5287 条）。
#
# ⚠️ 为什么不是「万得债券型基金指数」885005.WI：它在韭圈儿**源侧未收录**
# （2026-10-14 二次复核仍为空序列，见 `index_daily_job.WIND_INDEX_TARGETS` 的 ⏳）。
# 把一个**取不到序列**的代码挂在映射上，前端只能显示「基准已选定但暂无数据」——
# 映射看着完整，用户实际拿不到任何参照。中证全债是**真实的债券市场全价指数**，
# 比 885005.WI（同类基金加权）更适合回答「债基跑赢债市了吗」，且数据就在手边。
BENCH_BOND_FUND = 'H11001.CSI'  # 中证全债指数（中证官网日线）
# 交易所以内（.SH/.SZ）：宽基，腾讯源真实收盘。
BENCH_HS300 = '000300.SH'  # 沪深300
BENCH_CSI500 = '000905.SH'  # 中证500
BENCH_CSI1000 = '000852.SH'  # 中证1000
BENCH_CSI2000 = '932000.CSI'  # 中证2000（中证官网日线，见 index_daily_job）
BENCH_SSE_GOV_BOND = '000012.SH'  # 上证国债指数（纯债类的近似旁证，当前映射未使用）

# 代码 → 展示名。单一真相源在后端，前端直接展示，不再抄一份映射（同 #1425 的做法）。
BENCHMARK_LABELS: Dict[str, str] = {
    BENCH_EQUITY_FUND: '万得普通股票型基金指数',
    BENCH_HYBRID_FUND: '万得偏股混合型基金指数',
    BENCH_BALANCED_HYBRID_FUND: '万得平衡混合型基金指数',
    BENCH_BOND_FUND: '中证全债指数',
    BENCH_HS300: '沪深300',
    BENCH_CSI500: '中证500',
    BENCH_CSI1000: '中证1000',
    BENCH_CSI2000: '中证2000',
    BENCH_SSE_GOV_BOND: '上证国债指数',
}


@dataclass(frozen=True)
class BenchmarkChoice:
    """一只基金应参照哪个基准，以及这个判断的依据。"""

    code: str  # 指数代码（== index_daily.index_code）
    name: str  # 展示名
    matched_by: str  # 命中的规则名（口径留痕：用户可复核「凭什么拿它比」）

    # 注：这里**刻意没有** `unavailable` 字段（2026-10-14 删除）。它原用于标「映射成立
    # 但源侧未收录」的基准（885005.WI 那类），而那一形态与「已同步但序列暂缺」在
    # 前端是**同一种降级**（`available: false` + 各自的 reason），由 `_benchmark_payload`
    # 按 `load_index_points` 的实际结果判定即可，不需要映射表额外标一遍。
    # 留着它就得靠 monkeypatch 才跑得到分支——那正是「看起来在兜底、其实恒假」的死代码。


# ── 映射规则表（**有序**：靠前先命中）────────────────────────────────────────
#
# 每条 = (规则名, 需同时出现的子串元组, 基准代码)。匹配对象是 `fund_types.name`
# （形如「混合型-偏股」「指数型-股票」「债券型-长期纯债」）。
#
# 顺序的讲究（踩过就知道）：
# 1. **「偏债」必须先于「混合」**——「混合型-偏债」里同时含「混合」与「偏债」，
#    若「混合」在前，偏债混基会被判成偏股混基的基准（比沪深300 更贴，但仍然错）。
# 2. **「货币」必须在最前**——货基走万份收益分支，根本不该进这张表；放最前是为了
#    在调用方漏判时**显式返回 None**，而不是被后面的规则捡走。
# 3. 越具体的写法越靠前（「长期纯债」先于「债券」）。
_RULES: List[tuple] = [
    # 货基：显式不映射（它没有回撤/波动口径，比不了任何基准）
    ('货币基金不适用基准', ('货币',), None),
    # ETF / 联接 / 指数型：跟踪标的就是它的基准，但我们**没有**标的指数映射
    # （ETF 表的「跟踪标的」字段实测全空，见 fetch_etf_list docstring）⇒ 不猜。
    # 用宽基兜底会把「跟踪中证2000 的 ETF」拿去比沪深300，是错的。
    #
    # 这两条**不是**「反正后面也匹配不到」的摆设：去掉它，下面的债券族会把
    # 「指数型-债券」捡成「比同类债基」——而指数债基该比的是它跟踪的那只指数。
    # 变异探针实测确认（删掉规则后 `resolve('指数型-债券')` 变成债券族基准），
    # 故有 `test_index_bond_fund_not_mapped_to_peer_bond_fund` 钉住。
    ('指数型（跟踪标的不明，不猜）', ('指数',), None),
    ('ETF（跟踪标的不明，不猜）', ('ETF', '联接'), None),
    # ── 债券族（必须先于「混合」）──
    ('转债基金 → 可转债等权（暂未收录，降级）', ('可转债',), None),
    ('纯债 / 中长期纯债 → 中证全债指数', ('债', '纯债'), BENCH_BOND_FUND),
    ('债券型 → 中证全债指数', ('债券',), BENCH_BOND_FUND),
    ('偏债混合 → 中证全债指数', ('偏债',), BENCH_BOND_FUND),
    # ── 权益族 ──
    ('股票型 → 万得普通股票型基金指数', ('股票型',), BENCH_EQUITY_FUND),
    ('偏股混合 → 万得偏股混合型基金指数', ('偏股',), BENCH_HYBRID_FUND),
    ('平衡混合 → 万得平衡混合型基金指数', ('平衡',), BENCH_BALANCED_HYBRID_FUND),
    ('灵活 / 混合型 → 万得偏股混合型基金指数', ('混合',), BENCH_HYBRID_FUND),
    # ── QDII / 其他 ──
    # 海外资产不该比 A 股宽基（货币、交易时段、估值口径都不同）⇒ 不猜。
    ('QDII / 海外 → 无 A 股可比基准', ('QDII', '海外'), None),
    ('FOF → 无同源基准', ('FOF',), None),
]

# 通用兜底：命不中任何规则时**不猜**。理由：宁可让用户看到「暂无基准」，
# 也不要让他看到一个他不知道是错的对比（他没法分辨「没比」和「比错了」）。
_FALLBACK = None


def resolve(fund_type_name: Optional[str], variety_name: Optional[str] = None) -> Optional[BenchmarkChoice]:
    """按基金类型名解析应参照的基准指数。

    Args:
        fund_type_name: `fund_types.name`（小类，如「混合型-偏股」）。
        variety_name: `fund_varieties.name`（大类，如「混合型」）；小类缺失时的兜底。

    Returns:
        命中规则返回 ``BenchmarkChoice``；**规则命中但基准不适用**（货基 / 指数型 /
        QDII）返回 ``None``——调用方据此下发「暂无基准」，不得回退到某个宽基。
    """
    text = (fund_type_name or '').strip() or (variety_name or '').strip()
    if not text:
        return _FALLBACK

    for rule_name, needles, code in _RULES:
        if not all(n in text for n in needles):
            continue
        if code is None:
            return None
        return BenchmarkChoice(
            code=code,
            name=BENCHMARK_LABELS.get(code, code),
            matched_by=rule_name,
        )
    return _FALLBACK


def load_index_points(db, index_code: str, limit: int = 0):
    """从 ``index_daily`` 取基准点位序列，返回升序 ``[(date, close)]``。

    只读 market 域内的表，无跨域 JOIN、无外部请求。序列缺失（新指数 / 未收录）时返回
    空列表——调用方据此把基准块整体降级，**不用别的指数顶替**。

    Args:
        db: market 域会话。
        index_code: `index_daily.index_code`（如 ``881001.WI`` / ``000300.SH``）。
        limit: 需要的最多点数（0 = 不限）。需要窗口时传 ``WINDOW_3Y * 1.1`` 一类冗余值。
    """
    from app.domains.indices.models import IndexDaily

    query = db.query(IndexDaily.trade_date, IndexDaily.close).filter(IndexDaily.index_code == index_code)
    if limit:
        # 倒序取最近 N 条再翻转：与 fund_risk_metrics_job._nav_points 同一手法，
        # 避免「先升序再在 Python 里切尾巴」把全序列读进内存。
        rows = query.order_by(IndexDaily.trade_date.desc()).limit(limit).all()
        rows = list(reversed(rows))
    else:
        rows = query.order_by(IndexDaily.trade_date.asc()).all()
    return [(d, float(c)) for d, c in rows if c is not None and float(c) > 0]


__all__ = [
    'BENCHMARK_LABELS',
    'BenchmarkChoice',
    'load_index_points',
    'resolve',
]
