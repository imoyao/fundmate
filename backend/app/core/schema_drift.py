# -*- coding: utf-8 -*-
"""表结构漂移的**只读**探查（#2498）。

只读的原因
----------
``init_db()`` 里那一批 ``migrate_*`` 存量迁移**只对 SQLite 生效**，Postgres 路径一律
``[SKIP]``（见 ``migrations.migrate_watchlist_name_snapshot`` 的注释：「非 SQLite 引擎由 ORM
模型 / 迁移工具负责，直接跳过」）。于是生产的 user 域（Supabase）**永远不会被补列**——
``_validate_schema`` 每次启动都报同一处漂移，而报错只说「缺列」，说不出修复要付什么代价。

本模块只回答「漂到哪、修起来是哪一类活」，不执行任何 DDL：

=====================  ==========================================================
结论                    含义（决定谁来修、怎么修）
=====================  ==========================================================
``auto_addable``        只缺**非主键**列 → 可 ``ALTER TABLE ADD COLUMN`` 直接补
``requires_identity``   缺的是**模型主键列**，或库里主键与模型不一致 → 补列不够，
                        要**重建表 / 加主键约束**，且要先确认存量行（行数在这里给出）
``extra_columns``       库里有、模型没有的列 → **只报告，不删**（删列不可逆）
=====================  ==========================================================

为什么不直接做成「启动时自动补」
--------------------------------
补非主键列是安全的；但给存量表补主键（``watchlist_item_tags.id``）在 Postgres 与 SQLite 上
是两套动作（前者可 ``ADD COLUMN BIGSERIAL`` 再 ``ADD PRIMARY KEY``，后者必须整表重建），
且「历史行有没有、主键原来是什么」决定了旧行的归属。这类变更**不能靠猜**——
先只读地把事实列出来，再由人拍板。
"""

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy import inspect, text


@dataclass(frozen=True)
class TableDrift:
    """一张存量表的漂移现场（全部来自反射 + 模型，不写入）。"""

    table: str
    missing_columns: Tuple[str, ...]
    extra_columns: Tuple[str, ...]
    db_primary_key: Tuple[str, ...]
    model_primary_key: Tuple[str, ...]
    row_count: Optional[int] = None

    @property
    def missing_primary_key_columns(self) -> Tuple[str, ...]:
        """缺的列里属于模型主键的那些（补它们 = 改身份，不是补字段）。"""
        return tuple(col for col in self.missing_columns if col in self.model_primary_key)

    @property
    def primary_key_shape_differs(self) -> bool:
        """库里的主键与模型声明不一致（含「库里根本没有主键」）。"""
        return set(self.db_primary_key) != set(self.model_primary_key)

    @property
    def requires_identity_change(self) -> bool:
        """补列之外还要动主键 ⇒ 必须先有人拍板（重建表 / 加约束 / 旧行归属）。"""
        return bool(self.missing_primary_key_columns) or self.primary_key_shape_differs

    @property
    def auto_addable_columns(self) -> Tuple[str, ...]:
        """能直接 ``ALTER TABLE ADD COLUMN`` 的缺列（排除主键列）。"""
        return tuple(col for col in self.missing_columns if col not in self.model_primary_key)


def collect(bind: Any, tables: Sequence[Any]) -> List[TableDrift]:
    """比对「已有表」的库结构与模型定义，返回漂移清单（无漂移的表不出现）。

    Args:
        bind: SQLAlchemy engine（**任一数据域**均可；本函数不写库）。
        tables: 要检查的 ``Table`` 集合（调用方按数据域筛好；本模块不猜注册表）。

    Note:
        库里不存在的表不在此列：``create_all`` 会按新模型建表，报出来只会制造噪音。
        行数只对**需要改身份**的表统计（``COUNT(*)`` 在大表上不便宜，其余表不需要这个数）。
    """
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    drifts: List[TableDrift] = []

    for table in tables:
        if table.name not in existing_tables:
            continue
        db_columns = {column['name'] for column in inspector.get_columns(table.name)}
        model_columns = {column.name for column in table.columns}
        missing = tuple(sorted(model_columns - db_columns))
        extra = tuple(sorted(db_columns - model_columns))
        if not missing and not extra:
            continue
        primary_key = inspector.get_pk_constraint(table.name)
        drift = TableDrift(
            table=table.name,
            missing_columns=missing,
            extra_columns=extra,
            db_primary_key=tuple(primary_key.get('constrained_columns') or ()),
            model_primary_key=tuple(column.name for column in table.primary_key.columns),
        )
        if drift.requires_identity_change:
            drift = TableDrift(**{**drift.__dict__, 'row_count': _count_rows(bind, table.name)})
        drifts.append(drift)
    return drifts


