# -*- coding: utf-8 -*-
"""增量写入的来源标记判据（#3031 / G1-b）。

反向验证锚点：``test_explicit_form_longterm_is_still_user``。
若把 ``resolve_allocation_source`` 退回 G1-a 存量迁移的「值反推」口径
（``allocation != 'longterm'`` ⇒ user），本用例必须转红——那正是
「用户把 liquid 主动改回 longterm ⇒ 掉回 default ⇒ 被 G3 回填覆盖」的回归口。
"""

import pytest

from app.core.allocation_rules import (
    SOURCE_DEFAULT,
    SOURCE_GOVERNANCE,
    SOURCE_IMPORT,
    SOURCE_USER,
    resolve_allocation_source,
)
from app.domains.assets.schemas import AssetCreate, AssetUpdate
from app.domains.positions.schemas import PositionUpdate


class TestResolveAllocationSource:
    def test_not_explicit_returns_default(self):
        # 调用方没传 allocation ⇒ 保持列默认，别抢在推导规则前面打保护标
        assert resolve_allocation_source(explicit=False) == SOURCE_DEFAULT
        assert resolve_allocation_source(explicit=False, allocation='longterm') == SOURCE_DEFAULT

    def test_explicit_form_non_default_is_user(self):
        assert resolve_allocation_source(explicit=True, allocation='liquid', path='form') == SOURCE_USER
        assert resolve_allocation_source(explicit=True, allocation='stable') == SOURCE_USER

    def test_explicit_form_longterm_is_still_user(self):
        # 关键：显式性信号优先于值反推。用户主动改回默认值也是用户的选择。
        assert resolve_allocation_source(explicit=True, allocation='longterm') == SOURCE_USER

    def test_explicit_import_is_import(self):
        assert resolve_allocation_source(explicit=True, allocation='longterm', path='import') == SOURCE_IMPORT
        assert resolve_allocation_source(explicit=True, allocation='liquid', path='import') == SOURCE_IMPORT

    def test_unknown_path_raises(self):
        # 守卫失效必须红灯，不许静默按 form 放行
        with pytest.raises(ValueError, match='未知 allocation 写入路径'):
            resolve_allocation_source(explicit=True, path='sync')

    def test_protected_sources_are_excluded_from_backfill(self):
        # G3 回填判据（scripts/backfill_allocation.py:11）只放 default。
        # 三个受保护来源一旦与 default 取值撞车，保护即静默失效。
        assert SOURCE_USER != SOURCE_DEFAULT
        assert SOURCE_IMPORT != SOURCE_DEFAULT
        assert SOURCE_GOVERNANCE != SOURCE_DEFAULT
        assert resolve_allocation_source(explicit=True, path='form') not in {SOURCE_DEFAULT}
        assert resolve_allocation_source(explicit=True, path='import') not in {SOURCE_DEFAULT}


class TestWritePathStamping:
    """三处写入侧的接线判据：钉的是「model_dump 结果」，视图层一行未改。"""

    def test_asset_create_explicit_allocation_stamps_user(self):
        data = AssetCreate(major_category='cash', name='活钱', amount=100, allocation='liquid').model_dump()
        assert data['allocation_source'] == SOURCE_USER

    def test_asset_create_without_allocation_keeps_orm_default(self):
        data = AssetCreate(major_category='cash', name='活钱', amount=100).model_dump()
        assert 'allocation_source' not in data  # 让 ORM 列默认 default 生效

    def test_asset_update_name_only_does_not_wipe_user(self):
        # 反向验证锚点之二：若混入无条件输出 default，此用例必须红
        data = AssetUpdate(name='改个名').model_dump(exclude_unset=True)
        assert 'allocation_source' not in data

    def test_asset_update_explicit_longterm_is_still_user(self):
        data = AssetUpdate(allocation='longterm').model_dump(exclude_unset=True)
        assert data['allocation_source'] == SOURCE_USER

    def test_position_inline_edit_stamps_user(self):
        data = PositionUpdate(allocation='liquid').model_dump(exclude_unset=True)
        assert data['allocation_source'] == SOURCE_USER

    def test_frontend_cannot_forge_source(self):
        forged = AssetUpdate.model_validate({'name': 'x', 'allocation_source': 'hack'})
        assert 'allocation_source' not in forged.model_dump(exclude_unset=True)

        forged_with_alloc = AssetUpdate.model_validate({'allocation': 'liquid', 'allocation_source': 'hack'})
        assert forged_with_alloc.model_dump(exclude_unset=True)['allocation_source'] == SOURCE_USER
