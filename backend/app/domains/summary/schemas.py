# -*- coding: utf-8 -*-
"""汇总域的查询参数模型。

`MemberSliceQuery`（#1173）：按家庭成员切片。

放在 schemas 而不是视图里内联解析，有两个理由：
- **非法值不能静默**：手写 `int(request.args.get(...))` 失败时会抛 ValueError，
  而「传了非法 member_id 却返回全量数据」会让用户以为筛了成员、实际看的是全家。
  交给 pydantic → `parse_query` 统一转 422 错误信封（与 positions 域的
  `PositionListRequest` 同一套惯例）。
- **视图只做 HTTP 编排**：`scripts/check_view_thickness.py` 盯的是视图厚度，
  参数校验属 schema 层职责。
"""

from typing import Optional

from pydantic import BaseModel, Field


class MemberSliceQuery(BaseModel):
    """按家庭成员切片的查询参数。"""

    member_id: Optional[int] = Field(
        None,
        gt=0,
        description='家庭成员档案 ID（#1173）；不传 = 家庭级全量',
    )
