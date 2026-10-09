# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/9
# File : manager_profile.py
# app/services/manager_profile.py
"""基金经理资料聚合（#1970 · 产品详情页基金经理详情区块）。

反向于 :mod:`app.services.fund_profile`（那只回答「某只基金有哪些经理」）：
此处回答「**某位经理管过哪些基金**」。funds 域同样没有对应端点
（``/api/funds/managers/search/`` 是按姓名模糊搜，与本问题无关），故在此补出口。

## 为什么一期只给「任职基金列表」，且任期字段一律降级

设计文档 §6 标注经理「字段多为空 → 诚实降级」。本次对生产库（``managers`` 4267 行 /
``fund_managers`` 34812 行）实测填充率，结论与文档一致且更极端：

===========================  ==========  ======  ==========
字段                填充              说明
===========================  ==========  ======  ==========
``managers.name``            4267/4267  100%     可展示
``managers.company_id``      4264/4267  99.9%    可展示
``managers.appointment_date``      0/4267    0%  **全空**
``managers.sum_scale``             0/4267    0%  **全空**
``managers.best_return``           0/4267    0%  **全空**
``managers.avatar_url``            0/4267    0%  **全空**
``fund_managers.start_date``       0/34812   0%  **全空**
``fund_managers.end_date``         0/34812   0%  **全空**
===========================  ==========  ======  ==========

故任职起止、任期回报、管理规模一律返回 ``None``，前端显示「—」。
**不用 mock 顶替**（G1 教训），也不在本卡越界去爬数据源。

关联完整性实测：孤儿关联（``fund_id`` / ``mgr_id`` 失效）**0 条**，
无基金关联的经理**0 位**——故列表不需要额外的「数据异常」兜底分支。

## 为什么用 ``mgr_code`` 而非姓名做检索键

``managers`` 有 **119 组重名**（最多「吴昊」6 位、「张磊」「刘洋」各 5 位），
姓名不是唯一键；而 ``mgr_code`` 是 12 位哈希、100% 唯一，是 ``managers`` 表的
业务唯一键。故入参与路由均按 ``mgr_code``。

由于重名，列表里**必须带公司名**消歧，否则「吴昊」会显示成六个同名的人。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

# 列表默认返回条数。经理最多管 42 只基金，但那是极端值；20 条足够覆盖绝大多数，
# 且前端不做分页（详情页是「看一眼」的定位，不是列表页）。
DEFAULT_FUND_LIMIT = 20


def _iso(value) -> Optional[str]:
    """date/datetime → ISO 字符串；空值返回 None（前端降级为「—」）。"""
    if value is None:
        return None
    return value.isoformat()


def _fund_company(db: Session, company_id: Optional[int]) -> Optional[str]:
    """公司 id → 公司名。未绑定公司时返回 None。"""
    if not company_id:
        return None
    from app.domains.funds.models import FundCompany

    row = db.query(FundCompany.name).filter(FundCompany.id == company_id).first()
    return row[0] if row else None


def build_manager_profile(
    db: Session,
    mgr_code: str,
    fund_limit: int = DEFAULT_FUND_LIMIT,
) -> Optional[Dict[str, Any]]:
    """一次拼出单位基金经理的资料 + 其任职基金列表。

    Args:
        mgr_code: 12 位 ``managers.mgr_code``（**非姓名**，库内存在重名）。
        fund_limit: 任职基金返回条数上限。

    Returns:
        资料 dict；**经理不存在时返回 None**（由调用方转 404）。

    字段缺失一律 ``None``，由前端降级为「—」，不编造占位值。
    """
    from app.domains.funds.models import Manager

    code = (mgr_code or '').strip()
    if not code:
        raise ValueError('缺少 mgr_code')

    manager = db.query(Manager).filter(Manager.mgr_code == code).first()
    if manager is None:
        return None

    funds = _managed_funds(db, manager.id, fund_limit)

    return {
        'mgr_code': manager.mgr_code,
        'name': manager.name,
        # 重名靠公司消歧（库内 119 组重名，最多 6 位同名）
        'company': _fund_company(db, manager.company_id),
        'mgr_type': manager.mgr_type,
        # 以下四项实测填充率均为 0%，保留字段是为了让前端有明确的「降级目标」，
        # 而不是靠「字段不存在」来表达未落库（#1400 类数据缺口的通用约定）。
        'appointment_date': _iso(manager.appointment_date),
        'sum_scale': float(manager.sum_scale) if manager.sum_scale is not None else None,
        'best_return': float(manager.best_return) if manager.best_return is not None else None,
        'avatar_url': manager.avatar_url or None,
        'fund_count': funds['total'],
        'funds': funds['items'],
    }


def _managed_funds(db: Session, mgr_id: int, limit: int) -> Dict[str, Any]:
    """任职基金列表 + 总数。

    关联完整性已实测（孤儿 0 条），故不再逐条判断「基金是否已删除」。
    排序取**基金简称**而非任职起始日——``start_date`` 填充率为 0%，拿它排序会
    退化成无序（全表同值），按名称排至少稳定可读。
    """
    from app.domains.funds.models import Fund, FundManager

    total = db.query(FundManager).filter(FundManager.mgr_id == mgr_id).count()

    rows = (
        db.query(Fund.fund_code, Fund.name, FundManager.is_classic)
        .join(FundManager, FundManager.fund_id == Fund.id)
        .filter(FundManager.mgr_id == mgr_id)
        .order_by(Fund.name)
        .limit(limit)
        .all()
    )

    items: List[Dict[str, Any]] = [
        {
            'fund_code': fund_code,
            'name': name,
            'is_classic': bool(is_classic),
            # 任期起止实测全空，仍返回 key 以固定契约（前端统一降级「—」）
            'start_date': None,
            'end_date': None,
        }
        for fund_code, name, is_classic in rows
    ]

    return {'total': total, 'items': items}
