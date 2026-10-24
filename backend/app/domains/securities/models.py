# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 18:47
# File : models.py
# app/domains/securities/models.py

"""证券元数据模型（股票、ETF、可转债、期货等）"""

from sqlalchemy import Column, Date, Index, Integer, String, UniqueConstraint

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


class SecurityIndustryMap(Base, PrimaryKeyMixin, TimestampMixin):
    """**个股 / 可转债 → 行业**映射（#1981· 组合穿透补强）。

    ## 为什么需要这张表

    组合穿透（`services/penetration.py`）原先只对**基金**做行业层穿透：基金的行业配置
    来自 `fund_industry_allocs`（季报披露）。而**直持的股票 / 可转债**没有这条披露链，
    只能拿到市值、回答不了「这笔钱压在哪些行业」，于是被归为
    `industry_map_missing` —— 实测占组合 35.9%，是穿透率上不去的两大原因之一。

    这张表就是那条缺失的映射链：**证券代码 → 行业**，落库后读侧一次查询即可并入
    行业分布。

    ## `scheme` 必须存在，且**禁止跨体系相加**

    与 `fund_industry_allocs.scheme` 同理：证监会门类（`csrc`，19 个，粒度粗但稳定）
    与申万一级（`sw1`，31 个，粒度细、市场研究的事实标准）**语义不重叠**——同一家
    公司在两套里归属不同行业，跨体系求和会得出荒谬结论。读侧按 `scheme` 分区，
    主口径与基金侧对齐（`csrc`），其余单列。

    ## `source` / `effective_date` 是**必需**的，不是装饰

    行业分类会随财报与监管口径调整（申万每年调整、证监会门类偶有修订），映射会**过期**。
    故必须记来源（便于按 #897 的数据源优先级切换与追责）与来源侧标注的生效日期
    （判断新鲜度），否则表里会静默躺着一批无人知晓已失效的映射。

    ## 数据源（#1981 选型实证）

    - `swsresearch`（申万宏源研究官网 `www.swsresearch.com`）：**31 个一级行业 × 1 个请求**
      即可拿到全 A 映射，是本表全量刷新的主通道；
    - `cninfo`（巨潮资讯）：证监会门类，**逐只**取，成本高，故只按需补持仓实际出现的标的；
    - **东财已否决**（实证：同一端点分钟级从 200 变 `RemoteDisconnected`，且项目
      `core/requests_patch` 已注入东财头 + Referer + 退避重试仍失败）——间歇性不可达，
      不能作批量通道，详见 #1431。
    """

    __tablename__ = 'security_industry_maps'

    symbol = Column(String(30), nullable=False, index=True, comment='证券代码（归一裸码，如 600519）')
    scheme = Column(String(10), nullable=False, comment='分类体系: csrc(证监会门类) / sw1(申万一级)')
    industry_code = Column(String(20), nullable=False, comment='行业代码（csrc 单字母 / sw1 六位如 801010）')
    industry_name = Column(String(50), comment='行业名称')
    source = Column(String(30), nullable=False, comment='数据来源: swsresearch(申万宏源) / cninfo(巨潮资讯)')
    source_ref = Column(String(50), comment='来源侧原始代码（申万 801010 / 巨潮行业类别码），便于回溯')
    effective_date = Column(Date, comment='来源侧标注的生效或发布日期（分类会调整，用于判断映射新鲜度）')

    __table_args__ = (
        UniqueConstraint('symbol', 'scheme', name='uq_security_industry_symbol_scheme'),
        Index('ix_security_industry_scheme_symbol', 'scheme', 'symbol'),
    )


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

    # ── 条款增强两列（#1400 / #2575）────────────────────────────────────────
    # 数据源：东财 RPT_BOND_CB_LIST 批量报表口（带 quoteColumns），免 cookie。
    # 「三个缺口需登录态」的前提在 2026-10-24 实测后被推翻。
    stock_pb = Column(
        SafeNumeric(10, 4),
        comment='正股市净率 PB（东财 quoteColumns 关联带出；覆盖 99.1%）',
    )
    ytm = Column(
        SafeNumeric(12, 4),
        comment=(
            '到期税前收益 YTM（%，单利年化持有到期总回报，自算；'
            '口径同集思录。**深度价内债不出此值**——持有到期不成立，'
            '算出来是 -500% 这种无意义数）'
        ),
    )
