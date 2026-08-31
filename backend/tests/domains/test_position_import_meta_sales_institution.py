# -*- coding: utf-8 -*-
"""#1169 PositionImportMeta.sales_institution_id 归一化到销售机构（设计 B）。"""

from sqlalchemy import inspect

from app.core.constants import PositionSource
from app.domains.positions.models import (
    PositionImportMeta,
    SalesInstitution,
    resolve_sales_institution_id,
)


def test_position_import_meta_has_sales_institution_id_column(db):
    cols = {c['name'] for c in inspect(db.bind).get_columns('position_import_meta')}
    assert 'sales_institution_id' in cols


def test_resolve_sales_institution_id_by_org_name_and_alias(db):
    inst = SalesInstitution(org_name='蚂蚁基金销售有限公司', display_name='蚂蚁财富', is_active=True)
    db.add(inst)
    db.commit()
    assert resolve_sales_institution_id(db, '蚂蚁基金销售有限公司') == inst.id
    assert resolve_sales_institution_id(db, '蚂蚁财富') == inst.id
    assert resolve_sales_institution_id(db, '不存在的机构') is None


def test_resolve_sales_institution_id_empty_and_none(db):
    assert resolve_sales_institution_id(db, '') is None
    assert resolve_sales_institution_id(db, None) is None


def test_resolve_sales_institution_id_skips_inactive(db):
    inst = SalesInstitution(org_name='已下线机构', display_name='下线', is_active=False)
    db.add(inst)
    db.commit()
    assert resolve_sales_institution_id(db, '已下线机构') is None


def test_meta_persists_sales_institution_id(db):
    inst = SalesInstitution(org_name='天天基金销售有限公司', display_name='天天基金', is_active=True)
    db.add(inst)
    db.commit()
    meta = PositionImportMeta(
        position_id=999,
        symbol='000001',
        source=PositionSource.E_ACCOUNT,
        sales_institution_id=inst.id,
        family_id=1,
    )
    db.add(meta)
    db.commit()
    db.expire_all()
    got = db.query(PositionImportMeta).filter_by(position_id=999).first()
    assert got is not None
    assert got.sales_institution_id == inst.id
