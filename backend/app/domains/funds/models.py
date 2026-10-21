# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:31
# File : models.py
"""场外基金元数据模型"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


class FundCompany(Base, PrimaryKeyMixin, TimestampMixin):
    """基金公司主数据（**唯一可写表**，简称/全称同表双字段）。

    命名约定（与 `Fund` 一致）：
    - `name`：简称，如「易方达基金」——**界面默认显示这个**；
    - `full_name`：权威全称，如「易方达基金管理有限公司」——详情页/核对用。

    为什么要两个字段而不是两行：2026-09-10 实测库里存在 8 组「简称一行 + 全称一行」
    的重复实体（如 `华安基金` 与 `华安基金管理有限公司` 各占一行），同一家公司的
    经理被分裂挂到两行（招商基金 103 + 9）。**同一法人主体只能有一行**，
    全称是这一行的属性，不是另一行。

    单一写者原则（防跨源漂移，每个字段只有一个同步任务有写权）：
    - `code` / `name` / `scale` ← 东财链路（`company_resolver` 解析 code，
      `fund_detail_enrich_job` / 基金列表任务写名与规模）；
    - `full_name` / `register_addr` / `office_addr` / `website` / `phone` /
      `is_active` ← 仅 AMAC 名录任务（`amac_institution_job`）写。

    历史：曾另有 `fund_management_companies`（user 域）表达同一概念——实测零读者、
    零外键、零接口，2026-09-10 合并入本表后删除（见 `docs/spec/decisions.md`）。
    """

    __tablename__ = 'fund_companies'

    code = Column(String(20), unique=True, nullable=False, comment='公司编码（东财 jjjz_gs，8 位）')
    name = Column(String(60), nullable=False, comment='简称（界面默认显示）')
    full_name = Column(String(100), comment='权威全称（AMAC 公示）')
    scale = Column(Float, comment='管理规模(亿)')
    # ── 以下 5 列仅 AMAC 名录任务写（原 fund_management_companies 表字段，合并而来）──
    register_addr = Column(String(200), comment='注册地址（AMAC 公示）')
    office_addr = Column(String(200), comment='办公地址（AMAC 公示）')
    website = Column(String(200), comment='官网（AMAC 公示）')
    phone = Column(String(100), comment='客服电话（AMAC 公示）')
    is_active = Column(Boolean, default=True, server_default=text('1'), comment='是否在 AMAC 基金管理人公示名单内')


class FundVariety(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_varieties'

    name = Column(String(50), unique=True, nullable=False, comment='大类名称')
    fund_types = relationship('FundType', back_populates='variety')


class FundType(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_types'

    name = Column(String(50), unique=True, nullable=False, comment='类型名称')
    variety_id = Column(Integer, ForeignKey('fund_varieties.id'), comment='所属大类')
    variety = relationship('FundVariety', back_populates='fund_types')


class FundSaleOrg(Base, PrimaryKeyMixin):
    __tablename__ = 'fund_sales_orgs'

    org_id = Column(Integer, unique=True, comment='机构编号')
    name = Column(String(100), comment='机构名称')
    known_name = Column(String(50), comment='常用简称')


class Manager(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'managers'

    mgr_code = Column(String(30), unique=True, comment='管理人编码')
    name = Column(String(60), nullable=False, comment='姓名')
    mgr_type = Column(String(20), default='fund_manager', comment='类型: fund_manager, portfolio_manager, individual')
    company_id = Column(Integer, ForeignKey('fund_companies.id'), comment='所属公司')
    appointment_date = Column(Date, comment='任职起始日')
    sum_scale = Column(Float, comment='管理资产规模(亿)')
    best_return = Column(Float, comment='最佳回报(%)')
    avatar_url = Column(String(300))

    company = relationship('FundCompany', foreign_keys=[company_id])
    funds = relationship('Fund', secondary='fund_managers', back_populates='managers')


class Fund(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'funds'

    fund_code = Column(String(6), unique=True, nullable=False, comment='基金代码')
    name = Column(String(80), nullable=False, comment='简称')
    full_name = Column(String(100), comment='全称')
    pinyin_abbr = Column(String(30), comment='拼音缩写')
    pinyin_full = Column(String(80), comment='拼音全称')
    fund_type_id = Column(Integer, ForeignKey('fund_types.id'), comment='基金小类')
    fund_variety_id = Column(Integer, ForeignKey('fund_varieties.id'), comment='基金大类')
    company_id = Column(Integer, ForeignKey('fund_companies.id'), comment='基金公司')
    # ── #1286 品种差异化维度：基金规模 / 近似股票仓位 ──
    # 回填见 FundScaleSyncJob（全市场一次拉取）与 FundPositionSyncJob（逐只，仅核心池）
    # （2026-09-11 起由原 FundMetaSyncJob 拆分，见 #1403：逐只抓取必须按目标池限量）
    # 精度说明（PR #1358 review）：虽为市场参照估算字段（非用户记账链路），
    # 仍按份额/金额精度规范用 SafeNumeric，避免 Float 精度漂移。
    scale = Column(SafeNumeric(20, 6), comment='基金规模估算(亿元)=最近总份额×单位净值，来源 fund_scale_open_sina')
    recent_shares = Column(SafeNumeric(20, 4), comment='最近总份额(份)，来源 fund_scale_open_sina')
    # 口径（#870 修正）：改取**行业配置合计**（由 fund_industry_allocs 派生），不再取「前十大重仓之和」。
    # 为什么改：前十大只是季报/半年报里的前 10 名求和，对分散型基金系统性低估——实测
    # 005827 前十大 38.95% vs 全量 76.43%（偏差 −37.5pp）、000001 −36.2pp；且季报期只有
    # 前十大，与半年报口径不可比。而证监会要求季报**也**披露行业分类比例，故行业配置合计
    # 在任何报告期都是全量口径，且与持仓全量合计交叉吻合到小数点后两位
    # （110022: 87.18% vs 87.19%；005827: 76.42% vs 76.43%）。
    # 无源数据时**不覆盖**原值（明细是源、标量是派生，无源即不派生）。
    equity_position = Column(
        SafeNumeric(5, 2), comment='近似股票仓位(%)=行业配置合计，来源 fund_portfolio_industry_allocs（全量口径）'
    )
    equity_position_period = Column(String(8), comment='上述仓位对应的报告期，如 2026Q2（口径与版本留痕）')
    # ── #2478 风格箱维度：当前主导风格（派生标量，明细是 FundStyleExposure）──
    # 口径 = FundStyleExposure 最新 stat_date 时点暴露值最大的风格名（上游原文，
    # 如 '大盘成长' / '固收风格'）。同 equity_position 的「无源即不派生」：
    # 抓不到风格箱的基金保持 NULL，不用 '未知' 或旧值冒充新值。
    # QDII 不适用：韭圈儿对海外资产映射存疑（270042 纳指100 实测固收风格 81.28，
    # 见 fund_style_tag_feasibility.md §4），筛选场景应排除 QDII 后使用本字段。
    dominant_style = Column(String(20), comment='当前主导风格（韭圈儿风格箱暴露值最大项，上游原文）')
    style_period = Column(String(10), comment='上述主导风格对应的时点，如 2026-10-16（口径与版本留痕）')
    risk_level = Column(Integer, comment='风险等级 1-5')
    is_fe_charge = Column(Boolean, default=False, comment='前端收费')
    benchmark = Column(String(200), comment='业绩比较基准')
    create_time = Column(Date, comment='成立日期')
    symbol_prefix = Column(String(10), comment='代码前缀')
    is_active = Column(Boolean, default=True, server_default=text('1'), comment='是否参与净值同步')
    last_nav_check = Column(DateTime, comment='最后一次净值检查时间')
    nav_fail_count = Column(Integer, default=0, comment='连续获取净值失败次数')

    fund_type = relationship('FundType', foreign_keys=[fund_type_id])
    variety = relationship('FundVariety', foreign_keys=[fund_variety_id])
    company = relationship('FundCompany', foreign_keys=[company_id])
    managers = relationship('Manager', secondary='fund_managers', back_populates='funds')
    daily_worth = relationship('DailyWorth', back_populates='fund', order_by='DailyWorth.date.desc()')
    money_fund_daily_worth = relationship(
        'MoneyFundDailyWorth', back_populates='fund', order_by='MoneyFundDailyWorth.date.desc()'
    )


class FundManager(Base, PrimaryKeyMixin):
    """基金-经理**关联**：只表达「谁在管谁」（#2239 拆分后）。

    ## 为什么拆成两张表（#2239）

    本表原先同时承担「关联存在性」与「任职时间」两个职责，且**没有**
    ``(fund_id, mgr_id)`` 唯一约束。后果（真实库实测，#2239 卡内有数）：

    - ``fund_managers`` 69,684 行里只有 34,846 个唯一 ``(fund_id, mgr_id)`` 组合
      —— 几乎每行重复一份，且每次同步都会再写一遍（表持续膨胀，IO/存储白耗）；
    - ``start_date`` / ``end_date`` 填充率恒为 0%，前端「任职起止」永远是「—」；
    - 同一经理**多次任职同一基金**这种真实场景根本表达不了（一行一格）。

    #2229 只在**结果层**去重（``SELECT DISTINCT`` / 应用层过滤），表本身照旧膨胀，
    且任何写入路径漏做去重都会静默产生重复行 —— 根因是**表结构**，不是查询写法。
    故此处：关联归本表（带唯一约束），任期归 :class:`ManagerTenure`。

    ## 唯一约束是这套改造的**承重墙**

    ``uq_fund_managers_fund_mgr`` 是幂等的**数据库层**保证：写侧可以直接用
    ``INSERT OR IGNORE`` / ``ON CONFLICT DO NOTHING``（见
    ``sync/jobs/fund_manager_job``），不必再靠「先查已有、再过滤」的应用层两步法
    ——后者在并发或分批边界上仍会漏，且每次都多一轮查询。

    存量库由 :func:`app.core.migrations.migrate_fund_managers_split_tenures`
    整表重建补齐（SQLite 不支持给已存在的表加约束，只能「建新表→拷贝→删旧→改名」）。
    """

    __tablename__ = 'fund_managers'
    __table_args__ = (UniqueConstraint('fund_id', 'mgr_id', name='uq_fund_managers_fund_mgr'),)

    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=False)
    mgr_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    is_classic = Column(Boolean, default=False, comment='代表作品')


class ManagerTenure(Base, PrimaryKeyMixin, TimestampMixin):
    """基金经理**任期分段**（#2239 从 ``fund_managers`` 拆出）。

    ## 语义

    一段任期 = 「某经理在某基金的某段时间内在任」。同一 ``(fund_id, mgr_id)``
    **允许多段**（张坤在 005827 就有两段，见 ``adapters/manager_tenure.find_tenure``），
    这是拆表的核心收益：原表一行一格，表达能力上就写不下「两进两出」。

    ## 字段口径

    - ``start_date`` 非空、``end_date`` 可空：**NULL 表示仍在任**。展示层据此判在任
      （``manager_profile._managed_funds`` 的 ``is_active``），所以**不要**用「未来的
      end_date」或占位日期表示在任 —— 那会让「卸任日」这个词失去意义；
    - ``current`` 标记**当前在任段**，供「代表作」等需要快速筛选的场景用
      （``manager_holdings`` 原先按 ``start_date`` 最早挑，改为读本表后仍以任期长短为准，
      见该服务注释）。它与 ``end_date IS NULL`` 在正常数据下等价，但**不冗余**：
      数据源只给「截止某日」而调仓尚未确认时，两者会短暂分叉，届时以 ``current`` 为准；
    - ``source`` 记来源标识（``jjjl_f10`` = 天天基金 F10 经理页），便于日后换源时区分批次。

    ## 为什么仓位类字段不在这里

    本表**只存时间**。``is_classic``（代表作品）是「关联的属性」而非「任期的属性」，
    留在 :class:`FundManager` —— 一段任期结束时它不该跟着消失。

    ## 幂等键

    ``uq_manager_tenures_fund_mgr_start``：同一人、同一基金、同一入职日只允许一条。
    重复抓取（同一只基金反复 ``--targets``）因此天然幂等，不需要「删了重写」。
    """

    __tablename__ = 'manager_tenures'
    __table_args__ = (
        UniqueConstraint(
            'fund_id',
            'mgr_id',
            'start_date',
            name='uq_manager_tenures_fund_mgr_start',
        ),
        Index('ix_manager_tenures_mgr_id', 'mgr_id'),
        Index('ix_manager_tenures_fund_id', 'fund_id'),
    )

    fund_id = Column(Integer, ForeignKey('funds.id'), nullable=False)
    mgr_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    start_date = Column(Date, nullable=False, comment='任职起始')
    end_date = Column(Date, nullable=True, comment='任职结束；NULL = 仍在任')
    current = Column(
        Boolean,
        default=False,
        server_default=text('0'),
        comment='当前在任段（供「代表作」等快速筛选）；正常数据下等价于 end_date IS NULL',
    )
    source = Column(String(20), default='jjjl_f10', comment='来源标识（jjjl_f10 = 天天基金 F10 经理页）')


class ChannelLink(Base, PrimaryKeyMixin, TimestampMixin):
    """跨渠道关联（#1285 设计 §3.8）：指数↔ETF、ETF↔联接基金。

    同一底层资产在多个渠道的同义标的（指数 / 场内 ETF / 场外联接），用于自选页的
    「关联入口」（角标数量 + 浮层）。存**有向**关系 `from_symbol → to_symbol`，
    语义是「从该标的出发可跳转的关联标的」。

    - `link_type='index_etf'`：from=指数（裸代码，如 000300），to=ETF（裸代码，如 510300）
    - `link_type='etf_feeder'`：from=ETF（如 510300），to=联接基金（如 000051）

    **统一存裸代码**（不含 SH/SZ/CSI 前缀）：自选行的 symbol 前缀形态不统一
    （SH000300 / CSI000300 / SZ399006），按裸代码 join 才能前缀无关地命中；
    展示所需的名称冗余在 `from_name` / `to_name`。

    **为什么靠名称匹配**：akshare `fund_etf_spot_em` **无「跟踪标的」字段**、交易所规模表
    亦无（2026-09-11 实测），只能靠产品名。第一版（PR #1399）用东财**场内简称**
    （指数名被压没，覆盖 41.1%）→ 降级为 13 个宽基白名单、实落 274 条。2026-09-11 改版：
    换同花顺**基金全称**作匹配文本 + 最长核心名匹配（覆盖 89.0% 毛 / 66.4% 落库口径），
    并补齐 `etf_feeder` 第二层（68.3%）。算法与实测依据见 `services/sync/name_match.py`。
    仍匹配不上的（跨境/商品 ETF 的跟踪标的不在 `index_catalog` 内）留 `—`，缺口记 #1419。

    `match_type` 记录匹配置信方式，便于后续人工校正/扩面。
    """

    __tablename__ = 'channel_links'

    link_type = Column(String(20), nullable=False, comment='关系类型: index_etf / etf_feeder')
    from_symbol = Column(String(30), nullable=False, comment='起点裸代码（指数代码 / ETF 代码）')
    to_symbol = Column(String(30), nullable=False, comment='终点裸代码（ETF 代码 / 联接基金代码）')
    from_name = Column(String(80), comment='起点名称（冗余，浮层直接展示）')
    to_name = Column(String(80), comment='终点名称（冗余）')
    match_type = Column(
        String(20),
        comment='匹配置信方式: name_longest_core（指数↔ETF）/ feeder_core_manager（ETF↔联接）/ manual',
    )
    source = Column(String(20), default='auto', comment='来源: auto / manual')

    # #1491 评审：to_symbol 是查询/join 字段（见类注释），缺索引会全表扫描；
    # 存量库由 migrate_channel_link_indexes 在启动期补建（create_all 不给存量表加索引）
    __table_args__ = (
        UniqueConstraint('link_type', 'from_symbol', 'to_symbol', name='uk_channel_link'),
        Index('ix_channel_links_to_symbol', 'to_symbol'),
    )


class DailyWorth(Base, PrimaryKeyMixin, TimestampMixin):
    """基金每日净值"""

    __tablename__ = 'daily_worth'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    date = Column(Date, nullable=False, comment='净值日期')
    unit_nav = Column(SafeNumeric(18, 6), comment='单位净值（元），精度6位小数')
    acc_nav = Column(SafeNumeric(18, 6), comment='累计净值（元），精度6位小数')

    fund = relationship('Fund', back_populates='daily_worth')

    __table_args__ = (UniqueConstraint('fund_code', 'date', name='uq_daily_worth_code_date'),)


class FundValuationDaily(Base, PrimaryKeyMixin, TimestampMixin):
    """场外基金收盘估值定格（#2141）

    收盘后按固定时点（15:15 / 19:15 / 21:15）抓取天天基金估值快照，
    供「收盘后估值」定格展示与 pnl_calendar 当日估算回退。
    估值是时点数据：净值发布后源端会清空 GSZ，故同一 (fund_code, est_date)
    可能被多个时点覆盖——采用 REPLACE 语义，后写入的时点覆盖先写入的。
    fund_code 不设 FK：估值覆盖全市场场外基金，本地 funds 表可能不存在该基金
    （与 AdvisorHolding 同款业务键模式），跨域 join 本就禁止。

    ## 对照语义（#2142）

    官方净值（`daily_worth.unit_nav`）到位后，`fund_valuation_reconcile` job 把
    status 翻 `confirmed`，并把官方值**副本**与偏差记在本表（official_nav /
    deviation / deviation_pct），供「预估 vs 官方」对照与数据源质量观察。
    副本不是权威：唯一权威始终是 daily_worth，本表从不反向写它；
    官方迟到/缺失时行保持 estimated、三列 NULL（诚实降级，前端标注即可）。
    """

    __tablename__ = 'fund_valuation_daily'

    fund_code = Column(String(16), nullable=False, comment='基金代码')
    est_date = Column(Date, nullable=False, comment='估值日期（源端 PDATE）')
    estimated_nav = Column(SafeNumeric(18, 6), nullable=False, comment='估算净值（元），精度6位小数')
    change_pct = Column(SafeNumeric(10, 4), comment='估算涨跌幅（%），如 1.2345 表示 +1.2345%')
    source_time = Column(String(32), comment='源端估值时间字符串（GZTIME，原样存储，如 "2026-10-13 15:00"）')
    source = Column(String(32), default='tiantian_gsz', comment='数据源标识，默认天天基金 GSZ')
    status = Column(
        String(16), default='estimated', comment='估值状态: estimated / confirmed（官方到位后由对照 job 翻 confirmed）'
    )
    official_nav = Column(SafeNumeric(18, 6), comment='官方净值副本（元），对照用；权威仍是 daily_worth.unit_nav')
    deviation = Column(SafeNumeric(18, 6), comment='偏差（元）= 预估 − 官方')
    deviation_pct = Column(SafeNumeric(10, 4), comment='偏差率（%）= deviation / official_nav × 100')

    __table_args__ = (UniqueConstraint('fund_code', 'est_date', name='uq_fund_valuation_code_date'),)


class PurchaseRule(Base, PrimaryKeyMixin, TimestampMixin):
    """申购/认购费率阶梯的金额区间规则"""

    __tablename__ = 'purchase_rules'

    start_quota = Column(Integer, comment='起始金额(分)，包含')
    end_quota = Column(Integer, comment='结束金额(分)，不包含，NULL表示正无穷')

    # 同一金额区间只能有一条规则（2026-10-18）。**必须用表达式索引**：最后一档的
    # end_quota 恒为 NULL，而 SQLite 里 NULL 不参与唯一性判断——普通唯一索引对
    # 「无上限」那一档形同虚设。
    __table_args__ = (
        Index(
            'uq_purchase_rules_quota',
            text('COALESCE(start_quota, -1)'),
            text('COALESCE(end_quota, -1)'),
            unique=True,
        ),
    )


class RedeemRule(Base, PrimaryKeyMixin, TimestampMixin):
    """赎回费率阶梯的持有天数区间规则"""

    __tablename__ = 'redeem_rules'

    start_day = Column(Integer, nullable=False, default=0, comment='起始天数, 包含')
    end_day = Column(Integer, nullable=True, comment='结束天数, 不包含, NULL表示正无穷')

    # 同一持有天数区间只能有一条规则（2026-10-18）。表达式索引的理由同 PurchaseRule：
    # 最后一档 end_day 恒为 NULL，普通唯一索引管不到它。
    __table_args__ = (
        Index(
            'uq_redeem_rules_range',
            text('COALESCE(start_day, -1)'),
            text('COALESCE(end_day, -1)'),
            unique=True,
        ),
    )


class EtfFeeRate(Base, PrimaryKeyMixin, TimestampMixin):
    """ETF 运作费率缓存小表（market 域，#2333）。

    与 ``fee_ratios`` 的区别：那张是场外基金申购/赎回费率阶梯（外键 → funds）；
    本表只存**场内 ETF 的管理费率 + 托管费率**（%/年），是对比表费率列的
    「缓存即兜底」——免费 JSON 源经逐一排查实测不存在运作费用字段（#2333），
    只能走 HTML 双源（东财 F10 / 同花顺），双源都挂时沿用旧值。
    **只写对比表触达的 ETF**（读路径 = etf_compare 服务），不做全市场回填 job。
    """

    __tablename__ = 'etf_fee_rates'

    etf_code = Column(String(6), unique=True, nullable=False, comment='ETF 代码（裸 6 位码）')
    mgmt_fee_pct = Column(SafeNumeric(8, 4), comment='管理费率(%/年)，如 0.15')
    custody_fee_pct = Column(SafeNumeric(8, 4), comment='托管费率(%/年)，如 0.05')
    source = Column(String(10), comment='抓取来源: em=东财 F10 / ths=同花顺')
    # 读取时超 30 天尝试重抓（费率年频变化，30 天窗口足够新），失败沿用旧值
    fetched_at = Column(DateTime, nullable=False, comment='最近一次成功抓取时间（超 30 天读取时尝试重抓）')


class FeeRatio(Base, PrimaryKeyMixin, TimestampMixin):
    """基金费率与规则的关联表"""

    __tablename__ = 'fee_ratios'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    fee_type = Column(String(20), nullable=False, comment='费率类型: subscribe/purchase/redeem/management')
    rate = Column(SafeNumeric(10, 6), comment='费率(如0.015000=1.5%)')
    fee_amount = Column(Integer, comment='固定金额(分)，与rate互斥')
    currency = Column(String(10), nullable=False, default='CNY', comment='计费币种(ISO 4217)，默认CNY')
    purchase_rule_id = Column(Integer, ForeignKey('purchase_rules.id'), nullable=True)
    redeem_rule_id = Column(Integer, ForeignKey('redeem_rules.id'), nullable=True)

    # 「同一基金 + 同一费率类型 + 同一规则」只能有一条费率（2026-10-18）。
    #
    # ## 为什么补这条约束
    #
    # 本表此前**一个索引都没有**，于是 2026-05-31 的一次整表复制在库里留下 12,732 组
    # 逐字相同的副本行（fee_ratios 25,471 行，重复行的 rate/currency/created_at/
    # updated_at 全同），表现为「赎回费率分布每档显示两次」。应用层已收口为
    # upsert + 结构校验 + 清残档，但那些闸只在**已知写路径**上生效；唯一约束是最后
    # 一道、也是唯一会让错误**当场报错**而不是静默通过的一道。
    #
    # ## 为什么用表达式索引
    #
    # redeem 行的 purchase_rule_id 恒为 NULL、purchase 行的 redeem_rule_id 恒为 NULL，
    # 而 SQLite 里 NULL 不参与唯一性判断 → 普通唯一索引对一半的行形同虚设。
    # 故两个 rule id 都先 COALESCE(..., -1) 再比。
    __table_args__ = (
        Index(
            'uq_fee_ratios_scope',
            'fund_code',
            'fee_type',
            text('COALESCE(purchase_rule_id, -1)'),
            text('COALESCE(redeem_rule_id, -1)'),
            unique=True,
        ),
    )


class MoneyFundDailyWorth(Base, PrimaryKeyMixin, TimestampMixin):
    """货币基金每日万份收益与七日年化。

    nav_per_10k 语义（#863 复核）：存储单位为「元」——万份收益如 000198 余额宝
    2026-08-14 为 0.2233 元/万元/日。早期实现按「分」处理导致收益恒 0 的 bug 已修
    （见 money_fund_income.py 模块 docstring），此处类型从 Integer 修为小数精度。
    """

    __tablename__ = 'money_fund_daily_worth'

    fund_code = Column(String(6), ForeignKey('funds.fund_code'), nullable=False, comment='基金代码')
    date = Column(Date, nullable=False, comment='日期')
    nav_per_10k = Column(SafeNumeric(10, 4), default=0, comment='万份收益(元)，如 0.2233')
    annual_return_7d = Column(Float, comment='七日年化收益率(%)，精度0.0001')
    # #863 数据治理：写入来源/算法版本标记。存量旧数据在迁移脚本中置 'legacy_dirty'
    # （旧算法脏数据，需清空重建），新写入由 fund_nav_job / async_backfill 显式标 'v2_recalc'。
    # server_default='legacy_dirty' 保证新增行默认脏数据标记；存量 NULL 行由迁移脚本回填。
    source_version = Column(
        String(20),
        nullable=False,
        server_default='legacy_dirty',
        comment='数据来源版本（#863）：legacy_dirty/v2_recalc',
    )

    fund = relationship('Fund', back_populates='money_fund_daily_worth')

    __table_args__ = (UniqueConstraint('fund_code', 'date', name='uq_money_fund_daily_worth_code_date'),)


class AdvisorPortfolio(Base, PrimaryKeyMixin, TimestampMixin):
    """投顾/基金组合公开参照（market 域，Turso）。

    覆盖且慢/蛋卷/天天基金等平台的「投顾组合 / 实盘组合 / 基金组合」实体
    （如且慢「远足」「成长五剑」、蛋卷策略组合）。属公开、读多写少的参照数据，
    与用户私有 portfolios（组合归属）无关，落 market 域。

    用户侧「自选投顾」只存 platform+code 业务键（见 watchlist 设计），
    经 CrossDomainQuery 两步法回查本表，零跨域外键、零 SQL join。
    """

    __tablename__ = 'advisor_portfolios'

    code = Column(String(30), unique=True, nullable=False, comment='平台组合代码(且慢ZHxxxx/蛋卷CSIxxxx/天天基金combo)')
    platform = Column(String(20), nullable=False, comment='来源平台: QIEMAN/DANJUAN/TIANTIAN/YINGMI')
    name = Column(String(100), nullable=False, comment='组合名称')
    host = Column(String(60), comment='主理人')
    org_name = Column(String(100), comment='主理人所属机构/平台方')
    risk_level = Column(String(20), comment='风险等级')
    strategy_type = Column(String(40), comment='策略类型(均衡/进取/稳健)')
    cum_return = Column(SafeNumeric(7, 2), comment='累计收益(%)')
    annual_return = Column(SafeNumeric(7, 2), comment='年化收益(%)')
    running_days = Column(Integer, comment='运行天数')
    is_active = Column(Boolean, default=True, comment='是否在售/有效')
    # ── #1167 概览补充字段（天天基金 FundIATGInfoAggr / 平台元数据）──
    estab_date = Column(Date, comment='组合成立日期')
    strategy_desc = Column(String(500), comment='策略说明（STGCONCEPT）')

    # ── #1392 数据来历与平台特有字段（Ports & Adapters 收口）──
    # source：本行概览/指标**最近一次写入**的来源（tiantian / qieman / seed），
    #   与 advisor_holdings.source 同口径，用于回答「这行数据是谁写的」；
    #   抓取失败（空概览）时**不改写**，保留上一次成功来源。
    # extra：canonical 概览（见 adapters/advisor_source.CANONICAL_OVERVIEW_COLUMNS）
    #   覆盖不到的**平台特有字段**原样 JSON 保留 —— 新增平台不必为此加列，
    #   日后真要补列时可从这里回填，无需重新抓取。当前消费侧不读它。
    source = Column(String(20), comment='概览/指标最近一次写入来源: tiantian/qieman/seed')
    extra = Column(JSON, nullable=True, comment='平台特有字段（canonical 未覆盖的原始键值）')

    # ── #1392 投顾品类差异化指标（区间收益 / 回撤 / 超额，落库供自选投顾列展示）──
    # 数据源：天天基金 FundIATGInfoAggr 的 SYL_*，映射已实测核对（见 tiantian_advisor_adapter）。
    # 回撤/超额 API 不直接提供（实测结论），暂留空、待补算；列已就绪不影响主链路。
    return_1w = Column(SafeNumeric(7, 2), comment='近1周收益(%)（SYL_Z）')
    return_1m = Column(SafeNumeric(7, 2), comment='近1月收益(%)（SYL_Y）')
    return_1y = Column(SafeNumeric(7, 2), comment='近1年收益(%)（SYL_1N）')
    return_ytd = Column(SafeNumeric(7, 2), comment='今年以来收益(%)（SYL_JN）')
    return_since_incep = Column(SafeNumeric(7, 2), comment='成立以来收益(%)（SYL_LN）')
    benchmark = Column(String(50), comment='业绩比较基准')
    max_drawdown = Column(SafeNumeric(6, 2), comment='最大回撤(%)，API 未直接提供时为空')
    excess_return = Column(SafeNumeric(7, 2), comment='相对基准超额收益(%)，待补算')

    # ── #1468 且慢组合策展元数据（调研注册表 + GetStrategyDetails 实时抓取）──
    # 与上方 #1392 指标列一样，属「列已就绪、不影响主链路」的补充字段；
    # allocation 沿用 assets/positions 的「五笔钱」词表（见 core.constants.ALLOCATION_LABELS），
    # 且慢「四笔钱」活钱/稳钱/长钱 依次映射为 liquid/stable/longterm。
    volatility = Column(SafeNumeric(6, 2), comment='年化波动率(%)')
    sharpe_ratio = Column(SafeNumeric(6, 3), comment='夏普比率')
    allocation = Column(String(20), comment='配置目标（五笔钱：liquid/stable/longterm/...）')
    product_type = Column(String(20), comment='产品类型(货币/货币+/纯债/固收+/平衡/权益(偏股))')
    # 概览其余可用字段（一次抓取全部落库，避免日后为拿单个字段再手动抓）
    strategy_summary = Column(String(300), comment='策略简介（短，GetStrategyDetails 策略简介）')
    source_url = Column(String(120), comment='组合官方页面链接（且慢 qieman.com/alfa/portfolio/<code>）')
    nav = Column(SafeNumeric(12, 6), comment='组合最新净值')
    nav_date = Column(Date, comment='组合净值日期')
    return_1d = Column(SafeNumeric(7, 2), comment='近1日收益(%)')
    return_1q = Column(SafeNumeric(7, 2), comment='近1季度收益(%)')
    return_6m = Column(SafeNumeric(7, 2), comment='近半年收益(%)')


class AdvisorHolding(Base, PrimaryKeyMixin, TimestampMixin):
    """投顾组合当前基金级持仓（#1167）。

    语义：最新一次调仓后的基金占比快照（天天基金 getAdjustWarehouse tag=0 的
    afterRatio；且慢为 BatchGetStrategiesComposition 持仓占比，手动导入）。
    同一组合同一调仓日整体覆盖式更新。

    fund_code 用业务键不建硬外键：组合成分基金可能暂缺于本地 funds 表，
    硬外键会阻塞写入；关联查询走应用层两步法。
    """

    __tablename__ = 'advisor_holdings'

    portfolio_id = Column(
        Integer, ForeignKey('advisor_portfolios.id'), nullable=False, index=True, comment='所属投顾组合'
    )
    as_of_date = Column(Date, nullable=False, index=True, comment='调仓日期（快照日）')
    fund_code = Column(String(6), nullable=False, index=True, comment='成分基金代码（业务键）')
    fund_name = Column(String(100), comment='成分基金名称')
    pre_ratio = Column(SafeNumeric(5, 2), comment='调仓前占比(%)')
    after_ratio = Column(SafeNumeric(5, 2), comment='调仓后/当前占比(%)')
    op_code = Column(Integer, comment='操作类型: 1建仓/2加仓/3减仓/4新增/5持平')
    op_name = Column(String(10), comment='操作名称')
    source = Column(String(20), nullable=False, comment='数据来源: tiantian/qieman(自动)/qieman_manual(手动导入)')

    __table_args__ = (UniqueConstraint('portfolio_id', 'fund_code', 'as_of_date', name='uq_advisor_holding_p_f_d'),)


class AdvisorIndustryAlloc(Base, PrimaryKeyMixin, TimestampMixin):
    """投顾组合持仓行业配置（#1167，天天基金 getHoldWarehouseIndustryRatio）。"""

    __tablename__ = 'advisor_industry_allocs'

    portfolio_id = Column(
        Integer, ForeignKey('advisor_portfolios.id'), nullable=False, index=True, comment='所属投顾组合'
    )
    as_of_date = Column(Date, nullable=False, index=True, comment='快照日期')
    industry_name = Column(String(50), nullable=False, comment='行业名称')
    ratio = Column(SafeNumeric(5, 2), comment='行业占比(%)')
    source = Column(String(20), nullable=False, comment='数据来源: tiantian（当前仅天天提供行业配置）')

    __table_args__ = (
        UniqueConstraint('portfolio_id', 'industry_name', 'as_of_date', name='uq_advisor_industry_p_i_d'),
    )


