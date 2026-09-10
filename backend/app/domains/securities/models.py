# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 18:47
# File : models.py
# app/domains/securities/models.py

"""证券元数据模型（股票、ETF、可转债、期货等）"""

from sqlalchemy import Column, Date, Integer, String

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


class Security(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'securities'

    symbol = Column(String(30), unique=True, nullable=False, comment='代码，如 00700.HK, BTC-USD')
    name = Column(String(100), nullable=False, comment='名称')
    market = Column(String(20), nullable=False, comment='市场: CN_A, CN_HK, US, CRYPTO, COMMODITY')
    type = Column(String(20), nullable=False, comment='产品类型: stock, etf, bond, future, crypto')
    currency = Column(String(10), default='CNY', comment='交易币种')
    sector = Column(String(50), comment='行业/板块')


class ConvertibleBondTerm(Base, PrimaryKeyMixin, TimestampMixin):
    """可转债条款（#1285 消费侧 / #1393，market 域）。

    可转债的决策核心是**条款博弈**（强赎 / 下修 / 回售），条款状态优先于行情。
    本表落**静态条款**：触发价、转股价值/溢价率、评级、到期日、规模、强赎天计数
    （akshare `bond_cb_redeem_jsl` 已含计数）。动态计数（自算、含取整规则）为后期项。

    命名遵循「自解释、禁拼音简称」：`premium_rate` 而非 `syl_*`，`redeem_count` 而非缩写。
    """

    __tablename__ = 'convertible_bond_terms'

    symbol = Column(String(30), unique=True, nullable=False, comment='标准化转债代码，如 SH113050')
    bond_code = Column(String(10), comment='转债原始 6 位代码')
    name = Column(String(50), comment='转债名称')
    stock_symbol = Column(String(30), comment='正股标准化代码')
    stock_name = Column(String(50), comment='正股名称')

    price = Column(SafeNumeric(18, 6), comment='转债现价（元）')
    change_pct = Column(SafeNumeric(10, 4), comment='当日涨跌幅(%)')
    convert_price = Column(SafeNumeric(18, 6), comment='转股价（元）')
    convert_value = Column(SafeNumeric(18, 6), comment='转股价值（元）=100/转股价×正股价')
    premium_rate = Column(SafeNumeric(10, 4), comment='转股溢价率(%)')
    force_redeem_price = Column(SafeNumeric(18, 6), comment='强赎触发价（元）')
    put_convert_price = Column(SafeNumeric(18, 6), comment='回售触发价（元）')

    redeem_count = Column(Integer, comment='强赎天计数（近 30 交易日中收盘价达触发价的天数）')
    redeem_required = Column(Integer, comment='强赎触发所需达标天数（通常 15）')
    redeem_trigger_ratio = Column(SafeNumeric(6, 2), comment='强赎触发比(%)，如 130')
    redeem_status = Column(String(20), comment='强赎状态：已公告强赎 / 公告要强赎 / 公告不强赎 / 已满足强赎条件')
    redeem_clause = Column(String(200), comment='强赎条款原文')

    rating = Column(String(10), comment='信用评级，如 AA+')
    maturity_date = Column(Date, comment='到期日')
    issue_size = Column(SafeNumeric(18, 4), comment='发行规模（亿元）')
    remain_size = Column(SafeNumeric(18, 4), comment='剩余规模（亿元）')
    source = Column(String(20), comment='数据来源')
