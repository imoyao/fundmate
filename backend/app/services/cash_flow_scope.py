# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/11/27
# File : cash_flow_scope.py
# backend/app/services/cash_flow_scope.py

"""资金流动的作用域解析（family / ledger / portfolio 三级）—— 唯一出口。

## 为什么独立成文件

`cash_flow_service.py` 被 `scripts/guard_service_size.py` 冻结在 264 行（只减不增），
而三级作用域带来两件新事：参数自洽校验（`scope` 与 id 是否一致）+ 日序列来源分叉。
塞回主文件就是「往存量模块加职责」，故按 #2873 的拆法把解析下沉到这里，主文件只留聚合。

## 三级作用域的差别不只是过滤条件

| 作用域 | 成员账本 | 日净资产序列 |
|---|---|---|
| `ledger` | 单个（须属于本家庭） | `pnl_calendar.build_daily_pnl_series(ledger_id=…)` |
| `family` | 全家账本（`scope.family_ledger_ids`） | 同函数 `ledger_id=None`，家庭全量持仓 |
| `portfolio` | 组合成员（`scope.member_ledger_ids`） | `performance.twr.build_portfolio_daily_pnl_series`（Σ 成员） |

家庭级**刻意不用**「Σ 成员账本」自己合并：`build_daily_pnl_series` 的 `ledger_id=None`
本来就是家庭全量口径（家庭级 XIRR / 收益日历都走它）。自己合一份会多出一条
「任一成员某日缺数据 ⇒ 当天整体置缺」的规则，与收益日历对不上。

## `scope` 显式可省，但家庭级只能显式

- `scope=family` 是家庭级的**唯一入口**：它没有 id 可推断，而「两个 id 都不传」在
  #2616 的原始取舍里就是 400（静默回全家数据比报错更坏，用户会以为筛过了）；
- 旧调用点（账户页 / 组合页）不传 `scope`，按传入的 id 推断，行为与 #2681 完全一致；
- 显式 `scope` 与 id 必须自洽（说 family 就别带 id），否则 `ValueError` 由视图转 400
  —— 容忍矛盾参数会让「我要看组合、实际给了全家」这类错配静默生效。

⚠️ 内部划转抵消要求成员账本集合**完整**：账户级天然配不上对（A 的出金在 A 的集合里
没有对手），组合级 / 家庭级一次传全集才抵消（`cashflow_layers.pair_internal_transfers`）。
所以家庭级必须传全家账本 id，不能传 `None` 让下游「不过滤」——`collect_flows` 拿到空
集合会直接返回空流水，看起来像「这个家庭从没有过资金进出」。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.domains.ledgers.models import Ledger
from app.services.pnl_calendar import build_daily_pnl_series
from app.services.scope import ERR_MUTEX, family_ledger_ids, member_ledger_ids

#: 支持的作用域（顺序即报错文案里的顺序）
SCOPES = ('ledger', 'family', 'portfolio')

ERR_NEED_SCOPE = 'ledger_id、portfolio_id 或 scope=family 必填'


def _requested_scope(ledger_id: Optional[int], portfolio_id: Optional[int], scope: Optional[str]) -> str:
    """归一「作用域请求」：显式 `scope` 优先，缺省按传入的 id 推断，矛盾参数抛 `ValueError`。

    单独成函数的原因不只是可读：分支全堆在 `resolve_scope` 里会让它逼近圈复杂度闸门
    （NEW_FILE_LIMITS.max_cc = 20），而这两件事的判据本来就不同——这里判「参数怎么拼」，
    那里判「这个作用域能不能用」。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError(ERR_MUTEX)
    requested = (scope or '').strip().lower() or None
    if requested is None:
        if ledger_id is not None:
            return 'ledger'
        if portfolio_id is not None:
            return 'portfolio'
        raise ValueError(ERR_NEED_SCOPE)
    if requested not in SCOPES:
        raise ValueError(f'scope 参数非法，仅支持 {" / ".join(SCOPES)}')
    if requested == 'family' and (ledger_id is not None or portfolio_id is not None):
        raise ValueError('scope=family 时不能传 ledger_id / portfolio_id')
    if requested == 'ledger' and ledger_id is None:
        raise ValueError('scope=ledger 时必须提供 ledger_id')
    if requested == 'portfolio' and portfolio_id is None:
        raise ValueError('scope=portfolio 时必须提供 portfolio_id')
    return requested


