from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PositionCreate(BaseModel):
    symbol: Optional[str] = Field('manual', description='代码')
    name: Optional[str] = Field(None, description='名称')
    market: str = Field('CN_A', description='市场')
    asset_type: str = Field('stock', validation_alias='type', description='产品类型')
    account_name: Optional[str] = Field(None, description='所属账户')
    ledger_id: Optional[int] = Field(None, description='所属账户ID')  # 新增
    portfolio_id: Optional[int] = Field(None, description='所属组合ID(持仓级组合,可空)')
    quantity: Optional[float] = Field(None, description='数量')
    avg_price: Optional[float] = Field(None, description='平均价格/金额')
    currency: str = Field('CNY', description='币种')
    trade_date: Optional[date] = Field(None, description='交易日期')
    allocation: Optional[str] = Field(None, description='配置目标')
    notes: Optional[str] = Field(None, description='备注')
    fee: Optional[float] = Field(0.0, description='手续费')
    confirm_date: Optional[date] = Field(None, description='确认日期')
    op_type: Optional[str] = Field('buy', description='操作类型')
    position_id: Optional[int] = Field(None, description='关联持仓ID')
    isAfter15: Optional[bool] = Field(False, description='基金申购是否在15:00之后')
    interestRate: Optional[float] = Field(None, description='年化利率')
    amount: Optional[float] = Field(None, description='交易金额')
    model_config = ConfigDict(extra='allow')


class PositionUpdate(BaseModel):
    name: Optional[str] = Field(None, description='名称')
    account_name: Optional[str] = Field(None, description='所属账户')
    ledger_id: Optional[int] = Field(None, description='所属账户ID')  # 新增
    portfolio_id: Optional[int] = Field(None, description='所属组合ID(持仓级组合,可空)')
    quantity: Optional[float] = Field(None, description='数量')
    avg_price: Optional[float] = Field(None, description='平均价格')
    current_price: Optional[float] = Field(None, description='当前价格')
    currency: Optional[str] = Field(None, description='币种')
    trade_date: Optional[date] = Field(None, description='交易日期')
    notes: Optional[str] = Field(None, description='备注')


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: Optional[str] = None
    market: str
    type: str = Field(validation_alias='asset_type', serialization_alias='type')
    account_name: Optional[str] = None
    ledger_id: Optional[int] = None  # 新增
    portfolio_id: Optional[int] = None  # 持仓所属组合ID(D20)
    source: str = Field('manual', description='持仓来源: 见 app.core.constants.PositionSource')  # 新增：来源徽标依赖
    quantity: float
    avg_price: float
    currency: str
    current_price: float
    confirm_date: Optional[date] = None
    notes: Optional[str] = None
    allocation: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    type_label: Optional[str] = None
    market_label: Optional[str] = None
    allocation_label: Optional[str] = None


PositionOut.model_rebuild()
