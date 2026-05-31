# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:22
# File : sync_log.py
# -*- coding: utf-8 -*-
# app/models/sync_log.py
"""元数据同步审计日志模型"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, desc

from app.core.database import Base, PrimaryKeyMixin


class SyncLog(Base, PrimaryKeyMixin):
    __tablename__ = 'sync_logs'

    job_name = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False)
    full_sync = Column(Boolean, default=False)
    stats = Column(Text, nullable=True)
    error_detail = Column(Text, nullable=True)
    data_source = Column(String(50), nullable=True)
    data_source_version = Column(String(20), nullable=True)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    @classmethod
    def get_last_sync_time(cls, db, job_name: str) -> Optional[datetime]:
        """获取指定任务最后一次成功同步的开始时间（用于增量同步基准）"""
        log = (
            db.query(cls)
            .filter(cls.job_name == job_name, cls.status == 'success')
            .order_by(desc(cls.started_at))
            .first()
        )
        return log.started_at if log else None
