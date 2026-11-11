# -*- coding: utf-8 -*-
"""入参 schema 的「配置目标来源」条件注入（#3031 / G1-b）。

## WHY 用 ``model_serializer`` 而不是在视图里 setattr

G1-a 已把 ``allocation_source`` 列、迁移打标、出参归一做完了，但**增量写入侧没接**：
``assets/views.py`` 与 ``positions/views.py`` 的 ``setattr`` 循环只搬运请求体里出现的
字段，于是用户刚设的配置目标仍落到列默认 ``default`` —— 下一次 G3 回填
（``scripts/backfill_allocation.py:11`` 只放 ``default``）就会覆盖掉它，正是 P0-7。

直接改视图要顶破 ``check_view_thickness.py`` 的「按文件冻结、只减不增」基线；
把打标放进**入参 schema 的序列化出口**，则现有 ``model_dump`` → ``setattr`` 链路
原样复用，视图层零改动、零基线增长，判定逻辑仍只有 ``allocation_rules`` 一份。

## 条件注入是硬要求，不是美化

- 只在请求体**显式带了 allocation** 时才附带 ``allocation_source``。
  否则「只改个名字」的 PATCH 会把该行原有的 ``user`` 标记冲成 ``default``，
  保护被静默抹掉——比不接线更坏。
- ``allocation_source`` **不是入参字段**：出参 schema 早已注明「不接受前端写入，
  防止伪造 user 绕过回填」。前端即使硬塞该键，也会被判定结果覆盖或丢弃。
- 只判显式性，不按值反推：用户主动把 ``liquid`` 改回 ``longterm`` 仍是 ``user``，
  理由见 ``allocation_rules.resolve_allocation_source`` 的 docstring。

## 适用范围

目前挂到资产表单（``AssetCreate`` / ``AssetUpdate``）与持仓行内编辑
（``PositionUpdate``）。**导入器不在此列**：``orchestrator_holdings.py`` 构造持仓时
硬编码 ``allocation='longterm'``，按 G1-a 冻结判据本就落 ``default``（可被 G2 推导
覆盖，符合预期），无需接线；``import`` 枚举留给「导入文件显式带 allocation 列」的场景。
详见 ``docs/design/allocation-governance.md`` §4.2。
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, model_serializer

from app.core.allocation_rules import resolve_allocation_source


class AllocationSourceStampMixin(BaseModel):
    """给入参 schema 的 ``model_dump`` 结果条件附加 ``allocation_source``。

    子类必须自身声明 ``allocation`` 字段；否则 ``model_fields_set`` 永远不含它，
    本混入退化为恒不注入（不会报错，但也不会打标）。
    """

    @model_serializer(mode='wrap')
    def _stamp_allocation_source(self, handler: Callable[[Any], dict]) -> dict:
        data = handler(self)
        if 'allocation' in self.model_fields_set:
            data['allocation_source'] = resolve_allocation_source(
                explicit=True,
                allocation=data.get('allocation'),
                path='form',
            )
        else:
            # 防伪造：前端硬塞的 allocation_source 不许进入 setattr 循环
            data.pop('allocation_source', None)
        return data
