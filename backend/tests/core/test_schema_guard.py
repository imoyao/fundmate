# -*- coding: utf-8 -*-
"""启动期数据库结构校验守卫（issue #1036）。"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from app.core.database import _validate_schema


def _make_meta():
    meta = MetaData()
    Table(
        't_demo',
        meta,
        Column('id', Integer, primary_key=True),
        Column('name', String(50)),
    )
    return meta


def test_validate_schema_passes_when_consistent():
    """库结构与元数据一致（含新建表场景）→ 不抛错。"""
    eng = create_engine('sqlite:///:memory:')
    meta = _make_meta()
    meta.create_all(bind=eng)
    _validate_schema(eng, meta, label='test')


def test_validate_schema_missing_column_raises():
    """表已存在但缺列（模型加了字段、DB 未迁移）→ RuntimeError 列明缺失。"""
    eng = create_engine('sqlite:///:memory:')
    # 先建一张「旧版」表：少 name 列，模拟模型演进后 DB 未跟上
    old = MetaData()
    Table(
        't_demo',
        old,
        Column('id', Integer, primary_key=True),
    )
    old.create_all(bind=eng)

    meta = _make_meta()
    try:
        _validate_schema(eng, meta, label='test')
    except RuntimeError as e:
        assert 't_demo' in str(e)
        assert 'name' in str(e)
        assert '重建' in str(e) or '迁移' in str(e)
    else:
        raise AssertionError('缺列未触发 RuntimeError')


def test_validate_schema_new_table_skipped():
    """DB 中尚不存在的表交给 create_all 补建，守卫跳过不误报。"""
    eng = create_engine('sqlite:///:memory:')
    meta = _make_meta()  # 不 create_all，t_demo 在库里不存在
    _validate_schema(eng, meta, label='test')
