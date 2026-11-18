# -*- coding: utf-8 -*-
"""家庭财务规划配置服务（财务晴雨表 v2）。

只做配置的读写；自由度等派生比率在前端 financialHealth.ts 算，
后端不跨端重复造数（与 dividend_service 的 target 读写同模式）。

金额边界：API 层用元（float），存储层用整数分。null 表示「未配置」，
与 0 严格区分——0 元是用户真的填了 0，会让自由度分母为 0（不可算），
null 是还没填，两者在前端的提示文案不同。
"""

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.financial_plan.models import FamilyFinancialPlan
from app.domains.financial_plan.schemas import FinancialPlanUpdate


def read_plan(db: Session, family_id: int) -> dict[str, Any]:
    """读取家庭财务规划配置（元）。未配置返回两个 None，不抛 404。"""
    row = db.query(FamilyFinancialPlan).filter(FamilyFinancialPlan.family_id == family_id).first()
    if row is None:
        return {'estimated_annual_expense': None, 'estimated_annual_income': None}
    return {
        'estimated_annual_expense': (
            Money.cents_to_yuan(row.estimated_annual_expense_cents)
            if row.estimated_annual_expense_cents is not None
            else None
        ),
        'estimated_annual_income': (
            Money.cents_to_yuan(row.estimated_annual_income_cents)
            if row.estimated_annual_income_cents is not None
            else None
        ),
    }


def _to_cents(value: Optional[float]) -> Optional[int]:
    """元→分；None 保持 None（未配置），不经过 Money（它把 None 当 0）。"""
    return None if value is None else Money.yuan_to_cents(value)


def upsert_plan(db: Session, family_id: int, payload: FinancialPlanUpdate) -> dict[str, Any]:
    """写入 / 更新家庭财务规划。调用方负责 commit。

    只更新 payload **显式传入**的字段（`model_fields_set`）：
    前端可能只改年收入、不碰年支出，整体覆盖会把没动的那项清掉。
    显式传 null 才清除该项（存 None）。
    """
    row = db.query(FamilyFinancialPlan).filter(FamilyFinancialPlan.family_id == family_id).first()
    if row is None:
        row = FamilyFinancialPlan(family_id=family_id)
        db.add(row)

    fields = payload.model_fields_set
    if 'estimated_annual_expense' in fields:
        row.estimated_annual_expense_cents = _to_cents(payload.estimated_annual_expense)
    if 'estimated_annual_income' in fields:
        row.estimated_annual_income_cents = _to_cents(payload.estimated_annual_income)
    db.flush()
    return read_plan(db, family_id)
