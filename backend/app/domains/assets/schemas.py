# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:21
# File : schemas.py
# -*- coding: utf-8 -*-
"""通用资产的 Pydantic Schema."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.allocation_rules import derive_allocation, normalize_allocation_source
from app.core.allocation_source_stamp import AllocationSourceStampMixin
from app.core.asset_types import MAJOR_CATEGORY_VALUES


def _validate_major_category(value: str | None) -> str | None:
    """大类取值必须在权威词表内（#2136）。

    此前写入侧完全不校验，于是任何字符串都能落库；而读侧按词表过滤
    ⇒ 词表外的值（如历史上误用的 'current'）会变成**谁都读不到**的隐形行——
    账户现金恒为 0 就是这么来的。这里早失败，把错误挡在入库之前。
    """
    if value is None:
        return None
    if value not in MAJOR_CATEGORY_VALUES:
        raise ValueError(f'major_category 非法：{value!r}；合法取值见 /api/utils/enums/ 的 asset_category')
    return value


class AssetCreate(AllocationSourceStampMixin):
    """创建通用资产."""

    major_category: str = Field(..., max_length=20)
    minor_category: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=200)
    amount: float = Field(..., gt=0, description='资产金额，必须大于0')
    currency: str = 'CNY'
    ledger_id: Optional[int] = None  # 新增：关联账户 ID
    account_name: Optional[str] = Field(None, max_length=50)
    allocation: Optional[str] = 'longterm'
    status: str = 'active'
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)
    extra: Optional[dict] = None

    _check_major_category = field_validator('major_category')(_validate_major_category)

    @model_validator(mode='after')
    def _derive_allocation_default(self) -> 'AssetCreate':
        """未显式给配置目标时按大类推导（#3031 / P0-4）。

        WHY 在 schema 层而不是视图层：``assets/views.py`` 被
        ``scripts/check_view_thickness.py`` 冻结在 244 行，加一行即红；而「创建时
        该归哪一笔钱」本就是入参语义，推导规则仍在 ``core/allocation_rules`` 一份。

        三条边界：

        1. **只在请求体没带 allocation 时生效**（``model_fields_set`` 判定），
           用户显式写 ``longterm`` 就尊重用户（P0-7：显式性优先于值反推）。
        2. **负债直接跳过**：``derive_allocation`` 对负债抛 ``LiabilityAllocationError``
           是给「聚合侧忘了过滤负债」准备的规则级守卫，不该把它变成用户的 400。
        3. **推导结果不进 ``model_fields_set``**：否则 ``AllocationSourceStampMixin``
           会把它标成 ``user``，G3 回填从此不敢碰这些行——系统默认值被误记成用户配置。
        """
        if 'allocation' in self.model_fields_set:
            return self
        if self.major_category == 'liability':
            return self
        derived = derive_allocation(self.major_category)
        if derived is not None:
            self.allocation = derived
            # Pydantic v2 的赋值会把键写进 model_fields_set，等于把「系统推导」伪装成
            # 「请求体显式传入」——必须当场摘掉，否则来源标记会被混入判成 user。
            self.model_fields_set.discard('allocation')
        return self


class AssetUpdate(AllocationSourceStampMixin):
    """更新通用资产（PATCH，所有字段可选）."""

    major_category: Optional[str] = None
    minor_category: Optional[str] = None
    name: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    ledger_id: Optional[int] = None  # 新增
    account_name: Optional[str] = None
    allocation: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    extra: Optional[dict] = None
    # ── 值变动事件（D99/D100，设计 §8）────────────────────────────────
    # 全部可选；不传时 PATCH 的对外行为与第 2 期之前逐字相同。
    # delta 是独立业务事实（求和可交换 ⇒ 乱序补录零重算），不能由
    # 「新值 − 当前值」反推；amount 保留旧绝对值语义，由视图换算成 delta。
    delta: Optional[float] = Field(None, description='本次变动量（元，带符号；负数=还款/减少）')
    effective_date: Optional[date] = Field(None, description='业务发生日（用户显式提供，允许早于今天）')
    change_note: Optional[str] = Field(None, max_length=500, description='本次变动说明，写事件 notes')
    client_token: Optional[str] = Field(None, max_length=64, description='幂等令牌，重放不产生第二条事件')
    change_kind: Optional[str] = Field(None, description='仅允许 correction（标记冲销/更正）')

    _check_major_category = field_validator('major_category')(_validate_major_category)

    @field_validator('change_kind')
    @classmethod
    def _check_change_kind(cls, value: str | None) -> str | None:
        # 其余 kind 由服务按 major_category 派生，避免前端再维护一份词表
        if value is not None and value != 'correction':
            raise ValueError('change_kind 仅支持 correction')
        return value


class AssetOut(BaseModel):
    id: int
    user_id: int
    major_category: str
    minor_category: Optional[str] = None
    name: str
    amount: float  # 没有 gt 限制
    signed_amount: float  # 负债为负，资产为正
    currency: str = 'CNY'
    ledger_id: Optional[int] = None  # 新增：前端列表/详情需要
    account_name: Optional[str] = None
    allocation: Optional[str] = None
    allocation_label: Optional[str] = None
    #: 只读输出：来源标记不接受前端写入，防止伪造 user 绕过回填（#3031 / G1）
    allocation_source: str = 'default'
    type_label: Optional[str] = None  # 新增
    status: str = 'active'
    notes: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    extra: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator('allocation_source', mode='before')
    @classmethod
    def _normalize_allocation_source(cls, value: str | None) -> str:
        # ORM 纯内存对象拿不到 Column(default=...) 的值；归一只在出参层，不写回对象（#2406）
        return normalize_allocation_source(value)

    class Config:
        from_attributes = True


# 强制 Pydantic 重新解析继承链中的 datetime 类型
AssetOut.model_rebuild()
