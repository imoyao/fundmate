# -*- coding: utf-8 -*-
"""跨账本重复组的产品名解析（#2151 展示口径修复）。

WHY 独立模块：`summary_service` 是冻结服务（体量/圈复杂度只减不增），把「展示名
从哪来」的判据继续堆进去会顶破闸门。本模块只做一件事：把扫描到的流水行批量
翻译成人类可读的产品名，供组标题使用。

口径（用户 2026-11-27 反馈：有代码却没产品名，用户认不出是哪只产品）：
1. 真名优先取 `positions.name`，按 symbol + family 一次批量查询，不逐行查库；
2. 流水上的 `position_name` 只在**不是分红方案文本**时作为降级——导入器会把
   「每10份派现金2.5970元」写进该列，那是交易事实，不是标的名称；
3. 两者都没有 → `None`，调用方按「标的代码未填」处理，绝不拿方案文本冒充产品名。
"""

import re
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.domains.positions.models import Position

#: 分红方案文本特征：「每10份派现金2.5970元」「每 10 份派 0.05 元」等。
_PLAN_TEXT = re.compile(r'每\s*\d+\s*份\s*派')


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ''


def ghost_display_names(db: Session, family_id: int, groups: Iterable[Iterable[Any]]) -> dict[int, str | None]:
    """按流水 id 返回展示名。一次 positions 查询，组内顺序无关。"""
    rows = [row for group in groups for row in group]
    symbols = {getattr(row, 'symbol', '') for row in rows} - {''}

    names: dict[str, str] = {}
    if symbols:
        for symbol, position_name in (
            db.query(Position.symbol, Position.name)
            .filter(Position.family_id == family_id, Position.symbol.in_(symbols))
            .all()
        ):
            cleaned = _clean(position_name)
            if cleaned and not _PLAN_TEXT.search(cleaned):
                names.setdefault(symbol, cleaned)

    result: dict[int, str | None] = {}
    for row in rows:
        real_name = names.get(getattr(row, 'symbol', ''))
        if real_name:
            result[row.id] = real_name
            continue
        snapped = _clean(getattr(row, 'position_name', None))
        result[row.id] = None if _PLAN_TEXT.search(snapped) else (snapped or None)
    return result


def first_display_name(txns: Iterable[Any], names: dict[int, str | None]) -> str | None:
    """组内任一行有可读名称即取（复用后端既定的稳定排序，前端不再猜）。"""
    for txn in txns:
        name = names.get(txn.id)
        if name:
            return name
    return None
