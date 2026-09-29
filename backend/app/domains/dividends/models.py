# -*- coding: utf-8 -*-
"""股息目标模型（#872）。

**为什么不建「分红事件表」**：现金分红 / 红利再投 / 送股 / 红利税的事实来源已经是
`transactions`（导入链路与手动记账写入），再建一张事件表就是把同一事实存两遍，
必然出现「流水有、事件表没有」的漂移。本域只补一份**用户私有配置**——
家庭级股息目标；逐持仓的实际股息率由 `services/dividend_service.py` 实时从流水算，
不落库，因此不存在「配置与流水两套真值」的问题。
"""

from sqlalchemy import Column, Numeric, String, UniqueConstraint

from app.core.database import Base, FamilyScopedMixin, PrimaryKeyMixin, TimestampMixin


class DividendTarget(Base, PrimaryKeyMixin, TimestampMixin, FamilyScopedMixin):
    """家庭级股息目标：期望的年化股息率（%）。

    一个家庭一条（`uq_dividend_target_family`）：目标是组合层面的一个数
    （issue #872 的「股息目标组合」，如年化股息率 ≥ 4%），不做逐持仓多目标——
    逐持仓只呈现**实际**值，避免「给每只标的设目标」把配置面撑爆。
    """

    __tablename__ = 'dividend_targets'
    __table_args__ = (UniqueConstraint('family_id', name='uq_dividend_target_family'),)

    target_yield_pct = Column(Numeric(6, 2), nullable=False, comment='目标年化股息率(%)，如 4.00')
    notes = Column(String(200), nullable=True, comment='目标备注（如"退休现金流规划"）')
