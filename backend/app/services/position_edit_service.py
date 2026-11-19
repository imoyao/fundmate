# -*- coding: utf-8 -*-
"""持仓「编辑」写入规则：配置目标 / 现价 / 备注 / 到期日（#1123 P0 / #931）。

## 为什么在 services 而不在视图

`domains/ledgers/views.py` 有 656 行的冻结基线（`scripts/check_view_thickness.py`，
存量视图「只减不增」）。原实现把「五笔钱白名单」「金额单位换算」直接写在端点里，
本轮要加到期日就必然再长十来行。按 `conventions.md` §2.2（视图只做 HTTP 编排）
下沉到这里：端点只剩「取参 → 调本函数 → 组信封」，四个字段的口径也收在一处，
不必在两个端点之间对读。

## 到期日为什么按品类 fail closed

`positions.maturity_date` 只有逆回购（时间建模：到期即不再计入投资）与银行理财
（D121：仅记录，到期仍计入）有语义。基金 / 股票没有到期日，传进来是上游把字段
接错了；静默忽略会让「我明明设了到期日」变成一条查不出原因的 NULL——故报 400。
判据复用买入侧的 `assert_maturity_date_allowed`，同一份口径不写第二遍。
"""

from datetime import date
from typing import Any

from app.core.constants import ALLOCATION_LABELS
from app.core.money import Money
from app.services.position_write_policy import assert_maturity_date_allowed


def apply_position_edit(pos: Any, data: dict) -> None:
    """把编辑载荷应用到 `pos`（原地改属性，不 commit）。

    只认四个字段：配置目标 / 现价 / 备注 / 到期日。其余静默忽略——与本端点
    此前「字段白名单」口径一致：调用方多传字段不算错，落库前一律过滤。

    校验失败抛 `ValueError`，由视图转成 400（沿用 `abort(400, ...)` 的信封）。
    """
    if 'allocation' in data:
        # 五笔钱白名单（#1123 P0）；None = 清空语义保留
        if data['allocation'] is not None and data['allocation'] not in ALLOCATION_LABELS:
            raise ValueError('非法配置目标')
        pos.allocation = data['allocation']
    if 'current_price' in data:
        pos.current_price = Money.yuan_to_price_units(data['current_price'])
    if 'notes' in data:
        pos.notes = data['notes']
    if 'maturity_date' in data:
        pos.maturity_date = parse_maturity_date(data['maturity_date'], pos.asset_type)


def parse_maturity_date(raw: Any, asset_type: str) -> date | None:
    """解析到期日：空值 = 清空（合法，任何品类都允许）；品类不符 / 格式非法 = 400。

    `None` 与空串都按「清空」处理：前端 `el-date-picker` 清空后回传空串，
    若把它当非法格式拒绝，用户就永远撤不掉一个填错的日期。
    """
    if raw is None or raw == '':
        return None
    assert_maturity_date_allowed({'maturity_date': raw}, asset_type)
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError('到期日格式应为 YYYY-MM-DD') from None
