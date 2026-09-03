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
- reverse_repo 与货基同属「现金等价物」聚合桶；若二期将逆回购拆出为投资，只改
  `CASH_EQUIVALENT_ASSET_TYPES` 一处。

详见 `docs/working-notes/money-fund-caliber-reconcile-replan-2026-09-02.md`（#863）。
"""

from __future__ import annotations

import re
import time
from collections.abc import Collection

# 现金等价物资产类型（聚合桶：货基 + 逆回购；逆回购拆出时只改这里）
CASH_EQUIVALENT_ASSET_TYPES = ('money_fund', 'reverse_repo')

# market 域基金名录中的货币型小类名（fund_types.name）
_MONEY_FUND_TYPE_NAME = '货币型'

# 代码段兜底：深市货币基金/现金管理(1[01]xxxx)、沪市现金管理(97xxxx)
# 注意：511 等场内货币 ETF 无稳定代码段，必须依赖名录判定，避免 51 前缀误伤普通 ETF/LOF。
_CODE_FALLBACK_RE = re.compile(r'^(?:1[01]\d{4}|97\d{4})$')

# market 名录查询结果 TTL（秒）：写路径低频，5 分钟足够；聚合层不经过此缓存
_CACHE_TTL_SECONDS = 300
_cache: dict[str, tuple[float, bool]] = {}


def normalize_fund_code(symbol: str) -> str:
    """剥离交易所前缀，返回 6 位基金代码（SZ/SH 前缀历史数据兼容）。"""
    s = (symbol or '').strip().upper()
    return s[2:] if s[:2] in ('SZ', 'SH') else s


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


def resolve_money_fund_flags(codes: Collection[str]) -> dict[str, bool]:
    """批量解析基金代码是否货币型（写路径用），返回 {code: bool}。

    - 命中 market 名录（货币型）→ True；
    - 名录缺失 → 代码段兜底；
    - 其余 → False。
    """
    codes = {normalize_fund_code(c) for c in codes if c}
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
