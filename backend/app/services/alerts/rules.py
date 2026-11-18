# -*- coding: utf-8 -*-
"""自选提醒的**纯规则层**：阈值口径、触发判据、文案。

刻意不 import 任何数据库/框架模块（只有标准库 + 常量），原因有三：

1. **可单测**：触发判据是这类功能唯一容易出错的地方（正负号、除零、窗口边界），
   不该为了测它去搭一套 DB 夹具。
2. **可复用**：`notification_service.emit_many` 只吃候选 dict，本模块负责把
   「一行规则 + 一份行情」变成「一条候选」；新增一种提醒 = 加一个判据函数 +
   一条默认值，不动表结构、不动通知层。
3. **多租户安全**：判据是纯函数，天然无跨家庭读写的可能；家庭隔离全部收敛在
   `watchlist_alert_service` 的查询条件里（单一位置，便于审阅）。

## 阈值口径（前端可配，本模块只给默认值）
- 到价：绝对价格（元），必须 > 0。
- 单日跌幅：**正数百分比**（5 表示「跌 5%」）。判据是 `涨跌幅 <= -阈值`，
  即只报下跌方向——用户要的是「跌了」，涨回来不构成提醒。
- 回撤：**正数百分比**，自窗口内最高收盘价回撤。窗口天数放家庭设置（默认 60 日），
  逐标的规则里不重复存——窗口是「怎么看这个标的」的全局口径，不是每只都不同。

## 为什么不用「涨跌幅 >= 阈值」的绝对值判据
绝对值会让「涨 5%」也触发「跌幅提醒」，与用户预期相反；而双向异动提醒是另一种
产品语义（波动提醒），等真有需求再加类型，不在本类型里偷塞。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

# ── 类型 ──
ALERT_PRICE_UP = 'PRICE_UP'
ALERT_PRICE_DOWN = 'PRICE_DOWN'
ALERT_CHANGE_PCT = 'CHANGE_PCT'
ALERT_DRAWDOWN = 'DRAWDOWN'

PRICE_TYPES = (ALERT_PRICE_UP, ALERT_PRICE_DOWN)
MAGNITUDE_TYPES = (ALERT_CHANGE_PCT, ALERT_DRAWDOWN)
ALL_TYPES = PRICE_TYPES + MAGNITUDE_TYPES

# 通知类别取前端消息盒已预留的「订阅」页签（lay-notice/data.ts），
# 新增提醒类型不需要改前端通知组件。
NOTIFICATION_CATEGORY = 'watchlist'

# ── 默认值（表里只存用户改过的口径，缺行由此补齐）──
DEFAULT_SETTINGS: dict[str, dict] = {
    ALERT_CHANGE_PCT: {
        'is_enabled': False,
        'threshold_value': 5.0,
        'window_days': None,
        'level': 'P2',
    },
    ALERT_DRAWDOWN: {
        'is_enabled': False,
        'threshold_value': 10.0,
        'window_days': 60,
        'level': 'P2',
    },
}

PRICE_LEVEL = 'P1'

# ── 取值边界（服务层与 view 共用，避免两处各写一套）──
THRESHOLD_BOUNDS: dict[str, tuple[float, float]] = {
    ALERT_CHANGE_PCT: (0.5, 50.0),
    ALERT_DRAWDOWN: (1.0, 90.0),
}
WINDOW_BOUNDS = (5, 250)
MIN_PRICE = 0.001
MAX_PRICE = 1_000_000.0


def normalize_alert_type(raw: str) -> str:
    """类型规范化：去空格转大写并校验，非法值抛 ValueError（由 view 转 422）。"""
    value = (raw or '').strip().upper()
    if value not in ALL_TYPES:
        raise ValueError(f'不支持的提醒类型：{raw}')
    return value


def validate_threshold(alert_type: str, value: float) -> float:
    """阈值校验：到价看绝对价格区间，幅度类看百分比区间。"""
    if value is None:
        raise ValueError('阈值不能为空')
    number = float(value)
    if number != number:  # NaN
        raise ValueError('阈值必须是数字')
    if alert_type in PRICE_TYPES:
        if not (MIN_PRICE <= number <= MAX_PRICE):
            raise ValueError(f'到价提醒的阈值须在 {MIN_PRICE}~{MAX_PRICE} 元之间')
        return round(number, 4)
    low, high = THRESHOLD_BOUNDS[alert_type]
    if not (low <= number <= high):
        raise ValueError(f'幅度阈值须在 {low}~{high}% 之间')
    return round(number, 2)


def validate_window(days: Optional[int]) -> Optional[int]:
    """回撤窗口校验；其余类型忽略窗口（返回 None）。"""
    if days is None:
        return None
    low, high = WINDOW_BOUNDS
    value = int(days)
    if not (low <= value <= high):
        raise ValueError(f'回看窗口须在 {low}~{high} 个交易日之间')
    return value


def price_triggered(alert_type: str, latest: float, threshold: float) -> bool:
    """到价判据：涨到 / 跌到。等于阈值也算触发（用户设的是「到」）。"""
    if latest is None or threshold is None:
        return False
    if alert_type == ALERT_PRICE_UP:
        return latest >= threshold
    if alert_type == ALERT_PRICE_DOWN:
        return latest <= threshold
    return False


def change_pct(latest: Optional[float], prev: Optional[float]) -> Optional[float]:
    """单日涨跌幅（%）。缺前收 / 前收为 0 时返回 None（不拿 0 兜底假造涨跌）。"""
    if latest is None or prev is None or prev <= 0:
        return None
    return (latest - prev) / prev * 100.0


def pct_triggered(pct: Optional[float], threshold: float) -> bool:
    """跌幅判据：只报下跌方向（pct <= -threshold）。"""
    if pct is None or threshold is None:
        return False
    return pct <= -abs(threshold)


def drawdown_pct(latest: Optional[float], window_high: Optional[float]) -> Optional[float]:
    """自窗口最高收盘价回撤幅度（%，正数）。高点缺失或非正时返回 None。"""
    if latest is None or window_high is None or window_high <= 0:
        return None
    return (window_high - latest) / window_high * 100.0


def drawdown_triggered(drawdown: Optional[float], threshold: float) -> bool:
    if drawdown is None or threshold is None:
        return False
    return drawdown >= abs(threshold)


def weekly_anchor(day: date) -> date:
    """去重锚点：取当周周一。

    回撤是「持续的坏状态」而不是「一次事件」——按天去重会天天推同一条，
    按周去重才是「这周已经告诉过你它破线了」。到价 / 跌幅仍按行情日期去重。
    """
    return day - timedelta(days=day.weekday())


def price_message(name: str, alert_type: str, latest: float, threshold: float) -> tuple[str, str]:
    """到价通知文案：只陈述事实 + 说明「这条线是你设的」，不含方向性建议。"""
    direction = '涨到' if alert_type == ALERT_PRICE_UP else '跌到'
    title = f'到价提醒：{name} 现价 {latest:.3f} 元，已{direction}你设的 {threshold:.3f} 元'
    body = (
        f'{name} 最新价 {latest:.3f} 元，你设的到价线是 {threshold:.3f} 元。'
        '到价提醒是一次性的：本条已自动关闭，如需继续关注请重新设置。'
    )
    return title, body


def pct_message(name: str, pct: float, threshold: float, as_of: date) -> tuple[str, str]:
    title = f'单日跌幅：{name} {as_of.isoformat()} 跌 {abs(pct):.2f}%（你设的线 {threshold:.1f}%）'
    body = (
        f'{name} 在 {as_of.isoformat()} 的收盘价较前一交易日跌 {abs(pct):.2f}%，'
        f'越过了你设的 {threshold:.1f}% 阈值。同一份行情只提醒一次，不在次日重复。'
    )
    return title, body


def drawdown_message(name: str, drawdown: float, threshold: float, window_days: int, as_of: date) -> tuple[str, str]:
    title = f'回撤提醒：{name} 自近 {window_days} 日高点回撤 {drawdown:.2f}%（你设的线 {threshold:.1f}%）'
    body = (
        f'{name} 截至 {as_of.isoformat()} 的最新价，较近 {window_days} 个交易日的最高收盘价'
        f'回撤 {drawdown:.2f}%，越过了你设的 {threshold:.1f}% 阈值。'
        '回撤是持续状态，同一周内只提醒一次。'
    )
    return title, body
