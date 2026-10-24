from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.constants import ALLOCATION_LABELS


class PositionListRequest(BaseModel):
    """持仓列表过滤参数（#1966）。

    过滤一律**下推到 SQL**（由 `PositionService.build_position_list` 执行）——
    取全表后内存筛是数据策略硬约束 §6 明令禁止的写法。

    - `symbol`：产品代码过滤。同时匹配「展示形态」与 #1662 的「归一身份键」，
      故 `SZ000001` 与 `000001.SZ` 视为同一只产品（详见 service 内注释）。
    - `market`：市场过滤，与 symbol 组合用于同码跨市场消歧。
    - `ledger_id`：传字符串 `'null'` 表示仅查未归档持仓（`ledger_id IS NULL`）。
    - `group_by`：目前仅支持 `'account'`（按账户分组）。
    - `owner_user_id`：按归属家庭成员过滤（#1173）。成员 → 其名下 `ledger_id` 集合的
      换算收口在 `services/owner_scope`，**不**在此处拼 SQL。
    """

    group_by: str = Field('', description="分组维度，仅 'account' 生效")
    page: int = Field(1, description='页码（1 起）')
    per_page: int = Field(20, description='每页条数')
    ledger_id: str = Field('', description="账户 ID；'null' 表示仅未归档持仓")
    symbol: str = Field('', description='产品代码过滤（#1966）')
    market: str = Field('', description='市场过滤（#1966），与 symbol 组合消歧')
    owner_user_id: Optional[int] = Field(None, description='归属家庭成员 id（#1173）；缺省=全家庭')


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
    # 净值缺失先记账（三方约定，见 position_service.process_buy_or_deposit）：
    # nav 缺失时前端带 nav_pending 放行提交，官方净值落库后由 nav_backfill 回填份额/成本。
    nav_pending: bool = Field(False, description='买入时净值缺失：先记账，官方净值到位后由 nav_backfill 回填')
    nav_date: Optional[str] = Field(None, description='待回填目标净值日 YYYY-MM-DD（actualNavDate，缺省取 trade_date）')
    shares_manual: bool = Field(False, description='份额由用户手动填写（回填只校正净值，不覆盖份额）')
    currency: str = Field('CNY', description='币种')
    trade_date: Optional[date] = Field(None, description='交易日期')
    allocation: Optional[str] = Field(None, description='配置目标')
    notes: Optional[str] = Field(None, description='备注')
    fee: Optional[float] = Field(0.0, description='手续费')
    # #2137 费用拆分（元）：四类齐全才落拆分列，缺类显式传 0；全不传 = 未拆分
    # （存量语义，聚合 fee 为权威）。与 Transaction 的拆分不变量同口径。
    fee_commission: Optional[float] = Field(None, description='佣金(元，#2137)')
    fee_stamp_duty: Optional[float] = Field(None, description='印花税(元，#2137)')
    fee_transfer_fee: Optional[float] = Field(None, description='过户费等税费(元，#2137)')
    fee_other: Optional[float] = Field(None, description='其他费用(元，#2137)')
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


class ConversionFeeOverride(BaseModel):
    """人工修正费用（#2348）。

    真实确认单上的费用常与费率先算值不一致（基金公司活动、钱包垫资、持有期口径），
    用户必须能改，否则账实永远差几分钱。约定：只覆盖**金额**，两项独立、
    **不级联重算**（改赎回费不会重算补差费的费率阶梯）。
    """

    redeem: Optional[float] = Field(None, ge=0, description='赎回费（元）；缺省=沿用估算值')
    compensate: Optional[float] = Field(None, ge=0, description='补差费（元）；缺省=沿用估算值')
    model_config = ConfigDict(extra='forbid')


class ConversionEstimate(BaseModel):
    """基金转换试算入参（只读，不落库）。

    设计见 ``docs/working-notes/fund-conversion-design-2026-10-17.md`` §4.1。
    """

    ledger_id: Optional[int] = Field(None, description='账户ID；缺省取转出持仓所属账户（传入则校验一致）')
    out_position_id: int = Field(..., description='转出持仓ID')
    out_quantity: Optional[float] = Field(None, description='转出份额（份）；缺省或 <=0 = 全部转出')
    in_symbol: str = Field(..., description='转入基金代码（6位裸码）')
    in_amount: Optional[float] = Field(None, description='指定转入金额（元）；缺省 = 净额全部转入')
    in_quantity: Optional[float] = Field(
        None, description='指定转入份额（份，最多2位小数）；与 in_amount 二选一，缺省 = 净额全部转入'
    )
    fee_override: Optional[ConversionFeeOverride] = Field(None, description='人工修正赎回费/补差费（元）')
    trade_date: Optional[date] = Field(None, description='交易日期，缺省为今天')


class ConversionSubmit(BaseModel):
    """基金转换提交入参（落库，2~3 条流水同 link_group_id）。

    幂等键由前端按「一次提交意图」生成（UUID），网络重发沿用同键——
    服务端按 组号+leg角色 派生各流水 import_hash，撞唯一约束即 409。
    """

    ledger_id: Optional[int] = Field(None, description='账户ID；缺省取转出持仓所属账户（传入则校验一致）')
    out_position_id: int = Field(..., description='转出持仓ID')
    out_quantity: Optional[float] = Field(None, description='转出份额（份）；缺省或 <=0 = 全部转出（按持仓精确值）')
    in_symbol: str = Field(..., description='转入基金代码（6位裸码）')
    in_amount: Optional[float] = Field(None, description='指定转入金额（元）；缺省 = 净额全部转入')
    in_quantity: Optional[float] = Field(
        None, description='指定转入份额（份，最多2位小数）；与 in_amount 二选一，缺省 = 净额全部转入'
    )
    fee_override: Optional[ConversionFeeOverride] = Field(None, description='人工修正赎回费/补差费（元）')
    refund_mode: Optional[str] = Field(
        None, description='退款去向：money_fund=账户绑定的类现金产品 / account_cash=退回账户现金；存在退款时必填'
    )
    trade_date: Optional[date] = Field(None, description='交易日期，缺省为今天')
    idempotency_key: str = Field(..., min_length=8, description='幂等键（前端生成的 UUID），重复提交返回同一结果')


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
    # #1123 P0：持仓级配置目标（五笔钱）——白名单校验收在 schema（视图 setattr 循环自动应用），
    # 非法值 pydantic ValidationError → 422；None = 清空语义（与嵌套端点一致）
    allocation: Optional[str] = Field(None, description='配置目标（五笔钱枚举）')

    @field_validator('allocation')
    @classmethod
    def _check_allocation(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in ALLOCATION_LABELS:
            raise ValueError('非法配置目标')
        return value


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
    # #2406：列本身可空（存量导入/迁移行可能没有 market）。此前为必填，逼得
    # position_presenter 在 validate 前把 'UNKNOWN' 写回 ORM 对象（读函数写库，
    # 兜底值被 flush 落进 positions.market）。放宽后兜底下沉到 presenter 的
    # dict 层，wire 格式不变（仍输出 'UNKNOWN'）。
    market: Optional[str] = None
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
    # 当日已定型（#2210）：price_date 是否为今天（Asia/Shanghai）⇒ true=估值副行冗余，前端隐藏。
    # **派生字段**（Position 上无同名属性）：`model_validate` 只会填默认 None，
    # 真值由 `position_presenter.enrich_position_dict` 经 `pnl_settle.is_settled_today` 覆写。
    # 声明在 Out Schema 是为了契约可见（与 price_date 成对消费）；None=无价格日期，前端不隐藏。
    settled_today: Optional[bool] = None
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
