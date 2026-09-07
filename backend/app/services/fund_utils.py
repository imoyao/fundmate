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
  3. 代码段兜底：深市货币基金/现金管理 `1[01]xxxx`、沪市现金管理 `97xxxx`
     （与前端 `BuyForm.resolveFundAssetType` 一致；兜底仅覆盖名录缺失场景）。
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

# 现金等价物资产类型（聚合桶：货基 + 逆回购；逆回购拆出时只改这里）
CASH_EQUIVALENT_ASSET_TYPES = ('money_fund', 'reverse_repo')

# market 域基金名录中的货币型小类名（fund_types.name）
_MONEY_FUND_TYPE_NAME = '货币型'

# 代码段兜底：深市货币基金/现金管理(1[01]xxxx)、沪市现金管理(97xxxx)
# 注意：511 等场内货币 ETF 无稳定代码段，必须依赖名录判定，避免 51 前缀误伤普通 ETF/LOF。
_CODE_FALLBACK_RE = re.compile(r'^(?:1[01]\d{4}|97\d{4})$')

# market 名录查询结果 TTL（秒）：写路径低频，5 分钟足够；聚合层不经过此缓存
_CACHE_TTL_SECONDS = 300
_CACHE_MAX_SIZE = 4096
_cache: dict[str, tuple[float, bool]] = {}


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


def _code_segment_fallback(code: str) -> bool:
    return bool(_CODE_FALLBACK_RE.match(code))


def _query_market_money_fund_codes(codes: list[str]) -> set[str]:
    """跨域查 market 域 funds 名录：命中「货币型」小类的基金代码集。"""
    from app.core.db_factory import market_session_factory
    from app.domains.funds.models import Fund, FundType

    session = market_session_factory()()
    try:
        rows = (
            session.query(Fund.fund_code)
            .join(FundType, Fund.fund_type_id == FundType.id)
            .filter(Fund.fund_code.in_(codes), FundType.name == _MONEY_FUND_TYPE_NAME)
            .all()
        )
        return {row[0] for row in rows}
    finally:
        session.close()


def resolve_money_fund_flags(codes: Iterable[str]) -> dict[str, bool]:
    """批量解析基金代码是否货币型（写路径用），返回 {code: bool}。

    - 命中 market 名录（货币型）→ True；
    - 名录缺失 → 代码段兜底；
    - 其余 → False。
    """
    codes = {n for c in codes if c for n in [normalize_fund_code(c)] if n}
    if not codes:
        return {}
    now = time.time()
    result: dict[str, bool] = {}
    missing: list[str] = []
    for c in codes:
        hit = _cache.get(c)
        if hit is not None and now - hit[0] < _CACHE_TTL_SECONDS:
            result[c] = hit[1]
        else:
            missing.append(c)
    if missing:
        try:
            market_hits = _query_market_money_fund_codes(sorted(missing))
        except Exception:
            # market 域不可达（如名录未初始化）时降级代码段兜底，不阻断写路径
            market_hits = set()
        for c in missing:
            flag = c in market_hits or _code_segment_fallback(c)
            result[c] = flag
            _cache[c] = (now, flag)
    # 容量上限：长生命周期进程下避免 _cache 无界增长（命中项仍受 TTL 约束，淘汰仅触发重新解析）
    if len(_cache) > _CACHE_MAX_SIZE:
        # 先淘汰已过期条目：避免过期键残留、活跃长生命周期键被 FIFO 误逐（#1330 review）
        expired_keys = [k for k, (ts, _v) in _cache.items() if now - ts >= _CACHE_TTL_SECONDS]
        for k in expired_keys:
            _cache.pop(k, None)
        # 仍溢出则按插入顺序（FIFO）淘汰最旧项至容量上限
        while len(_cache) > _CACHE_MAX_SIZE:
            _cache.pop(next(iter(_cache)), None)
    return result


def is_money_fund_symbol(symbol: str, asset_type: str | None = None) -> bool:
    """单代码便捷判定：显式类型直接决定，否则名录/兜底解析。

    显式 asset_type 优先——'money_fund' 命中、其它显式类型（如 'bond'）直接返回 False，
    避免兜底解析覆盖显式分类造成误判。
    """
    if asset_type:
        return asset_type == 'money_fund'
    code = normalize_fund_code(symbol)
    return resolve_money_fund_flags([code]).get(code, False)


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
