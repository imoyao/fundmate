# -*- coding: utf-8 -*-
"""货币基金七日年化收益率（#2120 P0-1）。

## 为什么需要它

`money_fund_daily_worth` 存了 121 万行货基万份收益，但 `annual_return_7d` 列
**填充率 0.00%**——`fund_nav_job._save_data` 写死 `None  # 暂不计算`，而详情页
`fund_performance._money_fund_performance` 读的正是它，于是**货基「七日年化」恒为 `—`**。
本模块补上这个算法：这张表占净值类数据 14%，此前换不到一个有效数字。

## 口径（写死在本模块，读写两侧共用同一份实现）

    七日年化(%) = [ Σ(窗口内已发布的万份收益) / n ] / 10000 × 365 × 100

- **窗口 = 该行日期往前 7 个自然日**（`[D-6, D]`），**不是「最近 7 条观测」**。
  这是本模块最关键的一条，实测（2026-10-13，`invest.db`）踩过坑：
  热点货基 `000379` 在窗口 `[10-05, 10-11]` 内只有 **6 条**观测——因为 7 天国庆
  假期，最近 7 条观测一路跨到 13 个自然日前（09-29）。两种口径的差别取决于
  窗口内外的收益率是否突变：收益率恒定时几乎无差（实测 0.8422% vs 0.8426%），
  但一旦近期收益率跳变（实测把 13 天前 0.60 的高收益拉进窗口、窗口内实为 0.20，
  七日年化会从 0.73% 被抬到 0.94%，**+28%**）。按自然日走才与行业定义的
  「最近 7 个自然日」一致，窗口长度也不会被节假日拉长。
- **n = 窗口内「有发布」的天数**；缺失日**不补 0、不补均值**（不编造）。
  货基周末照常发布（实测周六行数与工作日持平），缺口来自法定节假日与漏跑同步，
  故 n 常态落在 5~7。窗口内要求「满 7 条」是不可行的：实测该条件下
  **全库填充率 0.0%**（没有任何一行满足）。
- **硬门槛 `n >= 2`**：单点不构成「平均」，宁缺勿滥，缺就返回 `None`。
- **`nav_per_10k` 单位是「元」**（每万份当日收益，000198 余额宝 2026-08-14 为
  0.2233 元），故 ÷10000 换成日收益率小数——漏掉这一步会算出 8000% 量级的荒谬值。
- 精度 4 位小数，对齐模型列注释「精度 0.0001」。
- 拿不到值一律返回 `None`，由前端降级「—」，**不编造占位值**
  （与 `fund_performance` 的诚实降级口径一致）。

量级自检：万份收益 0.23 元/万份/日 → 日收益率 0.0023% → 七日年化 ≈ **0.84%**，
与货基实际水平相符。
"""

from __future__ import annotations

from collections import deque
from datetime import date, timedelta
from typing import Deque, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

# 窗口跨度（自然日）：含当日共 7 天
_WINDOW_DAYS = 7
# 窗口内至少要有几个已发布日才承认是「七日平均」（单点不构成平均）
_MIN_SAMPLES = 2
# 万份收益（元）→ 日收益率小数：每万份 = 10000 元
_NAV_DIVISOR = 10000
# 年化天数
_DAYS_PER_YEAR = 365
# 精度（对齐模型列注释「精度 0.0001」）
_PRECISION = 4
# 批量 UPDATE 的分片大小（SQLite 变量上限 + 事务体积）
_UPDATE_CHUNK = 2000

# (日期, 万份收益元)；万份收益允许为 None（当日未发布）
YieldPoint = Tuple[date, Optional[float]]


def _annualize(values: Sequence[float]) -> Optional[float]:
    """把窗口内的万份收益日均值换算成七日年化（%）。样本不足返回 None。"""
    if len(values) < _MIN_SAMPLES:
        return None
    daily_yield = (sum(values) / len(values)) / _NAV_DIVISOR
    return round(daily_yield * _DAYS_PER_YEAR * 100, _PRECISION)


def annual_return_7d_at(points: Sequence[YieldPoint], as_of: date) -> Optional[float]:
    """单个日期的七日年化（%）。`points` 需为该基金的 (日期, 万份收益) 序列。"""
    start = as_of - timedelta(days=_WINDOW_DAYS - 1)
    values = [v for d, v in points if start <= d <= as_of and v is not None]
    return _annualize(values)