class AdvisorAdjustHistory(Base, PrimaryKeyMixin, TimestampMixin):
    """投顾组合历史调仓明细（#1167，天天基金 getAdjustWarehouse tag=1）。

    每条 = 某次调仓中单只基金的前后占比；同一(组合, 调仓日, 基金)唯一，
    重复同步按唯一键覆盖，调仓理由 reason 随行冗余存储。
    """

    __tablename__ = 'advisor_adjust_histories'

    portfolio_id = Column(
        Integer, ForeignKey('advisor_portfolios.id'), nullable=False, index=True, comment='所属投顾组合'
    )
    adjust_date = Column(Date, nullable=False, index=True, comment='调仓日期')
    reason = Column(String(300), comment='调仓理由')
    fund_code = Column(String(6), nullable=False, comment='成分基金代码（业务键）')
    fund_name = Column(String(100), comment='成分基金名称')
    pre_ratio = Column(SafeNumeric(5, 2), comment='调仓前占比(%)')
    after_ratio = Column(SafeNumeric(5, 2), comment='调仓后占比(%)')
    op_code = Column(Integer, comment='操作类型: 1建仓/2加仓/3减仓/4新增/5持平')
    op_name = Column(String(10), comment='操作名称')
    source = Column(String(20), nullable=False, comment='数据来源: tiantian(官方接口)/qieman(快照推导)')

    __table_args__ = (UniqueConstraint('portfolio_id', 'adjust_date', 'fund_code', name='uq_advisor_adjust_p_d_f'),)


