# -*- coding: utf-8 -*-
r"""交易场所（venue）的单一权威定义（#1662）。

## 两个维度必须分清

- **market（市场）**：`SH` / `SZ` / `BJ` / `HK` / `US` / `CRYPTO`，由 `StockCodeNormalizer`
  从代码形态推断，描述「哪个交易所 / 哪个市场」。
- **venue（交易场所）**：`EXCHANGE`（场内，交易所撮合） / `OTC`（场外，基金直销 / 代销申赎），
  描述「这笔交易发生在哪类场所」。它与 market 正交：场外基金有市场归属（`CN_A`）却
  **没有交易所归属**。

## symbol 存储约定（落库前唯一权威，禁止各模块自行拼 / 剥前缀）

- `EXCHANGE` → `{MARKET}{CODE6}`，如 `SH600519` / `SZ159915` / `SH113050`；
- `OTC`      → **裸 6 位码**，如 `004369` / `110001`（不加任何前缀）；
- 无交易场所实体（经理 `MGR_*` / 投顾组合 / 指数 `CSI*`、`CNI*`）→ 空串 `''`。

## 为什么 OTC 必须是裸码，且禁止「猜」交易所

场外基金代码由证监会独立分配，与交易所代码段**共用同一数字空间**：
`000651` 既是格力电器（深市股票）也是某只货基；本机 `securities` 名录里与某只货基
6 位数字完全相同的证券有 **111 条**（格力电器 / 长安汽车 / 长春高新 / 徐工机械…）。
因此「靠 6 位数字推断交易所」在 OTC 路径上**必然误判**（实测：场外货基 `004369`
被推成 `SZ004369` → 被判定为深市股票；`121011` 被推成 `SZ121011` → 深市可转债），
后果是后续取数按错误市场要行情、静默落空。

结论：**归一化器不许猜 venue**。调用方（建仓 API / 导入解析器 / 自选）本来就明确知道
这笔操作的场所，必须**显式传入**；只有 EXCHANGE 路径才允许做市场推断（那是它的职责）。

## asset_type → venue 的映射

本仓当前 `asset_type` 与 venue **不是全函数关系**（同一个 asset_type 可能落在不同场所，
已证例外见下），故下表只作**兼容缺省**：未显式传 venue 时按它推断，凡与缺省不一致的场景
（场内货基、场内 LOF）调用方**必须显式传 venue**，不能让本模块猜。

    fund       → OTC                 （场外公募申购；场内 LOF 走 etf）
    money_fund → OTC                 （**缺省取场外**：场外货基是主流；场内货基见下）
    stock / etf / bond / reverse_repo → EXCHANGE（交易所撮合）
    manager / portfolio / index → ''  （无交易场所，不进 positions）

⚠️ **asset_type → venue 不是全函数**（本模块最容易踩的坑），已证的例外：

   - **场内货基**：`970164 银河水星现金添利` 属 SH 场内货基段（`^97\d{4}$`），
     asset_type 是 `money_fund` 却属 EXCHANGE。故 `VENUE_ASSET_TYPES[EXCHANGE]`
     必须**双向覆盖** `money_fund`（读侧反查才不会漏掉既有场内货基行）；而
     `venue_of_asset_type` 对 `money_fund` 只能给 OTC 这个**缺省值** ——
     场内货基的写入**必须显式传 venue**。
   - **场内 LOF**：语义是 `fund` 却走交易所撮合。

结论：asset_type 推断只作**兼容缺省**。凡场所与缺省不一致（场内货基、场内 LOF），
调用方必须显式传 venue，不能让本模块猜（AGENTS.md「靠数字猜品种」教训的同一条）。
"""

from __future__ import annotations

import re

# ── venue 取值（唯一权威字符串，禁止在业务代码里手写 'OTC' / 'EXCHANGE'）──
EXCHANGE = 'EXCHANGE'
OTC = 'OTC'
NO_VENUE = ''

VENUE_LABELS: dict[str, str] = {
    EXCHANGE: '场内',
    OTC: '场外',
    NO_VENUE: '',
}

VENUE_VALUES: tuple[str, ...] = (EXCHANGE, OTC)

# 场内货基（沪市现金管理）：`SH970164` 银河水星现金添利 —— asset_type 是货基、场所却是交易所。
# 这是 `asset_type → venue` 唯一一处「缺省必然判错」的例外，故给一条**显式代码段规则**兜底
# （不是「猜」：97xxxx 段由交易所分配，判据确定）。与 `services/fund_utils._CODE_FALLBACK_RE`
# 的「沪市现金管理 97xxxx」同源；`scripts/audit_symbol_venue_conformance.py` 亦以此为准。
SH_EXCHANGE_MONEY_FUND_RE = re.compile(r'^SH97\d{4}$')