def compute_annual_return_7d_series(points: Sequence[YieldPoint]) -> List[Optional[float]]:
    """逐点七日年化（%），结果与 `points` **逐位对齐**（升序输入）。

    滑动窗口实现，O(n × 窗口天数)；`points` 必须按日期升序（DB 侧查询已保证）。
    """
    out: List[Optional[float]] = []
    window: Deque[YieldPoint] = deque()
    for day, _value in points:
        window.append((day, _value))
        cutoff = day - timedelta(days=_WINDOW_DAYS - 1)
        while window and window[0][0] < cutoff:
            window.popleft()
        out.append(_annualize([v for _d, v in window if v is not None]))
    return out


def compute_series_from_records(records: Sequence[dict]) -> List[Tuple[date, Optional[float], Optional[float]]]:
    """把 (fund_code, date, nav_per_10k) 记录转成 `(日期, 万份收益, 七日年化)` 三元组。

    供写入侧在**内存里**算完整序列（`async_backfill` 一次拿到全历史，无需回查 DB）。
    """
    ordered = sorted(records, key=lambda r: r['date'])
    points: List[YieldPoint] = [(r['date'], r['nav_per_10k']) for r in ordered]
    values = compute_annual_return_7d_series(points)
    return [(r['date'], r['nav_per_10k'], v) for r, v in zip(ordered, values)]


def recompute_annual_return_7d(
    db: Session,
    fund_codes: Optional[Sequence[str]] = None,
    apply: bool = False,
) -> Dict[str, int]:
    """重算 `money_fund_daily_worth.annual_return_7d`。

    默认 **dry-run**（`apply=False`）：只统计将要变动的行数，不写库。`apply=True`
    才真正 UPDATE，且**幂等**——值相同的行不动（重跑一次 changed 为 0）。

    按基金逐只处理（而非一次载入全表 121 万行），把内存占用压在单只基金的量级。

    **不自行 commit**：整个同步 job 是一个事务（提交权在 orchestrator，见
    `job_base.run` 无 commit、`orchestrator` 统一提交），此处 commit 会把
    job 的原子性打破。独立脚本请自行 `db.commit()`。

    Returns:
        ``{'scanned': 扫描行数, 'changed': 需要/已变动的行数, 'funds': 处理基金数}``
    """
    from app.domains.funds.models import MoneyFundDailyWorth

    query = db.query(
        MoneyFundDailyWorth.fund_code,
        MoneyFundDailyWorth.date,
        MoneyFundDailyWorth.nav_per_10k,
        MoneyFundDailyWorth.annual_return_7d,
    ).order_by(MoneyFundDailyWorth.fund_code, MoneyFundDailyWorth.date)
    if fund_codes:
        query = query.filter(MoneyFundDailyWorth.fund_code.in_(list(fund_codes)))

    scanned = 0
    changed = 0
    funds = 0
    current_code: Optional[str] = None
    rows: List[Tuple[str, date, Optional[float], Optional[float]]] = []
    update_stmt = text(
        'UPDATE money_fund_daily_worth SET annual_return_7d = :value, updated_at = :updated_at '
        'WHERE fund_code = :fund_code AND date = :row_date'
    )

    def flush(rows_to_write: List[Tuple[str, date, float]]) -> None:
        from app.core.time_utils import now_shanghai

        stamp = now_shanghai()
        payload = [
            {'fund_code': code, 'row_date': day, 'value': value, 'updated_at': stamp}
            for code, day, value in rows_to_write
        ]
        for i in range(0, len(payload), _UPDATE_CHUNK):
            db.execute(update_stmt, payload[i : i + _UPDATE_CHUNK])

    def finish_fund() -> None:
        nonlocal scanned, changed, funds
        if not rows:
            return
        funds += 1
        scanned += len(rows)
        points: List[YieldPoint] = [(day, nav) for _c, day, nav, _old in rows]
        values = compute_annual_return_7d_series(points)
        pending: List[Tuple[str, date, float]] = []
        for (_code, day, _nav, old), new in zip(rows, values):
            if new is None:
                # 样本不足：只把「原本有值、现在算不出」的行清空，避免留下旧口径的数
                if old is not None:
                    changed += 1
                    if apply:
                        pending.append((_code, day, None))  # type: ignore[arg-type]
                continue
            if old is None or round(float(old), _PRECISION) != new:
                changed += 1
                if apply:
                    pending.append((_code, day, new))
        if apply and pending:
            flush(pending)

    for code, day, nav, old in query.all():
        if current_code is not None and code != current_code:
            finish_fund()
            rows = []
        current_code = code
        rows.append((code, day, float(nav) if nav is not None else None, old))
    finish_fund()

    return {'scanned': scanned, 'changed': changed, 'funds': funds}
