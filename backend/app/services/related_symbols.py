# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : related_symbols.py
# app/services/related_symbols.py
"""跨渠道关联标的（#1976 · 产品详情页关联标的区块）。

同一底层资产常在多个渠道有同义标的：指数 / 场内 ETF / 场外联接基金。
``channel_links`` 存**有向**关系（``index_etf`` 指数→ETF、``etf_feeder`` ETF→联接），
本服务按裸代码**双向查**，对任一端都返回「另一侧」清单，前端无需判断方向。

## 为什么不复用 watchlist_display._apply_channel_link_fields

逻辑确实同源（同一张表、同一套双向规则），但它挂在**自选域的展示 enrich** 链上，
签名是「往 ``out`` dict 里塞字段」，是列表页批量 enrich 的一环。详情页是单标的按需取数
（数据策略：L4 关联关系类按需取 + 可降级），走自选域会：

- 让详情页依赖自选域的 enrich 链，破坏域边界；
- 复用不到它的批量语义（这里是单 symbol 查询）。

故独立成 service，取数规则保持一致（裸代码 + 双向），并在文档里互相指认。

## 覆盖率的诚实说明

关系靠**名称匹配**建立（实测 akshare ``fund_etf_spot_em`` 无「跟踪标的」字段），
落库口径覆盖率约 66.4%；跨境 / 商品 ETF 的跟踪标的不在 ``index_catalog`` 内，
缺口见 #1419。故：

- 无关联时返回 ``links: []``，前端渲染 ``—``，**不用「0 个」**（与全表约定一致）；
- 不返回「已知关联 N 条 / 覆盖率」这类容易被读成完整性的数字，避免误导。
"""

from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

# 裸代码最大长度：ETF / 联接基金 6 位，指数可能带后缀（如 931637），留余量到 10
MAX_BARE_CODE_LEN = 10


def _bare_code(symbol: str) -> str:
    """``SH000300`` / ``CSI930950`` / ``OF000001`` → ``000300`` / ``930950`` / ``000001``。

    ``channel_links`` 按**裸代码**存储（自选行symbol 前缀形态不统一：SH/CSI/SZ/OF…），
    故统一抽数字部分。

    注意不能用 ``str.isdigit()`` 之外的花样：混了 ``NDX``、``.WI`` 之类会引入脏匹配。
    """
    return ''.join(ch for ch in (symbol or '') if ch.isdigit())


def _label_for(link_type: str, self_is: str) -> str:
    """关联标的的分组标签，如「同标的 ETF」「场外联接」。

    ``self_is`` 标明**本标的**在这条关系里的角色（``index`` / ``etf`` / ``feeder``），
    用于决定「另一侧」该怎么称呼——对 ETF 而言指数是「跟踪指数」，反过来则是「同标的 ETF」。
    """
    if link_type == 'index_etf':
        return '同标的 ETF' if self_is == 'index' else '跟踪指数'
    return '场外联接' if self_is == 'etf' else '场内 ETF'


def _role_of(link_type: str, self_is_from: bool) -> str:
    """本标的在该关系中的角色。

    ``index_etf`` 的 from 是指数、to 是 ETF；``etf_feeder`` 的 from 是 ETF、to 是联接。
    """
    if link_type == 'index_etf':
        return 'index' if self_is_from else 'etf'
    return 'etf' if self_is_from else 'feeder'


def build_related_symbols(db: Session, symbol: str) -> Dict[str, Any]:
    """查一个标的的跨渠道关联清单。

    Args:
        db: market 域会话。
        symbol: 标准化 symbol（``SH510300``）或裸代码均可。

    Returns:
        ``{'links': [...], 'groups': [...]}``；**无关联时 links 为空列表**（前端降级 ``—``）。
        每个 link 形状：``{code, name, link_type, label}``。
    """
    from sqlalchemy import or_

    from app.domains.funds.models import ChannelLink

    code = _bare_code(symbol)
    if not code or len(code) > MAX_BARE_CODE_LEN:
        return {'links': [], 'groups': []}

    rows = (
        db.query(ChannelLink)
        .filter(
            or_(
                ChannelLink.from_symbol == code,
                ChannelLink.to_symbol == code,
            )
        )
        .all()
    )
    if not rows:
        return {'links': [], 'groups': []}

    links: List[Dict[str, Any]] = []
    for r in rows:
        # 有向表存 from→to；对任一端都返回「另一侧」，前端无需判断方向
        if r.from_symbol == code:
            other_code, other_name, self_is_from = r.to_symbol, r.to_name, True
        else:
            other_code, other_name, self_is_from = r.from_symbol, r.from_name, False

        links.append(
            {
                'code': other_code,
                'name': other_name or None,
                'link_type': r.link_type,
                'label': _label_for(r.link_type, _role_of(r.link_type, self_is_from)),
                # #1974：另一端的**品类**。前端要按它决定跳`/etf/` 还是 `/fund/`
                # （#1976 时期一律跳 `/fund/`，把场内 ETF 错标成了场外基金）。
                # 不让前端靠 `label` 文案反推——文案是给人看的，不是数据。
                'peer_role': _role_of(r.link_type, not self_is_from),
            }
        )

    # 排序：先按关系类型再按代码，保证同一标的多次刷新顺序稳定（不闪烁）
    links.sort(key=lambda x: (x['link_type'], x['code']))

    return {'links': links, 'groups': _group_labels(links)}


def _group_labels(links: List[Dict[str, Any]]) -> List[str]:
    """按出现顺序去重后的分组标签（用于前端分区展示）。"""
    seen: List[str] = []
    for item in links:
        label = item['label']
        if label not in seen:
            seen.append(label)
    return seen
