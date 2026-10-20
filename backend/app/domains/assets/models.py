# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 17:20
# File : models.py
# -*- coding: utf-8 -*-
"""通用资产模型 — 覆盖除交易性金融资产外的所有资产/负债."""

from loguru import logger
from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    event,
    func,
    inspect,
    select,
)

from app.core.database import Base


class Asset(Base):
    __tablename__ = 'assets'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, default=1, comment='用户 ID')
    family_id = Column(Integer, nullable=False, default=1, index=True, comment='归属家庭 ID（家庭共享层隔离键）')

    # 与账户的外键关联
    ledger_id = Column(
        Integer,
        ForeignKey('ledgers.id', ondelete='RESTRICT'),
        nullable=True,
        comment='关联账户ID',
    )
    account_name = Column(String(50), nullable=True, comment='所属账户名称（冗余快照）')

    major_category = Column(
        String(20),
        nullable=False,
        comment='大类：cash(流动资金)/fixed(固定资产)/investment(投资理财)/receivable(应收款)/liability(负债)/insurance(保险)/real_estate(房产)/precious_metal(贵金属)/custom(自定义)/bank_wealth(银行理财)/advisory(投顾)/trust(信托)/private_fund(私募)/wealth_insurance(理财型保险)',
    )
    minor_category = Column(
        String(50),
        nullable=True,
        comment='小类，自由输入，如 credit_card/mortgage/huabei/house/car/gold/personal_loan/social_insurance',
    )

    name = Column(String(200), comment='资产名称，如"招商银行房贷"')
    amount = Column(Integer, default=0, comment='当前价值/余额（单位：分）')
    currency = Column(String(3), default='CNY')

    allocation = Column(String(20), default='longterm', comment='配置目标（五笔钱）')
    status = Column(String(20), default='active', comment='active / closed')
    notes = Column(String(500), nullable=True)

    start_date = Column(Date, nullable=True, comment='购入/生效/起息日')
    end_date = Column(Date, nullable=True, comment='到期/还清日')

    extra = Column(JSON, nullable=True, comment='扩展属性')
    """
    # 扩展属性（JSON，存放各类资产的专属信息）
    # 例如：{"area": 120, "address": "xxx"} 用于房产
    #      {"license_plate": "京A12345"} 用于汽车
    #      {"borrower": "张三", "due_date": "2026-12-31"} 用于借款
    #      {"sum_insured": 500000, "premium": 5000, "period": "yearly"} 用于保险
    """

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 索引
    __table_args__ = (
        Index('idx_assets_ledger_id', 'ledger_id'),
        Index('idx_assets_account_name', 'account_name'),
    )


@event.listens_for(Asset, 'before_insert')
@event.listens_for(Asset, 'before_update')
def _fill_asset_account_name(mapper, connection, target: Asset) -> None:
    """落库前用 `ledger_id` 补齐 `account_name` 冗余快照（与 Position 同口径，#2372）。

    ## 为什么需要

    `account_name` 只是 `ledgers.name` 的冗余快照，账户的**唯一真相是 `ledger_id`**。
    `update_asset` 若只改 `ledger_id` 而不动快照，就会留下「外键已指向新账户、
    展示名仍是旧账户」的漂移行。此时账户改名会按 `ledger_id` 级联刷新快照，
    把用户刚迁走的资产显示名**刷回旧账户名**——一次「迁移」在界面上被静默还原，
    而库里外键早已搬走（#2372 症状 3 的同构形态）。

    ## 为什么挂在 mapper 事件而不是视图层

    视图层的判据是「只做 HTTP 编排」（`decisions.md` 2026-09-19，执行者
    `scripts/check_view_thickness.py`）。把快照同步写进 `update_asset` 会让
    `assets/views.py` 变厚并直接触发该守卫红灯——那不是绕开守卫的理由，
    而是这条逻辑本就不属于视图层的信号。挂在事件上则**一处覆盖全部写入路径**
    （创建 / 更新 / 脚本直写），与 Position 的 `_fill_position_account_name` 同因同解。

    ## 覆盖规则（与 Position 的 `_fill_position_account_name` 同口径）

    - **创建**：只补空值，**不覆盖**调用方显式传入的名字；
    - **更新且 `ledger_id` 确实变了**：**覆盖**为新账户名（否则就是漂移行）；
    - **更新但 `ledger_id` 未变**：不动，保护显式传入的名字。

    `ledger_id` 为空（未归档资产）时无从补齐，保持原值——它确实没有账户。

    ## 边界：只有部分表结构的库不参与回填（但要出声）

    与 Position 同一先例：先 `inspect(connection).has_table('ledgers')` 再决定动不动。
    刻意**不**用 `try/except OperationalError` 兜——那会把「表不存在」与「库被锁 /
    连接坏了」混成一类一起吞掉。
    """
    if not target.ledger_id:
        return
    # 延迟导入：ledgers 与 assets 同属 user 域，但模块加载期避免交叉导入。
    from app.domains.ledgers.models import Ledger

    if not inspect(connection).has_table('ledgers'):
        logger.warning(
            'assets.account_name 冗余快照无法回填：本引擎无 ledgers 表（ledger_id={}，仅部分表结构的库）',
            target.ledger_id,
        )
        return

    # 已有快照 ⇒ 仅在「持久化对象 + ledger_id 本条发生变更」时覆盖，其余情况保护显式传入的值
    state = inspect(target)
    if target.account_name and not (state.persistent and bool(state.attrs.ledger_id.history.has_changes())):
        return

    name = connection.execute(select(Ledger.name).where(Ledger.id == target.ledger_id)).scalar()
    if name:
        target.account_name = name
