# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : fund_profile.py
# app/services/fund_profile.py
"""基金资料聚合（#1968 · 产品详情页基金详情区块）。

为什么需要这个聚合函数（issue 的硬规则「拼不出首屏就在本卡内补端点」）：

- **日涨跌**：funds 域没有任何端点直接给。它必须由「最近两日单位净值」算出，
  照搬前端拼装就是两次串行请求（``?date=`` 当日 + 前一日），详情页首屏直接被拉长；
- **基金经理**：funds 域**根本没有「某只基金的经理」端点**——唯一暴露经理的
  ``/api/funds/managers/search/`` 是按经理姓名模糊搜，与「某只基金有哪些经理」无关。
  关系只在 ``funds.managers``（经 ``fund_managers`` 关联表）里；
- 费率虽有 ``/api/funds/<code>/fee-rates/``，但与净值/经理分属不同步的请求。

故此处**一次查完**并返回，前端一次请求拿到首屏所需全部字段。字段缺失一律返回
``None`` 由前端降级为「—」，不编造占位值。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session


def _latest_two_navs(db: Session, fund_code: str) -> List[Any]:
    """最近两条单位净值（倒序：第 0 条是最新）。"""
    from app.domains.funds.models import DailyWorth

    return (
        db.query(DailyWorth.date, DailyWorth.unit_nav)
        .filter(DailyWorth.fund_code == fund_code, DailyWorth.unit_nav.isnot(None))
        .order_by(DailyWorth.date.desc())
        .limit(2)
        .all()
    )


def _change_pct(latest: Optional[float], prev: Optional[float]) -> Optional[float]:
    """日涨跌（%）。前一日缺失或为 0 时返回 None——不返回 0，避免「没数据」被读成「没涨」。"""
    if latest is None or not prev:
        return None
    return round((latest - prev) / prev * 100, 2)


def _managers_of(fund) -> List[Dict[str, Any]]:
    """基金经理列表（含所属公司），按经理姓名排序。"""
    managers = []
    for mgr in getattr(fund, 'managers', []) or []:
        company = getattr(mgr, 'company', None)
        managers.append(
            {
                'mgr_code': mgr.mgr_code,
                'name': mgr.name,
                'company': getattr(company, 'name', None),
                'appointment_date': mgr.appointment_date.isoformat() if mgr.appointment_date else None,
            }
        )
    managers.sort(key=lambda m: m['name'] or '')
    return managers


def _fee_rates_of(db: Session, fund_code: str) -> Optional[Dict[str, Any]]:
    """费率（申购/赎回阶梯）。取不到时返回 None，由前端降级为「—」。"""
    from app.services.fund_service import FundService

    try:
        return FundService.get_fund_fee_rates(db, fund_code)
    except Exception:
        # 费率是补充信息，缺它不该让整个资料不可用
        return None


def build_fund_profile(db: Session, fund_code: str) -> Optional[Dict[str, Any]]:
    """一次拼出单只基金的资料（首屏四项 + 费率 / 经理 / 类型 / 规模）。

    Returns:
        资料 dict；**基金不存在时返回 None**（由调用方转 404）。
    """
    from app.domains.funds.models import Fund

    code = (fund_code or '').strip()
    if not code:
        raise ValueError('缺少 fund_code')

    fund = db.query(Fund).filter(Fund.fund_code == code).first()
    if fund is None:
        return None

    navs = _latest_two_navs(db, code)
    latest_date, latest_nav = navs[0] if navs else (None, None)
    prev_date, prev_nav = navs[1] if len(navs) >= 2 else (None, None)
    latest_nav = float(latest_nav) if latest_nav is not None else None
    prev_nav = float(prev_nav) if prev_nav is not None else None

    company = getattr(fund, 'company', None)
    fund_type = getattr(fund, 'fund_type', None)
    variety = getattr(fund, 'variety', None)

    return {
        'fund_code': fund.fund_code,
        'name': fund.name,
        'full_name': fund.full_name,
        # 类型标签直接用后端中文名（小类 / 大类），前端不另建映射表
        'fund_type': getattr(fund_type, 'name', None),
        'fund_variety': getattr(variety, 'name', None),
        'company': getattr(company, 'name', None),
        # 首屏三项：单位净值 + 净值日期 + 日涨跌
        'unit_nav': latest_nav,
        'nav_date': latest_date.isoformat() if latest_date else None,
        'prev_unit_nav': prev_nav,
        'prev_nav_date': prev_date.isoformat() if prev_date else None,
        'change_pct': _change_pct(latest_nav, prev_nav),
        # 资料项
        'scale': float(fund.scale) if fund.scale is not None else None,
        'create_time': fund.create_time.isoformat() if fund.create_time else None,
        'risk_level': fund.risk_level,
        'benchmark': fund.benchmark,
        'managers': _managers_of(fund),
        'fee_rates': _fee_rates_of(db, code),
    }