# asset_type → venue 的**缺省**推断表（非全函数，见模块 docstring）
_OTC_ASSET_TYPES: tuple[str, ...] = ('fund', 'money_fund')
_EXCHANGE_DEFAULT_ASSET_TYPES: tuple[str, ...] = ('stock', 'etf', 'bond', 'reverse_repo')
_NO_VENUE_ASSET_TYPES: tuple[str, ...] = ('manager', 'portfolio', 'index')

# venue → 该场所**可能**出现的 asset_type（读侧反查存量行用，必须双向覆盖）：
# EXCHANGE 额外含 `money_fund` —— 场内货基（`^97\d{4}$`）资产类型是货基但属交易所；
# 漏掉它，_find_existing_position 就找不到既有场内货基行 → 每次写入新建重复持仓。
VENUE_ASSET_TYPES: dict[str, tuple[str, ...]] = {
    OTC: _OTC_ASSET_TYPES,
    EXCHANGE: (*_EXCHANGE_DEFAULT_ASSET_TYPES, 'money_fund'),
    NO_VENUE: _NO_VENUE_ASSET_TYPES,
}


def is_valid_venue(venue: str | None) -> bool:
    """venue 是否合法（大小写不敏感，命中 EXCHANGE / OTC）。空值视为不合法。"""
    if not venue:
        return False
    return venue.strip().upper() in VENUE_VALUES


def normalize_venue(venue: str | None) -> str:
    """venue 规范化为大写；`None` / 空串 → 空串；非空非法值抛 ValueError。

    与 `asset_types.normalize_asset_type` 同体例：写时归一，消除大小写漂移。
    """
    if not venue:
        return NO_VENUE
    normalized = venue.strip().upper()
    if normalized not in VENUE_VALUES:
        raise ValueError(f'非法 venue: {venue!r}，应为 core/venues 的 VENUE_VALUES 之一（EXCHANGE / OTC）')
    return normalized


def venue_of_asset_type(asset_type: str | None) -> str:
    """asset_type → venue（缺省推断，兼容未显式传 venue 的历史调用）。

    只用于**缺省**：调用方明确知道场内 / 场外时应直接传 venue。未知 / 空 asset_type
    返回空串（不猜）。
    """
    if not asset_type:
        return NO_VENUE
    lowered = asset_type.strip().lower()
    if lowered in _OTC_ASSET_TYPES:
        return OTC
    if lowered in _EXCHANGE_DEFAULT_ASSET_TYPES:
        return EXCHANGE
    return NO_VENUE


def resolve_venue(venue: str | None, asset_type: str | None) -> str:
    """确定一笔写入的 venue：显式 venue 优先，缺失时按 asset_type 推断。

    显式 venue 非法 → 抛 ValueError（宁可报错也不要落错形态）；都拿不到 → 空串。
    """
    if venue:
        return normalize_venue(venue)
    return venue_of_asset_type(asset_type)


def asset_types_of_venue(venue: str | None) -> tuple[str, ...]:
    """venue → 该场所的 asset_type 集合（读侧反查存量行用；空串返回四类实体之外的集合）。"""
    return VENUE_ASSET_TYPES.get(normalize_venue(venue) if is_valid_venue(venue) else NO_VENUE, ())


def venue_of_row(symbol: str | None, asset_type: str | None, declared_venue: str | None = None) -> str:
    """**一行存量数据**的 venue：显式声明 > 场内货基特例 > asset_type 缺省推断（#1662 后续）。

    与 `resolve_venue`（写侧）的分工：`resolve_venue` 服务**新写入**，调用方明确知道场所；
    本函数服务**已在库里的行**（回填 / 审计 / 读侧反查），此时唯一的信号是行上已有的字段。
    两者共用同一张 `asset_type → venue` 表与同一条场内货基特例，口径不会分叉。

    `declared_venue` 非空且合法时**优先**（watchlist 有 venue 列，写入侧早已携带）；
    非法显式值不抛错而是**降级**到推断 —— 存量数据里可能有脏值，审计脚本要能把它们报出来，
    而不是在审计途中直接崩掉。

    判不出场所时返回空串 `NO_VENUE`（不猜）。
    """
    if declared_venue:
        normalized = str(declared_venue).strip().upper()
        if normalized in VENUE_VALUES:
            return normalized
    if SH_EXCHANGE_MONEY_FUND_RE.match((symbol or '').strip().upper()):
        return EXCHANGE
    return venue_of_asset_type(asset_type)


def get_venue_label(venue: str | None) -> str:
    """venue → 中文标签；空值返回空串，未知值原样返回。大小写不敏感（与 normalize_venue 同语义）。"""
    if not venue:
        return ''
    normalized = venue.strip().upper()
    return VENUE_LABELS.get(normalized, venue)
