# -*- coding: utf-8 -*-
"""首页「最新收益」卡：当日盈亏 + 按大类拆分 + 估/确认状态。

## 为什么单起一个出口，而不是前端拿持仓自己算

回答的是**同一个问题**：「今天赚了多少」，而盈亏口径全站只有一条
（`pnl_calendar._compute_days` 的 `total_pnl` 日差分，见 `pnl_calendar` 模块头）。
前端另算一套必然分叉，第一个坏结果是「首页卡 +1,227.88，收益日历当日格 +1,198.20」，
用户不会相信任何一侧。故本模块**复用同一次遍历**：只给 `_compute_days` 追加一个
`class_breakdown` 收集器，按 `asset_class` 把同一条水平值链聚到 3 个桶里。
构造上 `Σ 分项 ≡ 当日合计`，不是对账对出来的。

## 三个数字的先后关系（卡内自洽）

    Σ 大类当日盈亏 = 最新收益（本卡 hero）
    Σ 大类市值     = 投资类资产（本卡次级，= 股票 + 基金）
    家庭净资产 / 总负债 = 另一层刻度（含房产、现金、负债），由调用方从 /summary/ 取

覆盖范围（`CARD_CLASSES`）：**股票 + 基金**——前者含股票 / ETF / 可转债
（`position_price_job` 同一集合，都有交易所报价、盘中可取实时价），后者只有每日
净值 / 收盘估值。房产、银行理财、实物、货基没有统一的当日估值口径，硬塞进分项
只能填 0——那会把「不知道」画成「没赚没亏」；账户维度同理，没有当日价的资产
显示 `—`，不显示估值也不画 0。
（2026-11-04 D77 起 `asset_class` 把 etf / bond 归股票侧，此前二者分别落在「基金」
与「其他」，可转债因此完全不进卡面；2026-11-06 D91 起用户可见标签改为
「股票 / 基金」，集合边界由前端一行小字说明，key 与分桶一律不变。）

## 占比（2026-11-04 用户拍板：一律后端出，前端不做除法）

    classes[].share_of_invested = 该大类市值 ÷ 投资类资产
    invested_ratio_of_assets    = 投资类资产 ÷ 家庭总资产

两个比率的分子分母**必须与卡面上的数逐一对应**（同一份 `invested_cents`、
同一个 `family_totals`），否则会出现「卡面写 12.1%，手算 12.2%」这种自打脸。

2026-11-04 起分子与分母**同为当前市值口径**：分子由
`position_valuation.market_value_cents` 逐持仓求和（与 `/funds`、`/stocks`、
`/summary/` 同一函数同一参数），分母取 `family_totals`。此前分子来自收益引擎的
「当日价 × 引擎自算份额」，盘中与分母差一个交易日、且无报价标的被整笔漏掉；
现在市值与当日收益分开取数：市值（存量）全站一个数，收益（流量）只认当日真报价。
分母 ≤ 0 时 `ratio_pct` 返回 None。

## 估 / 确认（用户 2026-11-03 拍板）

    estimated  当日价里有基金来自收盘估值定格（`fund_valuation_daily`，#2141）
               ⇒ 徽标「估」，官方净值公布后自动翻转
    confirmed  该大类当日全部持仓都有官方当日价（场内收盘价 / 场外确认净值）
    partial    部分标的本日还没出价（盘中、或同步没跑）：金额只算了已出价的
    empty      该大类当日没有持仓

`estimated` **不按日期推断**，只看引擎真的用了估值行——语义与收益日历当日格的
`estimated` 同源（同一份 `_merge_today_estimates`）。

## 日期选择（为什么可能不是今天）

盘中（15:00 前）今日收盘价 / 当日净值都不存在，硬算出来是「0.00」——
那是把「还没有数据」说成「今天没赚没亏」（#1942 起全站禁止的形态）。
故取「**最近一个真有当日报价的日子**」；盘中自然落到上一交易日，前端再用实时
行情做价格替换（只替换价，不重算盈亏），收盘后估值定格一落地就自动切回今天。

## 通用化：一个资源，两个正交参数（2026-11-06 用户拍板，D92）

首页 / 账户列表 / 组合列表 / 品类各自估值回答的是**同一个问题**，只是切片不同，
故仍是这一个 `GET /summary/today-pnl/`，不按页面各开接口（REST 的域是资源边界，
不是页面边界；每页一个接口会让估/确认语义与「Σ ≡ 合计」校验分叉成四份）：

    dimension = class | ledger | portfolio   决定 groups[] 按什么分组
    ledger_id / portfolio_id（互斥）        决定作用域，scope 由 id 推导后回带

三条不能破的口径：

1. **决策集恒为家庭全量、值集按 scope 缩小**（`pnl_calendar._compute_days` 的
   `decision_positions` / `positions`）。反过来会让丢天与差分基准错位，D80 实测差
   93,712.70。价格序列按决策集取，故 scope 内持仓的取价不受裁剪影响。
2. **分桶只覆盖「有当日估值口径 + 已归属」的持仓**：桶函数对 `CLASS_OTHER`
   （银行理财 / 贵金属 / 实物 / 货基等 balance 模式）与未归属组合的持仓返回 None，
   它们不进任何 group，界面显示 `—` 而非 0。银行账户里持有的基金按其
   `asset_type` 照常估值——判据是**持仓资产类**，不是账户 `ledger_type`。
3. **`total_pnl = Σ groups[].pnl`**，由分桶和输出，不是 `daily_pnl`（后者含被
   排除的持仓）。因此组合维度下合计天然只含已归属部分，`excludes_unassigned`
   为 true 时前端用小字标记「不含未归属持仓」，不单列未归属桶。
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import EXCHANGE_RATES
from app.core.money import Money
from app.core.time_utils import now_shanghai
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.services.asset_class import (
    CLASS_FUND,
    CLASS_LABELS,
    CLASS_OTHER,
    CLASS_STOCK,
    class_of_position,
)
from app.services.nav_service import NavService
from app.services.pnl_calendar import (
    STATE_NO_POSITION,
    STATE_NO_PRICE,
    _as_of_shares,
    _compute_days,
    _positions,
    _price_presence,
)
from app.services.position_valuation import market_value_cents
from app.services.scope import filter_positions_by_scope, resolve_scope_label

# 家庭口径（总资产 / 总负债 / 净资产）与占比口径的唯一出口。
# 本模块**不**自己累加家庭资产：`investment_ratio` 的分母必须是 `family_totals`
# 那一个数，否则「投资类资产 ÷ 总资产」会与 /summary/ 的净资产/负债率不同源。
from app.services.summary_service import family_totals, ratio_pct

# 回看窗口：覆盖国庆 / 春节（最长 8 天假）+ 一个交易日，足以找到「最近有价的一天」
LOOKBACK_DAYS = 10

# 卡面只出这两类（有当日估值口径）
CARD_CLASSES = (CLASS_STOCK, CLASS_FUND)

# 分组维度：与 `domains/summary/schemas.py::TodayPnlQuery.dimension` 同一枚举。
# service 侧再校验一次是因为测试 / 内部调用可绕过 schema。
DIMENSION_CLASS = 'class'
DIMENSION_LEDGER = 'ledger'
DIMENSION_PORTFOLIO = 'portfolio'
DIMENSIONS = (DIMENSION_CLASS, DIMENSION_LEDGER, DIMENSION_PORTFOLIO)
ERR_DIMENSION = '不支持的 dimension: {}'

STATUS_ESTIMATED = 'estimated'
STATUS_CONFIRMED = 'confirmed'
STATUS_PARTIAL = 'partial'
STATUS_EMPTY = 'empty'


def _yuan(cents: Optional[int]) -> Optional[float]:
    return None if cents is None else round(Money.cents_to_yuan(cents), 2)


def _rate(pnl_cents: Optional[int], prev_mv_cents: Optional[int]) -> Optional[float]:
    """收益率（%）= 当日盈亏 / 前一基准日市值。分母缺失 ⇒ None，不造 0。"""
    if pnl_cents is None or not prev_mv_cents:
        return None
    return round(pnl_cents / abs(prev_mv_cents) * 100, 2)


def _group_status(key: str, rec: dict) -> str:
    """桶的估 / 确认状态；键可以是大类 / 账户 / 组合，判据与大类版逐位相同。"""
    held = rec['held'].get(key, 0)
    present = rec['present'].get(key, 0)
    if held <= 0:
        return STATUS_EMPTY
    if key in rec['estimated']:
        return STATUS_ESTIMATED
    if present >= held:
        return STATUS_CONFIRMED
    return STATUS_PARTIAL


def _pick_target(breakdown: Dict[str, dict], today: dt.date) -> str:
    """最近一个「真有当日报价」的日子；盘中 / 净值未出时回退到上一交易日。

    `_compute_days` 只记录 `daily_pnl is not None` 的日子，故 `breakdown` 的键
    天然都是「算得出数」的日期（休市 / 无价 / 无持仓的日子不在其中）。
    """
    dates = sorted(breakdown)
    latest = dates[-1]
    rec = breakdown.get(today.isoformat())
    if rec is None:
        return latest
    # 今天有任一标的拿到**当天**报价（含估值定格）才认今天；否则今天的
    # 「0.00」只是前值回填的产物，不能当成当日收益。
    # 遍历 present 的值而非固定三类：分桶后键是账户 / 组合 id，不是大类。
    has_fresh = any(v > 0 for v in rec['present'].values())
    if has_fresh:
        return today.isoformat()
    earlier = [d for d in dates if d < today.isoformat()]
    return earlier[-1] if earlier else latest


def _merge_holdings(rows: List[dict]) -> List[dict]:
    """逐持仓 → 按 (大类, 代码) 合并，供前端做**价格替换**。

    单位统一到「元 / 份」：引擎内部价是 0.0001 元、份额是 0.0001 份，出口一次折完，
    前端只做 `(实时价 − 当日价) × 份额`（不做盈亏计算，也不碰成本）。
    外币按引擎同一条 `EXCHANGE_RATES` 折进价格，`quantity` 保持份额原值。
    """
    merged: Dict[str, dict] = {}
    for row in rows:
        cls = row['class']
        if cls not in CARD_CLASSES or not row['symbol'] or row['quantity'] <= 0:
            continue
        key = f'{cls}:{row["symbol"]}:{row["fx"]}'
        item = merged.setdefault(
            key,
            {
                'symbol': row['symbol'],
                'class': cls,
                'quantity': 0.0,
                'price': 0.0,
            },
        )
        item['quantity'] += row['quantity'] / 10000
        item['price'] = round(row['price'] / 10000 * row['fx'], 6)
    for item in merged.values():
        item['quantity'] = round(item['quantity'], 4)
    return sorted(merged.values(), key=lambda x: (x['class'], x['symbol']))


def _dimension_buckets(
    db: Session,
    family_id: int,
    positions: List,
    dimension: str,
) -> Tuple[Dict[str, str], Tuple[str, ...], Callable[[object], Optional[str]], int]:
    """构造分桶方案：`(labels, keys, bucket_of, unassigned_count)`。

    `bucket_of` 返回 None 有两层含义，都是用户拍板要排除的部分：

    - 该持仓不是股票 / 基金（银行理财、贵金属、货基、实物等 balance 模式没有
      统一当日估值口径）⇒ 界面显示 `—`，不画 0。判据是**持仓 asset_type**，
      不是账户 `ledger_type`——银行账户里买的基金照常估值。
    - `dimension=portfolio` 且该持仓未归属任何有效组合 ⇒ 不单列未归属桶。

    组合归属与 `scope.py` 同款「显式覆盖继承」：`positions.portfolio_id` 优先，
    为空时继承 `Ledger.portfolio_id`；指向已删除 / 非本家庭组合一律视为未归属
    （不进分组，也不凭空造一个没有名字的桶）。
    """
    if dimension == DIMENSION_CLASS:
        labels = {c: CLASS_LABELS[c] for c in CARD_CLASSES}
        inherited: Dict[int, Optional[int]] = {}
    else:
        ledger_rows = (
            db.query(Ledger.id, Ledger.name, Ledger.portfolio_id)
            .filter(Ledger.family_id == family_id)
            .all()
        )
        inherited = {row.id: row.portfolio_id for row in ledger_rows}
        if dimension == DIMENSION_LEDGER:
            labels = {str(row.id): (row.name or f'账户 {row.id}') for row in ledger_rows}
        else:
            portfolios = (
                db.query(Portfolio.id, Portfolio.name)
                .filter(Portfolio.family_id == family_id, Portfolio.is_deleted.is_(False))
                .all()
            )
            labels = {str(row.id): (row.name or f'组合 {row.id}') for row in portfolios}

    def bucket_of(pos) -> Optional[str]:
        cls = class_of_position(pos)
        if cls not in CARD_CLASSES:
            return None
        if dimension == DIMENSION_CLASS:
            return cls
        if dimension == DIMENSION_LEDGER:
            return str(pos.ledger_id) if pos.ledger_id is not None else None
        pid = pos.portfolio_id if pos.portfolio_id is not None else inherited.get(pos.ledger_id)
        key = str(pid) if pid is not None else None
        return key if key in labels else None

    unassigned = (
        sum(1 for p in positions if class_of_position(p) in CARD_CLASSES and bucket_of(p) is None)
        if dimension == DIMENSION_PORTFOLIO
        else 0
    )
    keys = tuple(CARD_CLASSES) if dimension == DIMENSION_CLASS else tuple(labels)
    return labels, keys, bucket_of, unassigned


def _market_value_by_bucket(
    db: Session,
    positions: List,
    no_price_ids: Set[int],
    bucket_of: Callable[[object], Optional[str]],
) -> Tuple[Dict[str, int], int, int, int]:
    """当前市值：与 `/funds` `/stocks` `/summary/` 共用唯一出口，按分桶聚合。

    2026-11-04 之前卡面市值取自 `_compute_days` 的 `rec['mv']`
    （当日价 × 引擎自己累加的份额），与账户页的
    `position_valuation.market_value_cents`（当前价 × `positions.quantity`）
    是两套账：同一只 `SH688223` 账户页 12,617、首页 4,477。
    份额经 `_as_of_shares` 终点锚并轨后仍有**无当日报价**的标的：
    停牌可转债、净值恒 1 的组合 / 货基、同步漏掉的基金代码——
    收益引擎按设计跳过它们（`price_of` 返回 None ⇒ 不进 `day_split_rows`），
    账户页却照常计市值，于是数字永远差一截。

    修法不是给这些标的补一段价格序列（那会把「不知道」编成「没涨没跌」），
    而是把**市值（存量）**与**当日收益（流量）**分开取数：

    * 市值一律走 `market_value_cents`，与账户页同函数同参数同结果；
      无报价标的自然计入，不需要任何回填脚本，新数据也一样生效。
    * 当日收益仍只由 `_compute_days` 里真有当日报价的持仓产生，
      该大类一个报价都没有时 `pnl=None`，不编 0.00。

    Returns:
        `(各桶市值, 其他类市值, 无报价持仓笔数, 无报价持仓市值)`。
        分桶只累加 `bucket_of` 认领的持仓；其他类市值单列用于口径说明，
        未归属 / 无估值口径的持仓不进任何桶，也不冒充「零收益」。
    """
    fund_codes = [
        p.symbol
        for p in positions
        if p.symbol and p.asset_type in ('fund', 'money_fund') and class_of_position(p) in CARD_CLASSES
    ]
    navs = NavService.get_latest_navs(db, fund_codes, allow_remote=False) if fund_codes else {}

    by_bucket: Dict[str, int] = defaultdict(int)
    other_cents = 0
    frozen_count = 0
    frozen_cents = 0
    for pos in positions:
        key = class_of_position(pos)
        bucket = bucket_of(pos)
        nav = navs.get(pos.symbol) if pos.asset_type in ('fund', 'money_fund') else None
        cents = market_value_cents(
            pos,
            effective_nav_yuan=nav,
            rate=EXCHANGE_RATES.get(pos.currency, 1.0),
        )
        if key == CLASS_OTHER:
            other_cents += cents
        if bucket is None:
            continue
        by_bucket[bucket] += cents
        if pos.id in no_price_ids:
            frozen_cents += cents
            frozen_count += 1
    return dict(by_bucket), other_cents, frozen_count, frozen_cents


def _empty_payload(
    today: dt.date,
    reason: str,
    *,
    scope: str,
    dimension: str,
    ledger_id: Optional[int],
    portfolio_id: Optional[int],
    excludes_unassigned: bool = False,
) -> dict:
    """空态也要带全套契约字段：前端不必为「没数据」写第二套分支。"""
    return {
        'date': today.isoformat(),
        'is_today': True,
        'state': reason,
        'status': 'no_data',
        'total_pnl': None,
        'total_rate': None,
        'invested_value': None,
        'unvalued_count': 0,
        'unvalued_value': None,
        # 「无持仓」与「算不出来」共用空态：占比一并给 None，前端据此隐藏
        # 「占家庭总资产 x%」整段，而不是渲染成 0%（0% 会被读成「投资为 0」）
        'invested_ratio_of_assets': None,
        'other_value': None,
        'scope': scope,
        'dimension': dimension,
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'excludes_unassigned': excludes_unassigned,
        'groups': [],
        'classes': [],
        'holdings': [],
    }


def build_today_pnl(
    db: Session,
    family_id: int = 1,
    *,
    dimension: str = DIMENSION_CLASS,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> dict:
    """当日估值的唯一数据出口：单资源 + `dimension` 分组 + 可选作用域。

    Args:
        dimension: `class`（默认，首页股票 / 基金）/ `ledger` / `portfolio`。
        ledger_id / portfolio_id: 作用域，互斥；均不传 = 家庭级。`scope` 由
            这两个 id 推导后回带，不作为入参。

    Returns:
        不传参时与首页既有出参**逐位等价**，另加 `scope` / `dimension` /
        `ledger_id` / `portfolio_id` / `groups[]` / `excludes_unassigned`。
        `total_pnl = Σ groups[].pnl` 由构造保证；`classes[]` 仅在
        `dimension=class` 时与 groups 同源，其他维度为空数组。
    """
    if dimension not in DIMENSIONS:
        raise ValueError(ERR_DIMENSION.format(dimension))

    today = now_shanghai().date()
    all_positions = _positions(db, family_id, None)
    # 作用域解析走唯一出口；family 级直接复用原列表对象，保持
    # `_compute_days` 的「值集 is 决策集」身份，首页路径逐位等价。
    if ledger_id is not None or portfolio_id is not None:
        value_positions = filter_positions_by_scope(
            db, family_id, all_positions, ledger_id=ledger_id, portfolio_id=portfolio_id
        )
    else:
        value_positions = all_positions
    scope = resolve_scope_label(ledger_id, portfolio_id)

    labels, bucket_keys, bucket_of, unassigned_count = _dimension_buckets(
        db, family_id, value_positions, dimension
    )
    excludes_unassigned = dimension == DIMENSION_PORTFOLIO and unassigned_count > 0
    if not value_positions:
        return _empty_payload(
            today,
            STATE_NO_POSITION,
            scope=scope,
            dimension=dimension,
            ledger_id=ledger_id,
            portfolio_id=portfolio_id,
            excludes_unassigned=excludes_unassigned,
        )

    window_start = today - dt.timedelta(days=LOOKBACK_DAYS)
    shares, txns = _as_of_shares(db, family_id, today)
    # 无价集合按家庭全量判定（与收益日历同源）：scope 缩小不改变
    # 「这笔持仓有没有价格序列」这个事实；市值与无报价诊断只遍历值集。
    no_price_ids, _latest = _price_presence(db, all_positions, window_start, today)
    market_by_bucket, other_cents, frozen_count, frozen_cents = _market_value_by_bucket(
        db, value_positions, no_price_ids, bucket_of
    )

    breakdown: Dict[str, dict] = {}
    _compute_days(
        db,
        family_id,
        value_positions,  # 值集：只算本作用域持仓的当日盈亏
        all_positions,  # 决策集：恒为家庭全量（D80）
        window_start,
        today,
        None,
        window_start,
        no_price_ids,
        shares,
        txns,
        class_breakdown=breakdown,
        bucket_of=bucket_of,
        bucket_keys=bucket_keys,
    )
    target = _pick_target(breakdown, today) if breakdown else today.isoformat()
    # 全部持仓都无当日报价时不再返回空态：市值仍要照常显示（与账户页同源），
    # 只是「当日收益」这一流量没有数（total_pnl=None）。
    rec = breakdown.get(target) if breakdown else None

    # 品类按「股票 / 基金」固定顺序；账户 / 组合按 id 数值升序（稳定输出）。
    if dimension == DIMENSION_CLASS:
        ordered_keys: Tuple[str, ...] = CARD_CLASSES
    else:
        ordered_keys = tuple(sorted(labels, key=lambda k: int(k) if k.isdigit() else 0))

    groups: List[dict] = []
    invested_cents = 0
    covered_pnl_cents = 0
    covered_prev_cents = 0
    for key in ordered_keys:
        mv_cents = market_by_bucket.get(key, 0)
        held = rec['held'].get(key, 0) if rec else 0
        present = rec['present'].get(key, 0) if rec else 0
        pnl_cents = rec['pnl'].get(key, 0) if rec else 0
        if mv_cents <= 0 and held <= 0:
            continue
        # 该桶今天一个真报价都没有 ⇒ 金额是前值回填出来的 0，不是「没涨没跌」
        pnl_value = None if present == 0 else _yuan(pnl_cents)
        status = _group_status(key, rec) if rec and held > 0 else STATUS_PARTIAL
        invested_cents += mv_cents
        if pnl_value is not None:
            covered_pnl_cents += pnl_cents
            # 收益率分母用**卡面上那个市值**反推前值，避免分子分母两套口径
            covered_prev_cents += mv_cents - pnl_cents
        groups.append(
            {
                'key': key,
                'label': labels.get(key, key),
                'pnl': pnl_value,
                'rate': (_rate(pnl_cents, mv_cents - pnl_cents) if pnl_value is not None else None),
                'market_value': _yuan(mv_cents),
                'status': status,
            }
        )

    estimated = rec['estimated'] if rec else []
    if estimated:
        status = STATUS_ESTIMATED
    elif frozen_count or any(g['status'] == STATUS_PARTIAL for g in groups):
        status = STATUS_PARTIAL
    elif groups:
        status = STATUS_CONFIRMED
    else:
        status = STATUS_EMPTY

    invested_value = _yuan(invested_cents)
    # `classes` 是首页既有字段：只在品类维度与 groups 同源，占比分母恒为
    # 卡面那个「投资类资产」，不做二次求和。
    classes: List[dict] = []
    if dimension == DIMENSION_CLASS:
        classes = [dict(g) for g in groups]
        for item in classes:
            item['share_of_invested'] = ratio_pct(item['market_value'], invested_value)

    # 家庭总资产只用作占比分母：**非 class 维度的批量请求不需要它**，
    # 省一次全家庭聚合（列表页一次请求要出 N 个账户 / N 个组合）。
    # 失败只降级、不抛出：占比是展示派生，整卡失败不可接受（同原口径）。
    invested_ratio = None
    if dimension == DIMENSION_CLASS:
        try:
            household_assets = family_totals(db, family_id)['total_assets']
        except Exception:  # noqa: BLE001 —— 见上：占比缺失可接受，整卡失败不可接受
            logger.warning('家庭总资产聚合失败，投资占比降级为 None', exc_info=True)
            household_assets = None
        invested_ratio = ratio_pct(invested_value, household_assets)

    payload = {
        'date': target,
        'is_today': target == today.isoformat(),
        'state': rec['state'] if rec else STATE_NO_PRICE,
        'status': status,
        'total_pnl': (_yuan(covered_pnl_cents) if any(g['pnl'] is not None for g in groups) else None),
        'total_rate': _rate(covered_pnl_cents, covered_prev_cents),
        'invested_value': invested_value,
        'invested_ratio_of_assets': invested_ratio,
        'other_value': _yuan(other_cents),
        # 无当日报价但按账户页同一口径计入市值的持仓：卡面据此标注，
        # 不把「没数据」画成「没赚没亏」，也不让用户以为市值漏了一块
        'unvalued_count': frozen_count,
        'unvalued_value': _yuan(frozen_cents),
        'scope': scope,
        'dimension': dimension,
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'excludes_unassigned': excludes_unassigned,
        'groups': groups,
        'classes': classes,
        # 盘中价格替换输入：值集已按 scope 裁剪；非 class 维度不下发
        'holdings': _merge_holdings(rec['holdings']) if rec and dimension == DIMENSION_CLASS else [],
    }
    logger.debug(
        '当日收益派生完成 作用域={} 维度={} 日期={} 状态={} 合计={} 分组数={} 无报价持仓={}',
        scope,
        dimension,
        payload['date'],
        status,
        payload['total_pnl'],
        len(groups),
        frozen_count,
    )
    return payload


__all__ = ['build_today_pnl', 'DIMENSIONS', 'LOOKBACK_DAYS']
