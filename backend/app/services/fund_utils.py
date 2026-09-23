# -*- coding: utf-8 -*-
"""货基 / 现金等价物统一判定与分类（#863 口径 A：持仓优先）。

设计要点：
- 写路径（建仓/导入）解析 symbol 是否货币型后冗余落 `positions.is_money_fund`
  （user 域）；聚合分类（分布/桑基图把货基市值归入「现金/流动资金」桶）只读该冗余
  字段或 `asset_type == 'money_fund'`，聚合层**零跨域**——`funds`/`fund_types` 名录
  在 market 域（Turso），双库下无法 SQL JOIN，运行期逐次跨域不可行。
- 判定优先级：
  1. `asset_type == 'money_fund'`（显式归类）；
  2. market 域 funds 名录 `fund_types.name = '货币型'`（权威，含 511/000 等无稳定
     代码段前缀的场内外货基）；
  3. 代码段兜底（#1661 收紧）：**必须**带明确交易所前缀才成立——`SZ` + `1[01]xxxx`
     （深市货币基金/现金管理）、`SH` + `97xxxx`（沪市现金管理产品）。
     裸 6 位数字与其它前缀一律不判货基：场外基金代码由证监会独立分配，与交易所
     代码段无关（`100016` 富国天源沪港深平衡混合、`110001` 易方达平稳增长混合
     都落在 `1[01]xxxx` 段内），且 `SH11xxxx` 是**可转债**不是货基。
  名录一旦有该代码即以名录为唯一依据（可否决代码段兜底）。
- reverse_repo 与货基同属「现金等价物」聚合桶；分类统一由
  `effective_count_as_investment()`（见 `docs/working-notes/cash-equivalent-classification-design-2026-09-07.md`）判定，
  二期逆回购拆出为投资亦只改该函数一处。

详见 `docs/working-notes/cash-equivalent-classification-design-2026-09-07.md`（#863 口径已并入）。
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterable
from datetime import date

# 市场消歧唯一入口（#1661）：代码段兜底必须先拿到交易所，不能只看裸 6 位数字。
from app.core.symbol_utils import split_symbol

# 现金等价物资产类型（聚合桶：货基 + 逆回购；逆回购拆出时只改这里）
CASH_EQUIVALENT_ASSET_TYPES = ('money_fund', 'reverse_repo')

# market 域基金名录中的货币型小类名（fund_types.name）
_MONEY_FUND_TYPE_NAME = '货币型'

# 代码段兜底（#1661）：拆成两条**带交易所约束**的规则，绝不能合成一条裸代码正则。
#
# 为什么必须带交易所：`1[01]xxxx` / `97xxxx` 这两个段里，除了深市货币基金/沪市现金
# 管理产品，还塞满了**场外基金**代码（证监会独立分配，与交易所代码段无关）：
#   100016 富国天源沪港深平衡混合、100018 富国天利增长债券、100051 富国可转债、
#   110001 易方达平稳增长混合、110003 易方达上证50增强、970067 兴证资管金麒麟
#   消费升级混合、970185 招商资管核心优势混合……
# 实测：本机 `funds` 名录里命中 `1[01]xxxx|97xxxx` 的 106 个代码中，**0 个**是「货币型」。
# 另：`SH11xxxx` 是**沪市可转债**（110067 华安转债、113050 南银转债），同样落在该段内。
# 511 等场内货币 ETF 无稳定代码段，必须依赖名录判定，避免 51 前缀误伤普通 ETF/LOF。
_SZ_MONEY_FUND_RE = re.compile(r'^1[01]\d{4}$')
_SH_MONEY_FUND_RE = re.compile(r'^97\d{4}$')

# market 名录查询结果 TTL（秒）：写路径低频，5 分钟足够；聚合层不经过此缓存。
# 缓存的是**名录类型名**（与调用方传入的 symbol 形态无关，#1661），不是最终布尔结论——
# 结论还取决于 symbol 是否带交易所前缀，缓存结论会让 `SZ111000` 与裸 `111000` 互相污染。
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_SIZE = 4096
# 名录查询结果的两种「非货币型」，必须与「查不到」区分（#1661）：
#   名录**有**该代码但 fund_type_id 为空 → _TYPE_UNKNOWN（类型未知，不猜为货基）
#   名录**无**该代码                  → _NOT_IN_MARKET（允许落到代码段兜底）
_TYPE_UNKNOWN = '\x00type-unknown'
_NOT_IN_MARKET = '\x00absent'

_cache: dict[str, tuple[float, str]] = {}


def normalize_fund_code(symbol: str) -> str:
    """剥离交易所前缀，返回 6 位基金代码（兼容 SZ/SH/BJ 前缀及 sh.510300 / 510300.SH 等带分隔符表达）。"""
    s = (symbol or '').strip().upper()
    if '.' in s:
        s = s.replace('.', '')
    # 去掉首尾交易所代码（SH/SZ/BJ），保留中间 6 位代码
    if len(s) > 6 and s[:2] in ('SH', 'SZ', 'BJ'):
        s = s[2:]
    if len(s) > 6 and s[-2:] in ('SH', 'SZ', 'BJ'):
        s = s[:-2]
    return s[-6:] if len(s) >= 6 and s[-6:].isdigit() else ''


def _code_segment_fallback(symbol: str) -> bool:
    """代码段兜底（#1661）：先解析出交易所，再按该交易所专属代码段判定。

    - 深市货币基金 / 现金管理：`SZ` + `1[01]xxxx`
    - 沪市现金管理产品：`SH` + `97xxxx`

    裸 6 位数字经 `market_of_cn_a_code` 推断交易所（推断不出即 False）；带前缀的
    取前缀。判段只认「本交易所的段」，因此 `SH110067`（沪市可转债）与 `SZ128145`
    （深市可转债）都不会命中。
    """
    market, code = split_symbol(symbol)
    if market == 'SZ':
        return bool(_SZ_MONEY_FUND_RE.match(code))
    if market == 'SH':
        return bool(_SH_MONEY_FUND_RE.match(code))
    return False


def _lookup_market_type_names(codes: list[str]) -> dict[str, str]:
    """跨域查 market 域 funds 名录：`{fund_code: fund_types.name}`。

    用 **outer join**（原来 inner join + `name == '货币型'` 只回「命中集」，无法区分
    「名录有该代码但不是货基」与「名录根本没有」）：
    - 有记录且类型已知 → 类型名；
    - 有记录但 `fund_type_id` 为空 → `_TYPE_UNKNOWN`；
    - 无记录 → `_NOT_IN_MARKET`。
    """
    from app.core.db_factory import market_session_factory
    from app.domains.funds.models import Fund, FundType

    session = market_session_factory()()
    try:
        rows = (
            session.query(Fund.fund_code, FundType.name)
            .outerjoin(FundType, Fund.fund_type_id == FundType.id)
            .filter(Fund.fund_code.in_(codes))
            .all()
        )
    finally:
        session.close()
    found = {row[0]: (row[1] or _TYPE_UNKNOWN) for row in rows}
    return {c: found.get(c, _NOT_IN_MARKET) for c in codes}


def resolve_money_fund_flags(symbols: Iterable[str]) -> dict[str, bool]:
    """批量解析「是否货币型」（写路径用），返回 `{归一化代码: bool}`。

    入参是**原始 symbol**（可带 `SZ`/`SH`/`BJ` 前缀），返回键为归一化后的 6 位代码。
    保留原始形态是必需的：代码段兜底要先判交易所（#1661）。

    判定顺序（与 `core/symbol_utils._get_asset_type` 同口径）：

    1. **market 名录有该代码 → 以名录类型为唯一依据**（`货币型` → True，其余 → False）。
       名录能否决代码段兜底：`110001` 名录为「混合型」→ False，不再被 `1[01]xxxx` 段误判。
       名录有记录但 `fund_type_id` 为空 → `_TYPE_UNKNOWN` → False（类型未知，不猜）。
    2. 名录**无该代码** → 代码段兜底，且必须带明确交易所（见 `_code_segment_fallback`）。
    3. market 域不可达（名录未初始化 / 跨域读异常）→ 全部退回代码段兜底，不阻断写路径；
       此时**不写缓存**，避免把「查不到」长期固化成结论。

    为什么「宁漏不误」（#1661 的取舍）：误判为货基会让 `position_price_job` 把
    `current_price` 按面值 1.0000 回写（`sync/jobs/position_price_job.py:293`），
    持仓市值塌成「份额数」——**数据损坏**；漏判只是把货基归到「基金投资」而非
    「现金等价物」——**分类/展示偏差**。故一律偏向漏判。
    """
    forms: dict[str, list[str]] = {}
    for s in symbols:
        if not s:
            continue
        code = normalize_fund_code(s)
        if code:
            forms.setdefault(code, []).append(s)
    if not forms:
        return {}

    now = time.time()
    stale = [c for c in forms if (hit := _cache.get(c)) is None or now - hit[0] >= _CACHE_TTL_SECONDS]
    if stale:
        try:
            looked_up = _lookup_market_type_names(sorted(stale))
        except Exception:
            # market 域不可达（如名录未初始化）时降级代码段兜底，不阻断写路径
            looked_up = None
        if looked_up is not None:
            for c in stale:
                _cache[c] = (now, looked_up[c])

    result: dict[str, bool] = {}
    for c, ss in forms.items():
        hit = _cache.get(c)
        if hit is None or hit[1] == _NOT_IN_MARKET:
            # 名录不可达 / 名录无该代码 → 代码段兜底（同一代码的任一形态命中即算命中）
            result[c] = any(_code_segment_fallback(s) for s in ss)
        else:
            result[c] = hit[1] == _MONEY_FUND_TYPE_NAME

    _trim_cache(now)
    return result


def _trim_cache(now: float) -> None:
    """容量上限：长生命周期进程下避免 _cache 无界增长（过期键优先淘汰，其次 FIFO）。"""
    if len(_cache) <= _CACHE_MAX_SIZE:
        return
    # 先淘汰已过期条目：避免过期键残留、活跃长生命周期键被 FIFO 误逐（#1330 review）
    for k in [k for k, (ts, _v) in _cache.items() if now - ts >= _CACHE_TTL_SECONDS]:
        _cache.pop(k, None)
    # 仍溢出则按插入顺序（FIFO）淘汰最旧项至容量上限
    while len(_cache) > _CACHE_MAX_SIZE:
        _cache.pop(next(iter(_cache)), None)


def is_money_fund_symbol(symbol: str, asset_type: str | None = None) -> bool:
    """单代码便捷判定：显式类型直接决定，否则名录/兜底解析。

    显式 asset_type 优先——'money_fund' 命中、其它显式类型（如 'bond'）直接返回 False，
    避免兜底解析覆盖显式分类造成误判。
    """
    if asset_type:
        return asset_type == 'money_fund'
    # 传**原始 symbol**（不是归一化代码）：代码段兜底需要前缀来判交易所（#1661）
    return resolve_money_fund_flags([symbol]).get(normalize_fund_code(symbol), False)


def is_money_fund_position(position) -> bool:
    """聚合分类：该持仓是否货币型（冗余标记优先，asset_type 兜底）。零跨域。

    适用于从 DB 加载的完整 Position ORM 对象；若调用方只查询了部分列且两字段均
    缺失，返回 False（归「基金投资」侧），调用方需自行保证列加载。
    """
    flag = getattr(position, 'is_money_fund', None)
    if flag is not None:
        return bool(flag)
    return getattr(position, 'asset_type', None) == 'money_fund'


def effective_count_as_investment(position, as_of_date: date | None = None) -> bool:
    """该持仓是否计入「投资」（与 should_exclude_from_investment 互补）。

    分类 / 聚合层判定唯一入口（#1354 消弭方案，决策 #7）：饼图分桶、TNA、类现金统计均改调本函数
    （及 should_exclude_from_investment 反向视图），替代原先打架的 EXCLUDED_ASSET_TYPES
    与 CASH_EQUIVALENT_ASSET_TYPES。

    注意：收益层（XIRR）**不**走本函数。XIRR 引擎改用 EXCLUDED_ASSET_TYPES 硬隔离，
    货基 / 逆回购无论 count_as_investment 如何都隔离在 INTEREST 桶，绝不混入 CAPITAL_GAIN
    分母（#1354 决策 #4 / 设计文档 §3.4）。两套机制正交。

    判定：
      1. 非货基/逆回购/cash → 永远算投资。
      2. cash → 永远不算投资（现金不是投资）。
      3. 货基（含 is_money_fund 标记）→ 默认不算投资；仅当用户显式 count_as_investment==True 才纳入。
      4. 逆回购 → override（count_as_investment）优先；缺失则按 maturity_date 动态判定：
         未到期 → 算投资；已到期（含到期当日）→ 自动变现金（不算投资）。
         maturity_date 缺失（防御，导入应已校验必填）→ 默认算投资。

    as_of_date 缺省取今天，为逆回购「已到期」判定提供时间基准。
    """
    asset_type = getattr(position, 'asset_type', None)
    is_mf = bool(getattr(position, 'is_money_fund', False)) or (asset_type == 'money_fund')
    is_rr = asset_type == 'reverse_repo'
    is_cash = asset_type == 'cash'
    if not (is_mf or is_rr or is_cash):
        return True  # 非类现金 → 永远算投资
    if is_cash:
        return False  # 现金永远是现金
    # 货基 / 逆回购：显式覆盖优先
    override = getattr(position, 'count_as_investment', None)
    if override is not None:
        return bool(override)
    if is_mf:
        return False  # 货基默认现金（不算投资）
    # 逆回购：按到期日动态判定
    maturity = getattr(position, 'maturity_date', None)
    if maturity is None:
        # 决策#7：无 maturity_date 默认算投资；导入层应校验必填
        return True
    as_of = as_of_date or date.today()
    return as_of < maturity  # 未到期 → 算投资；到期当日即算现金


def should_exclude_from_investment(position, as_of_date: date | None = None) -> bool:
    """该持仓是否应从「投资组合分类 / 聚合（饼图 / TNA / 类现金统计）」中排除。

    分类 / 聚合层反向视图，等价于 `not effective_count_as_investment(position, as_of_date)`。
    唯一真理源（#1354 消弭方案，决策 #7）。

    ⚠️ 与收益层（XIRR）无关：XIRR 分母的现金等价物隔离由 xirr_engine 用 EXCLUDED_ASSET_TYPES
    硬实现，不受 count_as_investment 影响（#1354 决策 #4 / 设计文档 §3.4）。
    """
    return not effective_count_as_investment(position, as_of_date)


def is_cash_equivalent_position(position) -> bool:
    """聚合分类：该持仓是否现金等价物（货基 + 逆回购）。

    覆盖 is_money_fund（货基冗余标记）与 asset_type ∈ 现金等价物集合两条路，
    供分布/桑基图把这类持仓市值归入「现金/流动资金」桶（#863 口径 A）。
    """
    if getattr(position, 'asset_type', None) in CASH_EQUIVALENT_ASSET_TYPES:
        return True
    return bool(getattr(position, 'is_money_fund', False))


def is_cash_equivalent_asset_type(asset_type: str | None) -> bool:
    """该资产类型是否现金等价物（货基/逆回购）。"""
    return asset_type in CASH_EQUIVALENT_ASSET_TYPES
