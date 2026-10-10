from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PositionListRequest(BaseModel):
    """持仓列表过滤参数（#1966）。

    过滤一律**下推到 SQL**（由 `PositionService.build_position_list` 执行）——
    取全表后内存筛是数据策略硬约束 §6 明令禁止的写法。

    - `symbol`：产品代码过滤。同时匹配「展示形态」与 #1662 的「归一身份键」，
      故 `SZ000001` 与 `000001.SZ` 视为同一只产品（详见 service 内注释）。
    - `market`：市场过滤，与 symbol 组合用于同码跨市场消歧。
    - `ledger_id`：传字符串 `'null'` 表示仅查未归档持仓（`ledger_id IS NULL`）。
    - `group_by`：目前仅支持 `'account'`（按账户分组）。
    """

    group_by: str = Field('', description="分组维度，仅 'account' 生效")
    page: int = Field(1, description='页码（1 起）')
    per_page: int = Field(20, description='每页条数')
    ledger_id: str = Field('', description="账户 ID；'null' 表示仅未归档持仓")
    symbol: str = Field('', description='产品代码过滤（#1966）')
    market: str = Field('', description='市场过滤（#1966），与 symbol 组合消歧')


class PositionCreate(BaseModel):
    symbol: Optional[str] = Field('manual', description='代码')
    name: Optional[str] = Field(None, description='名称')
    market: str = Field('CN_A', description='市场')
    asset_type: str = Field('stock', validation_alias='type', description='产品类型')
    venue: Optional[str] = Field(
        None,
        description='交易场所 EXCHANGE/OTC（#1662）：场内代码带 SH/SZ/BJ 前缀、场外为 6 位裸码。'
        '缺省时按 asset_type 推断（股票/ETF/债券/逆回购→EXCHANGE，基金/货基→OTC）。',
    )
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
    valuation_mode: Optional[str] = Field('nav', description='计价模式: nav=份额×净值 / balance=直接余额(#1174)')
    market_value_override: Optional[float] = Field(
        None, description='人工录入市值(元)；非空时优先于派生计算（balance 模式必填）'
    )
    nav: Optional[float] = Field(None, description='净值（红利再投资申购价）')
    dividend_amount: Optional[float] = Field(None, description='分红金额（红利再投资可再投金额）')
    import_hash: Optional[str] = Field(
        None,
        description='幂等键（手动记账由前端按提交意图生成）。'
        '落库后受 UNIQUE(ledger_id, import_hash) 约束保护，拦截网络重发导致的重复写入；'
        '两条内容相同但意图独立的记账（如同日同基金同金额两笔买入）拥有不同键，互不误杀。',
    )
    model_config = ConfigDict(extra='allow')


class PositionUpdate(BaseModel):
    name: Optional[str] = Field(None, description='名称')
    account_name: Optional[str] = Field(None, description='所属账户')
    ledger_id: Optional[int] = Field(None, description='所属账户ID')  # 新增
    portfolio_id: Optional[int] = Field(None, description='所属组合ID(持仓级组合,可空)')
    quantity: Optional[float] = Field(None, description='数量')
    avg_price: Optional[float] = Field(None, description='平均价格')
    current_price: Optional[float] = Field(None, description='当前价格')
    valuation_mode: Optional[str] = Field(None, description='计价模式: nav=份额×净值 / balance=直接余额(#1174)')
    market_value_override: Optional[float] = Field(None, description='人工录入市值(元)；非空时优先于派生计算')
    currency: Optional[str] = Field(None, description='币种')
    trade_date: Optional[date] = Field(None, description='交易日期')
    notes: Optional[str] = Field(None, description='备注')


class AllocateValueRequest(BaseModel):
    """按占比批量更新某产品跨账户总价（P1-4）。"""

    symbol: str = Field(..., description='产品代码（同一产品跨账户分摊总价）')
    total_value: float = Field(..., gt=0, description='产品维度新总价（元）')
    as_of: Optional[date] = Field(None, description='市值录入日期，默认今天')
    ledger_id: Optional[int] = Field(None, description='限定只分摊到某个账户；缺省跨该 family 下全部活跃账户')


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: Optional[str] = None
    market: str
    type: str = Field(validation_alias='asset_type', serialization_alias='type')
    # #1305 #11：三态冗余判定（True=货基 / False=非货基 / None=未判定）。
    # 列在 `positions.is_money_fund`（#863 引入）。**必须在 Out Schema 里声明**，
    # 否则 `model_validate` 后该字段被静默丢掉，前端拿不到；而 None 是合法值，
    # 不能被当成 False 用（判货基一律 `is_money_fund.is_(True)`）。
    is_money_fund: Optional[bool] = None
    account_name: Optional[str] = None
    ledger_id: Optional[int] = None  # 新增
    portfolio_id: Optional[int] = None  # 持仓所属组合ID(D20)
    source: str = Field('manual', description='持仓来源: 见 app.core.constants.PositionSource')  # 新增：来源徽标依赖
    quantity: float
    avg_price: float
    currency: str
    current_price: float
    # 当日盈亏基准（#2007）：与 current_price **同批**写入的上一确认价及其交易日。
    # 必须声明在 Out Schema 里——否则 `model_validate` 后被静默丢掉、前端拿不到
    # （与上面 `is_money_fund` 同一条坑）。None 是合法值：读取端按「无基准」处理，
    # **不得当成 0**（0 会被读成「今天没涨没跌」，而真相是没数据）。
    prev_close: Optional[float] = None
    price_date: Optional[date] = None
    valuation_mode: str = 'nav'
    market_value_override: Optional[float] = None
    value_override_at: Optional[datetime] = None
    confirm_date: Optional[date] = None
    holding_days: Optional[int] = None  # 派生：截至今天持有时长（天），#862
    notes: Optional[str] = None
    allocation: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    type_label: Optional[str] = None
    market_label: Optional[str] = None
    allocation_label: Optional[str] = None


PositionOut.model_rebuild()
