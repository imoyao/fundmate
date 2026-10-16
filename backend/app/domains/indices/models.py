# -*- coding: utf-8 -*-
"""指数成分域模型（market 域）。

指数成分股是公开、读多写少、随指数调样微调的参照数据，归 market 域（Turso）。
为 #1286「品种差异化描述维度」中「指数 → 成分」维度提供数据底座；回填链路见
services/sync/jobs/index_constituent_job.py（复用 akshare 的 index_stock_cons_csindex /
index_stock_cons，不自行造轮子）。
"""

from sqlalchemy import Boolean, Column, Date, Integer, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


class IndexValuation(Base, PrimaryKeyMixin, TimestampMixin):
    """指数估值（market 域，#1285 消费侧「指数」品类估值列）。

    与 IndexDaily 的区别：日线是「点位」，本表是「估值指标」（市盈率 / 股息率）。
    数据源：中证指数**官方**估值文件（akshare `stock_zh_index_value_csindex`，读
    csindex OSS 的 indicator.xls，免 cookie、按指数代码），按 (index_code, trade_date)
    覆盖式 upsert；回填链路见 services/sync/jobs/index_valuation_job.py。

    口径提示（§3.10）：官方列名为「市盈率1 / 市盈率2 / 股息率1 / 股息率2」，本项目
    **原样落库**、不做主观口径命名，避免把官方口径写错；前端展示取 pe_1 / dividend_yield_1。
    历史分位（percentile）**不在本表计算**：官方文件仅下发近约 20 个交易日，长历史基线
    由乐咕乐股月频序列另表承载（见 IndexValuationBaseline，#1407 拍板「组合方案」），
    分位在读路径上现算（services/index_percentile.py）。
    """

    __tablename__ = 'index_valuations'

    index_code = Column(String(20), nullable=False, comment='指数代码（如 000300，不含交易所后缀）')
    index_name = Column(String(60), comment='指数中文简称')
    trade_date = Column(Date, nullable=False, comment='估值日期')
    pe_1 = Column(SafeNumeric(12, 4), comment='市盈率1（中证官方列名，口径以官方为准）')
    pe_2 = Column(SafeNumeric(12, 4), comment='市盈率2（中证官方列名，口径以官方为准）')
    dividend_yield_1 = Column(SafeNumeric(12, 4), comment='股息率1(%)（中证官方列名）')
    dividend_yield_2 = Column(SafeNumeric(12, 4), comment='股息率2(%)（中证官方列名）')
    source = Column(String(20), default='csindex', comment='数据来源')

    __table_args__ = (UniqueConstraint('index_code', 'trade_date', name='uk_index_valuation_code_date'),)


class IndexValuationBaseline(Base, PrimaryKeyMixin, TimestampMixin):
    """指数估值分位基线（market 域，#1407 拍板「组合方案」的乐咕乐股一路）。

    为什么**不复用** ``index_valuations``：那张表的 ``(index_code, trade_date)`` 唯一键
    会被乐咕月末采样日与中证官方日频行**相撞**（月末多数是交易日），且 ``pe_1`` 的
    列语义是中证官方口径（滚动 PE 只是其中一个候选），混入乐咕「滚动市盈率」会静默
    改掉既有列的口径。分位基线与官方估值是两份口径不同的数据，必须分表。

    - 数据源：乐咕乐股（akshare ``stock_index_pe_lg``，月频、约 21 年历史），
      只取**滚动市盈率**单列（#1407 拍板：口径列不堆砌）；
    - 仅导入**近 5 年**（分位窗口同长，更长的市场结构不可比）；
    - 读路径：``services/index_profile.py`` 按窗口取序列 → ``index_percentile`` 现算；
    - 回填链路：``services/sync/jobs/index_valuation_lg_job.py``（覆盖式 upsert）。

    股息率分位不在本表：乐咕无股息率序列，待自建日频 ``index_valuations`` 积累满
    1 年后由读路径另行计算（#1407 拍板第 3 条）。
    """

    __tablename__ = 'index_valuation_baselines'

    index_code = Column(String(20), nullable=False, comment='指数代码（裸 6 位码，与 index_valuations 同约定）')
    trade_date = Column(Date, nullable=False, comment='采样日期（乐咕月末采样，非交易日日频）')
    pe_ttm = Column(SafeNumeric(12, 4), comment='滚动市盈率（乐咕口径，分位基线唯一使用列）')
    index_name = Column(String(60), comment='指数中文简称（乐咕侧返回，冗余便于排查）')
    source = Column(String(20), default='lg', comment='数据来源：lg=乐咕乐股')

    __table_args__ = (UniqueConstraint('index_code', 'trade_date', name='uk_index_valuation_baseline_code_date'),)


class IndexConstituent(Base, PrimaryKeyMixin, TimestampMixin):
    """指数成分股：某指数在某一刻的成分股票清单（按指数整体覆盖式更新）。"""

    __tablename__ = 'index_constituents'

    index_code = Column(String(20), nullable=False, comment='指数代码(如 000300，不含交易所后缀)')
    index_name = Column(String(60), comment='指数名称')
    symbol = Column(String(10), nullable=False, comment='成分股代码(如 000001)')
    stock_name = Column(String(60), comment='成分股名称')
    in_date = Column(String(20), comment='纳入日期(来源接口提供时回填)')

    __table_args__ = (UniqueConstraint('index_code', 'symbol', name='uk_index_constituent'),)


