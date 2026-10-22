# -*- coding: utf-8 -*-
"""表结构漂移只读探查（#2498）。

判据：报告必须能区分两类活 ——「补非主键列」与「改身份（补主键 / 主键形态不一致）」，
并且**只读**（跑完库结构一字不改）。分不清这两类，用户就只能在「重建整表」和「补几列」之间猜。
"""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

from app.core.database import _validate_schema
from app.core.schema_drift import collect, render, split_tables


def _make_engine(tmp_path):
    return create_engine(f'sqlite:///{tmp_path / "drift.db"}')


def _legacy_groups(engine):
    """旧版 watchlist_groups：只有 id / name（模拟生产库的存量形态）。"""
    meta = MetaData()
    table = Table('watchlist_groups', meta, Column('id', Integer, primary_key=True), Column('name', String(50)))
    meta.create_all(bind=engine)
    return table


def _model_groups():
    """模型侧：多出 family_id / entity_type 两个非主键列。"""
    meta = MetaData()
    return Table(
        'watchlist_groups',
        meta,
        Column('id', Integer, primary_key=True),
        Column('name', String(50)),
        Column('family_id', Integer),
        Column('entity_type', String(20)),
    )


def test_missing_non_primary_key_columns_are_auto_addable(tmp_path):
    engine = _make_engine(tmp_path)
    _legacy_groups(engine)

    drifts = collect(engine, [_model_groups()])

    assert len(drifts) == 1
    drift = drifts[0]
    assert drift.missing_columns == ('entity_type', 'family_id')
    assert drift.auto_addable_columns == ('entity_type', 'family_id')
    assert drift.requires_identity_change is False
    assert drift.row_count is None  # 不需要改身份时不必 COUNT(*)


def test_missing_primary_key_column_requires_identity_change(tmp_path):
    """``watchlist_item_tags`` 的场景：模型有 id，库里没有 ⇒ 不能只补列。"""
    engine = _make_engine(tmp_path)
    legacy = MetaData()
    Table(
        'watchlist_item_tags',
        legacy,
        Column('item_id', Integer, primary_key=True),
        Column('tag_id', Integer, primary_key=True),
    )
    legacy.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text('INSERT INTO watchlist_item_tags (item_id, tag_id) VALUES (1, 11), (2, 22)'))

    model = MetaData()
    table = Table(
        'watchlist_item_tags',
        model,
        Column('id', Integer, primary_key=True),
        Column('item_id', Integer),
        Column('tag_id', Integer),
    )
    drift = collect(engine, [table])[0]

    assert drift.missing_columns == ('id',)
    assert drift.missing_primary_key_columns == ('id',)
    assert drift.auto_addable_columns == ()  # 主键列不算「可直接补」的列
    assert drift.requires_identity_change is True
    assert drift.row_count == 2  # 存量行数：决定「旧行怎么归位」的必要事实


def test_extra_columns_are_reported_but_not_deleted(tmp_path):
    engine = _make_engine(tmp_path)
    legacy = MetaData()
    Table(
        'watchlist_groups',
        legacy,
        Column('id', Integer, primary_key=True),
        Column('name', String(50)),
        Column('legacy_flag', Integer),
    )
    legacy.create_all(bind=engine)

    drift = collect(engine, [_model_groups()])[0]

    assert drift.extra_columns == ('legacy_flag',)
    result = render([drift])
    assert '只报告，不删' in result


def test_no_drift_returns_empty_list(tmp_path):
    engine = _make_engine(tmp_path)
    model = _model_groups()
    model.metadata.create_all(bind=engine)

    assert collect(engine, [model]) == []
    assert '没有结构漂移' in render([])


def test_tables_missing_from_db_are_skipped(tmp_path):
    """库里没有这张表 ⇒ 交给 create_all，报出来只会制造噪音。"""
    engine = _make_engine(tmp_path)

    assert collect(engine, [_model_groups()]) == []


def test_collect_is_read_only(tmp_path):
    engine = _make_engine(tmp_path)
    _legacy_groups(engine)
    before = {c['name'] for c in inspect(engine).get_columns('watchlist_groups')}

    collect(engine, [_model_groups()])

    after = {c['name'] for c in inspect(engine).get_columns('watchlist_groups')}
    assert after == before  # 报告工具绝不允许顺手把列补上


def test_render_flags_identity_change_and_row_count(tmp_path):
    engine = _make_engine(tmp_path)
    legacy = MetaData()
    Table(
        'watchlist_item_tags',
        legacy,
        Column('item_id', Integer, primary_key=True),
        Column('tag_id', Integer, primary_key=True),
    )
    legacy.create_all(bind=engine)

    model = MetaData()
    table = Table(
        'watchlist_item_tags',
        model,
        Column('id', Integer, primary_key=True),
        Column('item_id', Integer),
        Column('tag_id', Integer),
    )
    result = render(collect(engine, [table]))

    assert '需要改身份' in result
    assert '存量行数: 0' in result  # 空表 ⇒ 「重建」风险最低，这个数字必须出现在报告里
    assert 'SQLite 必须整表重建' in result


def _missing_table():
    meta = MetaData()
    return Table('not_created_yet', meta, Column('id', Integer, primary_key=True))


def test_empty_database_is_not_reported_as_clean(tmp_path):
    """空库上 ``collect()`` 也返回空列表 ⇒ 报告必须说「没有结论」，不能说「没有漂移」。"""
    engine = _make_engine(tmp_path)

    drifts = collect(engine, [_model_groups()])
    present, absent = split_tables(engine, [_model_groups()])

    assert drifts == []
    assert present == ()
    assert absent == ('watchlist_groups',)
    result = render(drifts, absent_tables=absent)
    assert '不构成' in result
    assert '不存在' in result


def test_split_tables_separates_present_from_absent(tmp_path):
    engine = _make_engine(tmp_path)
    _legacy_groups(engine)

    present, absent = split_tables(engine, [_model_groups(), _missing_table()])

    assert present == ('watchlist_groups',)
    assert absent == ('not_created_yet',)


def test_validate_schema_error_points_at_the_report_command(tmp_path):
    """启动期报错必须给出「下一步命令」，否则现场只能靠猜（#2498 的原始痛点）。"""
    engine = _make_engine(tmp_path)
    _legacy_groups(engine)
    model = MetaData()
    Table(
        'watchlist_groups',
        model,
        Column('id', Integer, primary_key=True),
        Column('name', String(50)),
        Column('family_id', Integer),
    )

    with pytest.raises(RuntimeError) as excinfo:
        _validate_schema(engine, model, label='user')
    message = str(excinfo.value)
    assert 'pdm run user-schema-report' in message
    assert '只对 SQLite 生效' in message
