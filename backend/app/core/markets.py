# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/10
# File : markets.py
# app/core/markets.py
"""市场（market）口径与归一。

## 为什么需要它：库里 market 有两套词表

同一个概念在两类表里存成了不同形态（2026-10-09 本机库实测）：

- `securities.market` / `positions.market` → **契约市场**（`CN_A` / `CN_HK` / `US` / `CRYPTO`），
  `positions` 155 行**全部**是 `CN_A`；
- `watchlist.market` → **normalizer 命名空间**（`SH` 13 行 / `SZ` 22 行 / `CN_A` 118 行，
  场内是交易所、场外与基金是 `CN_A`）。

**注意：后者不是脏值，不能"顺手统一"**。`cross_domain._join_key` 直接拿
`watchlist.market` 当跨域冗余键，`to_security_key` 的映射表 `_SECURITY_MARKET_BY_KEY_MARKET`
**只认 `SH` / `SZ` / `BJ` / `HK`**。把 `watchlist.market` 改成 `CN_A` 会让场内自选的
市场侧资料 / 估值**全部取不到**（2026-10-10 核实，写入侧归一方案据此撤回）。

而跨表口径不一致的**实际危害**在别处：详情页把 resolve 回来的 `SH` 当持仓过滤条件，
`Position.market == 'SH'` 恒不成立 → 「已持有」与「暂无持仓记录」同屏（#1969 P0）。

## 三条规则

1. **出口一律说契约市场**：`to_contract_market()` 是**出口**归一入口（resolve 返回前等）；
   **写入侧保持各表既有口径**（`watchlist` 存命名空间、`positions` 存契约市场），
   因为前者是跨域键的契约形态；
2. **读侧兼容两种形态**：`market_aliases()` 让查询同时命中 `CN_A` 与 `SH`/`SZ`，
   避免把「已自选」误判成未自选；
3. **symbol 前缀只用于推断，不能当存储值**——`SH`/`SZ` 这类形态来自 `symbol` 前缀，
   别把它们当成"市场"再传给别人算。
"""

from __future__ import annotations

# 交易所前缀（或历史脏值）→ 契约市场。**归一表的唯一真相源**。
EXCHANGE_PREFIX_TO_MARKET: dict[str, str] = {
    'SH': 'CN_A',
    'SZ': 'CN_A',
    'BJ': 'CN_A',
    'HK': 'CN_HK',
    'US': 'US',
    'CR': 'CRYPTO',
}

# 契约市场 → 该市场在**存量数据里出现过的全部形态**（含交易所别名）。
# 仅供读侧兼容；写入侧只写契约值，待数据迁移后别名即可退化为单值。
_MARKET_ALIASES: dict[str, tuple] = {
    'CN_A': ('CN_A', 'SH', 'SZ', 'BJ'),
    'CN_HK': ('CN_HK', 'HK'),
    'CRYPTO': ('CRYPTO', 'CR'),
}

# 契约市场取值集合（不含指数名录的中证/国证命名空间 CSI / CNI，那是独立维度）
CONTRACT_MARKETS: tuple[str, ...] = ('CN_A', 'CN_HK', 'US', 'CRYPTO')


def to_contract_market(market: str | None, symbol: str = '') -> str:
    """把任意市场形态归一为**契约市场**；入参为空时按 symbol 前缀补全。

    为什么空值也接受：手输 `/stock/600519` 这类入口本来就不带 market，此时按前缀
    推断是唯一可行的兜底（只读口径，不抛错）。识别不了就返回空串，由调用方决定
    是否兜底成 `UNKNOWN`——本函数**不编造**市场。
    """
    raw = (market or '').strip().upper()
    if not raw:
        return EXCHANGE_PREFIX_TO_MARKET.get((symbol or '')[:2].upper(), '')
    return EXCHANGE_PREFIX_TO_MARKET.get(raw, raw)


def market_aliases(contract_market: str) -> tuple:
    """契约市场 → 查询时需一并匹配的别名列表（含存量脏值形态）。

    读侧放宽而非写侧容忍：库里 `watchlist.market` 的历史值混着 `SH` / `SZ` / `CN_A`，
    查询只用契约值会**静默漏掉**存量行（归一后「已自选」反而被判成未自选）。
    """
    return _MARKET_ALIASES.get(contract_market, (contract_market,))
