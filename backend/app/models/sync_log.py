# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:22
# File : sync_log.py
# -*- coding: utf-8 -*-
# app/models/sync_log.py
"""元数据同步审计日志模型"""

import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, Column, DateTime, Float, String, Text, desc, text
from sqlalchemy.orm import Session

from app.core.database import Base, PrimaryKeyMixin
from app.core.time_utils import now_shanghai


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


#: 与 SQLite `DateTime` 列的存储形态一致（SQLAlchemy 的默认 `storage_format`）
AUDIT_TS_FORMAT = '%Y-%m-%d %H:%M:%S.%f'


def insert_audit_row(
    db: Session,
    *,
    job_name: str,
    status: str,
    stats: Optional[Dict[str, Any]] = None,
    full_sync: bool = False,
    data_source: str = 'local',
) -> None:
    """往 `sync_logs` 写一行审计记录（本表**唯一**的原生 SQL 写入口）。

    三条约束都是踩出来的（#3182，2026-11-19）：

    1. **时间必须先格式化成字符串**。原生 `text()` 没有列类型信息，SQLAlchemy 不会给参数
       套 `DateTime` 的绑定处理器，`datetime` 对象会原样交给驱动；Turso 的 libsql 驱动只认
       int / float / str / bytes / None，`cursor.execute` 抛
       `ValueError: Unsupported parameter type`——冷集膨胀巡检与份额反证巡检两条审计写入
       因此**同时**失效，而本机 SQLite 复现不出来（它自带已废弃的 datetime 适配器会悄悄
       转成字符串）。ORM 路径没事：那边类型来自列定义。格式取 SQLite `DateTime` 的存储
       形态，读回来仍是同值 datetime。
    2. **`full_sync` 显式转 0/1**：bool 虽是 `int` 子类，但别把「驱动认不认子类」当契约。
    3. **不在这里 commit**：事务边界归调用方（两处都按自己的 `commit` 参数决定）。

    不用 ORM 的理由见 `cold_set_guard.last_guard_stats`：`SyncLog` 走 ORM 会触发 mapper
    全量解析，把 `Ledger→Fund` 这类跨域关系拉进来（实测 `InvalidRequestError`）。
    `sync_logs` 属 market 域，裸 SQL 在这里落点是对的。
    """
    ts = now_shanghai().strftime(AUDIT_TS_FORMAT)
    db.execute(
        text(
            'INSERT INTO sync_logs '
            '(job_name, status, full_sync, stats, data_source, started_at, finished_at) '
            'VALUES (:job, :status, :full_sync, :stats, :src, :started, :finished)'
        ),
        {
            'job': job_name,
            'status': status,
            'full_sync': int(bool(full_sync)),
            'stats': json.dumps(stats or {}, ensure_ascii=False),
            'src': data_source,
            'started': ts,
            'finished': ts,
        },
    )
