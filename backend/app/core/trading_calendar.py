# -*- coding: utf-8 -*-
"""A 股交易日历的**唯一出口**（#1217）。

WHY
    `chinese_calendar.is_workday` / `find_workday` 算的是**法定工作日**，
    与 **A 股开盘日**并不等价。差异恰好是「调休补班的周末」——
    打工人要上班（`is_workday=True`），但沪深交易所休市（不是开盘日）。
    2026 年属于此类的有 6 天：01-04、02-14、02-28、05-09、09-20、10-10。

    改造前两处各自直接调 chinese_calendar，其中一处还把结果塞进了名叫
    `is_trading_day` 的字段（`domains/utils/views.py` 的 `/api/utils/trading-days/`），
    名实不符：调休日会告诉用户「今天是交易日」，而市场是关的。
    另一处 `core/utils.get_confirm_date`（场外基金 T+1/T+2 确认日）同理。

口径定义（本模块是唯一实现，**禁止各处再直接调 chinese_calendar**）：

    is_trading_day(d) = d 是周一至周五 且 是法定工作日

    为什么这条规则对 A 股准确：交易所周一至周五开市、法定节假日休市，
    且**交易所不补班**（调休补班的周末照常休市）。因此：

    - 普通工作日 → 开盘
    - 节假日中的工作日 → 休市
    - 调休补班周末 → 因不是周一至周五而判休市（关键修正）
    - 普通周末 → 休市

    未覆盖：极罕见的临时休市，`chinese_calendar` 本身也不建模，故不构成回退。

适用范围（用户确认）：投顾 / 理财等无净值产品虽然不在交易所交易，但其底层
通常是场内 / 场外基金，净值更新跟随交易所日历，故统一按**开盘日**口径。
因此场外基金 T+1/T+2 确认日同样收敛到本模块。
"""

from datetime import date, timedelta

from chinese_calendar import is_workday
from loguru import logger

# 扫描上限（自然日）：chinese_calendar 缺少某年份节假日数据时会抛异常，
# is_trading_day 会保守返回 False；若无上限，next_trading_day 将死循环。
_MAX_LOOKAHEAD_DAYS = 730


def is_trading_day(d: date) -> bool:
    """指定日期是否为 A 股开盘日。

    保守降级：chinese_calendar 无该年份数据时抛异常，按**休市**处理
    （与既有 `/api/utils/trading-days/` 的兜底一致，避免给用户错误指引）。
    """
    try:
        return d.weekday() < 5 and is_workday(d)
    except Exception as exc:  # pragma: no cover - 仅缺少年份节假日数据时触发
        logger.warning(f'交易日判定失败（{d}），按休市处理：{exc}')
        return False


def next_trading_day(d: date, delta_days: int = 1) -> date:
    """自 d 起算，第 delta_days 个**开盘日**（不含 d 本身）。

    delta_days=1 → 下一个开盘日。用于「下一个开盘日应更新其他存量持仓」提示
    （#1217）与场外基金 T+1/T+2 确认日顺延（`core/utils.get_confirm_date`）。
    """
    if delta_days < 1:
        raise ValueError(f'delta_days 必须 >= 1，收到 {delta_days}')

    result = d
    remaining = delta_days
    scanned = 0
    while remaining > 0:
        result += timedelta(days=1)
        scanned += 1
        if scanned > _MAX_LOOKAHEAD_DAYS:
            raise ValueError(f'{_MAX_LOOKAHEAD_DAYS} 个自然日内未找到第 {delta_days} 个交易日（起始 {d}）')
        if is_trading_day(result):
            remaining -= 1
    return result
