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

# 已就「日历未覆盖某年」告警过的年份（同一年只 ERROR 一次，其余降为 DEBUG）
_warned_years: set[int] = set()


class CalendarCoverageError(ValueError):
    """交易日历数据**未覆盖**目标年份。

    WHY 单独一个异常类型
    --------------------
    `chinese_calendar` 的数据按年发布（实测 1.11.0 覆盖 2004~2026），
    查未覆盖年份会抛 `NotImplementedError`。旧实现把它当成「普通异常」
    一律吞掉并按休市处理 ⇒ **2027 年起，每个工作日都会被静默判成休市**：
    调度器整天跳过、收益日历整年显示「休市」、场外基金 T+1/T+2 确认日
    顺延时扫满 730 天后抛一个看不懂的 ValueError。

    这就是「拿不到输入 ⇒ 结论看起来正常」那一类失败（CNB #171 同族）：
    数据源缺数据时，**必须显式喊出来**，不能退化成一个看起来合理的答案。

    继承 `ValueError`（而不是 RuntimeError）：调用方原有的 `except ValueError`
    仍能兜住它（`tools/sync_cli.py` 等处），不必逐处改 except 子句。
    """


def calendar_coverage() -> tuple[int, int]:
    """当前日历数据覆盖的年份区间（闭区间）。

    读 `chinese_calendar.constants.holidays` 的键（日期）取年份集合；
    读不到就返回 (0, 0)——调用方据此判「完全没覆盖」。
    """
    try:
        from chinese_calendar.constants import holidays

        years = {day.year for day in holidays}
    except Exception as exc:  # pragma: no cover - chinese_calendar 结构变化时触发
        logger.warning(f'读取日历覆盖年份失败（按未覆盖处理）：{exc}')
        return (0, 0)
    if not years:
        return (0, 0)
    return (min(years), max(years))


def calendar_covers(d: date) -> bool:
    """日历数据是否覆盖 d 所在年份。"""
    low, high = calendar_coverage()
    return low <= d.year <= high


def ensure_calendar_covers(d: date, lookahead_days: int = 0) -> None:
    """日历未覆盖目标日期（含前瞻天数）⇒ 抛 `CalendarCoverageError`。

    用在**会决定「要不要干活」的地方**（调度入口、顺延计算）：
    缺数据时宁可大声失败，也不要静默按休市处理。
    """
    target = d + timedelta(days=lookahead_days)
    if calendar_covers(target):
        return
    low, high = calendar_coverage()
    raise CalendarCoverageError(
        f'交易日历未覆盖 {target.year} 年（当前覆盖 {low}~{high}）：'
        f'chinese_calendar 按年发布数据，需升级到覆盖该年份的版本'
        f'（或改用市场日历，见 #2139）。'
        f'目标日期 {target}（含前瞻 {lookahead_days} 天）无法判定交易日。'
    )


def is_trading_day(d: date) -> bool:
    """指定日期是否为 A 股开盘日。

    保守降级：chinese_calendar 无该年份数据时抛异常，按**休市**处理
    （与既有 `/api/utils/trading-days/` 的兜底一致，避免给用户错误指引）。

    但「未覆盖年份」不是普通异常：它意味着**整年**都判休市（实测 1.11.0
    只覆盖 2004~2026 ⇒ 2027 年每个工作日都判休市，调度器整天跳过、
    收益日历整年显示休市）。因此这里按 **ERROR** 级别留痕并写清覆盖范围，
    让「静默停摆」变成「看得见的红灯」（#2139 跟进换市场日历）。
    """
    try:
        return d.weekday() < 5 and is_workday(d)
    except Exception as exc:  # pragma: no cover - 仅缺少年份节假日数据时触发
        if not calendar_covers(d):
            low, high = calendar_coverage()
            if d.year not in _warned_years:
                # 同一年只报一次 ERROR：收益日历等调用方会按天反复问，
                # 每天刷一条 ERROR 会把真正的告警淹掉。
                _warned_years.add(d.year)
                logger.error(
                    '交易日历**未覆盖 {} 年**（当前覆盖 {}-{}）：按休市处理，'
                    '但该年会导致调度整年跳过、收益日历整年显示休市；'
                    '请升级 chinese_calendar 或改用市场日历（#2139）。原始异常：{}',
                    d.year,
                    low,
                    high,
                    exc,
                )
            else:
                logger.debug(f'交易日历未覆盖 {d.year} 年（已告警过），按休市处理：{exc}')
        else:
            logger.warning(f'交易日判定失败（{d}），按休市处理：{exc}')
        return False


def next_trading_day(d: date, delta_days: int = 1) -> date:
    """自 d 起算，第 delta_days 个**开盘日**（不含 d 本身）。

    delta_days=1 → 下一个开盘日。用于「下一个开盘日应更新其他存量持仓」提示
    （#1217）与场外基金 T+1/T+2 确认日顺延（`core/utils.get_confirm_date`）。

    日历未覆盖目标年份时**立刻**抛 `CalendarCoverageError`：否则会在 730 天
    扫描后抛一个「730 个自然日内未找到第 N 个交易日」的 ValueError，
    读者完全看不出真正原因是「日历缺 2027 年数据」。
    """
    if delta_days < 1:
        raise ValueError(f'delta_days 必须 >= 1，收到 {delta_days}')

    # 先看日历覆盖到哪一年：顺延目标必然落在 d 之后，覆盖不足时直接说清楚
    ensure_calendar_covers(d + timedelta(days=min(delta_days * 7, _MAX_LOOKAHEAD_DAYS)))

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
