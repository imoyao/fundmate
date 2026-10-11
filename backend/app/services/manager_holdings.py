# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/10
# File : manager_holdings.py
# app/services/manager_holdings.py
"""基金经理代表作的前十大重仓（#1970 扩展 · 详情页经理区块）。

## 回答什么问题

「这位经理**代表作**现在持有哪些股票」。它是 ``fund_holdings`` 的**读取出口** ——
``fund_holdings`` 此前只有 :mod:`app.services.penetration` 一个消费者，而那个是
**家庭级穿透**（把全家持仓打散重算行业暴露），回答不了「某经理怎么看」。

## 为什么选「代表作」而不是「全部在管基金」

一个经理管 20~42 只基金，全列重仓会让这一块从「看一眼」变成「读报表」，
且**没有信息增益**：多只基金的十大重仓高度重叠（同一经理同一策略），
堆20 份近乎重复的名单只是把首屏撑爆。故：

- **优先取 ``is_classic=True``** 的代表作；
- 没有标记代表作时，退化为**取任期最长的那只**（任期长 = 策略延续久 = 更有代表性）。

**绝不取「规模最大」那只**：规模大不等于代表作，且会与头部「管理规模」指标
读成同一件事，用户会以为看到的是同一个数。

## 口径：与 penetration 严格一致，不自造第二套

``holding_basis`` 有 ``full`` / ``top10`` 两套并存（实测季报只有 top10、
半年报/年报才全量），**不做单值覆盖**——合并会让季报数据莫名"缩水"，
被误读成大幅减仓。组内**优先 ``full``**，无 ``full`` 才用 ``top10`` 并据此打标，
与 :func:`app.services.penetration._load_holding_map` 同规则。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.services.penetration import BASIS_FULL

# 前十大重仓展示条数上限。重仓表本身按 rank 最多 10 条（全量口径可能更多，
# 但详情页只展示「十大」这一概念，超出部分没有展示位）。
DEFAULT_TOP_N = 10


def _pick_representative_fund(db: Session, mgr_id: int, fund_ids: List[int]) -> Optional[int]:
    """选代表作的 ``fund_id``：``is_classic`` 优先，否则取任期最长的那只。

    **为什么不用「规模最大」**：规模指标已在头部展示，用它挑代表作会让用户
    误以为看到的是同一个数字；而重仓解读真正关心的是「策略延续性」，任期长度
    才是该维度的代理。

    Args:
        mgr_id: 经理 id。
        fund_ids: 该经理关联的基金 id 列表（**已受 fund_limit 截断**）。

    Returns:
        代表作 ``fund_id``；无关联基金时返回 None。
    """
    from app.domains.funds.models import FundManager

    if not fund_ids:
        return None

    rows = (
        db.query(FundManager.fund_id, FundManager.is_classic, FundManager.start_date)
        .filter(FundManager.mgr_id == mgr_id, FundManager.fund_id.in_(fund_ids))
        .all()
    )
    if not rows:
        return None

    classics = [r.fund_id for r in rows if r.is_classic]
    if classics:
        return classics[0]

    # 无标记代表作 → **最早**任职的那只（任期最长 = 策略延续最久 = 最有代表性）。
    #
    # 两个易错点，写在这里防止后来者改回去：
    # 1. 必须 `min` 不是 `max` —— 任职**最早**的才是任期最长；
    # 2. 必须先剔除 `start_date` 为空的行。库内任期只对目标池回填，大量行为空，
    #    而空值参与比较会被判成"最早"而误选。全部为空时才退回第一只（无任期可比较，
    #    此时任何选择都是任意的，不如稳定取第一只以保证同一请求结果可复现）。
    dated = [r for r in rows if r.start_date is not None]
    if not dated:
        return rows[0].fund_id
    return min(dated, key=lambda r: r.start_date).fund_id


def build_manager_holdings(
    db: Session,
    mgr_code: str,
    fund_limit: int = 20,
    top_n: int = DEFAULT_TOP_N,
) -> Optional[Dict[str, Any]]:
    """某位经理代表作的前十大重仓。

    Args:
        db: market 域会话。
        mgr_code: ``managers.mgr_code``（**非姓名**，库内119 组重名）。
        fund_limit: 参与「选代表作」的候选基金条数上限（与 manager-profile 同参）。
        top_n: 返回条数上限。

    Returns:
        ``{fund_code, fund_name, report_period, report_date, basis, basis_label,
        total_ratio, rows[]}``；**经理不存在时返回 None**（由调用方转 404）。

    ``rows[]`` 每项：``{rank, stock_code, stock_name, ratio, market_value}``。

    ``basis_label`` 把 ``full`` / ``top10`` 翻成中文，**必须下发给前端**——
    用户看到「十大重仓」时需要知道这是季报口径（前十大）还是半年报全量，
    否则会把「只披露了 10 只」误读成「只买了 10 只」。
    """
    from app.domains.funds.models import Fund, FundManager, Manager

    code = (mgr_code or '').strip()
    if not code:
        raise ValueError('缺少 mgr_code')

    manager = db.query(Manager).filter(Manager.mgr_code == code).first()
    if manager is None:
        return None

    rel_rows = (
        db.query(FundManager.fund_id)
        .filter(FundManager.mgr_id == manager.id)
        .limit(fund_limit)
        .all()
    )
    fund_ids = [r.fund_id for r in rel_rows]
    representative_id = _pick_representative_fund(db, manager.id, fund_ids)
    if representative_id is None:
        return _empty('该经理无关联基金，无重仓数据')

    fund = db.query(Fund).filter(Fund.id == representative_id).first()
    if fund is None:
        return _empty('代表作记录缺失（基金已被删除）')

    record = _load_latest_holdings(db, fund.fund_code)
    if record is None:
        return _empty('该基金暂无重仓披露（未到披露期或抓取未覆盖）', fund_code=fund.fund_code, fund_name=fund.name)

    basis, holdings = record
    rows = sorted(holdings, key=lambda h: (h.rank if h.rank is not None else 999))[:top_n]

    return {
        'fund_code': fund.fund_code,
        'fund_name': fund.name,
        'report_period': rows[0].report_period if rows else None,
        'report_date': _iso(rows[0].report_date) if rows else None,
        'basis': basis,
        'basis_label': _BASIS_LABELS.get(basis, basis or '未知口径'),
        # 前十大合计占比：给用户一个「集中度」锚点。只在 top10 口径下有意义，
        # full 口径下是**全量合计**，故用 basis 区分，不改名以免前端误解。
        'total_ratio': round(sum(float(h.ratio) for h in rows if h.ratio is not None), 2) if rows else None,
        'rows': [
            {
                'rank': h.rank,
                'stock_code': h.stock_code,
                'stock_name': h.stock_name or None,
                'ratio': float(h.ratio) if h.ratio is not None else None,
                'market_value': float(h.market_value) if h.market_value is not None else None,
            }
            for h in rows
        ],
    }


def _empty(reason: str, fund_code: Optional[str] = None, fund_name: Optional[str] = None) -> Dict[str, Any]:
    """无数据时的**固定契约**返回（不返回 None，避免前端把「无数据」当「接口 404」）。

    保留 ``fund_code`` 等 key 的理由与 ``manager_profile`` 一致（#1400 通用约定）：
    前端拿到 key 才知道「这个位置本该有值、只是没数据」，从而降级为准确空态。
    """
    return {
        'fund_code': fund_code,
        'fund_name': fund_name,
        'report_period': None,
        'report_date': None,
        'basis': None,
        'basis_label': None,
        'total_ratio': None,
        'rows': [],
        'empty_reason': reason,
    }


def _load_latest_holdings(db: Session, fund_code: str):
    """取该基金**最新报告期**的重仓，返回 ``(basis, rows)``；无数据返回 ``None``。

    口径优先级（与 :func:`app.services.penetration._load_holding_map` 一致）：
    组内优先 ``full``，无 ``full`` 才用 ``top10``。
    """
    from app.domains.funds.models import FundHolding

    rows = (
        db.query(FundHolding)
        .filter(FundHolding.fund_code == fund_code)
        .order_by(FundHolding.report_period.desc())
        .all()
    )
    if not rows:
        return None

    latest_period = rows[0].report_period
    same_period = [r for r in rows if r.report_period == latest_period]

    full = [r for r in same_period if r.holding_basis == BASIS_FULL]
    chosen = full or same_period
    basis = BASIS_FULL if full else (chosen[0].holding_basis or 'unknown')
    return basis, chosen


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    return value.isoformat()


#: ``holding_basis`` → 中文标签。**必须下发给前端**（理由见函数 docstring）。
_BASIS_LABELS = {
    BASIS_FULL: '全量披露（半年报/年报）',
    'top10': '前十大（季报）',
}