# ── 基金持仓明细 / 行业配置（#870 基金持仓穿透）─────────────────────────────────
# 语义是**报告期快照**，不是日期序列：东财只提供报告期粒度（`季度`），无任意日期查询。
# 版本键统一用 `report_period`（如 '2026Q2'），不用日期。
#
# 两表都用 `fund_code` 业务键、**不建硬外键**（与 AdvisorHolding 同因：成分标的有可能
# 暂缺于本地 funds 表，硬外键会阻塞写入；关联查询走应用层两步法）。


class FundHolding(Base, PrimaryKeyMixin, TimestampMixin):
    """基金持仓明细（#870，来源：东财基金档案-投资组合 / ccmx）。"""

    __tablename__ = 'fund_holdings'

    fund_code = Column(String(6), nullable=False, index=True, comment='基金代码（业务键）')
    report_period = Column(String(8), nullable=False, index=True, comment='报告期，如 2026Q2（版本键）')
    report_date = Column(Date, comment='报告期截止日')
    holding_basis = Column(String(8), nullable=False, comment='披露口径: full(半年报/年报全量) / top10(季报前十大)')
    stock_code = Column(String(10), nullable=False, comment='股票代码（A 股 6 位 / 港股 5 位，不做补零）')
    stock_name = Column(String(50), comment='股票名称')
    ratio = Column(SafeNumeric(5, 2), comment='占净值比例(%)')
    shares = Column(SafeNumeric(20, 4), comment='持股数(万股)')
    market_value = Column(SafeNumeric(20, 4), comment='持仓市值(万元)')
    rank = Column(Integer, comment='期内序号（1 起，按披露顺序）')
    source = Column(String(20), nullable=False, comment='数据来源: eastmoney(东财基金档案)')

    __table_args__ = (
        # 前十大与全量**并存**、不做单值覆盖：季报只有前十大，若与半年报合并成一个口径，
        # 季报期数据会莫名其妙"缩水"，被误读成大幅减仓。
        UniqueConstraint(
            'fund_code', 'report_period', 'holding_basis', 'stock_code', name='uq_fund_holding_code_period_basis_stock'
        ),
        Index('ix_fund_holding_period_basis', 'report_period', 'holding_basis'),
    )