class IndexCatalog(Base, PrimaryKeyMixin, TimestampMixin):
    """指数名录：可搜索的指数条目（#1286 品种差异化维度 + 聚合搜索）。

    与 IndexConstituent 的关系：名录是「有哪些指数」，成分是「某指数里有哪些股票」。
    回填链路见 services/sync/jobs/index_catalog_job.py（#1365 三源合并：
    sina index_stock_info / 中证 index_csindex_all / 国证 index_all_cni）。
    """

    __tablename__ = 'index_catalog'

    index_code = Column(String(20), unique=True, nullable=False, comment='指数代码(如 000300，不含交易所后缀)')
    name = Column(String(60), nullable=False, comment='指数名称')
    exchange = Column(String(10), comment='命名空间前缀: SH/SZ(交易所) / CSI(中证) / CNI(国证)，#1365')
    source = Column(String(20), default='sina', comment='数据来源: sina/csindex/cni')
    # ── 核心指数白名单（#1365）：人工策展，三源覆盖式重建时必须保留（见 job._save_data）──
    is_core = Column(Boolean, default=False, comment='核心指数白名单（自选「指数」分组置顶/优先展示）')
    core_rank = Column(Integer, comment='核心指数展示排序（越小越靠前；非核心为 NULL）')
    # ── 编制/发布机构（#1425 搜索区分度）──
    # 存**代码**而非中文名：展示名可能调整、代码稳定，且未来可按发布方筛选/分组；
    # 中文名由后端统一映射（INDEX_PUBLISHER_LABELS）后经搜索 extra 下发，前端直接展示不抄映射。
    # 回填由 index_catalog_job 按来源写入（csindex→CSI、cni→CNI、sina→NULL）：
    # sina 只是行情转发源，无法权威判定发布方（沪深300 若按 SH 前缀写成「上交所」即错误），
    # 留空 = 前端不展示该维度，可降级（data-strategy「参考展示类」口径，宁缺勿错）。
    publisher = Column(
        String(20),
        nullable=True,
        comment='编制/发布机构代码: CSI=中证指数公司 / CNI=国证指数 / WIND=万得…，未知留空',
    )


# 编制/发布机构代码 → 中文展示名（#1425）。单一真相源在后端，前端直接展示、不再抄一份映射。
INDEX_PUBLISHER_LABELS = {
    'CSI': '中证指数公司',
    'CNI': '国证指数',
    'WIND': '万得',
}

# 数据源 → 发布机构代码回填映射（#1425）。
# csindex（中证官网）/ cni（国证官网）可权威判定；sina 是行情转发源 → 不回填（NULL）。
PUBLISHER_BY_SOURCE = {
    'csindex': 'CSI',
    'cni': 'CNI',
}


class IndexDaily(Base, PrimaryKeyMixin, TimestampMixin):
    """指数日线点位（market 域，#275 基准对比 / #861 绩效分析的数据底座）。

    与 index_catalog 的关系：名录是「有哪些指数」（搜索/引用），本表是
    「某指数的历史点位序列」。代码用**数据源原生形态**：万得系带 `.WI`
    （如 881001.WI），交易所指数带交易所后缀（如 000300.SH、399006.SZ）。

    两路来源（2026-10-01 起）：
    - `jiucaishuo`：万得系全家桶。点位经公开接口**反推派生**（价格口径，非 Full
      Return 全收益），锚点随最新收盘平移——仅用于展示与对比，勿做跨年回测级依赖；
      口径细节见 jiucaishuo_adapter.py 模块注释。
    - `tencent`：交易所指数（沪深300 / 中证500 / 创业板指…），腾讯日线直连的**真实
      收盘价**，口径 `raw`。补这一路的动因见 sync/jobs/index_daily_job.py 模块注释。
    """

    __tablename__ = 'index_daily'

    index_code = Column(String(20), nullable=False, comment='指数代码（数据源原生形态，如 881001.WI / 000300.SH）')
    trade_date = Column(Date, nullable=False, comment='交易日')
    close = Column(SafeNumeric(18, 6), comment='收盘点位（口径见 price_mode：raw=源侧真实收盘；其余为派生/归一化）')
    ret_pct = Column(SafeNumeric(12, 4), comment='区间累计收益率(%)（数据源原始值，可空）')
    source = Column(String(20), default='jiucaishuo', comment='数据来源: jiucaishuo(万得系) / tencent(交易所指数)')
    price_mode = Column(
        String(10),
        default='anchored',
        comment='点位口径: raw(源侧真实收盘，交易所指数) / anchored(有真实收盘锚、反推派生，如 881001) / '
        'normalized(起点归一化 1000，如 885 系基金指数)，#275',
    )

    __table_args__ = (UniqueConstraint('index_code', 'trade_date', name='uk_index_daily_code_date'),)
