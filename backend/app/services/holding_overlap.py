# -*- coding: utf-8 -*-
"""组合内基金持仓重叠度分析（#2604）：把「看着分散、实则同涨同跌」从净值曲线补到持仓层。

## 背景（父卡 #866）

持仓相关性（``services/analytics/correlation.py``）只能用**净值曲线**回答「两只基金是不是
一起涨跌」，但用户真正想问的是「我这几只基金是不是重仓了同一批股票」——那只看持仓明细。
本模块是父卡 #866 的**持仓腿**：读 ``fund_holdings``（东财基金档案-投资组合），
逐对计算组合内基金的重仓股重叠度。

## 口径（维护者拍板，**不得自行改口径**）

1. **每只基金取各自最新报告期**，不强制对齐共同日期。强制对齐会把报告期落后的基金
   整体排除（新建仓基金报告期天然滞后），反而低估重叠。故每只基金各带自己的
   ``report_period``，由前端展示。
2. **``holding_basis`` 不混算**：只在**同一 basis** 的两只基金之间计算重叠度；跨 basis
   的对**不计算**，但要如实给出被跳过的对数（``skipped_basis_mismatch``）。理由：季报只
   披露前十大（``top10``），其重仓集合天然是全量（``full``）的子集，混算出的重叠度
   **系统性偏低**，会让用户得到「我的基金不重叠」的**错误安心**。宁可少给一对，
   不可给一个偏低的数。
3. **同一基金有多个 basis 时取 full 优先**（full 是全量口径，覆盖更全）——在**该基金
   自己最新报告期内**优先（与 ``penetration`` / ``manager_holdings`` 既有实现同口径，
   见下节）。
4. **两个口径都要给**：
   - ``jaccard`` = |A∩B| / |A∪B|（按 ``stock_code`` 集合），无量纲，取值 0~1；
   - ``weighted_overlap`` = Σ min(ratioA, ratioB)，单位是**百分点**（``ratio`` 本身是 %）。
   两者互补：jaccard 说「重合了几只股票」，weighted 说「重合了多少仓位」。
5. **比对以 ``stock_code`` 为准，``stock_name`` 只作展示**。同一只股票在不同基金里的
   ``stock_name`` 写法可能不一致（如「贵州茅台」vs「贵州茅台股份」），按名字比对会漏配。
6. **同基金多账户先合并再参与计算**（避免同一只基金在多账户下被算成多只、互相算出
   100% 的假重叠）。
7. **超阈值给「配置重复」提示**（卡面 #866）：每对带 ``overlap_level``——
   ``weighted_overlap >= 20`` 或 ``jaccard >= 0.5`` 判 ``duplicate``；
   ``>= 10`` 或 ``>= 0.3`` 判 ``watch``；其余 ``low``。阈值取值有实证依据，
   见 ``DUPLICATE_WEIGHTED_PCT`` 上方注释（**改阈值前先重跑那份实测**，
   否则就是拿感觉替掉分布）。
8. **同一只基金的不同份额不算配置重复**：持仓集合与占比逐行相同 ⇒
   ``overlap_level='same-series'``，**不计入** ``duplicate_count``。判据与不判
   「``jaccard == 1``」的原因见 ``_is_identical_holdings``。
9. **换手率口径如实声明、不假装判定**（卡面 #866 的硬约束）：卡面指出「持仓重叠度
   只对低换手基金有效」，但基金级换手率**并未入库**（现有 turnover 全是市场/行业
   拥挤度与用户自身的交易换手）。故本模块只在 ``caveats`` 里声明该局限，**不输出**
   「哪只基金高换手」这类没有数据支撑的结论。
10. **重复投入金额是提示的前置闸门**：``overlap_amount_cents`` = Σ min(市值A×占比A,
    市值B×占比B)，即「两侧各自在这批共同持仓上的实际敞口取小」之和——它才有资格回答
    「这笔重复值不值得管」。只投几块钱的观察仓与重仓基金比例再高也只重复几毛钱，
    低于 ``MIN_OVERLAP_AMOUNT_CENTS`` 一律判 ``trivial``（**不提示**），但仍保留比例
    信息在 ``overlap_reason`` 里。**取 ``min`` 而非求和**：小仓位那侧决定真实影响上限，
    一只 ¥0.53、一只 ¥19,404 的同一只基金，重复的是那 5 毛 3 对应的钱。
    金额是**保守下界**（季报只披露前十大，未披露的持仓看不见）。
11. **排序先按档位、档内按金额降序**：第一屏必须是「花最多钱重复的地方」。若仍按
    ``weighted_overlap`` 排，第 1 名会是一对只投了几毛钱、比例 90% 的观察仓——
    那正是这张卡要消除的噪音。

## 复用既有口径（不自造第二份）

- **报告期 / basis 解析**复用 ``services/penetration._load_holding_map``（多基金版：
  取各自最新报告期 → 期内 ``full`` 优先）。该实现与 ``manager_holdings._load_latest_holdings``
  （单基金版）口径一致，是全库唯一的权威口径；跨模块引用「私有」函数是仓库既有惯例
  （``penetration`` 自己就引用 ``summary_service._load_user_assets``），目的是**口径只有一份**。
- **持仓市值**复用 ``position_aggregation.get_fund_aggregation``（product 维度按 symbol
  跨渠道合并），不另写一套市值逻辑。

## 降级契约

任一取数环节失败 → **该维度置空** + ``degraded=True``，**不 500、不拿 0 冒充**：
- 持仓聚合失败 → 整体空结构 + ``degraded=True``；
- 持仓明细查询失败 → 保留已知的持仓市值，但 ``pairs`` 置空、``coverage_pct=0.0``、
  ``degraded=True``（前端据此提示「暂时取不到」，不得渲染成「覆盖 0%」的真结论）。

**``ratio`` 为 NULL 的持仓行排除并计数**（``skipped_null_ratio``）：占比缺失时它既不能
参与 jaccard 的集合（有行无值 = 不知道是不是同一只票），也无法参与 weighted（min 无从
算起）；把它当 0 参与计算会**系统性低估**重叠度，同样是错误安心。排除后两个口径
（jaccard / weighted）跑在**同一份可比较行集**上，二者才可比。

## 空 ``pairs`` 的三种成因（消费方必须区分，不得一律当「重叠 0%」）

1. ``degraded=True`` —— 取数失败，该维度置空（诚实降级，不是结论）；
2. ``fund_count < 2`` —— 可比基金不足 2 只，**算不出**（样本不足，不是「不重叠」）；
3. ``fund_count >= 2`` 且 ``pairs`` 为空 —— 算出来了，结论就是**确实无共同重仓股**。

三者都表现为 ``pairs == []``，只能靠 ``degraded`` 与 ``fund_count`` 区分开——这也是
本模块**不**把「样本不足」塞进 ``degraded`` 的原因：``degraded`` 的语义严格是
「取数失败」（与 ``funds/views.py`` 的既有 ``degraded`` 用法一致），一旦混用，
消费方就无法分辨「暂时取不到」与「算出来没有」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from loguru import logger
from sqlalchemy.orm import Session

from app.services.fund_utils import normalize_fund_code
from app.services.penetration import BASIS_FULL, BASIS_TOP10, _load_holding_map
from app.services.position_aggregation import get_fund_aggregation

#: 出参的数据来源标识（前端据此标注「数据来源：东财基金档案」）。
SOURCE = 'fund_holdings'

#: 可参与两两比较的披露口径。``full``（半年报/年报全量）与 ``top10``（季报前十大）是
#: 仅有的两种真实披露强度；其余（空串 / 未知值）代表口径不可判定——它连「这是哪个口径」
#: 都说不清，与谁比都是错配，故不参与比较（也不计入 ``skipped_basis_mismatch``：
#: 那条计数只记「两只都有口径但口径不同」）。
KNOWN_BASES = (BASIS_FULL, BASIS_TOP10)

#: 百分比换算基数（``ratio`` 已是 %，算覆盖率时乘 100 与之对齐）。
_PERCENT_SCALE = 100

#: 分 → 元（金额展示用；与 ``_PERCENT_SCALE`` 数值相同但语义不同，不合并）。
_CENTS_PER_YUAN = 100

# ── 「配置重复」阈值（卡面 #866）──────────────────────────────────────────────
#
# **这一组只回答「算不算重复」，不回答「值不值得提示」**——后者由下方
# ``MIN_OVERLAP_AMOUNT_CENTS`` 的金额闸门把关。两层缺一不可：只判比例会先炸出
# 一屏观察仓的假警报（实测 55 对里 45 对重复金额不到 1 元）。
#
# 取值依据：2026-10-27 用本地真实库实测（96 只可比基金、1834 对有共同持仓）——
# ``weighted_overlap`` p50=0.09 / max=94.83，``jaccard`` p50=0.021 / max=1.0；
# 阈值都落在分布尾部（weighted>=20 命中 55 对、jaccard>=0.5 命中 8 对）。
#
# **不能只用一个口径**：jaccard 只看「重合几只股票」——两家公司跟踪同一指数的基金
# jaccard 恒为 1.0，却可能只差 0.07 个百分点的仓位；weighted 只看「重合多少仓位」——
# 前十大中重合 2 只但每只都重仓，weighted 也能很高而 jaccard 只有 0.2。任一越线都
# 值得提示，但**理由必须分开写**（见 ``_classify_overlap``），否则用户不知道该看哪一面。
DUPLICATE_WEIGHTED_PCT = 20.0
#: 集合口径「配置重复」阈值（0~1）：两者重仓股有一半以上重合。
DUPLICATE_JACCARD = 0.5
#: 加权口径「需留意」阈值（百分点）。
WATCH_WEIGHTED_PCT = 10.0
#: 集合口径「需留意」阈值（0~1）。
WATCH_JACCARD = 0.3

# ── 「重复投入金额」提示线 ───────────────────────────────────────────────────
#
# 只看比例会炸出一屏假警报：真实的组合里通常躺着几十只**观察仓**（买几块到几十块
# 试试水），它们的持仓比例与重仓基金完全一样，但重复的只是几毛钱。
#
# 2026-10-27 用本地真实库实测（96 只可比基金、1834 对有重叠）：
#   重复投入金额 p50=¥0.68 / p75=¥3.42 / p95=¥65.66 / p99=¥837.97 / max=¥7,279.57
# 可见按纯比例判出的 55 对「配置重复」里，绝大多数是**金额不到 1 元**的噪音。
#
# 取 ¥1,000 的理由：本组合总市值 ¥285,694，¥1,000 约 0.35%；低于这个数的重复敞口
# 对组合波动的影响远小于一次正常调仓，提示它只会让人学会忽略提示。
# 该门槛是**绝对值、不随组合市值缩放**——相对门槛会让提示列表随每日市值抖动，
# 用户无法理解「昨天报了今天没报」。命中数：¥1,000 → 10 对 duplicate（无门槛时 55 对）。
# **改这个数前先重跑那份分布**，不要凭感觉调。
MIN_OVERLAP_AMOUNT_CENTS = 1000 * 100

#: 档位展示优先级（前端按此顺序折叠；``duplicate`` 永远排第一）。
LEVEL_ORDER = {'duplicate': 0, 'watch': 1, 'same-series': 2, 'low': 3, 'trivial': 4}

#: 浮点比较容差：``ratio`` 落库是 REAL，同一份额的同一行可能带极小误差。
_RATIO_EPS = 1e-9

#: 口径声明（随出参下发，前端原样展示）。**不是**每对的具体结论，而是
#: 「这个数字在什么条件下会失真」——卡面 #866 明确要求交代换手率口径，
#: 而基金级换手率数据并未入库（现有 turnover 全是市场/行业拥挤度与用户交易换手），
#: 故只能如实声明局限、**不假装做了基金级判定**。
_CAVEATS = [
    '重叠度基于基金定期报告披露的持仓快照，两次报告之间的调仓看不到；各基金报告期见每一对下方。',
    '高换手基金的季报持仓是滞后快照，季报之间可能已换掉大半持仓，此时重叠度参考价值下降。'
    '系统未接入基金级换手率，无法自动标出哪只属于高换手——看到季报前十大（top10）口径的对，请自行掂量。',
    '重复投入金额按「各基金披露持仓比例 × 你的持仓市值、两侧取小」估算，是保守下界：'
    '季报只披露前十大，未披露的持仓看不到，真实重复只会更多。',
]


@dataclass
class _Fund:
    """组合内一只基金（已按业务码合并多账户）的可比较持仓。

    Attributes:
        fund_code: 6 位业务码（与 ``fund_holdings.fund_code`` 对齐）。
        symbol: 展示用 symbol（持仓原始写法，保留给用户认得出是哪只）。
        name: 展示名（取持仓名，缺失时回退业务码）。
        market_value_cents: 合并后的持仓市值（分）。
        report_period: 该基金自身最新报告期（如 ``2026Q2``）。
        basis: 该基金所取报告期的披露口径（``full`` / ``top10``）。
        ratios: ``stock_code -> 占净值比例(%)``，仅含**可比**行（占比存在且为正）。
        stock_names: ``stock_code -> 股票名``，仅作展示（口径 5）。
    """

    fund_code: str
    symbol: str
    name: str
    market_value_cents: int
    report_period: Optional[str] = None
    basis: Optional[str] = None
    ratios: Dict[str, float] = field(default_factory=dict)
    stock_names: Dict[str, str] = field(default_factory=dict)

    @property
    def codes(self) -> Set[str]:
        """该基金的可比重仓股集合（按 ``stock_code``，口径 5）。"""
        return set(self.ratios)


def _empty_result() -> Dict[str, Any]:
    """空结果骨架（降级 / 无持仓时返回，字段与正常路径完全一致）。"""
    return {
        'pairs': [],
        'fund_count': 0,
        'skipped_basis_mismatch': 0,
        'skipped_null_ratio': 0,
        'total_market_value_cents': 0,
        'coverage_pct': 0.0,
        'uncovered': [],
        'duplicate_count': 0,
        #: 被金额闸门挡下的对数（比例可能很高，但重复的只是几毛钱）。前端据此折叠，
        #: 并与 ``duplicate_count`` 分开陈述——「忽略了多少」本身是信息。
        'trivial_count': 0,
        #: 下发的金额提示线（分），前端展示「低于 ¥X 未提示」时用，避免两端各写一个数。
        'min_overlap_amount_cents': MIN_OVERLAP_AMOUNT_CENTS,
        # 口径声明与数据无关：它描述的是本模块**固有**的失真条件，取不到数也照样成立。
        'caveats': list(_CAVEATS),
        'degraded': False,
        'source': SOURCE,
    }


def _merge_positions(groups: List[Dict[str, Any]]) -> List[_Fund]:
    """把 ``get_fund_aggregation`` 的分组按**业务码**合并成一只只基金（口径 6）。

    ``get_fund_aggregation`` 已按 ``symbol`` 跨渠道合并；这里再按 6 位业务码二次合并，
    因为同一只基金在不同账户下可能写成 ``OTC:004369`` / ``004369`` 两种 symbol——不归一
    就会被当成两只基金，进而互相算出 100% 的假重叠。市值按合并后求和。

    Args:
        groups: 聚合服务返回的分组（每项含 ``symbol`` / ``name`` / ``market_value_cents``）。

    Returns:
        合并后的基金列表（尚未装载持仓明细）。
    """
    merged: Dict[str, _Fund] = {}
    for group in groups or []:
        symbol = (group.get('symbol') or '').strip()
        name = (group.get('name') or '').strip()
        market_value = int(group.get('market_value_cents') or 0)
        fund_code = normalize_fund_code(symbol)
        if not fund_code:
            # 归一不出 6 位业务码 → 不可能对上 ``fund_holdings``，按「无明细」处理，
            # 但仍要计入分母（覆盖率是结果的一部分，缺口不许被藏起来）。
            fund_code = f'__unresolved__{symbol}'
        bucket = merged.get(fund_code)
        if bucket is None:
            merged[fund_code] = _Fund(
                fund_code=fund_code,
                symbol=symbol,
                name=name or fund_code,
                market_value_cents=market_value,
            )
        else:
            bucket.market_value_cents += market_value
            if not bucket.name or bucket.name == bucket.fund_code:
                bucket.name = name or bucket.name
    return list(merged.values())


def _load_fund_details(db: Session, funds: List[_Fund]) -> int:
    """给每只基金装载可比持仓明细（口径 1/2/3 + ratio 缺失行计数）。

    报告期与 basis 的解析**不在这里另写**：直接用 ``penetration._load_holding_map``
    （全库唯一权威口径：各自最新报告期 → 期内 ``full`` 优先）。

    Args:
        db: 数据库会话。
        funds: 待装载的基金列表（原地填充 ``report_period`` / ``basis`` / 明细）。

    Returns:
        因 ``ratio`` 缺失或非正而被排除的持仓行数（口径要求的「排除并计数」）。
    """
    skipped_null_ratio = 0
    codes = [fund.fund_code for fund in funds if not fund.fund_code.startswith('__unresolved__')]
    if not codes:
        return skipped_null_ratio

    holding_map = _load_holding_map(db, codes)
    for fund in funds:
        record = holding_map.get(fund.fund_code)
        if record is None:
            # 该基金无任何持仓明细 → 不进比较集（调用方记入 uncovered）。
            continue
        fund.report_period = record.report_period
        fund.basis = record.basis
        if record.basis not in KNOWN_BASES:
            # 口径不可判定：与谁比都是错配，不参与比较（也不计入 basis mismatch）。
            continue
        for row in record.rows:
            # 只取与该基金口径**一致**的行：同一报告期内若混入了别的口径的行，
            # 混进来就等于自造了一个「混算」（口径 2 的禁区）。
            if (row.holding_basis or '') != record.basis:
                continue
            stock_code = (row.stock_code or '').strip()
            if not stock_code:
                continue
            ratio = row.ratio
            if ratio is None:
                # 占比缺失：当 0 参与计算会系统性低估重叠度 → 排除并计数。
                skipped_null_ratio += 1
                continue
            ratio_value = float(ratio)
            if ratio_value <= 0:
                # 占比为 0 / 负：脏数据（唯一键挡不住），同样排除（占比为 0 的行不构成
                # 「持有」，算进集合只会虚增重叠）。
                skipped_null_ratio += 1
                continue
            fund.ratios[stock_code] = ratio_value
            if row.stock_name:
                fund.stock_names.setdefault(stock_code, row.stock_name)
    return skipped_null_ratio


def _pair_detail(a: _Fund, b: _Fund) -> Dict[str, Any]:
    """计算一对基金的重叠度明细（口径 4/5）。

    Args:
        a: 第一只基金。
        b: 第二只基金。

    Returns:
        ``{jaccard, weighted_overlap, overlap_amount_cents, common_holdings,
        identical_holdings}``。``common_holdings`` 按 ``min_ratio`` 降序（重合仓位重的
        排前面），同值按 ``stock_code`` 升序保证稳定。
    """
    codes_a = a.codes
    codes_b = b.codes
    common = codes_a & codes_b
    union = codes_a | codes_b
    jaccard = (len(common) / len(union)) if union else 0.0

    weighted = 0.0
    #: 重复投入金额（分）：共同持仓上「两侧各自的实际敞口取小」求和。
    #: 取 ``min`` 是因为小仓位那侧才决定真实影响上限——一只投 ¥0.53、一只投 ¥19,404
    #: 的同一只基金（招商白酒 A/C 实测），重复的只是那 5 毛 3 对应的钱，不是 1.9 万。
    #: 语义是**保守下界**：季报只披露前十大，未披露的持仓看不到，真实重复只会更多。
    amount_cents = 0.0
    holdings: List[Dict[str, Any]] = []
    for stock_code in common:
        ratio_a = a.ratios[stock_code]
        ratio_b = b.ratios[stock_code]
        min_ratio = min(ratio_a, ratio_b)
        weighted += min_ratio
        amount_cents += min(
            a.market_value_cents * ratio_a / _PERCENT_SCALE,
            b.market_value_cents * ratio_b / _PERCENT_SCALE,
        )
        holdings.append(
            {
                'stock_code': stock_code,
                # 名称只作展示（口径 5）：优先取 a 侧的写法，a 没有则用 b 的。
                'stock_name': a.stock_names.get(stock_code) or b.stock_names.get(stock_code) or stock_code,
                'ratio_a': ratio_a,
                'ratio_b': ratio_b,
                'min_ratio': min_ratio,
            }
        )
    holdings.sort(key=lambda item: (-item['min_ratio'], item['stock_code']))
    return {
        'jaccard': round(jaccard, 4),
        'weighted_overlap': round(weighted, 2),
        'overlap_amount_cents': int(round(amount_cents)),
        'common_holdings': holdings,
        'identical_holdings': _is_identical_holdings(codes_a, codes_b, a, b),
    }


def _is_identical_holdings(codes_a: Set[str], codes_b: Set[str], a: _Fund, b: _Fund) -> bool:
    """两只基金是不是**同一只基金的不同份额**（如 A/C 类，口径 8）。

    这类对持仓集合与占比逐行相同，算出来必然接近 100% 重叠——但那是「同一只基金
    买了两次」，不是「两只基金买重了」。若不给它们单独定性，阈值提示的第一屏就会是
    假警报（实测：``161725 招商中证白酒A`` / ``012414 招商中证白酒C``，weighted 86.48）。

    判据取「集合完全相同 **且** 占比全等」，不查 ``funds`` 表也不做名称模糊匹配：
    - 实测真实库全库只有 1 对满足（就是上面那对 A/C 份额）；
    - 不同公司跟踪同一指数（``017513 广发北证50`` / ``023887 永赢北证50``）集合相同、
      但占比差 0.07 个百分点，**不会**被误判成份额重复——这正是不用「``jaccard == 1``」
      当判据的原因。
    """
    if not codes_a or codes_a != codes_b:
        return False
    return all(abs(a.ratios[code] - b.ratios[code]) <= _RATIO_EPS for code in codes_a)


def _classify_overlap(jaccard: float, weighted: float, common_count: int) -> tuple[str, str]:
    """按双口径阈值给一对基金定级（卡面 #866 的「超过阈值给配置重复提示」）。

    两个口径谁越线都提示，但**理由分开写**：只说「配置重复」用户不知道是「重合的
    股票多」还是「重合的仓位重」，而这两种情况的处置并不一样。

    Args:
        jaccard: 集合口径重叠度（0~1）。
        weighted: 加权口径重叠度（百分点）。
        common_count: 共同重仓股只数。

    Returns:
        ``(level, reason)``。``level`` ∈ ``{'duplicate', 'watch', 'low'}``；
        ``low`` 时 ``reason`` 为空串（不占版面）。
    """
    jaccard_pct = jaccard * _PERCENT_SCALE
    if weighted >= DUPLICATE_WEIGHTED_PCT:
        return 'duplicate', f'共同重仓 {common_count} 只、{weighted:.1f}% 仓位重叠'
    if jaccard >= DUPLICATE_JACCARD:
        return 'duplicate', f'重仓股重合 {jaccard_pct:.0f}%（{common_count} 只），标的重复但仓位有差异'
    if weighted >= WATCH_WEIGHTED_PCT:
        return 'watch', f'共同重仓 {common_count} 只、{weighted:.1f}% 仓位重叠'
    if jaccard >= WATCH_JACCARD:
        return 'watch', f'重仓股重合 {jaccard_pct:.0f}%（{common_count} 只）'
    return 'low', ''


def _apply_amount_gate(level: str, reason: str, weighted: float, amount_cents: int) -> tuple[str, str]:
    """按「重复投入金额」给比例定级做二次过滤（观察仓不该报重复）。

    只看比例的致命问题：组合里通常躺着几十只**观察仓**（买几块到几十块试水），
    它们的持仓与重仓基金完全一致，比例能到 90%+，但重复的只有几毛钱。
    实测本地库 1834 对里，金额中位数是 ¥0.68——不设闸门时 55 对「配置重复」
    绝大多数是这种噪音，用户很快就会学会无视整条提示。

    闸门只降级、不升级：金额不足时无论比例多高都判 ``trivial``，但**理由里保留
    比例信息**（「重叠 94.8% 但重复投入约 ¥12」），让用户知道「不是没重叠，
    是这笔钱不值得管」。``same-series`` 不参与闸门——它是定性事实（你买的是
    同一只基金的两个份额），与金额无关，且不计入 ``duplicate_count``。

    Args:
        level: ``_classify_overlap`` 给出的比例档位。
        reason: 对应的理由（``low`` 时为空）。
        weighted: 加权口径重叠度（百分点），仅在理由里回显。
        amount_cents: 重复投入金额（分）。

    Returns:
        ``(level, reason)``。未过闸时 ``level='trivial'``。
    """
    if level == 'same-series' or amount_cents >= MIN_OVERLAP_AMOUNT_CENTS:
        return level, reason
    head = f'重叠 {weighted:.1f}% 但' if level in ('duplicate', 'watch') else ''
    return (
        'trivial',
        f'{head}重复投入约 ¥{amount_cents / _CENTS_PER_YUAN:,.0f}，'
        f'低于 ¥{MIN_OVERLAP_AMOUNT_CENTS / _CENTS_PER_YUAN:,.0f} 提示线',
    )


def _build_pairs(funds: List[_Fund]) -> tuple[List[Dict[str, Any]], int]:
    """两两配对并计算重叠度（口径 2/4）。

    Returns:
        ``(pairs, skipped_basis_mismatch)``。``pairs`` **先按档位、档内按重复金额降序**：
        第一屏永远是「花最多钱重复的地方」，而不是「比例最高但只投了 5 毛钱」的观察仓。
        只含 ``weighted_overlap > 0`` 的对（无重合的基金对不占版面，也没信息量）。
        每对带 ``overlap_amount_cents``（重复投入金额，分）与 ``overlap_level``
        （``duplicate`` / ``watch`` / ``same-series`` / ``low`` / ``trivial``）
        及 ``overlap_reason``（人话解释触发点，``low`` / ``trivial`` 只讲为什么没提示）。
    """
    pairs: List[Dict[str, Any]] = []
    skipped_basis_mismatch = 0
    for index, fund_a in enumerate(funds):
        for fund_b in funds[index + 1 :]:
            if fund_a.basis != fund_b.basis:
                # 口径不同 → 不计算（口径 2），但如实计数。
                skipped_basis_mismatch += 1
                continue
            detail = _pair_detail(fund_a, fund_b)
            if detail['weighted_overlap'] <= 0:
                continue
            if detail['identical_holdings']:
                # 同一只基金的不同份额：不参与阈值判定，否则第一屏全是假警报（口径 8）。
                level, reason = 'same-series', '同一只基金的不同份额（持仓与占比完全相同），属份额重复而非配置重复'
            else:
                level, reason = _classify_overlap(
                    detail['jaccard'], detail['weighted_overlap'], len(detail['common_holdings'])
                )
                # 比例达标也可能只是观察仓：把钱的门槛套在比例之上（口径 10）。
                level, reason = _apply_amount_gate(
                    level, reason, detail['weighted_overlap'], detail['overlap_amount_cents']
                )
            pairs.append(
                {
                    'fund_code_a': fund_a.fund_code,
                    'fund_name_a': fund_a.name,
                    'report_period_a': fund_a.report_period,
                    'fund_code_b': fund_b.fund_code,
                    'fund_name_b': fund_b.name,
                    'report_period_b': fund_b.report_period,
                    'holding_basis': fund_a.basis,
                    'jaccard': detail['jaccard'],
                    'weighted_overlap': detail['weighted_overlap'],
                    'overlap_amount_cents': detail['overlap_amount_cents'],
                    'overlap_level': level,
                    'overlap_reason': reason,
                    'common_holdings': detail['common_holdings'],
                }
            )
    pairs.sort(
        key=lambda item: (
            LEVEL_ORDER.get(item['overlap_level'], 9),
            -item['overlap_amount_cents'],
            -item['weighted_overlap'],
            item['fund_code_a'],
            item['fund_code_b'],
        )
    )
    return pairs, skipped_basis_mismatch


def portfolio_holding_overlap(db: Session, family_id: int = 1) -> Dict[str, Any]:
    """组合内基金持仓重叠度分析（#2604）。

    Args:
        db: 数据库会话（路由会话：持仓在 user 域、持仓明细在 market 域，跨域零 JOIN）。
        family_id: 家庭 ID（数据隔离维度）。

    Returns:
        见模块 docstring 的出参结构。``pairs`` 按 ``weighted_overlap`` 降序；只含
        ``weighted_overlap > 0`` 的基金对。``coverage_pct`` = 有持仓明细的基金市值 /
        全部持仓市值 * 100；``uncovered`` 列出无持仓明细的持仓（市值降序）。

        注：``uncovered`` 里会包含货基等**本质无股票持仓**的标的（无持仓明细不等于
        数据缺口），覆盖率因此天然偏低——这是口径事实，不是取数失败。

    降级：任一取数环节失败 → 该维度置空 + ``degraded=True``，**不 500、不拿 0 冒充**。
    """
    result = _empty_result()

    # ── 1) 持仓（市值口径 + 多账户合并的载体）──
    try:
        payload = get_fund_aggregation(db, family_id, page_size=0)
        groups = payload.get('groups') or []
    except Exception as exc:  # noqa: BLE001 - 展示接口不该因取数失败整体挂掉
        logger.warning(f'持仓重叠度：持仓聚合失败（降级回空）: {exc}')
        result['degraded'] = True
        return result

    funds = _merge_positions(groups)
    result['total_market_value_cents'] = sum(fund.market_value_cents for fund in funds)
    if not funds:
        return result

    # ── 2) 持仓明细（market 域）：各自最新报告期 + 期内 full 优先 ──
    try:
        skipped_null_ratio = _load_fund_details(db, funds)
    except Exception as exc:  # noqa: BLE001 - 明细取数失败：明细维度置空，不影响市值
        logger.warning(f'持仓重叠度：持仓明细查询失败（降级回空）: {exc}')
        result['degraded'] = True
        result['uncovered'] = [
            {'symbol': fund.symbol, 'name': fund.name, 'market_value_cents': fund.market_value_cents}
            for fund in sorted(funds, key=lambda f: -f.market_value_cents)
        ]
        return result
    result['skipped_null_ratio'] = skipped_null_ratio

    # ── 3) 配对计算 ──
    comparable = [fund for fund in funds if fund.basis in KNOWN_BASES and fund.ratios]
    covered_codes = {fund.fund_code for fund in comparable}
    covered_market_value = sum(fund.market_value_cents for fund in comparable)
    result['fund_count'] = len(comparable)
    result['coverage_pct'] = (
        round(covered_market_value / result['total_market_value_cents'] * _PERCENT_SCALE, 2)
        if result['total_market_value_cents'] > 0
        else 0.0
    )
    result['uncovered'] = [
        {'symbol': fund.symbol, 'name': fund.name, 'market_value_cents': fund.market_value_cents}
        for fund in sorted(
            (fund for fund in funds if fund.fund_code not in covered_codes),
            key=lambda f: -f.market_value_cents,
        )
    ]

    pairs, skipped_basis_mismatch = _build_pairs(comparable)
    result['pairs'] = pairs
    result['skipped_basis_mismatch'] = skipped_basis_mismatch
    # 只数真·配置重复：``same-series``（同一基金不同份额）不计——那是份额重复，
    # 计进来会让「你有 N 对配置重复」这个汇总数字说谎；``trivial``（金额不足提示线）
    # 也不计——它压根没被提示，计进「重复」等于把没报的算成报了。
    result['duplicate_count'] = sum(1 for pair in pairs if pair['overlap_level'] == 'duplicate')
    result['trivial_count'] = sum(1 for pair in pairs if pair['overlap_level'] == 'trivial')
    return result
