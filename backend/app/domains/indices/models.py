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


class IndexDaily(Base, PrimaryKeyMixin, TimestampMixin):
    """指数日线点位（market 域，#275 基准对比 / #861 绩效分析的数据底座）。

    与 index_catalog 的关系：名录是「有哪些指数」（搜索/引用），本表是
    「某指数的历史点位序列」。存储数据源原生代码（如 881001.WI），
    交易所指数（000300 等）行情可后续经 akshare 通道补充进同表。

    万得全A（881001.WI）点位经韭圈儿公开接口**反推派生**（价格口径，
    非 Full Return 全收益），锚点随最新收盘平移——仅用于展示与对比，
    勿做跨年回测级依赖；来源与口径细节见 jiucaishuo_adapter.py 模块注释。
    """

    __tablename__ = 'index_daily'

    index_code = Column(String(20), nullable=False, comment='指数代码（数据源原生形态，如 881001.WI）')
    trade_date = Column(Date, nullable=False, comment='交易日')
    close = Column(SafeNumeric(18, 6), comment='收盘点位（韭圈儿来源为反推派生值，价格口径）')
    ret_pct = Column(SafeNumeric(12, 4), comment='区间累计收益率(%)（数据源原始值，可空）')
    source = Column(String(20), default='jiucaishuo', comment='数据来源: jiucaishuo')

    __table_args__ = (UniqueConstraint('index_code', 'trade_date', name='uk_index_daily_code_date'),)
