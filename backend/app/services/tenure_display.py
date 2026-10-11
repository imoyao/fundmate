# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/10
# File : tenure_display.py
# app/services/tenure_display.py
"""任职年限的展示换算（#1970 扩展 · 转换层）。

## 为什么单独一个模块

「库里存什么」与「界面显示什么」是两件事，且**必须能独立演进**：

- 库里存**事实**：``managers.appointment_date`` 是一次写入即终局的客观日期；
- 界面显示**解读**：``14 年又 15 天``，且这个数字必须**随今天自然增长**。

若把换算写进视图层或前端，就会出现「每处各算一次、口径慢慢漂移」的老问题
（`conventions.md` §16.2 反对把复杂度搬家）。故换算单点收口在本模块，
服务层与视图层都只调用它。

## 三条硬约束

1. **前端永远拿不到原始天数**。``5125`` 是存储口径，不是人话；一旦它漏到前端，
   就得在前端再写一次「÷365」的换算，正是本模块要消灭的事。
2. **每个换算值必须附口径元数据**（``basis`` + 可选 ``raw``）。没有口径的数字
   等于假数字——「14 年」是「东财口径的日历跨度」，与「累计在任年数」不是一回事。
3. **本模块不返回颜色**，只返回带符号的数值。涨跌配色是前端 ``design.md``
   的事（``--color-rise`` / ``--color-fall``），服务层返回颜色会让色板分裂成两套。

## 口径对照（``basis``取值）

===================== ====================================================
``basis``             含义
===================== ====================================================
``em_days_derived``   由东财「累计从业时间」反推的首次任职日；
                      **日历跨度**，公转私/ 断档不扣减（实测张坤 001373
                      卸任后的空档未从5125 天中扣除）
``derived_from_start``由库内任期起始日反推（无东财数据时的降级路径）
===================== ====================================================
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

# 展示文本里的年数上限：超过这个值不是「从业」，而是数据脏了。
# 东财实测 max=8145 天（约 22.3 年），留足余量后取 80 年为硬上限。
_MAX_REASONABLE_DAYS = 80 * 365


def format_tenure_days(days: int) -> str:
    """天数 → 「X 年又 Y 天」/ 「X 年」/ 「Y 天」。

    与天天基金 F10 的展示口径一致（实测张坤 F10 显示「14 年又 15 天」，
    与 5125 天算出的 14 年 15 天完全一致），避免同一数据在两个页面显示不同。

    Args:
        days: 整年余外的剩余天数可为 0；负数或None 由调用方拦掉。

    Returns:
        如 ``14 年又 15 天`` / ``3 年`` / ``87 天``。
    """
    total = int(days)
    if total <= 0:
        return '不足 1 天'
    years, rest = divmod(total, 365)
    if years <= 0:
        return f'{rest} 天'
    if rest <= 0:
        return f'{years} 年'
    return f'{years} 年又 {rest} 天'


def build_tenure_display(
    start: Optional[date],
    basis: str,
    as_of: Optional[date] = None,
    raw: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """任职起始日 → 展示用年限 dict。

    Args:
        start: 任职/ 首次任职起始日；``None`` 时返回 ``None``（前端降级「—」）。
        basis: 口径标记，见模块 docstring 的口径对照表。
        as_of: 计算基准日，默认今天。测试可注入以得到确定结果。
        raw: 溯源原值（如东财的 5125 天），仅作审计线索返回，**前端不渲染**。

    Returns:
        ``{'years', 'text', 'basis', 'raw', 'start_date', 'as_of'}``；
        无数据时返回 ``None``。

    **为什么同时给``years`` 与 ``text``**：``years`` 供前端做数值比较与排序，
    ``text`` 供直接展示。若只给 text，前端就得再解析一次中文，解析即失真。
    """
    if start is None:
        return None

    base = as_of or date.today()
    days = (base - start).days
    if days < 0:
        # 起始日晚于基准日 = 数据异常。不抛异常也不返回负年限，直接降级为None，
        # 与「脏输入不产出假事实」同原则。
        return None
    if days > _MAX_REASONABLE_DAYS:
        # 起始日过于久远 = 上游写入了坏日期。宁可显示「—」也不要展示 200 年从业。
        return None

    return {
        'years': round(days / 365, 1),
        'text': format_tenure_days(days),
        'basis': basis,
        'raw': raw,
        'start_date': start.isoformat(),
        'as_of': base.isoformat(),
    }


# ── 规模 / 回报的展示换算 ──────────────────────────────────────
#
# 为什么不做成「万 / 亿」自动进位：基金经理管理规模全行业都在 1 亿 ~ 千亿量级，
# 一律用「亿元」+ 两位小数最易读；自动进位反而制造「0.31 万亿」这种反直觉读数。
# 若将来真出现万亿级，届时再加档位也不迟。


def build_scale_display(yi: Optional[float], basis: str = 'em_yi') -> Optional[Dict[str, Any]]:
    """管理规模（亿元）→ 展示 dict。

    Args:
        yi: 库内 ``sum_scale``（东财「现任基金资产总规模」，单位**亿元**）。
        basis: 口径标记。

    Returns:
        ``{'text', 'value', 'unit', 'basis'}``；``yi`` 为 None 时返回 ``None``。

    ⚠️ **口径警示**：这是「现任基金资产总规模」，即该经理**当前在管**基金的合计，
    **不包含**已卸任基金。若用户拿它与「历史管理规模」比较会得到偏小的数，
    故``basis`` 必须让前端有机会标注口径。
    """
    if yi is None:
        return None
    return {
        'text': f'{yi:.2f} 亿元',
        'value': float(yi),
        'unit': '亿元',
        'basis': basis,
    }


def build_return_display(pct: Optional[float], basis: str = 'em_tenure') -> Optional[Dict[str, Any]]:
    """回报率（%）→ 展示 dict。

    Args:
        pct: 库内 ``best_return``（东财「现任基金最佳回报」，单位 %）或现算的任期回报。
        basis: 口径标记。

    Returns:
        ``{'text', 'value', 'basis'}``；``pct`` 为 None 时返回 ``None``。

    **显式带符号**：``+43.59%`` / ``-18.52%``。数值本身带符号，前端按正负选色；
    本层不返回颜色（见模块 docstring 约束 3）。
    """
    if pct is None:
        return None
    return {
        'text': f'{pct:+.2f}%',
        'value': float(pct),
        'basis': basis,
    }