class FundIndustryAlloc(Base, PrimaryKeyMixin, TimestampMixin):
    """基金行业配置（#870，来源：东财 f10/HYPZ）。

    **独立成表而非并入 `fund_holdings`**：值是「占净值比例」而非持仓数量，分类体系也不同。

    `scheme` 标记分类体系——东财同一端点**混用两套且不做标记**：境内股票走证监会门类
    （`csrc`，单字母 A~S），港股等走 GICS 板块（`gics`，两位数字）。两套体系语义不重叠
    （GICS 的「非必需消费品」在证监会门类里并入「制造业」），**聚合时按 `scheme` 分区
    各自求和，禁止跨体系相加**，否则会得出「制造业与非必需消费品同级并列」的荒谬结论。
    """

    __tablename__ = 'fund_industry_allocs'

    fund_code = Column(String(6), nullable=False, index=True, comment='基金代码（业务键）')
    report_period = Column(String(8), nullable=False, index=True, comment='报告期，如 2026Q2（版本键）')
    report_date = Column(Date, comment='报告期截止日')
    industry_code = Column(String(10), nullable=False, comment='行业代码（csrc 单字母 / gics 两位数字）')
    industry_name = Column(String(50), comment='行业名称')
    scheme = Column(String(10), nullable=False, comment='分类体系: csrc(证监会门类) / gics(GICS 板块)')
    ratio = Column(SafeNumeric(5, 2), comment='行业占净值比例(%)')
    source = Column(String(20), nullable=False, comment='数据来源: eastmoney(f10/HYPZ)')

    __table_args__ = (
        UniqueConstraint('fund_code', 'report_period', 'industry_code', name='uq_fund_industry_code_period'),
        Index('ix_fund_industry_period_scheme', 'report_period', 'scheme'),
    )


