# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:20
# File : db_utils.py
# app/core/db_utils.py

"""数据库工具函数，如批量插入去重等"""

from typing import List

from sqlalchemy.orm import Session


def bulk_insert_if_not_exists(
    db: Session,
    model,
    data: List[dict],
    unique_key: str,
    batch_size: int = 1000,
) -> int:
    """
    批量插入不存在的记录，已存在的跳过。

    Args:
        db: SQLAlchemy Session
        model: ORM 模型类
        data: 待插入的字典列表，每个字典必须包含 unique_key 字段
        unique_key: 唯一键字段名（如 'fund_code', 'symbol'）
        batch_size: 每批插入数量

    Returns:
        实际插入的记录数
    """
    if not data:
        return 0

    total_inserted = 0
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]
        unique_values = [item[unique_key] for item in batch]

        existing = set(
            row[0]
            for row in db.query(getattr(model, unique_key)).filter(getattr(model, unique_key).in_(unique_values)).all()
        )

        new_data = [item for item in batch if item[unique_key] not in existing]
        if new_data:
            db.bulk_insert_mappings(model, new_data)
            total_inserted += len(new_data)

    db.flush()
    return total_inserted
