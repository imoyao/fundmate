# -*- coding: utf-8 -*-
"""汇总域的查询参数模型。

`MemberSliceQuery`（#1173）：按家庭成员切片。
`TodayPnlQuery`（#2965）：当日估值的「单资源 + 分组维度 + 作用域」查询。

放在 schemas 而不是视图里内联解析，有两个理由：
- **非法值不能静默**：手写 `int(request.args.get(...))` 失败时会抛 ValueError，
  而「传了非法 member_id 却返回全量数据」会让用户以为筛了成员、实际看的是全家。
  交给 pydantic → `parse_query` 统一转 422 错误信封（与 positions 域的
  `PositionListRequest` 同一套惯例）。
- **视图只做 HTTP 编排**：`scripts/check_view_thickness.py` 盯的是视图厚度，
  参数校验属 schema 层职责。
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class MemberSliceQuery(BaseModel):
    """按家庭成员切片的查询参数。"""

    member_id: Optional[int] = Field(
        None,
        gt=0,
        description='家庭成员档案 ID（#1173）；不传 = 家庭级全量',
    )


class TodayPnlQuery(BaseModel):
    """`GET /summary/today-pnl/` 的通用查询参数（#2965）。

    一个资源覆盖首页 / 账户 / 组合 / 品类四个页面，靠**两个正交参数**切：

    - `dimension`：响应 `groups[]` 按什么分组。默认 `class`（股票 / 基金），
      与首页既有行为逐位等价；`ledger` / `portfolio` 供列表页一次批量取数。
    - `ledger_id` / `portfolio_id`：作用域。均不传 = 家庭级；互斥校验与组合
      存在性交给 `services/scope.py` 的 `ValueError`（视图转 400），不在此重复。
      `scope` **不作为入参**：它由这两个 id 推导，响应回带即可；让调用方再传
      一个可能与之矛盾的 `scope` 只会制造第三种真相。

    `dimension` 白名单与 `services/today_pnl.py::DIMENSIONS` 必须一致；service
    侧仍再校验一次，因为测试与内部调用可以绕过 schema。
    """

    dimension: Literal['class', 'ledger', 'portfolio'] = Field(
        'class',
        description='分组维度：class（品类）/ ledger（账户）/ portfolio（组合）',
    )
    ledger_id: Optional[int] = Field(None, gt=0, description='账户级作用域')
    portfolio_id: Optional[int] = Field(None, gt=0, description='组合级作用域')