def resolve_scope(
    db: Session,
    family_id: int,
    *,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    scope: Optional[str] = None,
) -> Tuple[str, List[int]]:
    """解析作用域 → ``(scope, 成员账本 id 列表)``；参数非法抛 `ValueError`（视图转 400）。

    账户不存在（含非本家庭）同样抛 `ValueError('账户不存在')`，与 #2616 同文案
    ——不区分「不存在」与「无权访问」，避免泄漏存在性。
    """
    requested = _requested_scope(ledger_id, portfolio_id, scope)

    if requested == 'ledger':
        owned = db.query(Ledger.id).filter(Ledger.id == ledger_id, Ledger.family_id == family_id).first()
        if owned is None:
            raise ValueError('账户不存在')
        return 'ledger', [ledger_id]
    if requested == 'portfolio':
        return 'portfolio', sorted(member_ledger_ids(db, family_id, portfolio_id))
    return 'family', sorted(family_ledger_ids(db, family_id))


def daily_series(
    db: Session,
    family_id: int,
    scope: str,
    *,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> dict:
    """按作用域取日净资产序列（家庭级 / 账户级同一函数，组合级 Σ 成员）。

    组合级把它放到函数内导入：`performance` 包在导入期会拉起一批计算模块，
    放模块顶端容易与 `pnl_calendar` 形成环（原在 `cash_flow_service` 里也是这么绕的）。
    """
    if scope == 'portfolio':
        from app.services.performance.twr import build_portfolio_daily_pnl_series

        return build_portfolio_daily_pnl_series(db, family_id, portfolio_id, start_date, end_date)
    scoped_ledger_id = ledger_id if scope == 'ledger' else None
    return build_daily_pnl_series(db, family_id, start_date, end_date, scoped_ledger_id)


def latest_market_value(days: Sequence[dict]) -> float:
    """日序列里**最后一个非空** `net_worth`：区间末日缺价时不能把资产报成 0。

    缺价日 `net_worth` 为 None（面板保持断线、不补 0），故从尾部往前取第一个有值的；
    一天都没有则 0.0（页面据此显示「暂无价格」而不是假的资产数）。
    """
    for day in reversed(days or []):
        if day.get('net_worth') is not None:
            return float(day['net_worth'])
    return 0.0


def derive_asset_totals(scope: str, totals: dict, market_value: float) -> dict:
    """把 L1 汇总 + 持仓市值合成「现金残差 / 净投入 / 期末资产 / 累计收益」。

    账户级 / 组合级：期末资产 = 持仓市值 + 现金残差（推导值），累计收益 = 期末资产 − 净投入。

    **家庭级不推导**（返回 null）——现金残差的前提是「这个集合里每个账户的入金都记全了」。
    账户级还能靠余额自证（真库实测微众银行残差 +7.1 万，与其实际现金余额对得上）；
    家庭合并后只要有一个账户漏记入金，残差就是大额负数，把「资产」算成负的
    （同一份真库数据：家庭残差 −34.2 万 ⇒ 期末资产 −8.2 万）。与其给一个负资产，
    不如让页面拿可靠的持仓市值报数（`market_value` 照常返回）。
    """
    net_invested = float(totals['net_invested'])
    if scope == 'family':
        return {'cash_residual': None, 'net_invested': net_invested, 'end_asset': None, 'total_return': None}
    cash_residual = float(totals['cash_residual'])
    end_asset = round(market_value + cash_residual, 2)
    return {
        'cash_residual': cash_residual,
        'net_invested': net_invested,
        'end_asset': end_asset,
        'total_return': round(end_asset - net_invested, 2),
    }
