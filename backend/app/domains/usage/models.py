# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : models.py
"""通用用量表模型.

设计（issue #823）：一个表承载所有按日限次的付费候选功能，
按 (user_id, feature, period_date) 唯一计数，避免每功能建表。

用法示例：
    ocr_import  → 每日 5 次（OCR 截图导入）
    txn_import  → 后期交易记录导入（预留 feature 名）
"""

from sqlalchemy import Column, Date, Index, Integer, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class UserUsage(Base, PrimaryKeyMixin, TimestampMixin):
    """用户功能用量计数表（按日）。"""

    __tablename__ = 'user_usage'

    user_id = Column(Integer, nullable=False, index=True, comment='用户 ID')
    feature = Column(String(50), nullable=False, comment='功能名：ocr_import / txn_import')
    period_date = Column(Date, nullable=False, comment='统计周期（按自然日）')
    count = Column(Integer, nullable=False, default=0, comment='当日已用次数')
    quota = Column(Integer, nullable=False, default=5, comment='当日配额上限')

    __table_args__ = (
        UniqueConstraint('user_id', 'feature', 'period_date', name='uk_usage_user_feature_date'),
        Index('idx_usage_feature_date', 'feature', 'period_date'),
    )