class FundStyleExposure(Base, PrimaryKeyMixin, TimestampMixin):
    """基金投资风格箱暴露明细（#2478，来源：韭圈儿免登录 API `get-style-history`）。

    晨星式 8 分类（大盘成长/大盘价值/中盘成长/中盘价值/小盘成长/小盘价值/港股风格/
    固收风格），**月度频率**，每时点 8 个风格值合计 = 100（百分比暴露）。

    **long 格式（每风格一行）而非 wide（8 列一行）**：风格名保留上游原文、
    上游增删分类时免迁移表结构；与 `MarketSingleValue`（温度计）同构。

    **append-only**：某 stat_date 的上游值落库后不修改（上游按月重算，历史点不变），
    故 job 侧按 `(fund_code, style_name, stat_date)` 去重后纯插入。

    **无清理策略**：与 composite/multi 的 1 年保留不同——风格漂移历史是「自建历史」
    的唯一来源（上游不提供回补），断档即永久缺口，故无限保留。

    ⚠️ QDII 口径存疑：韭圈儿对海外资产映射不合理（270042 纳指100 实测
    「固收风格 81.28」），落库原值但展示层须注明来源；风格筛选应排除 QDII
    （评估文档：fund_style_tag_feasibility.md §4）。
    """

    __tablename__ = 'fund_style_exposures'

    fund_code = Column(String(6), nullable=False, index=True, comment='基金代码（业务键）')
    stat_date = Column(Date, nullable=False, index=True, comment='上游时点（月末或当月最新日，原样保留）')
    style_name = Column(String(20), nullable=False, comment='风格名（上游原文，如 大盘成长/固收风格）')
    value = Column(SafeNumeric(6, 2), comment='该风格暴露值(%)，每时点 8 风格合计=100')
    source = Column(String(30), nullable=False, default='jiucaishuo_style', comment='数据来源: jiucaishuo_style')

    __table_args__ = (
        UniqueConstraint('fund_code', 'style_name', 'stat_date', name='uq_fund_style_code_name_date'),
        Index('ix_fund_style_code_date', 'fund_code', 'stat_date'),
    )


