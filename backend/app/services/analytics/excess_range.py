# -*- coding: utf-8 -*-
# Author : imoyao
"""基准超额曲线的区间左界解析（`start_date=inception` 哨兵）。

`/summary/benchmark-excess/` 的口径层（`analytics/benchmark_excess.build_scope_excess`）
只认具体日期——它要用同一个 `start` 同时算区间收益、指数涨跌幅与逐日曲线，任何
「相对区间」的含义在那里都必须先落成绝对日期。而前端「成立来」档发的是哨兵
`start_date=inception`：前端此刻并不知道作用域最早一笔流水，若先取一次再发第二次，
既多一轮请求（冷启动鸡生蛋），两次请求还会各算一遍区间口径而漂移。

故在本层把哨兵解析成绝对日期，口径层零改动：

1. 有流水 ⇒ 作用域最早一笔资金流水的生效日（`scope.first_investment_date`，
   **含出入金** —— 组合的第一笔入金就是它的起点，等第一笔买入会砍掉最开始那段）；
2. 无流水 ⇒ 回落到「近 90 天」窗口，并**如实把解析后的日期写回响应**。
   前端 caption 读的是响应里的 `start_date`，于是显示的是真实区间，
   不会把 90 天说成「成立来」（与 `cash_flow_service.DEFAULT_RANGE_DAYS`
   的兜底同纪律：宁可窗口短，不说假话）。

## 为什么单独一个模块

`domains/summary/views.py` 与 `analytics/benchmark_excess.py` 都在
`check_view_thickness.py` / `guard_service_size.py` 的冻结基线里（**只减不增**）。
把这段逻辑塞进任一处都只能靠删口径注释腾行——那会把「为什么不是先取起点」
这类判据挤掉，下一次改动就会有人把它改回去。新模块走 `NEW_FILE_LIMITS`，
反而让判据有地方写全。
"""

import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from app.services.scope import INCEPTION, first_investment_date

#: 无流水时的兜底窗口天数（与 `cash_flow_service.DEFAULT_RANGE_DAYS` 同值）
DEFAULT_RANGE_DAYS = 90


def _as_date(value: object, field: str) -> dt.date:
    """`YYYY-MM-DD` → date；格式错抛 ValueError（端点层映射 400，不静默兜底）。"""
    try:
        return dt.date.fromisoformat(str(value))
    except (ValueError, TypeError) as e:
        raise ValueError(f'{field} 格式须为 YYYY-MM-DD: {e}') from e


def resolve_scope_start(
    db: Session,
    family_id: int,
    start_date: Optional[str],
    end_date: Optional[str],
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> Optional[str]:
    """把 `inception` 解析成作用域最早资金流水日；其余入参原样返回。

    非哨兵时**不做任何校验**：日期格式与区间倒挂仍由口径层统一拒绝，
    免得两处各写一遍校验而演化出「一个接受 X、一个拒绝 X」的漂移。
    """
    if start_date != INCEPTION:
        return start_date
    end = _as_date(end_date, 'end_date')
    first = first_investment_date(db, family_id, ledger_id=ledger_id, portfolio_id=portfolio_id)
    return first or (end - dt.timedelta(days=DEFAULT_RANGE_DAYS)).isoformat()
