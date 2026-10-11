# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/10
# File : advisor_profile.py
# app/services/advisor_profile.py
"""投顾组合资料聚合（#1975 · 产品详情页投顾组合区块）。

## 为什么补这个端点

``advisor_portfolios`` 的**档案与指标字段此前没有任何读取出口** —— funds 域只有
``advisors/<code>/holdings/`` 与 ``advisors/<code>/adjusts/`` 两个端点，它们回答
「持什么、调过什么」，回答不了「这是个什么组合」。而详情页首屏要的正是后者。

照 :mod:`app.services.fund_profile`（#1968）/ :mod:`app.services.manager_profile`（#1970）
的惯例放在 products 域：它们服务的是**同一个详情页**，同族。

持仓与调仓**不复用不了也没重写** —— 那两个端点已上线且被自选速览抽屉消费，本端点只补档案。

## 字段可得性（本机真实库实测，105 个组合）

=========================================  =========  ==================================
字段                                        填充        处置
=========================================  =========  ==================================
``name`` / ``platform`` / ``org_name``        100%    展示
``risk_level``                                100%    展示
``annual_return`` 及 ``return_1d..1y``      91~98%    展示
``return_since_incep``                       98.1%    展示
``estab_date`` / ``strategy_desc``          97~99%    展示
``allocation`` / ``strategy_summary``       96~97%    展示
``max_drawdown`` / ``volatility``           92~95%    展示
``sharpe_ratio`` / ``nav`` / ``source_url`` 92~96%    展示
**``host``（主理人）**                       **1.9%**  返回，多为 None
**``return_ytd``**                           **2.9%**  返回 None
**``strategy_type`` / ``cum_return`` /        **0%**  返回 None（固定契约，前端「—」）
``running_days`` / ``benchmark`` /
``excess_return``
=========================================  =========  ==================================

⚠️ 设计 §2.6 要求组合类标的靠「名称 + 品类 + **平台/主理人**」识别，但主理人实测几乎
全空（2/105）。故识别信息实际由「**名称 + 平台 + 机构**（``org_name``，100%）」承担，
主理人有值时才显示 —— 不为了凑设计条文去编一个主理人。

## 为什么把恒为 None 的字段也返回

**固定契约**：前端拿到 key 才知道「这个位置本该有值、只是没数据」，从而降级「—」；
若字段直接缺席，前端只能猜是「这个品类没有这项」还是「这次没取到」。
与 `manager_profile` 处理 0% 填充字段的做法一致（#1400 数据缺口的通用约定）。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

# 需要 float() 化的数值列（Decimal → float，前端直接渲染）。
# 全部为 None 时也保留 key —— 见模块 docstring「固定契约」。
_NUMERIC_FIELDS = (
    'annual_return',
    'cum_return',
    'return_1d',
    'return_1w',
    'return_1m',
    'return_1q',
    'return_6m',
    'return_1y',
    'return_ytd',
    'return_since_incep',
    'max_drawdown',
    'volatility',
    'sharpe_ratio',
)


def _iso(value) -> Optional[str]:
    """date/datetime → ISO 字符串；空值返回 None（前端降级为「—」）。"""
    if value is None:
        return None
    return value.isoformat()


def _num(value) -> Optional[float]:
    """Decimal/数值 → float；空值返回 None。"""
    return float(value) if value is not None else None


def build_advisor_profile(db: Session, code: str) -> Optional[Dict[str, Any]]:
    """拼出投顾组合的档案 + 可得指标。

    Args:
        code: ``advisor_portfolios.code``（平台组合码，如 ``ZH012926`` / ``XCOVSEX``）。

    Returns:
        档案 dict；**组合不存在时返回 None**（由调用方转 404）。

    字段缺失一律 ``None``，由前端降级为「—」，不编造占位值。
    """
    from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorPortfolio

    normalized = (code or '').strip()
    if not normalized:
        raise ValueError('缺少 code')

    portfolio = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == normalized).first()
    if portfolio is None:
        return None

    # 持仓 / 调仓的**条数**：让前端据此决定「要不要渲染那一块、发不发那两个请求」。
    # 实测调仓只覆盖 16/105 个组合，多数组合点进来是没有调仓的 —— 有计数才能给准确空态，
    # 而不是先请求两次再显示「暂无」。
    holding_count = db.query(AdvisorHolding).filter(AdvisorHolding.portfolio_id == portfolio.id).count()
    adjust_count = db.query(AdvisorAdjustHistory).filter(AdvisorAdjustHistory.portfolio_id == portfolio.id).count()

    profile: Dict[str, Any] = {
        'code': portfolio.code,
        'name': portfolio.name,
        # 平台码（QIEMAN/TIANTIAN…）→ 中文标签由前端 constants/advisorPlatform 负责，
        # 后端不重复维护一份映射。
        'platform': portfolio.platform,
        'org_name': portfolio.org_name,
        'host': portfolio.host or None,
        'risk_level': portfolio.risk_level,
        'product_type': portfolio.product_type,
        'strategy_type': portfolio.strategy_type,
        'strategy_summary': portfolio.strategy_summary,
        'strategy_desc': portfolio.strategy_desc,
        'allocation': portfolio.allocation,
        'estab_date': _iso(portfolio.estab_date),
        'running_days': portfolio.running_days,
        'benchmark': portfolio.benchmark,
        'excess_return': _num(portfolio.excess_return),
        'nav': _num(portfolio.nav),
        'nav_date': _iso(portfolio.nav_date),
        'source_url': portfolio.source_url,
        'is_active': bool(portfolio.is_active),
        'holding_count': holding_count,
        'adjust_count': adjust_count,
    }
    profile.update({field: _num(getattr(portfolio, field)) for field in _NUMERIC_FIELDS})
    return profile