class FundRiskMetrics(Base, PrimaryKeyMixin, TimestampMixin):
    """基金风险收益指标日快照（#167 P0：最大回撤 / 本轮回撤 / 夏普族）。

    为什么落库（而不只像 ``fund_risk_metrics`` 那样纯函数现算）
    -----------------------------------------------------------
    产品要的是「按指标横向筛」与「回撤序列」——前者要跨基金排序，后者要按时间看。
    两者都无法靠「一次请求现算一只」满足：

    - 横向筛：页面打开时不可能对全市场逐只现算（逐只读 3 年日净值）；
    - 回撤序列：现算只能返回当次窗口内的极值，历史进程不可回溯。

    故本表是 ``daily_worth`` 的可复现**派生投影**（L2 派生计算），落**最新一交易日一行**，
    口径由 ``caliber_version`` 标记（与 ``pnl_daily_snapshots`` 同范式）。

    「本轮回撤」的定义（#167 用户明确要求「本轮回撤」）
    ----------------------------------------------------
    不是「最近 N 天跌了多少」，而是**当前所处回撤区间**：从**最近一次净值新高**到
    **最新一日**的跌幅（新高日之后没有更新的新高，即「还在坑里」）。
        - ``current_drawdown`` = (最新净值 − 最近高点) / 最近高点，负数；
        - 最新一日即新高时 = **0.0**（不是 NULL）——「此刻在最高点」是事实，不是缺数据；
        - ``drawdown_peak_date`` / ``drawdown_days`` 是它的口径元数据（哪天掉下来的、熬了多久）。
    与 ``max_drawdown``（窗口内**历史上最深**的那一次）是两个不同问题：前者问「现在疼不疼」，
    后者问「最疼过多少」。

    字段读者（AGENTS.md 数据策略硬约束 §1，新列必须当场指定读者）
    -------------------------------------------------------------
    - ``max_drawdown`` / ``current_drawdown`` → 详情页「业绩与风险」区块 + 按指标筛选列表；
    - ``sharpe`` / ``sortino`` / ``calmar`` / ``ulcer_index`` / ``upi`` / ``return_drawdown_ratio``
      → 风险指标表（同类内排序，跨类别不比绝对值）；
    - ``win_rate`` / ``win_rate_period`` → 同上；
    - ``ret_1m`` / ``ret_3m`` / ``ret_1y`` → 同类风险榜「近1月/近3月/近1年」三列（#2284）；
    - ``basis`` / ``sample_points`` / ``as_of`` / ``caliber_version`` → 口径元数据，
      随值下发（不告诉口径的数字不可复核）。

    ⚠️ 跨类别不可直接比绝对值（债基波动小 ⇒ 夏普系统性偏高），排序一律**同类内**，
    故 ``fund_type_id`` 随行落库，供读路径分组。
    """

    __tablename__ = 'fund_risk_metrics'

    fund_code = Column(String(6), nullable=False, comment='基金代码（业务键）')
    as_of = Column(Date, nullable=False, comment='指标截至日（= 该基金最后一根净值日期）')
    # 同类内排序的分组键。不设外键（与 fund_industry_allocs 同范式：本表是派生投影，
    # 上游 fund_types 重建时不应因引用而阻塞），值由 job 从 Fund 冗余写入。
    fund_type_id = Column(Integer, nullable=True, comment='基金类型 ID（读路径同类内排序的分组键）')

    max_drawdown = Column(SafeNumeric(10, 4), nullable=True, comment='窗口内最大回撤(%)，负数')
    max_drawdown_peak_date = Column(Date, nullable=True, comment='最大回撤的高点日')
    max_drawdown_trough_date = Column(Date, nullable=True, comment='最大回撤的低点日')
    current_drawdown = Column(SafeNumeric(10, 4), nullable=True, comment='本轮回撤(%)，负数；0=正在新高')
    drawdown_peak_date = Column(Date, nullable=True, comment='本轮回撤起点（最近一次新高日）')
    drawdown_days = Column(Integer, nullable=True, comment='本轮自高点起熬过的自然日数')

    annual_return = Column(SafeNumeric(10, 4), nullable=True, comment='年化收益(%)')
    annual_volatility = Column(SafeNumeric(10, 4), nullable=True, comment='年化波动率(%)')
    sharpe = Column(SafeNumeric(10, 4), nullable=True, comment='夏普（(年化−rf)/年化波动）')
    sortino = Column(SafeNumeric(10, 4), nullable=True, comment='索提诺（只罚下行波动）')
    calmar = Column(SafeNumeric(10, 4), nullable=True, comment='卡玛（年化/|最大回撤|）')
    ulcer_index = Column(SafeNumeric(10, 4), nullable=True, comment='溃疡指数 UI(%)')
    upi = Column(SafeNumeric(10, 4), nullable=True, comment='UPI（年化/UI，参考方简化式）')
    return_drawdown_ratio = Column(SafeNumeric(10, 4), nullable=True, comment='波回比')
    win_rate = Column(SafeNumeric(10, 4), nullable=True, comment='胜率(%)')
    win_rate_period = Column(String(8), nullable=True, comment='胜率周期 day/week/month')
    # 区间收益（#2284）：自然日端点（30/90/365），与拟涨幅共用取数规则，见
    # fund_risk_metrics.PERIOD_RETURN_SPANS；可空列，历史不足该窗口为 NULL（诚实降级）。
    ret_1m = Column(SafeNumeric(10, 4), nullable=True, comment='近1月区间收益率(%)，30 自然日端点')
    ret_3m = Column(SafeNumeric(10, 4), nullable=True, comment='近3月区间收益率(%)，90 自然日端点')
    ret_1y = Column(SafeNumeric(10, 4), nullable=True, comment='近1年区间收益率(%)，365 自然日端点')

    sample_points = Column(Integer, nullable=False, default=0, comment='参与计算的净值点数')
    basis = Column(String(16), nullable=False, comment='口径/可信度：acc_nav / distorted / insufficient')
    window_label = Column(String(16), nullable=False, comment='窗口中文标签（如「近3年」）')
    caliber_version = Column(
        Integer,
        nullable=False,
        default=2,
        server_default=text('2'),
        comment='口径版本；与 fund_risk_metrics_job.CALIBER_VERSION 不符即作废（改口径先 bump）',
    )

    __table_args__ = (
        UniqueConstraint('fund_code', 'as_of', name='uq_fund_risk_metrics_code_asof'),
        # 按指标横向筛：`WHERE basis='acc_nav' ORDER BY sharpe DESC` 走它
        Index('ix_fund_risk_metrics_basis_sharpe', 'basis', 'sharpe'),
        Index('ix_fund_risk_metrics_type', 'fund_type_id'),
        Index('ix_fund_risk_metrics_caliber', 'caliber_version'),
    )
