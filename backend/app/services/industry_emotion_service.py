# -*- coding: utf-8 -*-
"""行业恐贪读取服务（#2479 前端出口）：探市「行业情绪」档的数据出口。

数据来源只有一处：``market_single_values``（source='jiucaishuo_industry'，
由 TemperatureJob 每日落库；single 不被 cleanup_old_data 清理，历史可累积）。
本模块**纯只读**。

上游形态（2026-10-21 实测）：每次请求只返回**当日轮换的少数行业**（name 形如
「军工PH值」「新能源TF值」），因此「最新快照」= 最新 collected_at 当日的全部行，
行业清单逐日可能不同——前端须如实呈现，不得假设行业全集固定（原站 App 页展示
7 个行业，走的是 App 内多参请求；免登录端点实测当日仅 4 条）。

name 解析纪律：保留上游原文 ``name``；``industry``（去掉指标后缀）与 ``metric``
（PH/TF）仅为展示派生——后缀语义未实证（PH/TF 并非恐惧/贪婪的确认映射），
**只透出不解读**；解析不出后缀时 industry=name 原文、metric=None，不猜语义。
``history_days`` 为该 name 在库内累积的天数（自建历史，为二期走势图铺路）。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.temperature.models import MarketSingleValue

EMOTION_SOURCE = 'jiucaishuo_industry'

# 上游指标后缀（实测只见 PH/TF；不匹配的一律按「无指标」处理，name 原文展示）
_METRIC_RE = re.compile(r'^(.+?)(PH|TF)值$')


def split_emotion_name(name: str) -> Tuple[str, Optional[str]]:
    """'军工PH值' → ('军工', 'PH')；解析不出后缀 → (name 原文, None)。

    纯函数（便于单测）。**不建立 PH/TF → 恐惧/贪婪的映射**——语义未实证，
    按项目「宁缺毋假」纪律只透出原文后缀。
    """
    m = _METRIC_RE.match(name or '')
    if not m:
        return (name or '', None)
    return (m.group(1), m.group(2))


def get_latest_industry_emotion(db: Session) -> Optional[Dict[str, Any]]:
    """最新一日的行业恐贪快照；无数据返回 None（前端显示「暂无数据」）。

    - 快照 = 最新 collected_at 当日的全部行（当日轮换到什么就展示什么）；
    - ``history_days``：该 name 在库内的累积天数（含当日）。上游当日首次出现的
      行业为 1——前端可据此展示「已累积 N 天」并判断二期走势图何时可画；
    - items 按 value 降序（NULL 最后），前端可直接使用或重排。
    """
    latest_date = (
        db.query(func.max(MarketSingleValue.collected_at))
        .filter(
            MarketSingleValue.source == EMOTION_SOURCE,
            MarketSingleValue.stale.is_(False),
        )
        .scalar()
    )
    if latest_date is None:
        return None

    rows = (
        db.query(MarketSingleValue)
        .filter(
            MarketSingleValue.source == EMOTION_SOURCE,
            MarketSingleValue.collected_at == latest_date,
            MarketSingleValue.stale.is_(False),
        )
        .order_by(MarketSingleValue.value.desc())
        .all()
    )
    # 每 name 的累积天数：一次 group-by 计数，行数 ≤ 行业数 × 指标数，代价可忽略
    counts: Dict[str, int] = dict(
        db.query(MarketSingleValue.name, func.count())
        .filter(
            MarketSingleValue.source == EMOTION_SOURCE,
            MarketSingleValue.stale.is_(False),
        )
        .group_by(MarketSingleValue.name)
        .all()
    )

    items: List[Dict[str, Any]] = []
    for row in rows:
        industry, metric = split_emotion_name(row.name)
        items.append(
            {
                'name': row.name,
                'industry': industry,
                'metric': metric,
                'value': float(row.value) if row.value is not None else None,
                'history_days': int(counts.get(row.name, 0)),
            }
        )
    return {
        'updated_at': latest_date.isoformat(),
        'items': items,
        'source': EMOTION_SOURCE,
    }
