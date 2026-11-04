# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/12 19:29
# File : schemas.py
# app/domains/performance/schemas.py
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class XirrRequest(BaseModel):
    """年化收益率查询参数"""

    scope: str = Field(..., description='查询范围: position / portfolio / symbol')
    position_id: Optional[int] = Field(None, description='持仓ID（scope=position时必填）')
    portfolio_id: Optional[int] = Field(None, description='投资组合ID（scope=portfolio时用于指定组合）')
    symbol: Optional[str] = Field(
        None, description='产品代码（scope=symbol 时必填；跨账户按 symbol 汇总现金流，算产品级持有年化）'
    )
    include_cash_equivalents: bool = Field(
        False, description='是否将货币基金/逆回购/现金等现金等价物纳入年化收益分母；默认 False=仅主动投资'
    )
    method: str = Field(
        'xirr',
        description=(
            '收益率方法（#871）：xirr=年化资金加权（默认，对申赎时点敏感）；'
            'twr=时间加权（剔除自身现金流影响，跨账户/跨人可比，需历史估值）；'
            'dietz=Modified Dietz 区间收益（线性近似，不年化，答「本月贡献多少」）'
        ),
    )


class TwrRequest(BaseModel):
    """时间加权收益率查询参数（#2133）。

    只支持家庭级 / 账户级：TWR 需要「每日净资产」序列，产品级与单持仓没有这条序列，
    硬算会把家庭净资产当成某个标的的分母。前端 / 调用方请勿传其它作用域。
    组合级 TWR 走 `/xirr/?method=twr&scope=portfolio&portfolio_id=...`（#871）。
    """

    ledger_id: Optional[int] = Field(None, description='账户ID；不传=家庭级（与收益日历同语义）')
    start_date: Optional[date] = Field(None, description='起始日期(YYYY-MM-DD)，默认近 30 天（与收益日历同一缺省规则）')
    end_date: Optional[date] = Field(None, description='结束日期(YYYY-MM-DD)，默认今天')


class MoneyFundIncomeRequest(BaseModel):
    """货币基金每日收益查询参数"""

    scope: Optional[str] = Field(None, description='查询范围: ledger / family / portfolio')
    ledger_id: Optional[int] = Field(None, description='账户ID（scope=ledger时必填）')
    portfolio_id: Optional[int] = Field(
        None, description='投资组合ID（scope=portfolio时必填，由后端解析为关联账户集合）'
    )
    start_date: Optional[date] = Field(None, description='起始日期(YYYY-MM-DD)，默认近30天')
    end_date: Optional[date] = Field(None, description='结束日期(YYYY-MM-DD)，默认今天')


class XirrResponse(BaseModel):
    """收益率查询响应（#871：method 决定哪些字段有值，其余为 None）

    - ``method=xirr``：``xirr`` 年化资金加权（默认，历史行为不变）；
    - ``method=dietz``：``dietz`` 区间收益（不年化）；
    - ``method=twr``：``twr`` 区间 + ``twr_annualized`` 年化，另附
      ``days_used`` / ``days_skipped``（缺数据跳过的天数，见
      `services/performance/twr.py` 的诚实降级）。TWR 口径为总资产
      （日净资产序列天然含货币基金等现金等价物）。
    """

    method: str = Field('xirr', description='实际使用的收益率方法')
    xirr: Optional[float] = Field(None, description='年化收益率，如 0.1234 表示 12.34%（method=xirr）')
    dietz: Optional[float] = Field(None, description='区间收益率，不年化（method=dietz）')
    twr: Optional[float] = Field(None, description='时间加权区间收益率（method=twr；无数据时为 None）')
    twr_annualized: Optional[float] = Field(None, description='时间加权年化收益率（method=twr）')
    total_invested: float = Field(..., description='累计买入金额（毛额，同一笔钱反复买卖会重复累加）')
    total_withdrawn: float = Field(..., description='历史收回金额（卖出 + 分红，不含当前市值）')
    net_invested: float = Field(
        ...,
        description='净投入 = 累计买入 − 历史收回，即当前还压在里面的本金；展示口径应优先用它，而非毛额 total_invested',
    )
    current_value: float = Field(..., description='当前市值')
    total_return: float = Field(..., description='总收益 = 当前市值 − 净投入（含已实现 + 未实现 + 分红）')
    cashflow_count: int = Field(..., description='参与计算的现金流笔数')
    days_used: Optional[int] = Field(None, description='TWR 参与连乘的天数（method=twr）')
    days_skipped: Optional[int] = Field(None, description='TWR 因缺数据被跳过的天数（method=twr；跳过而非当 0）')
