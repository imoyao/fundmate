# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 11:20
# File : db_utils.py
# app/core/db_utils.py

"""数据库工具函数，如批量插入去重等"""

from decimal import Decimal
from typing import List

from loguru import logger
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from sqlalchemy.types import Numeric, TypeDecorator


def bulk_insert_if_not_exists(
    db: Session,
    model,
    data: List[dict],
    unique_key: str,
    batch_size: int = 1000,
    unique_columns: List[str] = None,
) -> int:
    """
    批量插入不存在的记录，已存在的跳过。
    使用数据库原生冲突忽略机制，避免竞态条件。

    Args:
        db: SQLAlchemy Session
        model: ORM 模型类
        data: 待插入的字典列表
        unique_key: 单列唯一键字段名（兼容旧调用，当 unique_columns 未提供时使用）
        batch_size: 每批插入数量
        unique_columns: 联合唯一键列表，如 ['fund_code', 'date']。
                        提供时覆盖 unique_key，直接走数据库级冲突忽略。

    Returns:
        实际插入的记录数（估算值，冲突忽略时可能包含被跳过的条数）
    """
    if not data:
        return 0

    dialect_name = db.bind.dialect.name if hasattr(db.bind, 'dialect') else 'sqlite'

    # 确定冲突列
    if unique_columns:
        conflict_cols = unique_columns
    else:
        conflict_cols = [unique_key]

    total_inserted = 0
    for i in range(0, len(data), batch_size):
        batch = data[i : i + batch_size]

        if dialect_name == 'postgresql':
            stmt = pg_insert(model).values(batch).on_conflict_do_nothing(index_elements=conflict_cols)
        else:
            # SQLite 使用 INSERT OR IGNORE，需要完整的 INSERT 语句
            stmt = model.__table__.insert().prefix_with('OR IGNORE').values(batch)

        result = db.execute(stmt)
        total_inserted += result.rowcount if hasattr(result, 'rowcount') else len(batch)

    db.commit()
    return total_inserted


class SafeNumeric(TypeDecorator):
    """
    Numeric 安全适配器。

    - 写入时自动量化到指定位数
    - 读取时绕过 Numeric 默认处理器，直接处理原始值（兼容 SQLite TEXT）
    - 适用于所有数据库
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, *arg, **kw):
        super().__init__(*arg, **kw)
        self.quantize_exp = -self.impl.scale
        self.quantize_val = Decimal(10) ** self.quantize_exp

    def process_bind_param(self, value, dialect):
        """写入前转为数据库接受的数值类型"""
        if value is None:
            return None
        if isinstance(value, Decimal) and value.as_tuple()[2] < self.quantize_exp:
            value = value.quantize(self.quantize_val)

        # SQLite 严格模式下 REAL 列拒绝字符串，必须传入数值
        if dialect.name == 'sqlite':
            return float(value)
        # PostgreSQL 等可直接使用 Decimal
        return value

    def result_processor(self, dialect, coltype):
        """返回自定义结果处理器，代替 Numeric 默认的 DecimalResultProcessor"""

        def process(value):
            if value is None:
                return None
            if isinstance(value, Decimal):
                return value
            try:
                return Decimal(str(value))
            except (ValueError, TypeError):
                logger.warning(f'Invalid numeric value from DB: {value!r}')
                return None

        return process
