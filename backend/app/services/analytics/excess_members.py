# -*- coding: utf-8 -*-
# Author : imoyao
"""组合级超额聚合的成员规范化：空成员剔除 + 新建成员的期初基线归零。

## 两个真实缺陷（2026-11-14 真库实测，组合 1 / 6 个成员）

`build_scope_excess` 的组合分支沿用「Σ成员盈亏 ÷ Σ成员区间前一日净资产」，
并对**任一**成员 `range_baseline is None` 一律整组降级（`baseline_missing`）。
这在成员集合稳定的短窗口里没问题，但一次都躲不过下面两种形态：

1. **清仓后闲置的旧成员**（账本 2024-06 全部清仓，112 个持仓 quantity=0）：
   区间内无持仓 ⇒ 引擎回 `_empty_payload`（`range_baseline=None`、`total_positions=0`）
   ⇒ 整个组合的超额走势与卡片**永久降级**，连「近1月」都是 0 点。
   它的贡献恒为 0（没持仓就没有盈亏），跳过不改变结果。
2. **区间中途才加入的新成员**（账本 2026-01-28 首笔）：区间前一日它还没有资产，
   `range_baseline=None` 且 `total_positions>0` ⇒ 同样整组降级。
   但它的期初资产**就是 0**——组合收益率 = Σ区间盈亏 ÷ Σ期初资产，新成员对分母的
   贡献为 0、对分子的贡献是它自己的盈亏，这是数学上正确的组合口径，不是造数。
   两种形态都算「新」：有买入流水的（`first_txn_date`）、只有导入持仓的
   （`positions.snapshot_date` 锚点，账本 21 那样零买入流水、只有分红）。

## 与「真缺口」的边界（这条不能含糊）

只有**能证明「区间首日之前它的资产还不存在」**（流水日 / 持仓锚点日都不早于区间
首日）的新成员，才把基线归 0。其余 `baseline is None` 一律原样保留 ⇒ 整组继续降级：

- 老成员缺净值 / 缺价日 ⇒ 分母不完整，用剩下的人算等于用部分成员冒充整个组合；
- 两种存在性证据都没有（无流水、无锚点）却有持仓 ⇒ 流水与持仓错配（#1916 一类），
  无从判断，宁可降级也不猜。
"""

from typing import Dict, Optional

from sqlalchemy import func

from app.domains.positions.models import Position


def _anchor_dates(db, family_id: int, member_ids) -> Dict[int, str]:
    """成员的持仓快照锚点日（`positions.snapshot_date` 最早一天）。

    导入型持仓（`upsert_from_holding`：写快照数量 + 锚点日，**没有买入流水**）只有
    这个字段能证明「它是哪天开始存在的」。真库组合 1 的账本 21 就是这种形态：
    30 笔持仓、21 笔分红、**零买入流水** ⇒ `first_txn_date` 恒 None。它 2026-08-12
    之前每日净资产皆 NULL、之后才有值——锚点与引擎的可算起点严格一致。
    """
    if not member_ids:
        return {}
    rows = (
        db.query(Position.ledger_id, func.min(Position.snapshot_date))
        .filter(
            Position.family_id == family_id,
            Position.ledger_id.in_(list(member_ids)),
            Position.snapshot_date.isnot(None),
        )
        .group_by(Position.ledger_id)
        .all()
    )
    return {lid: str(anchor)[:10] for lid, anchor in rows if anchor}


def _member_start(payload: dict, anchor: Optional[str]) -> Optional[str]:
    """成员「资产起点」：首笔改变份额的流水日与持仓锚点日里更早的那个。

    两者都是**存在性证据**，谁是更早的还得看数据（老账户历史买入 + 后来一次导入）。
    都没有 ⇒ None（无从判断，调用方必须保持降级，不许猜）。
    """
    dates = [str(d)[:10] for d in (payload.get('first_txn_date'), anchor) if d]
    return min(dates) if dates else None


def _starts_after(payload: dict, anchor: Optional[str], start_date: Optional[str]) -> bool:
    """该成员的资产起点是否不早于区间首日（= 区间内才建仓 / 才导入持仓）。"""
    if not start_date:
        return False
    begin = _member_start(payload, anchor)
    return bool(begin) and begin >= str(start_date)[:10]


def normalize_member_payloads(
    payload_by_id: Dict[int, dict],
    start_date: Optional[str] = None,
    anchor_by_id: Optional[Dict[int, str]] = None,
) -> Dict[int, dict]:
    """规范化组合成员的逐日载荷（纯函数：不查库、不改入参、顺序保持）。

    - `baseline is None` 且区间内无持仓 ⇒ **剔除**（清仓空成员，贡献恒 0）；
    - `baseline is None` 但可证明「区间内才有资产」⇒ 基线归 **0.0**（期初无资产）；
    - 其余原样保留（含真缺口，仍会让整组降级）。

    `anchor_by_id` = 成员持仓锚点日（见 `_anchor_dates`），缺省 None 时只认流水。
    """
    anchors = anchor_by_id or {}
    kept: Dict[int, dict] = {}
    for ledger_id, payload in payload_by_id.items():
        coverage = payload.get('coverage') or {}
        has_position = bool(coverage.get('total_positions'))
        if payload.get('range_baseline') is None:
            if not has_position:
                continue
            if _starts_after(payload, anchors.get(ledger_id), start_date):
                kept[ledger_id] = {**payload, 'range_baseline': 0.0}
                continue
        kept[ledger_id] = payload
    return kept


def build_member_payloads(
    db,
    family_id: int,
    member_ids,
    start_date: Optional[str],
    end_date: Optional[str],
) -> Dict[int, dict]:
    """组合级聚合的唯一入口：逐成员取逐日载荷 → 规范化。

    取数保持**顺序**（SQLite 下并发写物化会争锁，收益不抵风险）；重复的家庭级
    派生查询由 `request_memo` 在本次调用内复用（6 成员 5 年窗口实测 9.4s → 5.2s）。
    """
    # 延迟导入：`pnl_calendar` 会连带载入日历引擎与快照存储，模块级导入拉长冷启动
    from app.core.request_memo import request_memo
    from app.services.pnl_calendar import build_daily_pnl_series

    anchors = _anchor_dates(db, family_id, member_ids)
    with request_memo(db):
        raw = {lid: build_daily_pnl_series(db, family_id, start_date, end_date, ledger_id=lid) for lid in member_ids}
    return normalize_member_payloads(raw, start_date, anchors)
