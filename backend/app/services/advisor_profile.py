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
~~``strategy_type`` / ``cum_return`` /        ~~0%~~    2026-10-29 起：``cum_return`` /
``running_days`` / ``benchmark`` /                     ``running_days`` 由适配器补写；
``excess_return``~~                                    ``excess_return`` 读取侧现算；
                                                       ``strategy_type`` / ``benchmark``(名称)
                                                       仍无写者（tech-debt）
=========================================  =========  ==================================

> ⚠️ 上表是 **2026-10-10 本机库快照**，不要当成实时事实：2026-10-29 复测时
> ``max_drawdown`` / ``sharpe_ratio`` / ``running_days`` / ``return_2y`` / ``return_3y`` /
> ``benchmark_return_*`` 在天天侧**已有数据源**（适配器此前没请求），下一次同步后才会填充；
> 这里不改数字，只记录「为什么它当时是 0%」——否则下一个人会把 0% 当成数据源缺失。

## 派生字段的处理

``excess_return`` **不读库列**（该列没有写者），由本模块用
``return_since_incep − benchmark_return_since_incep`` 现算；任一缺失给 ``None``，
**不把缺失当 0**（否则「基准还没披露」会渲染成「跑赢 25 个百分点」）。

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
    'return_2y',
    'return_3y',
    'return_ytd',
    'return_since_incep',
    'max_drawdown',
    'volatility',
    'sharpe_ratio',
    # 投顾详情页 P0（2026-10-29）：业绩基准同区间收益，与上面 return_* 逐区间配对。
    # 前端「业绩表现」表每行三列（本组合 / 业绩基准 / 超额），基准列直接读这些键。
    'benchmark_return_1m',
    'benchmark_return_1q',
    'benchmark_return_6m',
    'benchmark_return_ytd',
    'benchmark_return_1y',
    'benchmark_return_2y',
    'benchmark_return_3y',
    'benchmark_return_since_incep',
)


def _excess(nav: Optional[float], bench: Optional[float]) -> Optional[float]:
    """区间超额 = 组合收益 − 基准收益；任一缺失 → None（不把缺失当 0 参与减法）。

    「把 None 当 0」会让「基准还没披露」渲染成「跑赢基准 25 个百分点」——宁可显示「—」。
    """
    if nav is None or bench is None:
        return None
    return round(nav - bench, 2)


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
        'excess_return': None,  # 见下方「读取侧现算」，先占位保证 key 恒存在
        'nav': _num(portfolio.nav),
        'nav_date': _iso(portfolio.nav_date),
        'source_url': portfolio.source_url,
        'is_active': bool(portfolio.is_active),
        'holding_count': holding_count,
        'adjust_count': adjust_count,
    }
    profile.update({field: _num(getattr(portfolio, field)) for field in _NUMERIC_FIELDS})
    # 超额收益：**读取侧现算**，不读库内 ``excess_return`` 列（该列无写者，见 models 注释）。
    # 取「成立以来」这一组，因为它是唯一在天天两个数据面都稳定有值的同区间对
    # （组合 SYL_LN ↔ 基准 BENCHSYL_LN）；其余区间的超额由前端按同一公式
    # `return_x - benchmark_return_x` 自算 —— 派生值多一个后端出口，就多一处会算错的地方。
    profile['excess_return'] = _excess(profile.get('return_since_incep'), profile.get('benchmark_return_since_incep'))
    return profile
