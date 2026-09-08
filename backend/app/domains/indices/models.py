# -*- coding: utf-8 -*-
"""指数成分域模型（market 域）。

指数成分股是公开、读多写少、随指数调样微调的参照数据，归 market 域（Turso）。
为 #1286「品种差异化描述维度」中「指数 → 成分」维度提供数据底座；回填链路见
services/sync/jobs/index_constituent_job.py（复用 akshare 的 index_stock_cons_csindex /
index_stock_cons，不自行造轮子）。
"""

from sqlalchemy import Column, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin


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
    回填链路见 services/sync/jobs/index_catalog_job.py（akshare index_stock_info_sina）。
    """

    __tablename__ = 'index_catalog'

    index_code = Column(String(20), unique=True, nullable=False, comment='指数代码(如 000300，不含交易所后缀)')
    name = Column(String(60), nullable=False, comment='指数名称')
    exchange = Column(String(10), comment='所属交易所: SH/SZ')
    source = Column(String(20), default='sina', comment='数据来源: sina')
