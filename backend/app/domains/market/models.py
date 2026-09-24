# -*- coding: utf-8 -*-
"""探市 · 大类资产观察的数据底座（#1460 P1）。

落库对象：探市「大类资产观察」的 20 个**固定**资产品种（见 market_service.ASSET_CONFIG），
不是「用户触达资产」——探市是免登录沙盒，访客没有 positions / watchlist，
若按持仓∪自选去重会漏掉几乎所有品种，落库也就失去了首屏加速的意义。

存什么：每日一行**日频快照**，含当日涨跌、相对位置分位、⚡ 异动判定结果。
分位与 σ 由同步任务在后台算好后入库，接口读库直接组装（毫秒级），
不再每次请求实时拉全量历史现算（原冷启动 42.2s 串行 / 12.4s 并发 6）。

不存什么：**长历史日线序列不落库**（#1460 第 2 步，需另行拍板）。
历史序列仅在同步任务内临时使用、算完即弃；按数据策略「按需存」，
确有需要时再按品种按需回填。
"""

from sqlalchemy import Boolean, Column, Date, Integer, String, UniqueConstraint

from app.core.database import Base, PrimaryKeyMixin, TimestampMixin
from app.core.db_utils import SafeNumeric


class MarketAssetDaily(Base, PrimaryKeyMixin, TimestampMixin):
    """大类资产日频快照（market 域，#1460 P1）。

    唯一键 (asset_key, trade_date)：每日每品种一行，覆盖式 upsert。
    20 行/天 ⇒ 约 7,300 行/年，量级可忽略。

    available=False 表示软占位（缺源 / 取数失败 / 超时降级），前端按 reason
    展示置灰 + —，与实时取数路径的口径保持一致（不把降级伪装成真实值）。
    """

    __tablename__ = 'market_asset_daily'

    asset_key = Column(String(30), nullable=False, comment='资产键（ASSET_CONFIG.key，如 sh000001）')
    trade_date = Column(Date, nullable=False, comment='交易日（快照归属日）')
    close = Column(SafeNumeric(18, 6), comment='收盘价/点位（可空，仅用于核对与排错）')
    change_pct = Column(SafeNumeric(12, 4), comment='当日涨跌幅(%)')
    position_percentile = Column(SafeNumeric(8, 2), comment='相对位置分位(0-100)')
    position_label = Column(String(10), comment='相对位置标签: 偏低/适中/偏高')
    position_basis = Column(String(30), comment='相对位置口径: 价格分位/收益率分位')
    position_window = Column(Integer, comment='分位窗口（交易日数）')
    anomaly = Column(Boolean, default=False, comment='是否命中⚡异动（双线规则）')
    anomaly_sigma = Column(SafeNumeric(12, 6), comment='异动判定用的 σ（近窗口日收益标准差）')
    anomaly_rule = Column(String(20), comment='命中规则: sigma(线1) / absolute(线2)')
    anomaly_basis_note = Column(String(300), comment='异动规则自述（前端 tooltip）')
    available = Column(Boolean, default=True, comment='是否可取数（False=软占位）')
    reason = Column(String(300), comment='软占位原因（缺源/取数失败/超时降级）')
    caliber = Column(String(120), comment='口径提示（商品含夜盘/汇率非DXY等）')
    data_asof = Column(String(30), comment='数据截止（源侧日期/时刻）')
    source = Column(String(20), default='akshare', comment='数据来源')

    __table_args__ = (UniqueConstraint('asset_key', 'trade_date', name='uk_market_asset_daily_key_date'),)


class MarketBondYieldDaily(Base, PrimaryKeyMixin, TimestampMixin):
    """债券 10Y 收益率日频快照（market 域，#1460 P1）。

    overview 的 bond_yield 轨（中债 / 美债 10Y 及其变动 bp）单独成表：
    它是「一个整体对象」而非 20 个品种之一，与资产快照的粒度不同，
    硬塞进 MarketAssetDaily 会让「20 资产」的语义失真。

    唯一键 trade_date：每日一行，覆盖式 upsert。
    """

    __tablename__ = 'market_bond_yield_daily'

    trade_date = Column(Date, nullable=False, unique=True, comment='交易日')
    cn_10y = Column(SafeNumeric(10, 4), comment='中债 10Y 收益率(%)')
    cn_10y_change_bp = Column(SafeNumeric(10, 2), comment='中债 10Y 变动(bp)')
    us_10y = Column(SafeNumeric(10, 4), comment='美债 10Y 收益率(%)')
    us_10y_change_bp = Column(SafeNumeric(10, 2), comment='美债 10Y 变动(bp)')
    source = Column(String(20), default='akshare', comment='数据来源')
