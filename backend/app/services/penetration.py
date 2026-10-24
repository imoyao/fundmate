# -*- coding: utf-8 -*-
# Author : imoyao
"""基金持仓穿透（#870 Step 2）：把用户组合穿透到底层行业 / 个股。

## 为什么要有这个模块

`fund_industry_allocs` / `fund_holdings` 两张表在 #870 Step 1 之前只有**写入侧**
（`services/sync/jobs/fund_position_job.py` 落库），全仓没有任何读侧消费方 ——
用户看得到「我买了哪些基金」，看不到「我的钱最终压在哪些行业 / 个股上」。
本模块补齐这个读侧。

## 硬口径（改动前务必读完，每条都有实测依据）

1. **覆盖率有硬上限，不得假装 100%**。实测本机组合：fund 61.4% / stock 22.9% /
   etf 10.5% / bond 5.2%；基金中 csrc 覆盖 85.9% ⇒ 可穿透上限约 53%。
   直持股票没有「个股→行业」映射、场内 ETF 没有底层持仓数据、货基债基本身无股票敞口。
   故出参必须分「已穿透 / 未穿透」两栏，且未穿透要带 `reason`（见 `_REASON_*`），
   把「真缺口」与「本质上就不该有行业敞口」区分开。
2. **csrc / gics 禁止跨体系相加**。`scheme='csrc'` 是证监会门类（单字母 A~S），
   `scheme='gics'` 是 GICS 板块（两位数字，港股等走这套）。GICS 的「非必需消费品」
   在证监会门类里被并进「制造业」，两套语义不重叠 —— 跨体系求和会得出
   「制造业与非必需消费品同级并列」的荒谬结论。本模块按 scheme 分区聚合，
   主口径默认 csrc，其余 scheme 单列透传（`other_schemes`）。
3. **聚合键必须是 `industry_code`，不是 (code, name)**。实测生产库 GICS 存在同码多名：
   `45` = 信息技术 / 科技；`25` = 非必需消费品 / 非日常生活消费品；
   `50` = 通讯 / 电信服务 / 通信服务。按 (code, name) 分组会把同一板块拆成两个行业。
4. **ratio 禁止归一化到 100%**。实测单基金单期合计 86.02% ~ 95.04%，差额是现金 /
   债券 / 其他资产。归一化会抹掉基金之间真实的现金垫差异（86% 仓位的基金被拉成满仓）。
   差额单独出 `industry_non_equity_cny`，不摊进行业。
5. **报告期逐基金取各自最新**，不全局取 `max(report_period)`。实测 99 只基金在 2026Q2、
   1 只在 2026Q1、1 只在 2025Q4 —— 新建仓基金的报告期天然滞后，全局取最大会让这些
   基金凭空消失。出参带 `report_periods` 把口径不一致透明化。
6. **市值口径复用 `position_valuation.market_value_cents`**，且**不传** `effective_nav_yuan`
   —— 与 `summary_service.get_summary_data` 完全一致（都走 `positions.current_price`
   快照价），保证穿透总额与仪表盘总额对得上。传净值会引入远程请求副作用且造成口径分叉。
7. **个股层必须带 `holding_basis`**：季报只披露前十大（`top10`），半年报 / 年报全量
   （`full`）。行业层则任何报告期都是全量、不失真（#870 正文 §七 实证）——
   两者口径强度不同，出参不可混看。

## 与其它模块的关系

- 持仓加载复用 `summary_service._load_user_assets`，与其保持同一过滤口径
  （只取 `ownership_status='active'`，排除 E 账户影子记录）。
- **纯读侧**：不写库、不触网、无副作用。可在请求路径上安全调用。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.core.time_utils import today_shanghai
from app.domains.funds.models import FundHolding, FundIndustryAlloc
from app.domains.securities.models import SecurityIndustryMap
from app.services.fund_utils import (
    is_cash_equivalent_position,
    normalize_business_code,
    resolve_money_fund_flags_strict,
)
from app.services.position_valuation import market_value_cents
from app.services.scope import filter_positions_by_scope, resolve_scope_label

# 复用 summary_service 的持仓加载器（同一过滤口径：active only）。
# 跨模块引用「私有」函数是刻意的：口径只有一份，比各自查一遍更不容易漂。
from app.services.summary_service import _load_user_assets

# ── 主口径与分类体系 ──
DEFAULT_SCHEME = 'csrc'
SCHEME_LABELS: dict[str, str] = {
    'csrc': '证监会门类',
    'gics': 'GICS 板块',
    # #1981：申万一级（31 个）。**只在 `security_industry_maps` 里有数据**——
    # 基金侧行业配置（`fund_industry_allocs`）只有 csrc / gics 两套，没有申万口径。
    # 故它只覆盖直持腿，与主口径的基金部分互补，绝不并入主口径。
    'sw1': '申万一级',
}

# 可尝试穿透的持仓类型（基金 / ETF）。ETF 目前无底层数据，仍走同一路径，
# 待 B3 补齐 ETF 持仓后自动生效，无需改这里。
_PENETRABLE_TYPES: tuple[str, ...] = ('fund', 'etf')

# ── 未穿透原因（前端 / Agent 按此枚举展示，禁止自由字符串）──
REASON_CASH_EQUIVALENT = 'cash_equivalent'
REASON_FUND_ALLOC_MISSING = 'fund_alloc_missing'
REASON_ETF_HOLDING_MISSING = 'etf_holding_missing'
REASON_INDUSTRY_MAP_MISSING = 'industry_map_missing'

REASON_LABELS: dict[str, str] = {
    REASON_CASH_EQUIVALENT: '现金等价物（货基/逆回购），本质无股票敞口',
    REASON_FUND_ALLOC_MISSING: '基金无行业配置记录（真缺口，待采集）',
    REASON_ETF_HOLDING_MISSING: '场内 ETF 无底层持仓数据（真缺口，待采集）',
    REASON_INDUSTRY_MAP_MISSING: '直持股票/可转债无「个股→行业」映射（真缺口，待补源）',
}

# 个股层持仓依据标签（与 fund_holdings.holding_basis 同源）
BASIS_FULL = 'full'
BASIS_TOP10 = 'top10'

_ZERO = Decimal(0)
_HUNDRED = Decimal(100)


@dataclass
class _Leg:
    """一条持仓在穿透视角下的展开单元。"""

    symbol: str
    name: str
    asset_type: Optional[str]
    value_cents: int
    code: str = ''
    reason: Optional[str] = None


@dataclass
class _AllocRecord:
    """某只基金在其自身最新报告期的行业配置。"""

    report_period: str
    items: list[tuple[str, Optional[str], float]] = field(default_factory=list)


@dataclass
class _HoldingRecord:
    """某只基金在其自身最新报告期的个股持仓（同期内优先全量口径）。"""

    report_period: str
    basis: str
    rows: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _cny(cents: int) -> float:
    """分 → 元（2 位小数）。出参统一用元，与 `summary_service` 的 `*_cny` 风格一致。"""
    return round(Money.cents_to_yuan(cents), 2)


def _ratio(part_cents: int, whole_cents: int) -> float:
    """占比（4 位小数）。分母为 0 时返回 0.0，不抛异常。"""
    if whole_cents <= 0:
        return 0.0
    return round(part_cents / whole_cents, 4)


def _share(value_cents: int, ratio_pct: float) -> int:
    """按「占净值比例(%)」把市值分摊到某一行业/个股，四舍五入到分。

    用 Decimal 而非 float 直接乘，避免 0.1+0.2 类累积误差渗进金额。
    """
    if value_cents <= 0 or ratio_pct <= 0:
        return 0
    exact = Decimal(value_cents) * Decimal(str(ratio_pct)) / _HUNDRED
    return int(exact.to_integral_value(rounding='ROUND_HALF_UP'))


def _business_code(symbol_norm: str, symbol: str) -> str:
    """从归一身份键取业务码（薄封装，口径与理由见 `fund_utils.normalize_business_code`）。

    #1981 起不再自持一份解析：写侧的行业映射采集要用**同一个**键，两处各写一遍必然漂。
    """
    return normalize_business_code(symbol_norm, symbol)


def _load_industry_map(db: Session, codes: Iterable[str], scheme: str) -> dict[str, _AllocRecord]:
    """加载各基金**自身最新报告期**的行业配置：`{fund_code: _AllocRecord}`。

    刻意不做全局 `max(report_period)`——见模块头口径 5。
    """
    code_list = [c for c in {c for c in codes if c}]
    if not code_list:
        return {}

    latest = (
        db.query(
            FundIndustryAlloc.fund_code.label('fund_code'),
            func.max(FundIndustryAlloc.report_period).label('rp'),
        )
        .filter(FundIndustryAlloc.fund_code.in_(code_list), FundIndustryAlloc.scheme == scheme)
        .group_by(FundIndustryAlloc.fund_code)
        .subquery()
    )
    rows = (
        db.query(FundIndustryAlloc)
        .join(
            latest,
            and_(
                FundIndustryAlloc.fund_code == latest.c.fund_code,
                FundIndustryAlloc.report_period == latest.c.rp,
            ),
        )
        .filter(FundIndustryAlloc.scheme == scheme)
        .all()
    )

    out: dict[str, _AllocRecord] = {}
    for row in rows:
        rec = out.get(row.fund_code)
        if rec is None:
            rec = _AllocRecord(report_period=row.report_period)
            out[row.fund_code] = rec
        rec.items.append((row.industry_code, row.industry_name, float(row.ratio or 0)))
    return out


def _load_security_industry_map(db: Session, codes: Iterable[str], scheme: str) -> dict[str, tuple[str, str]]:
    """直持证券的「代码 → (行业代码, 行业名)」映射（#1981）。

    **刻意与 :func:`_load_industry_map` 分开两张表读**：那张是**基金**的报告期行业配置
    （带 `report_period` 与 `ratio`，要按「各自最新报告期」去重），本表是**证券**的行业
    归属（无期间、无比例，一码一条）。混用会让「按报告期去重」的逻辑把证券映射也按期
    切一遍，或者反之——两套口径的键根本不同。

    ``scheme`` 显式入参：证监会门类（``csrc``，与基金侧同口径、**主口径**）与申万一级
    （``sw1``，细粒度、只进 ``other_schemes`` 单列）各自取，互不混用。
    """
    code_list = sorted({c for c in codes if c})
    if not code_list:
        return {}

    rows = (
        db.query(SecurityIndustryMap.symbol, SecurityIndustryMap.industry_code, SecurityIndustryMap.industry_name)
        .filter(SecurityIndustryMap.scheme == scheme, SecurityIndustryMap.symbol.in_(code_list))
        .all()
    )
    return {sym: (code, name or '') for sym, code, name in rows}


def _other_scheme_note(scheme_key: str, label: str) -> str:
    """非主口径的覆盖范围说明（#1981 起**按体系分述**）。

    原先是一句写死的「GICS 只标注港股」。加入申万一级后这句话对 ``sw1`` 不成立——
    ``sw1`` 恰恰**只**覆盖直持腿（基金侧没有申万口径），两者互补而非重叠，
    用同一句话会把一个高覆盖率的体系描述成残缺的，前端也会照着错误地降级展示。
    """
    if scheme_key == 'gics':
        return (
            f'{label} 仅覆盖基金持仓的一部分（实测 GICS 只标注港股），'
            '行业合计远低于参与基金市值，不可当作独立穿透口径与主口径并列展示。'
        )
    if scheme_key == 'sw1':
        return (
            f'{label} 只覆盖**直持**股票 / 可转债——基金侧行业配置只有证监会门类、没有申万口径。'
            '故它与主口径的基金部分**互补而不重叠**；`direct_industries` 即其全部覆盖范围，'
            '与主口径 `industries`（基金部分）相加才是申万一级的完整分布。'
        )
    return f'{label} 覆盖范围有限，不可当作独立穿透口径与主口径并列展示。'


def _load_holding_map(db: Session, codes: Iterable[str]) -> dict[str, _HoldingRecord]:
    """加载各基金**自身最新报告期**的个股持仓：`{fund_code: _HoldingRecord}`。

    同一报告期内 `full` 与 `top10` 可能并存（实测：季报只有 top10、半年报全量），
    组内**优先 full**，无 full 才用 top10 并据此打标。
    """
    code_list = [c for c in {c for c in codes if c}]
    if not code_list:
        return {}

    latest = (
        db.query(
            FundHolding.fund_code.label('fund_code'),
            func.max(FundHolding.report_period).label('rp'),
        )
        .filter(FundHolding.fund_code.in_(code_list))
        .group_by(FundHolding.fund_code)
        .subquery()
    )
    rows = (
        db.query(FundHolding)
        .join(
            latest,
            and_(
                FundHolding.fund_code == latest.c.fund_code,
                FundHolding.report_period == latest.c.rp,
            ),
        )
        .all()
    )

    grouped: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[row.fund_code].append(row)

    out: dict[str, _HoldingRecord] = {}
    for code, group in grouped.items():
        full = [r for r in group if r.holding_basis == BASIS_FULL]
        chosen = full or group
        basis = BASIS_FULL if full else (chosen[0].holding_basis or 'unknown')
        out[code] = _HoldingRecord(report_period=chosen[0].report_period, basis=basis, rows=chosen)
    return out


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def build_penetration(
    db: Session,
    family_id: int = 1,
    *,
    scheme: str = DEFAULT_SCHEME,
    top_n: int = 20,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> dict[str, Any]:
    """构建基金穿透视图（家庭 / 账户 / 组合三级口径，#2595）。

    Args:
        db: 数据库会话。
        family_id: 家庭 ID（数据隔离维度）。
        scheme: 主聚合口径（`csrc` / `gics`），默认证监会门类。其余体系单列透传。
        top_n: 个股分布截断条数，超出部分合并为一条 `其他`（`top_n <= 0` 表示不截断）。
        ledger_id: 账户级口径；与 `portfolio_id` 互斥（冲突抛 `ValueError`）。
        portfolio_id: 组合级口径（显式归属 + 成员账本继承，解析唯一出口
            `services/scope.py`）；不存在 / 非本家庭抛 `ValueError`。

    Returns:
        分层穿透结果，见模块头注释与 `docs/working-notes/fund-penetration-design-2026-10-01.md`。
        金额字段统一 `*_cny`（元，2 位小数）；比率为 `ratio_*`（4 位小数）。
        出参带 `scope` / `ledger_id` / `portfolio_id` 标明本次口径。
    """
    positions, _assets = _load_user_assets(db, family_id)
    # 三级口径唯一解析出口（#2595）：与归因 / 超额同一条组合语义（显式归属 +
    # 成员账本继承），禁止在本模块内手写成员账本查询——口径漂移会破坏「Σ 账户 ≡ 家庭」。
    positions = filter_positions_by_scope(
        db, family_id, positions, ledger_id=ledger_id, portfolio_id=portfolio_id
    )

    # 场内货币 ETF（如 511990 华宝添益）以 asset_type='etf' 录入时 is_money_fund
    # 为 False（写路径 #1661：显式 etf 类型一律 False，绝不落回名录），分流只看
    # 类型会把它当普通 ETF → 永远报 etf_holding_missing（假缺口：它本质无股票
    # 敞口）。这里只在**读侧**补判：仅对 etf 持仓批量查一次名录，取 strict
    # 明确确认为货币型（True）的归一代码进豁免集。
    # 键一致性：返回值键 = normalize_fund_code(symbol)，leg.code =
    # _business_code(...) 最终同样 normalize_fund_code，对 SH511990 /
    # EXCHANGE:SH511990 / 裸 511990 三种形态产出一致，可直接比较。
    # 为什么不动写侧置 is_money_fund=True：position_price_job 见
    # money_fund / is_money_fund 会按面值 1.0000 回写 current_price，而场内
    # 货基 ETF 每份约 100 元，市值会塌约 100 倍（#1661 同型事故）。
    etf_symbols = [getattr(p, 'symbol', '') or '' for p in positions if (getattr(p, 'asset_type', None) or '') == 'etf']
    money_fund_etf_codes: set[str] = set()
    if etf_symbols:
        # strict 内部已捕获 market 域不可达异常并全返 None，无需再包 try；
        # None（名录没说话）不进豁免集——维持现状走 fund_leg，不猜。
        flags = resolve_money_fund_flags_strict(etf_symbols)
        money_fund_etf_codes = {code for code, is_money in flags.items() if is_money is True}

    # ── 1. 逐持仓定值 + 分流 ──────────────────────────────────────────────
    fund_legs: list[_Leg] = []
    direct_legs: list[_Leg] = []
    total_cents = 0

    for p in positions:
        rate = EXCHANGE_RATES.get(getattr(p, 'currency', None), 1.0)
        cents = market_value_cents(p, rate=rate)
        if cents <= 0:
            continue

        leg = _Leg(
            symbol=getattr(p, 'symbol', '') or '',
            name=getattr(p, 'name', '') or '',
            asset_type=getattr(p, 'asset_type', None),
            value_cents=cents,
            code=_business_code(getattr(p, 'symbol_norm', '') or '', getattr(p, 'symbol', '') or ''),
        )
        total_cents += cents

        if is_cash_equivalent_position(p) or ((leg.asset_type or '') == 'etf' and leg.code in money_fund_etf_codes):
            # 货基 / 逆回购：本质无股票敞口，归未穿透但**不是**数据缺口。
            # 场内货币 ETF（511990 类）同理：名录（strict）明确货币型即归此桶。
            leg.reason = REASON_CASH_EQUIVALENT
            direct_legs.append(leg)
        elif (leg.asset_type or '') in _PENETRABLE_TYPES:
            fund_legs.append(leg)
        else:
            # 直持股票 / 可转债：有行业属性，但缺「个股→行业」映射
            leg.reason = REASON_INDUSTRY_MAP_MISSING
            direct_legs.append(leg)

    # ── 2. 行业层穿透（主口径 + 其它体系单列）────────────────────────────
    fund_cents = sum(leg.value_cents for leg in fund_legs)
    fund_codes = [leg.code for leg in fund_legs if leg.code]
    primary_map = _load_industry_map(db, fund_codes, scheme)

    # ── 直持腿的行业映射（#1981）────────────────────────────────────────
    # 只对「因缺映射而未穿透」的直持腿生效：**现金等价物（货基 / 逆回购）不参与映射**
    # ——它本质无股票敞口，即便代码碰巧撞上某行业也不该被归类，那等于把现金算成
    # 某个行业的暴露。
    #
    # 命中即把 ``reason`` 清空：它不再是缺口，下面的行业层会把它全额并进去。
    # 未命中的**保持原样**，仍在 ``unpenetrated`` 里带 ``industry_map_missing`` ——
    # 这正是验收第 2 条要求的「不得凭空调出 0 值行业」。
    mappable = [leg for leg in direct_legs if leg.reason == REASON_INDUSTRY_MAP_MISSING and leg.code]
    direct_map = _load_security_industry_map(db, [leg.code for leg in mappable], scheme)
    mapped_direct = [leg for leg in mappable if leg.code in direct_map]
    for leg in mapped_direct:
        leg.reason = None

    penetrated_cents = 0
    industry_cents: dict[str, int] = defaultdict(int)
    industry_names: dict[str, str] = {}
    industry_funds: dict[str, set[str]] = defaultdict(set)
    residual_cents = 0
    # 按**基金码**去重（同一基金可能在多个账本各有一条持仓，那是同一份报告期口径），
    # 出参语义是「多少只基金用的哪一期」，不是「多少条持仓」。
    period_funds: dict[str, set[str]] = defaultdict(set)
    # 只收「仍带 reason」的腿：命中映射的直持腿已转入行业分布，不再是缺口（#1981）
    unpenetrated: list[_Leg] = [leg for leg in direct_legs if leg.reason is not None]

    for leg in fund_legs:
        rec = primary_map.get(leg.code)
        # ratio <= 0 的行是脏数据（表上唯一键挡不住 0 值行）。若某基金的行全为 0，
        # 必须按未穿透处理 —— 否则它会被计进 `penetrated_cny` 却贡献不出任何行业，
        # 让用户看到「已穿透 60%」但行业列表是空的。
        usable = [(c, n, r) for c, n, r in (rec.items if rec else []) if r > 0]
        if not usable:
            # ETF 与无行业记录的基金分开报因：前者缺底层持仓，后者缺行业配置
            leg.reason = REASON_ETF_HOLDING_MISSING if leg.asset_type == 'etf' else REASON_FUND_ALLOC_MISSING
            unpenetrated.append(leg)
            continue

        penetrated_cents += leg.value_cents
        period_funds[rec.report_period].add(leg.code)
        allocated = 0
        for industry_code, industry_name, ratio_pct in usable:
            part = _share(leg.value_cents, ratio_pct)
            industry_cents[industry_code] += part
            allocated += part
            industry_funds[industry_code].add(leg.code)
            if industry_code not in industry_names and industry_name:
                industry_names[industry_code] = industry_name
        # ratio 合计不足 100% 的差额 = 该基金的**债券 / 现金 / 其他**资产。
        # 实测这不是误差：99 只 csrc 基金里 34 只合计 90~100、32 只 70~90、20 只 40~70、
        # 13 只 <40（债基 / 指数联接基金的股票仓位本就极低）。故不摊进行业、不归一化。
        residual_cents += leg.value_cents - allocated

    # ── 直持腿并入行业分布（#1981）──────────────────────────────────────
    # 直持股票没有 report_period / ratio 可摊：**全额**归到它自己的行业。
    # 它不进 period_funds（那是「多少只基金用的哪一期报告」的语义，直持腿不是基金、
    # 也没有报告期），改用 direct_counts 单独计数。
    direct_counts: dict[str, int] = defaultdict(int)
    for leg in mapped_direct:
        industry_code, industry_name = direct_map[leg.code]
        industry_cents[industry_code] += leg.value_cents
        penetrated_cents += leg.value_cents
        direct_counts[industry_code] += 1
        if industry_name and industry_code not in industry_names:
            industry_names[industry_code] = industry_name

    industries = [
        {
            'code': code,
            'name': industry_names.get(code) or code,
            'value_cny': _cny(value),
            'ratio_of_total': _ratio(value, total_cents),
            'ratio_of_penetrated': _ratio(value, penetrated_cents),
            'fund_count': len(industry_funds[code]),
            # 直持腿命中数（#1981）：与 fund_count 分开，因为两者语义不同——
            # 前者是「多少只基金的行业配置里有它」，后者是「多少只直持证券归它」。
            'direct_count': direct_counts.get(code, 0),
        }
        for code, value in sorted(industry_cents.items(), key=lambda kv: -kv[1])
    ]

    # ── 3. 其它分类体系单列（禁止并入主口径）────────────────────────────
    # 注意语义：非主口径**不是**「另一套等价分类」，而是「同一批基金里另一块敞口」。
    # 实测 GICS 只标注基金持仓中的港股部分（44 只基金有 gics 行，行业合计仅占参与
    # 基金市值的个位数百分比，residual 高达 90%），故必须带 `covered_ratio_of_fund`
    # 与 `note`，否则前端会把它当独立穿透率并列展示。
    other_schemes: dict[str, Any] = {}
    for other in sorted(set(SCHEME_LABELS) - {scheme}):
        other_map = _load_industry_map(db, fund_codes, other)
        agg: dict[str, int] = defaultdict(int)
        names: dict[str, str] = {}
        covered_cents = 0
        for leg in fund_legs:
            rec = other_map.get(leg.code)
            if rec is None:
                continue
            usable_other = [(c, n, r) for c, n, r in rec.items if r > 0]
            if not usable_other:
                continue
            covered_cents += leg.value_cents
            for industry_code, industry_name, ratio_pct in usable_other:
                agg[industry_code] += _share(leg.value_cents, ratio_pct)
                if industry_code not in names and industry_name:
                    names[industry_code] = industry_name

        # 直持腿在该体系下的分布（#1981），**单列**而不是并进 agg：
        # `covered_cny` / `covered_ratio_of_fund` 的分母是「参与基金市值」，把直持腿
        # 混进分子会让这个比值失真（甚至 > 1）。单列后前端可自行把两者相加，
        # 而 `industries` 仍是纯基金口径、`covered_ratio` 语义不变。
        direct_other_map = _load_security_industry_map(db, [leg.code for leg in mappable], other)
        direct_agg: dict[str, int] = defaultdict(int)
        direct_names: dict[str, str] = {}
        for leg in mappable:
            hit = direct_other_map.get(leg.code)
            if hit is None:
                continue
            direct_code, direct_name = hit
            direct_agg[direct_code] += leg.value_cents
            if direct_name and direct_code not in direct_names:
                direct_names[direct_code] = direct_name

        # 两侧都空才算这一体系没有数据。**不能只看 agg**：申万一级在基金侧
        # 没有对应记录（`fund_industry_allocs` 只有 csrc / gics），只有直持腿有，
        # 若沿用旧的 `if not agg: continue`，sw1 会被整条跳过、白采一遍。
        if not agg and not direct_agg:
            continue
        industry_total = sum(agg.values())
        label = SCHEME_LABELS.get(other, other)
        other_schemes[other] = {
            'label': label,
            'covered_cny': _cny(covered_cents),
            'covered_ratio_of_fund': _ratio(covered_cents, fund_cents),
            'industry_total_cny': _cny(industry_total),
            'industry_ratio_of_covered': _ratio(industry_total, covered_cents),
            'note': _other_scheme_note(other, label),
            'industries': [
                {
                    'code': code,
                    'name': names.get(code) or code,
                    'value_cny': _cny(value),
                    'ratio_of_total': _ratio(value, total_cents),
                }
                for code, value in sorted(agg.items(), key=lambda kv: -kv[1])
            ],
            # 直持腿在该体系下的行业分布（#1981），与上面 `industries`（基金部分）
            # 互补不重叠，相加才是该体系的完整分布
            'direct_industries': [
                {
                    'code': code,
                    'name': direct_names.get(code) or code,
                    'value_cny': _cny(value),
                    'ratio_of_total': _ratio(value, total_cents),
                }
                for code, value in sorted(direct_agg.items(), key=lambda kv: -kv[1])
            ],
        }

    # ── 4. 个股层（basis 打标；季报仅前十大，不可与行业层混看）────────────
    holding_map = _load_holding_map(db, fund_codes)
    stock_cents: dict[str, int] = defaultdict(int)
    stock_names: dict[str, str] = {}
    stock_funds: dict[str, set[str]] = defaultdict(set)
    stock_coverage_cents = 0
    basis_counter: Counter[str] = Counter()
    basis_periods: dict[str, str] = {}

    for leg in fund_legs:
        rec = holding_map.get(leg.code)
        if rec is None or not rec.rows:
            continue
        stock_coverage_cents += leg.value_cents
        basis_counter[rec.basis] += 1
        basis_periods.setdefault(rec.basis, rec.report_period)
        for row in rec.rows:
            stock_code = row.stock_code or ''
            ratio_pct = float(row.ratio or 0)
            if not stock_code or ratio_pct <= 0:
                continue
            stock_cents[stock_code] += _share(leg.value_cents, ratio_pct)
            stock_funds[stock_code].add(leg.code)
            if stock_code not in stock_names and row.stock_name:
                stock_names[stock_code] = row.stock_name

    ranked = sorted(stock_cents.items(), key=lambda kv: -kv[1])
    truncated = 0
    if top_n > 0 and len(ranked) > top_n:
        truncated = sum(value for _, value in ranked[top_n:])
        ranked = ranked[:top_n]

    stocks = [
        {
            'code': code,
            'name': stock_names.get(code) or code,
            'value_cny': _cny(value),
            'ratio_of_total': _ratio(value, total_cents),
            'holder_fund_count': len(stock_funds[code]),
        }
        for code, value in ranked
    ]
    if truncated:
        stocks.append(
            {
                'code': '__other__',
                'name': '其他',
                'value_cny': _cny(truncated),
                'ratio_of_total': _ratio(truncated, total_cents),
                'holder_fund_count': 0,
            }
        )

    # ── 5. 分层汇总（三层守恒为硬口径）─────────────────────────────────
    direct_cents = sum(leg.value_cents for leg in direct_legs if leg.reason == REASON_INDUSTRY_MAP_MISSING)
    cash_equiv_cents = sum(leg.value_cents for leg in direct_legs if leg.reason == REASON_CASH_EQUIVALENT)
    # #1981：命中映射的直持腿**已并入 penetrated_cents**，故这里只是把它单列出来做
    # 透明度（用户能看到「直持有多少已按行业归类」），**绝不能再计入 direct_cny**，
    # 否则同一笔钱会被算两次、守恒立刻破。
    mapped_direct_cents = sum(leg.value_cents for leg in mapped_direct)
    unpenetrated_fund_cents = sum(
        leg.value_cents for leg in unpenetrated if leg.reason in (REASON_FUND_ALLOC_MISSING, REASON_ETF_HOLDING_MISSING)
    )

    return {
        'as_of': today_shanghai().isoformat(),
        'scheme': scheme,
        'scheme_label': SCHEME_LABELS.get(scheme, scheme),
        # #2595 三级口径出参：本次穿透统计的作用域（family / ledger / portfolio）
        'scope': resolve_scope_label(ledger_id, portfolio_id),
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'total_value_cny': _cny(total_cents),
        'coverage': {
            'penetrated_cny': _cny(penetrated_cents),
            'unpenetrated_cny': _cny(total_cents - penetrated_cents),
            'penetrated_ratio': _ratio(penetrated_cents, total_cents),
            'fund_cny': _cny(fund_cents),
            'direct_cny': _cny(direct_cents),
            # #1981：直持腿已按行业归类的金额（**已含在 penetrated_cny 内**，此处仅作拆分展示）
            'mapped_direct_cny': _cny(mapped_direct_cents),
            'cash_equivalent_cny': _cny(cash_equiv_cents),
            'unpenetrated_fund_cny': _cny(unpenetrated_fund_cents),
        },
        'industries': industries,
        'industry_non_equity_cny': _cny(residual_cents),
        'other_schemes': other_schemes,
        'stocks': stocks,
        'stocks_coverage': {
            'covered_cny': _cny(stock_coverage_cents),
            'fund_count_by_basis': dict(basis_counter),
            'report_period_by_basis': basis_periods,
        },
        'unpenetrated': [
            {
                'symbol': leg.symbol,
                'name': leg.name,
                'asset_type': leg.asset_type,
                'value_cny': _cny(leg.value_cents),
                'ratio_of_total': _ratio(leg.value_cents, total_cents),
                'reason': leg.reason,
                'reason_label': REASON_LABELS.get(leg.reason or '', ''),
            }
            for leg in sorted(unpenetrated, key=lambda x: -x.value_cents)
        ],
        'report_periods': {period: len(codes) for period, codes in sorted(period_funds.items())},
        'notes': [
            '穿透仅覆盖持仓（positions），不含通用资产（assets 表：房产/现金/应收款等）。',
            '行业金额来自基金「行业配置占净值比例」，剩余部分是该基金的债券/现金/其他资产'
            '（见 industry_non_equity_cny），**不是缺失数据**，故未归一化到 100%。'
            '实测基金间差异极大：股票型多在 90% 以上，债基/指数联接基金可低至个位数。',
            f'行业分类体系为 {SCHEME_LABELS.get(scheme, scheme)}，与其它体系不可相加，'
            '非主口径结果在 other_schemes 单列（各体系的覆盖范围见其 note 字段）。',
            '直持股票/可转债按「代码→行业」映射**全额**并入主口径行业分布（#1981）：'
            '命中的计入 penetrated_cny，并在 industries[].direct_count 可见来源；'
            '未命中的仍带 industry_map_missing，**绝不凭空补出一个 0 值行业**。',
            '申万一级（sw1）只覆盖直持腿（基金侧行业配置只有证监会门类，没有申万口径），'
            '故其 direct_industries 与主口径 industries 的基金部分互补而不重叠。',
            '个股层季报只披露前十大（basis=top10），与半年报全量（full）口径强度不同，'
            'stocks_coverage.fund_count_by_basis 标明各口径基金数。',
            '未穿透逐条带 reason：cash_equivalent 是本质无股票敞口（非缺口），其余三项才是待补的真缺口。',
        ],
    }
