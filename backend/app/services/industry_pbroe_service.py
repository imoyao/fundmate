# -*- coding: utf-8 -*-
"""行业 PB-ROE 读取服务（#2481）：探市行业比较的数据出口。

数据来源只有一处：``market_composites``（source='jiucaishuo_pbroe'，
由 ``sync/jobs/industry_pbroe_job.py`` 每日写入）。本模块**纯只读**。

展示层约定：散点图 x=ROE(%)、y=PB；``update_time`` 为上游数据日期，
前端须原样展示「数据更新至 X」——不伪装实时。负 ROE 行业有效（PB-ROE
模型下负盈利行业照样在图上），不做剔除。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.domains.temperature.models import MarketComposite

PBROE_SOURCE = 'jiucaishuo_pbroe'


def get_latest_industry_pbroe(db: Session) -> Optional[Dict[str, Any]]:
    """最新一日的行业 PB-ROE 矩阵；无数据返回 None（前端显示「暂无数据」）。

    读侧只看 ``stale=False`` 的最近一行——上游失败当日本来就不会落库
    （job 的 _allow_empty_data 路径），不存在「写进去又标 stale」的形态，
    但保留该过滤与 temperature 读侧同构，防未来写入侧变化。
    """
    record = (
        db.query(MarketComposite)
        .filter(MarketComposite.source == PBROE_SOURCE, MarketComposite.stale.is_(False))
        .order_by(MarketComposite.collected_at.desc())
        .first()
    )
    if record is None:
        return None
    data = dict(record.data or {})
    data['collected_at'] = record.collected_at.isoformat()
    data['source'] = PBROE_SOURCE
    return data
