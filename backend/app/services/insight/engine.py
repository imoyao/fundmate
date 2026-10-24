# -*- coding: utf-8 -*-
# File : engine.py
# app/services/insight/engine.py
"""诊断提示的取数 + 规则执行（#1017）。

## 取数只复用既有口径，不另算一遍

| 快照字段 | 来源 | 为什么是它 |
|---|---|---|
| `holdings` / `total_cents` | `position_aggregation.get_fund_aggregation` + `get_securities_aggregation` | 与持仓页同一个聚合入口，过滤规则（类现金排除、ownership 等）不重写 |
| `top_industry` / `penetration_ratio` | `penetration.build_penetration`（主口径 `csrc`） | 行业数据只有这一条链路，自己 join 会造第二套口径 |
| `latest_day` | `pnl_calendar.build_daily_pnl_series` 的最近有效日 | 组合级日收益率，与收益日历同源 |

**只读、不落库**：提示是派生结果，没有「历史上的提示」这种语义（同一账户同一时点结果必然相同），
落库只会带来过期数据与同步负担。

## 降级原则

任一路取数失败 → 对应维度置空（`top_industry=None` 等），**其余规则照跑**；
一条数据源挂掉不该让整页提示消失。取不到就明确不提示，不用 0 冒充。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.services.insight.rules import evaluate
from app.services.penetration import build_penetration
from app.services.pnl_calendar import build_daily_pnl_series
from app.services.position_aggregation import get_fund_aggregation, get_securities_aggregation

# 行业集中度看主口径（证监会门类）。GICS / 申万是「同一批基金的另一块敞口」，
# 不可跨体系相加（见 penetration 模块头），所以这里只取主口径。
INDUSTRY_SCHEME = 'csrc'

# 日跌幅只看最近这么多个自然日，够覆盖周末/长假后的第一个交易日
LATEST_WINDOW_DAYS = 10


def _load_holdings(db: Session, family_id: int) -> List[Dict[str, Any]]:
    """全量投资持仓（基金 + 证券），分页关掉。"""
    rows: List[Dict[str, Any]] = []
    for getter in (get_fund_aggregation, get_securities_aggregation):
        try:
            payload = getter(db, family_id, page_size=0)
        except Exception as e:
            logger.warning(f'诊断取数失败({getter.__name__})，该维度降级为空: {e}')
            continue
        # product 维度下 `groups` 的每一项就是「一只标的」（跨渠道已合并），不是分页行袋
        rows.extend(payload.get('groups') or [])
    return [
        {
            'symbol': row.get('symbol'),
            'name': row.get('name'),
            'asset_type': row.get('asset_type'),
            'market_value_cents': row.get('market_value_cents') or 0,
        }
        for row in rows
    ]


def _load_top_industry(db: Session, family_id: int) -> tuple[Optional[Dict[str, Any]], float]:
    try:
        penetration = build_penetration(db, family_id, scheme=INDUSTRY_SCHEME, top_n=1)
    except Exception as e:
        logger.warning(f'诊断取数失败(行业穿透)，该规则降级不触发: {e}')
        return None, 0.0
    industries = penetration.get('industries') or []
    ratio = ((penetration.get('coverage') or {}).get('penetrated_ratio')) or 0
    top = industries[0] if industries else None
    return top, float(ratio)


def _load_latest_day(db: Session, family_id: int) -> Optional[Dict[str, Any]]:
    """最近一个**有效**交易日的组合收益率（百分比）。"""
    try:
        series = build_daily_pnl_series(db, family_id=family_id)
    except Exception as e:
        logger.warning(f'诊断取数失败(收益日历)，单日跌幅规则降级不触发: {e}')
        return None
    for day in reversed(series.get('days') or []):
        rate = day.get('rate')
        if rate is not None:
            return {'date': day.get('date'), 'rate_pct': float(rate)}
    return None


def build_snapshot(db: Session, family_id: int = 1) -> Dict[str, Any]:
    """构造规则读数所需的一次性快照（各数据源各查一次）。"""
    holdings = _load_holdings(db, family_id)
    total_cents = sum(row['market_value_cents'] for row in holdings)
    top_industry, penetration_ratio = _load_top_industry(db, family_id)
    non_zero = [row for row in holdings if row['market_value_cents'] > 0]
    return {
        'holdings': non_zero,
        'total_cents': total_cents,
        'holding_count': len(non_zero),
        'top_industry': top_industry,
        'penetration_ratio': penetration_ratio,
        'latest_day': _load_latest_day(db, family_id),
    }


def build_tips(db: Session, family_id: int = 1) -> Dict[str, Any]:
    """跑一遍注册表，返回提示列表 + 快照摘要（前端要拿摘要解释「为什么没有提示」）。"""
    snapshot = build_snapshot(db, family_id)
    tips = evaluate(snapshot)
    logger.info(f'诊断提示完成(family_id={family_id}): 命中 {len(tips)} 条')
    return {
        'items': tips,
        'count': len(tips),
        'snapshot': {
            'holding_count': snapshot['holding_count'],
            'total_value_cents': snapshot['total_cents'],
            'penetration_ratio': round(snapshot['penetration_ratio'], 4),
            'latest_day': snapshot['latest_day'],
        },
    }
