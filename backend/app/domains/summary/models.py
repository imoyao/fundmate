# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/10 21:00
# File : models.py
"""资产快照模型：每日记录家庭总资产/负债/净资产，支撑同比计算（历史积累期）。"""

from sqlalchemy import Column, Date, Integer, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


class AssetSnapshot(Base, PrimaryKeyMixin, TimestampMixin):
    """家庭每日资产快照。

    与 D1 家庭共享层一致按 `family_id`（而非 user_id）隔离；金额一律整数分（×100）。
    (family_id, snapshot_date) 唯一约束实现幂等 upsert：同一自然日重复记录会覆盖更新。
    """

    __tablename__ = 'asset_snapshots'
    __table_args__ = (UniqueConstraint('family_id', 'snapshot_date', name='uq_asset_snapshots_family_date'),)

    family_id = Column(Integer, default=1, index=True, comment='归属家庭 ID（家庭共享层隔离键）')
    snapshot_date = Column(Date, nullable=False, comment='快照日期（上海时区本地日期）')
    total_assets = Column(Integer, nullable=False, comment='总资产（分）')
    total_liabilities = Column(Integer, nullable=False, comment='总负债（分）')
    net_worth = Column(Integer, nullable=False, comment='净资产（分）')