def split_tables(bind: Any, tables: Sequence[Any]) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """把待检表分成「库里存在」与「库里不存在」两组。

    为什么必须分开：``collect()`` 会跳过不存在的表（交给 ``create_all``），于是**空库**
    与**无漂移**在返回值上完全一样（都是空列表）。只读报告若把两者说成一句话，
    就会在空库上输出「✅ 没有结构漂移」——那是「还没有存量结构可查」，不是结论
    （同族：#171 拿不到输入却输出一个看起来正常的结论）。
    """
    existing = set(inspect(bind).get_table_names())
    present = tuple(table.name for table in tables if table.name in existing)
    absent = tuple(table.name for table in tables if table.name not in existing)
    return present, absent


def _count_rows(bind: Any, table_name: str) -> Optional[int]:
    """``COUNT(*)``；读不到就返回 ``None``（**不返回 0**：0 会被读成「表是空的，随便改」）。"""
    quoted = bind.dialect.identifier_preparer.quote(table_name) if bind.dialect else table_name
    try:
        with bind.connect() as conn:
            return int(conn.execute(text(f'SELECT COUNT(*) FROM {quoted}')).scalar() or 0)
    except Exception:  # noqa: BLE001 - 读不到行数不是致命错误，但必须显式为 None
        return None


def render(drifts: Sequence[TableDrift], absent_tables: Sequence[str] = ()) -> str:
    """人话报告（终端直接可读；不打印任何连接串 / 凭据）。

    Args:
        drifts: :func:`collect` 的结果。
        absent_tables: 库中不存在的待检表。**必须传**，否则空库与无漂移会输出同一句话。
    """
    if not drifts:
        if absent_tables:
            sample = ', '.join(absent_tables[:6])
            more = '…' if len(absent_tables) > 6 else ''
            return (
                f'⚠️ 待检的 {len(absent_tables)} 张表在库里不存在（空库 / 未初始化）：{sample}{more}\n'
                '   create_all 会按新模型建表；**本次不构成「没有漂移」的结论**（还没有存量结构可查）。'
            )
        return '✅ 没有结构漂移：模型里的每一列在库里都存在。'
    lines: List[str] = [f'发现 {len(drifts)} 张表结构漂移：', '']
    for drift in drifts:
        lines.append(f'- 表 {drift.table}')
        if drift.missing_columns:
            lines.append(f'    缺列: {", ".join(drift.missing_columns)}')
        if drift.extra_columns:
            lines.append(f'    库多列（只报告，不删）: {", ".join(drift.extra_columns)}')
        lines.append(f'    主键: 库里 {list(drift.db_primary_key) or "无"} / 模型 {list(drift.model_primary_key)}')
        if drift.row_count is not None:
            lines.append(f'    存量行数: {drift.row_count}')
        if drift.requires_identity_change:
            reason = '缺主键列' if drift.missing_primary_key_columns else '主键形态与模型不一致'
            lines.append(f'    ⚠️ 需要改身份（{reason}）⇒ 不能只补列：Postgres 可 ADD COLUMN + ADD PRIMARY KEY，')
            lines.append('       SQLite 必须整表重建；旧行归属需先确认（这是决策，不是配置）')
        if drift.auto_addable_columns:
            lines.append(f'    可直接补（ALTER TABLE ADD COLUMN）: {", ".join(drift.auto_addable_columns)}')
        lines.append('')
    if absent_tables:
        sample = ', '.join(absent_tables[:6])
        more = '…' if len(absent_tables) > 6 else ''
        lines.append(f'另有 {len(absent_tables)} 张待检表在库里不存在（create_all 会建）：{sample}{more}')
    return '\n'.join(lines).rstrip()
